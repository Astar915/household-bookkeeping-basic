"""Revision checked startup downloads, shared by desktop and web workspaces."""
from __future__ import annotations

import hashlib
from io import BytesIO
import json
from pathlib import Path
import sqlite3
import threading
from datetime import datetime, timezone
import zipfile

from .storage import LedgerError


def local_revision(database_path, **stores):
    digest = hashlib.sha256()
    path = Path(database_path).resolve()
    if path.exists():
        connection = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=5)
        try:
            connection.execute('BEGIN')
            tables = [r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
            for table in tables:
                if table.startswith('web_'):
                    continue
                name = '"' + table.replace('"', '""') + '"'
                rows = connection.execute('SELECT * FROM ' + name).fetchall()
                if table == 'settings':
                    rows = [r for r in rows if not str(r[0]).startswith('web_')]
                digest.update(json.dumps([table, sorted(rows, key=repr)], ensure_ascii=True, default=str).encode())
        finally:
            connection.close()
    for key in ('payment_store', 'bookkeeping_skill_store', 'food_skill_store'):
        store = stores.get(key)
        value = store.load() if store else None
        if key.endswith('skill_store') and value:
            value = value['content']
        digest.update(json.dumps([key, value], sort_keys=True, ensure_ascii=True).encode())
    image_dir = stores.get('receipt_image_directory')
    if image_dir and Path(image_dir).exists():
        for file in sorted(Path(image_dir).rglob('*')):
            if file.is_file() and not file.is_symlink():
                digest.update(str(file.relative_to(image_dir)).encode())
                with file.open('rb') as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b''):
                        digest.update(block)
    return digest.hexdigest()


class PullState:
    def __init__(self, path):
        self.path = Path(path)

    def load(self):
        if not self.path.exists():
            return {}
        value = json.loads(self.path.read_text(encoding='utf-8'))
        if not isinstance(value, dict):
            raise LedgerError('云端下载检查点损坏，请先检查本机备份。')
        return value

    def save(self, value):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(value, ensure_ascii=True), encoding='utf-8')
        temp.replace(self.path)

    def synced(self, provider, repository, sha, revision, created_at=None, etag=None):
        state = self.load()
        key = provider + ':' + repository
        previous = state.setdefault('clouds', {}).get(key, {})
        cloud = {'sha': sha, 'created_at': created_at or ''}
        # An ETag is only valid for the exact file representation it came from.
        current_etag = etag or (previous.get('etag') if previous.get('sha') == sha else None)
        if current_etag:
            cloud['etag'] = current_etag
        state['clouds'][key] = cloud
        state['revision'] = revision
        self.save(state)

    def pause_downloads(self, *, choice_pending=False):
        state = self.load()
        state['automatic_download_paused'] = True
        state['download_choice_pending'] = choice_pending
        state['download_choice_generation'] = state.get('download_choice_generation', 0) + 1
        self.save(state)

    def resume_downloads(self):
        state = self.load()
        state['automatic_download_paused'] = False
        state['download_choice_pending'] = False
        state['download_choice_generation'] = state.get('download_choice_generation', 0) + 1
        self.save(state)


def _paused_download_result(checkpoint):
    if checkpoint.get('automatic_download_paused'):
        return {'status': 'choice_required' if checkpoint.get('download_choice_pending') else 'local_kept',
                'restored': False}
    return None


def automatic_pull(
    database_path,
    candidates,
    state,
    restore,
    *,
    stores=None,
    lock=None,
    cancelled=None,
    progress=None,
):
    """Download off-lock, then check local edits and restore with the caller's backup routine.

    candidates contain (provider, repository, client, save_remote_checkpoint).
    The first opt-in download preserves a full recovery backup via restore().
    Later downloads protect edits made since the last successful synchronization.
    """
    stores = stores or {}
    lock = lock or threading.RLock()

    def report_progress(message):
        if progress is None:
            return
        try:
            progress(message)
        except Exception:
            # Progress reporting is best-effort and must never fail a restore.
            pass

    report_progress('正在检查云端账本版本…')
    with lock:
        checkpoint = state.load()
        paused = _paused_download_result(checkpoint)
        if paused:
            return paused
    versions, failures = [], []
    original = None
    for provider, repository, client, save_remote in candidates:
        try:
            report_progress(
                '正在检查 GitHub 云端版本…' if provider == 'github' else '正在检查 Gitee 云端版本…'
            )
            known = checkpoint.get('clouds', {}).get(provider + ':' + repository, {})
            snapshot_reader = getattr(type(client), 'bundle_snapshot_with_etag', None)
            etag = known.get('etag')
            unchanged = False
            download_kwargs = None
            if snapshot_reader is not None:
                sha, etag, unchanged, initial_data = snapshot_reader(client, repository, etag)
                if unchanged:
                    sha = known.get('sha')
                    if not sha:
                        sha, etag, unchanged, initial_data = snapshot_reader(client, repository, None)
                    if sha:
                        download_kwargs = {
                            'initial_sha': sha,
                            'initial_etag': etag,
                            'initial_data': None,
                        }
                elif sha:
                    download_kwargs = {
                        'initial_sha': sha,
                        'initial_etag': etag,
                        'initial_data': initial_data,
                    }
            else:
                sha = client.bundle_sha(repository)
            if not sha:
                continue
            body = None
            created = known.get('created_at', '') if known.get('sha') == sha else ''
            if not created:
                if known.get('sha') != sha and original is None:
                    # Only hash the local ledger if we have confirmed a new cloud
                    # version and may need to restore it.
                    with lock:
                        original = local_revision(database_path, **stores)
                    if checkpoint.get('revision') and original != checkpoint['revision']:
                        raise LedgerError('本机有尚未同步的修改，已暂停自动下载；请先核对并上传或手动恢复。')
                report_progress('发现云端更新，正在下载并校验…')
                if download_kwargs is not None:
                    body, sha = client.download_bundle_with_revision(repository, **download_kwargs)
                else:
                    body, sha = client.download_bundle_with_revision(repository)
                with zipfile.ZipFile(BytesIO(body)) as archive:
                    item = archive.getinfo('manifest.json')
                    if item.file_size > 1024 * 1024:
                        raise LedgerError('云端备份清单过大。')
                    created = json.loads(archive.read(item)).get('created_at', '')
                parsed = datetime.fromisoformat(created.replace('Z', '+00:00'))
                if parsed.tzinfo is None:
                    raise LedgerError('云端备份时间缺少时区。')
                if known.get('sha') == sha:
                    body = None
            cloud = {'sha': sha, 'created_at': created}
            if etag:
                cloud['etag'] = etag
            checkpoint.setdefault('clouds', {})[provider + ':' + repository] = cloud
            timestamp = datetime.fromisoformat(created.replace('Z', '+00:00')).timestamp()
            versions.append((timestamp, provider, repository, sha, body, save_remote, created, etag))
        except LedgerError:
            raise
        except Exception:
            failures.append(provider)
    if not versions:
        if failures:
            raise LedgerError('无法检查云端账本，请检查网络与云端授权。')
        return {'status': 'unconnected', 'restored': False}
    if failures:
        # An unavailable provider may have a newer snapshot than the reachable
        # one. Do not automatically roll back to an unverified older backup.
        raise LedgerError('无法检查云端账本，请检查网络与云端授权。')
    _, provider, repository, sha, body, save_remote, created, etag = max(versions, key=lambda x: x[0])
    if body is None:
        with lock:
            # Keep the upload/restore baseline, even when local edits exist.
            current_state = state.load()
            current_state['clouds'] = checkpoint['clouds']
            state.save(current_state)
        return {'status': 'current', 'restored': False, 'warnings': failures}
    with lock:
        current_checkpoint = state.load()
        paused = _paused_download_result(current_checkpoint)
        if paused:
            return paused
        if current_checkpoint.get('download_choice_generation', 0) != checkpoint.get('download_choice_generation', 0):
            return {'status': 'choice_changed', 'restored': False}
        if cancelled and cancelled():
            raise LedgerError('自动下载已取消，本机账本保持原样。')
        current = local_revision(database_path, **stores)
        if (original is not None and current != original) or (checkpoint.get('revision') and current != checkpoint['revision']):
            raise LedgerError('本机有尚未同步的修改，已暂停自动下载；请先核对并上传或手动恢复。')
        report_progress('下载完成，正在备份本机账本并应用云端数据…')
        backup = restore(body, provider)
        save_remote(sha)
        state.synced(provider, repository, sha, local_revision(database_path, **stores), created, etag)
    return {'status': 'restored', 'restored': True, 'provider': provider,
            'backup': str(backup), 'warnings': failures}
