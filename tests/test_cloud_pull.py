from __future__ import annotations

from io import BytesIO
import json
import hashlib
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

from bookkeeping.cloud_pull import PullState, automatic_pull, local_revision
from bookkeeping.github_sync import GitHubClient, create_sync_bundle, restore_sync_bundle
from bookkeeping.payment_preferences import PaymentPromptStore
from bookkeeping.skill_settings import BookkeepingSkillStore, FoodHealthSkillStore
from bookkeeping.storage import Database, LedgerError
from bookkeeping.sync_snapshot import (
    SNAPSHOT_ROOT,
    plan_from_legacy_bundle,
    snapshot_manifest_bytes,
)


class CloudPullTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, HOUSEHOLD_BOOKKEEPING_APP_DATA=str(self.root / 'app'))
        self.env.start()
        self.path = self.root / 'local.sqlite3'
        self.make_db(self.path, 'Local')
        self.state = PullState(self.root / 'pull.json')
        self.stores = dict(payment_store=PaymentPromptStore(self.root / 'payment.json'),
            bookkeeping_skill_store=BookkeepingSkillStore(self.root / 'skill.json', default_path=self.root / 'absent.md'),
            food_skill_store=BookkeepingSkillStore(self.root / 'food.json', default_path=self.root / 'absent-food.md'),
            receipt_image_directory=self.root / 'images')
        self.saved = []
        self.restores = []

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def make_db(self, path, account):
        db = Database(path)
        db.initialize()
        db.add_account(name=account, account_type='bank', currency='JPY', opening_balance='100', opening_date='2026-01-01')
        db.close()

    def bundle(self, name='Remote', created='2026-10-23T01:00:00+00:00'):
        source = self.root / (name + '.sqlite3')
        if not source.exists():
            self.make_db(source, name)
        raw = create_sync_bundle(source, self.root / (name + '.zip'), **self.stores)
        output = BytesIO()
        with zipfile.ZipFile(BytesIO(raw)) as original, zipfile.ZipFile(output, 'w') as target:
            for file in original.namelist():
                body = original.read(file)
                if file == 'manifest.json':
                    manifest = json.loads(body); manifest['created_at'] = created
                    body = json.dumps(manifest).encode()
                target.writestr(file, body)
        return output.getvalue()

    def candidate(self, body, sha='v1', provider='github'):
        client = Mock()
        client.bundle_sha.return_value = sha
        client.download_bundle_with_revision.return_value = (body, sha)
        return (provider, 'owner/repo', client, self.saved.append)

    def restore(self, body, provider):
        backup = restore_sync_bundle(body, self.path, **self.stores,
            backup_directory=self.root / 'backups', skill_restore_directory=self.root / 'restored', backup_provider=provider)
        self.restores.append(backup)
        return backup

    def pull(self, candidates, **kwargs):
        return automatic_pull(self.path, candidates, self.state, self.restore, stores=self.stores, **kwargs)

    def names(self):
        db = Database(self.path)
        try:
            return [r[0] for r in db.connection.execute('SELECT name FROM accounts')]
        finally:
            db.close()

    def edit(self):
        db = Database(self.path)
        db.add_account(name='Unsent', account_type='wallet', currency='JPY', opening_balance='1', opening_date='2026-01-01')
        db.close()

    def test_new_snapshot_restores_and_keeps_a_complete_recovery_backup(self):
        result = self.pull([self.candidate(self.bundle())])
        self.assertTrue(result['restored'])
        self.assertEqual(self.names(), ['Remote'])
        self.assertEqual(self.saved, ['v1'])
        self.assertTrue(self.restores[0].is_file())
        with zipfile.ZipFile(self.restores[0]) as archive:
            archived = self.root / 'before.sqlite3'
            archived.write_bytes(archive.read('ledger.sqlite3'))
        db = Database(archived)
        self.assertEqual(db.connection.execute('SELECT name FROM accounts').fetchone()[0], 'Local')
        db.close()

    def test_folder_snapshot_download_materializes_a_local_restore_bundle(self):
        plan = plan_from_legacy_bundle(self.bundle())
        manifest_body = snapshot_manifest_bytes(plan.manifest)
        revision = hashlib.sha1(
            f'blob {len(manifest_body)}\0'.encode('ascii') + manifest_body
        ).hexdigest()
        archive_body = BytesIO()
        prefix = f'owner-repo-main/{SNAPSHOT_ROOT}/'
        with zipfile.ZipFile(archive_body, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(prefix + 'manifest.json', manifest_body)
            for relative, body in plan.files.items():
                archive.writestr(prefix + relative, body)

        client = GitHubClient('ghu_test-token')
        client.read_snapshot_manifest = Mock(return_value=(plan.manifest, revision, None, False))
        client.cloud_revision = Mock(return_value=revision)
        client.request_raw = Mock(return_value=archive_body.getvalue())

        bundle, downloaded_revision = client.download_bundle_with_revision('owner/repo')

        self.assertEqual(downloaded_revision, revision)
        self.assertEqual(client.request_raw.call_count, 1)
        with zipfile.ZipFile(BytesIO(bundle)) as restored:
            self.assertIn('ledger.sqlite3', restored.namelist())
            manifest = json.loads(restored.read('manifest.json'))
            self.assertEqual(manifest['version'], 3)

    def test_local_zip_upload_is_converted_to_the_shared_folder_snapshot(self):
        client = GitHubClient('ghu_test-token')
        client.read_snapshot_manifest = Mock(return_value=(None, None, None, False))
        client._legacy_bundle_sha = Mock(return_value=None)
        client.upload_snapshot = Mock(return_value='folder-revision')

        result = client.upload_bundle('owner/repo', self.bundle(), expected_sha=None)

        self.assertEqual(result, 'folder-revision')
        client.upload_snapshot.assert_called_once()
        uploaded_plan = client.upload_snapshot.call_args.args[1]
        self.assertIn('meta/schema.json', uploaded_plan.files)
        self.assertEqual(client.upload_snapshot.call_args.kwargs['expected_sha'], None)

    def test_folder_snapshot_delta_uses_local_files_and_checks_manifest_revision(self):
        plan = plan_from_legacy_bundle(self.bundle())
        manifest_body = snapshot_manifest_bytes(plan.manifest)
        revision = hashlib.sha1(
            f'blob {len(manifest_body)}\0'.encode('ascii') + manifest_body
        ).hexdigest()
        client = GitHubClient('ghu_test-token')
        client.cloud_revision = Mock(return_value=revision)

        def fetch_file(path, **_kwargs):
            relative = path.split(f'/{SNAPSHOT_ROOT}/', 1)[1]
            return plan.files[relative]

        client.request_raw = Mock(side_effect=fetch_file)
        bundle, downloaded_revision = client.download_snapshot_delta_with_revision(
            'owner/repo', {}, expected_sha=revision, manifest=plan.manifest,
        )

        self.assertEqual(downloaded_revision, revision)
        self.assertEqual(client.request_raw.call_count, len(plan.files))
        with zipfile.ZipFile(BytesIO(bundle)) as restored:
            self.assertIn('ledger.sqlite3', restored.namelist())

    def test_restore_falls_back_to_sqlite_backup_when_windows_blocks_replace(self):
        body = self.bundle()
        reader = sqlite3.connect(self.path)
        reader.execute('SELECT name FROM accounts').fetchone()
        real_replace = os.replace

        def block_open_ledger(source, destination):
            if Path(destination).resolve() == self.path.resolve():
                error = PermissionError('ledger file is still open')
                error.winerror = 32
                raise error
            return real_replace(source, destination)

        try:
            with patch('bookkeeping.github_sync.os.replace', side_effect=block_open_ledger):
                backup = restore_sync_bundle(
                    body,
                    self.path,
                    **self.stores,
                    backup_directory=self.root / 'backups',
                    skill_restore_directory=self.root / 'restored',
                )
            self.assertTrue(backup.is_file())
            self.assertEqual(self.names(), ['Remote'])
        finally:
            reader.close()

    def test_pull_reports_check_download_and_restore_progress(self):
        progress = []
        result = self.pull(
            [self.candidate(self.bundle())],
            progress=progress.append,
        )

        self.assertTrue(result['restored'])
        self.assertIn('正在检查云端账本版本…', progress)
        self.assertIn('正在检查 GitHub 云端版本…', progress)
        self.assertIn('发现云端更新，正在下载并校验…', progress)
        self.assertIn('下载完成，正在备份本机账本并应用云端数据…', progress)

    def test_same_sha_does_not_download_or_overwrite_unsent_local_changes(self):
        candidate = self.candidate(self.bundle())
        self.pull([candidate]); self.edit()
        with self.assertRaisesRegex(LedgerError, '不能确认云端已同步'):
            self.pull([candidate])
        self.assertIn('Unsent', self.names())
        self.assertEqual(candidate[2].download_bundle_with_revision.call_count, 1)

    def test_updated_cloud_refuses_to_overwrite_unsent_local_changes(self):
        self.pull([self.candidate(self.bundle())]); self.edit()
        with self.assertRaisesRegex(LedgerError, '尚未同步'):
            self.pull([self.candidate(self.bundle('New'), 'v2')])
        self.assertIn('Unsent', self.names())

    def test_edit_during_download_stops_the_restore(self):
        candidate = self.candidate(self.bundle())
        candidate[2].download_bundle_with_revision.side_effect = lambda repo: (self.edit() or self.bundle(), 'v1')
        with self.assertRaisesRegex(LedgerError, '尚未同步'):
            self.pull([candidate])
        self.assertEqual(self.restores, [])

    def test_selects_newest_manifest_across_github_and_gitee(self):
        older = self.candidate(self.bundle('Older', '2026-10-22T00:00:00+00:00'))
        newer = self.candidate(self.bundle('Newer', '2026-10-23T00:00:00+00:00'), 'v2', 'gitee')
        result = self.pull([older, newer])
        self.assertEqual(result['provider'], 'gitee')
        self.assertEqual(self.names(), ['Newer'])

    def test_cancel_before_apply_preserves_local_data(self):
        with self.assertRaisesRegex(LedgerError, '取消'):
            self.pull([self.candidate(self.bundle())], cancelled=lambda: True)
        self.assertEqual(self.names(), ['Local'])

    def test_network_failure_and_invalid_bundle_never_change_local_data(self):
        candidate = self.candidate(b'not-a-zip')
        with self.assertRaises(LedgerError):
            self.pull([candidate])
        candidate[2].bundle_sha.side_effect = TimeoutError()
        with self.assertRaises(LedgerError):
            self.pull([candidate])
        self.assertEqual(self.names(), ['Local'])

    def test_upload_checkpoint_without_timestamp_skips_restore_of_same_cloud_version(self):
        candidate = self.candidate(self.bundle())
        self.state.synced('github', 'owner/repo', 'v1', local_revision(self.path, **self.stores))
        self.edit()
        with self.assertRaisesRegex(LedgerError, '不能确认云端已同步'):
            self.pull([candidate])
        self.assertIn('Unsent', self.names())

    def test_unchanged_etag_skips_bundle_download_but_verifies_local_revision(self):
        etag = '"etag-1"'
        created = '2026-10-23T01:00:00+00:00'
        self.state.synced('github', 'owner/repo', 'v1',
                          local_revision(self.path, **self.stores), created, etag)

        class ConditionalClient:
            def bundle_snapshot_with_etag(self, repository, cached_etag=None):
                self.cached_etag = cached_etag
                return None, etag, True, None

            def download_bundle_with_revision(self, repository):
                raise AssertionError('unchanged bundle must not be downloaded')

        client = ConditionalClient()
        result = self.pull([('github', 'owner/repo', client, self.saved.append)])

        self.assertEqual(result['status'], 'current')
        self.assertEqual(result['provider'], 'github')
        self.assertEqual(result['created_at'], created)
        self.assertEqual(client.cached_etag, etag)

    def test_same_cloud_version_without_local_baseline_is_not_marked_synced(self):
        candidate = self.candidate(self.bundle())
        self.state.synced('github', 'owner/repo', 'v1', '')
        result = self.pull([candidate])
        self.assertEqual(result['status'], 'unverified')
        self.assertEqual(result['provider'], 'github')
        self.assertFalse(result['restored'])

    def test_github_metadata_body_is_reused_instead_of_downloading_bundle_twice(self):
        body = self.bundle()

        class SnapshotClient:
            def bundle_snapshot_with_etag(self, repository, cached_etag=None):
                return 'v1', 'etag-1', False, body

            def download_bundle_with_revision(self, repository, **kwargs):
                self.download_kwargs = kwargs
                return kwargs['initial_data'], kwargs['initial_sha']

        client = SnapshotClient()
        result = self.pull([('github', 'owner/repo', client, self.saved.append)])

        self.assertTrue(result['restored'])
        self.assertEqual(client.download_kwargs['initial_data'], body)
        self.assertEqual(client.download_kwargs['initial_sha'], 'v1')

    def test_checkpoint_keeps_etag_for_same_blob_and_drops_it_for_new_blob(self):
        self.state.synced('github', 'owner/repo', 'v1', 'rev-1', '2026-10-23T01:00:00+00:00', 'etag-1')
        self.state.synced('github', 'owner/repo', 'v1', 'rev-2')
        self.assertEqual(self.state.load()['clouds']['github:owner/repo']['etag'], 'etag-1')
        self.state.synced('github', 'owner/repo', 'v2', 'rev-3')
        self.assertNotIn('etag', self.state.load()['clouds']['github:owner/repo'])

    def test_mobile_pull_is_account_isolated_and_does_not_expose_tokens(self):
        from bookkeeping.web import BookkeepingWebServer
        import uuid
        server = BookkeepingWebServer(('127.0.0.1', 0), self.root / 'web')
        try:
            ws = server.workspace
            uid, other = str(uuid.uuid4()), str(uuid.uuid4())
            self.make_db(ws.db_path(uid), 'Phone')
            self.make_db(ws.db_path(other), 'Other')
            cfg = ws.config(uid)
            cfg['cloud']['github'] = {'repository':'owner/repo','token':'synthetic-secret'}
            ws.save_config(uid, cfg)
            client = self.candidate(self.bundle())[2]
            client.token = 'synthetic-secret'; client.refresh_token = ''
            with patch('bookkeeping.web_features.GitHubClient', return_value=client):
                result = ws._startup_pull(uid)
            self.assertTrue(result['restored'])
            db = Database(ws.db_path(other))
            self.assertEqual(db.connection.execute('SELECT name FROM accounts').fetchone()[0], 'Other')
            db.close()
            self.assertNotIn('synthetic-secret', json.dumps(ws.public_settings(uid)))
            with self.assertRaisesRegex(LedgerError, '离线'):
                ws._remote(uid, 'startup_pull', {'pendingOutbox':True}, {})
        finally:
            server.server_close()


if __name__ == '__main__':
    unittest.main()
