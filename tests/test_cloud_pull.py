from __future__ import annotations

from io import BytesIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

from bookkeeping.cloud_pull import PullState, automatic_pull, local_revision
from bookkeeping.github_sync import create_sync_bundle, restore_sync_bundle
from bookkeeping.payment_preferences import PaymentPromptStore
from bookkeeping.skill_settings import BookkeepingSkillStore, FoodHealthSkillStore
from bookkeeping.storage import Database, LedgerError


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

    def test_same_sha_does_not_download_or_overwrite_unsent_local_changes(self):
        candidate = self.candidate(self.bundle())
        self.pull([candidate]); self.edit()
        result = self.pull([candidate])
        self.assertFalse(result['restored'])
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
        result = self.pull([candidate])
        self.assertFalse(result['restored'])
        self.assertIn('Unsent', self.names())

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
