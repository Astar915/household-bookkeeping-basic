"""Exercise the deployed adapter with synthetic HTTP responses and ledgers."""
from __future__ import annotations

import base64
import asyncio
from contextlib import closing
import hashlib
import importlib.util
from io import BytesIO
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from urllib.error import HTTPError
from urllib.request import Request
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bookkeeping.cloud_pull import PullState, automatic_pull, local_revision
from bookkeeping.github_sync import GitHubAuthError, GitHubClient
from bookkeeping.storage import LedgerError
from model_jobs import (
    ModelRequestRequired, ReplayOpener, request_envelope, save_model_response,
    load_model_replies, encode_response_record, decode_response_record,
)


def fixture_crypto():
    # WebCrypto is unavailable in CPython. Mock that boundary only, retaining
    # the production D1 queries, chunking, record format and AAD checks.
    module = ModuleType("secret_crypto")
    async def encrypt(value, key, purpose):
        return base64.b64encode(json.dumps([key, purpose, value]).encode()).decode()
    async def decrypt(value, key, purpose):
        stored_key, stored_purpose, text = json.loads(base64.b64decode(value))
        if (stored_key, stored_purpose) != (key, purpose):
            raise ValueError("Fixture encryption context mismatch")
        return text
    module.encrypt_text, module.decrypt_text = encrypt, decrypt
    return module


class FixtureD1:
    def __init__(self):
        self.batching = False
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("CREATE TABLE app_jobs(user_id TEXT, operation_id TEXT, PRIMARY KEY(user_id,operation_id))")
        self.connection.execute("INSERT INTO app_jobs VALUES('fixture-user','fixture-operation')")
        schema = Path(__file__).resolve().parents[1] / "schema/0002_encrypted_model_jobs.sql"
        self.connection.executescript(schema.read_text(encoding="utf-8"))

    def prepare(self, sql):
        connection = self.connection
        database = self
        class Statement:
            def bind(self, *values):
                self.values = values
                return self
            async def run(self):
                cursor = connection.execute(sql, self.values)
                rows = [dict(row) for row in cursor.fetchall()] if cursor.description else []
                if not database.batching:
                    connection.commit()
                return {"results": rows, "meta": {"changes": max(cursor.rowcount, 0)}}
            async def first(self):
                row = connection.execute(sql, self.values).fetchone()
                return dict(row) if row is not None else None
        return Statement()

    async def batch(self, statements):
        self.batching = True
        try:
            with self.connection:
                return [await statement.run() for statement in statements]
        finally:
            self.batching = False

    def close(self):
        self.connection.close()


class PlatformFixtureD1(FixtureD1):
    def __init__(self):
        self.batching = False
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        for schema in sorted((Path(__file__).resolve().parents[1] / "schema").glob("*.sql")):
            self.connection.executescript(schema.read_text(encoding="utf-8"))
        self.connection.execute("INSERT INTO cloud_users VALUES('fixture-user','fixture-login','fixture-github-id','2026-10-28')")
        self.connection.execute("INSERT INTO user_state_roots VALUES('fixture-user','0','{}','2026-10-28')")
        self.connection.commit()


class CloudWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.ledger = self.root / "ledger.sqlite3"
        with closing(sqlite3.connect(self.ledger)) as db:
            db.execute("CREATE TABLE entries(id INTEGER PRIMARY KEY, label TEXT)")
            db.execute("INSERT INTO entries VALUES(1,'original synthetic ledger')")
            db.commit()
        self.state = PullState(self.root / "pull.json")
        self.restored = []
        self.saved = []
        self.requests = []
        output = BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("manifest.json", json.dumps({"created_at": "2026-10-28T01:00:00+00:00"}))
            archive.writestr("fixture.txt", "synthetic backup; no user data")
        self.bundle = output.getvalue()
        self.sha = hashlib.sha1(f"blob {len(self.bundle)}\0".encode() + self.bundle).hexdigest()
        self.etag = '"synthetic-version"'
        self.network = patch("urllib.request.urlopen", side_effect=AssertionError("Real network disabled"))
        self.network.start()
        self.addCleanup(self.network.stop)

    def metadata(self, *, inline):
        value = {"sha": self.sha, "size": len(self.bundle)}
        if inline:
            value.update(encoding="base64", content=base64.b64encode(self.bundle).decode())
        return json.dumps(value).encode()

    def run_pull(self, provider):
        database = FixtureD1()
        self.addCleanup(database.close)
        crypto_patch = patch.dict(sys.modules, {"secret_crypto": fixture_crypto()})
        crypto_patch.start()
        self.addCleanup(crypto_patch.stop)
        env = SimpleNamespace(TOKEN_ENCRYPTION_KEY="fixture-key")
        replies = []
        for _ in range(12):
            opener = ReplayOpener(replies, "synthetic-ledger-revision")
            client = GitHubClient("ghu_synthetic", refresh_token="synthetic-refresh", opener=opener)
            try:
                return automatic_pull(
                    self.ledger, [("github", "fixture/private-repo", client, self.saved.append)],
                    self.state, lambda body, source: self.restored.append((body, source)) or "fixture-backup.zip",
                )
            except ModelRequestRequired as request:
                self.requests.append(request.envelope)
                status, body, headers = provider(request.envelope)
                asyncio.run(save_model_response(
                    database, env, "fixture-user", "fixture-operation", request.envelope,
                    status, body, response_headers=headers,
                ))
                replies, revision = asyncio.run(load_model_replies(
                    database, env, "fixture-user", "fixture-operation",
                ))
                self.assertEqual(revision, "synthetic-ledger-revision")
        self.fail("Workflow did not complete within the expected request count")

    def provider(self, *, inline):
        def fetch(envelope):
            url = envelope["url"]
            if "/git/blobs/" in url:
                return 200, self.bundle, {}
            if "/contents/household-bookkeeping/snapshot-v1/manifest.json" in url:
                return 404, b'{"message":"Not Found"}', {}
            if "/contents/household-bookkeeping/sync-bundle.zip" in url:
                if any(k.lower() == "if-none-match" for k in envelope["headers"]):
                    return 304, b"", {"etag": self.etag}
                return 200, self.metadata(inline=inline), {"etag": self.etag}
            raise AssertionError(f"Unexpected synthetic GitHub request: {url}")
        return fetch

    def test_workflow_wait_signal_escapes_cloud_failure_handler(self):
        client = GitHubClient("ghu_synthetic", opener=ReplayOpener([], "revision"))
        with self.assertRaises(ModelRequestRequired):
            automatic_pull(self.ledger, [("github", "fixture/repo", client, self.saved.append)],
                           self.state, lambda *_: self.fail("must not restore before response"))

    def test_first_download_reuses_metadata_body_and_checkpoints_etag(self):
        result = self.run_pull(self.provider(inline=True))
        self.assertTrue(result["restored"])
        self.assertEqual(self.restored, [(self.bundle, "github")])
        self.assertEqual(len(self.requests), 3)
        self.assertFalse(any("/git/blobs/" in request["url"] for request in self.requests))
        self.assertEqual(self.state.load()["clouds"]["github:fixture/private-repo"]["etag"], self.etag)

    def test_large_file_download_uses_blob_and_validates_version(self):
        result = self.run_pull(self.provider(inline=False))
        self.assertTrue(result["restored"])
        self.assertEqual(self.restored[0][0], self.bundle)
        self.assertEqual(len(self.requests), 4)
        self.assertEqual(sum("/git/blobs/" in request["url"] for request in self.requests), 1)

    def test_unchanged_version_never_downloads_or_scans_ledger(self):
        self.state.synced("github", "fixture/private-repo", self.sha, "baseline",
                          "2026-10-28T01:00:00+00:00", self.etag)
        with patch("bookkeeping.cloud_pull.local_revision", side_effect=AssertionError("No full scan")):
            result = self.run_pull(self.provider(inline=False))
        self.assertEqual(result["status"], "current")
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.restored, [])

    def test_expired_token_refreshes_and_continues_download(self):
        def fetch(envelope):
            if envelope["url"].endswith("/login/oauth/access_token"):
                return 200, b'{"access_token":"ghu_refreshed","refresh_token":"rotated"}', {}
            auth = next((v for k, v in envelope["headers"].items() if k.lower() == "authorization"), "")
            if auth == "Bearer ghu_synthetic":
                return 401, b'{"message":"Bad credentials"}', {}
            return self.provider(inline=True)(envelope)
        self.assertTrue(self.run_pull(fetch)["restored"])
        self.assertEqual(len(self.requests), 5)
        self.assertEqual(len(self.restored), 1)

    def test_wrong_refresh_client_requires_reauthorization_without_restoring(self):
        def fetch(envelope):
            if envelope["url"].endswith("/login/oauth/access_token"):
                return 200, b'{"error":"incorrect_client_credentials","error_description":"The client_id and/or client_secret passed are incorrect."}', {}
            return 401, b'{"message":"Bad credentials"}', {}
        with self.assertRaisesRegex(GitHubAuthError, "重新连接 GitHub"):
            self.run_pull(fetch)
        self.assertEqual(len(self.requests), 2)
        self.assertEqual(self.restored, [])

    def test_unsynced_changes_are_not_overwritten(self):
        self.state.synced("github", "fixture/private-repo", "old-sha", local_revision(self.ledger),
                          "2026-10-27T01:00:00+00:00", '"old-etag"')
        with closing(sqlite3.connect(self.ledger)) as db:
            db.execute("INSERT INTO entries VALUES(2,'unsynced fixture')")
            db.commit()
        def fetch(envelope):
            if "/contents/household-bookkeeping/snapshot-v1/manifest.json" in envelope["url"]:
                return 404, b'{"message":"Not Found"}', {}
            return 200, self.metadata(inline=False), {"etag": self.etag}
        with self.assertRaisesRegex(LedgerError, "尚未同步"):
            self.run_pull(fetch)
        self.assertEqual(self.restored, [])
        self.assertEqual(len(self.requests), 1)

    def test_bad_blob_checksum_never_reaches_restore(self):
        original = self.provider(inline=False)
        def fetch(envelope):
            if "/git/blobs/" in envelope["url"]:
                return 200, b"corrupt backup", {}
            return original(envelope)
        with self.assertRaises(LedgerError):
            self.run_pull(fetch)
        self.assertEqual(self.restored, [])

    def test_replayed_http_response_has_status_and_case_insensitive_headers(self):
        request = Request("https://api.github.com/repos/fixture/repo/contents/backup")
        envelope = request_envelope(request, 0, "revision")
        opener = ReplayOpener([{"requestHash": envelope["requestHash"], "status": 200,
                                "body": b"{}", "headers": {"etag": self.etag}}], "revision")
        with opener(request) as response:
            self.assertEqual(response.getcode(), 200)
            self.assertEqual(response.headers.get("ETag"), self.etag)
            self.assertEqual(response.read(), b"{}")

    def test_not_modified_error_keeps_etag(self):
        request = Request("https://api.github.com/fixture")
        envelope = request_envelope(request, 0, "revision")
        opener = ReplayOpener([{"requestHash": envelope["requestHash"], "status": 304,
                                "body": b"", "headers": {"etag": self.etag}}], "revision")
        with self.assertRaises(HTTPError) as caught:
            opener(request)
        self.assertEqual(caught.exception.headers.get("ETag"), self.etag)
        caught.exception.close()


class ResponseStorageTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.database = FixtureD1()
        self.addCleanup(self.database.close)
        crypto_patch = patch.dict(sys.modules, {"secret_crypto": fixture_crypto()})
        crypto_patch.start()
        self.addCleanup(crypto_patch.stop)
        self.env = SimpleNamespace(TOKEN_ENCRYPTION_KEY="fixture-key")
        self.envelope = request_envelope(Request("https://api.github.com/fixture"), 0, "fixture-revision")

    async def test_chunked_response_preserves_body_and_only_allowed_headers(self):
        body = b"synthetic backup bytes" * 12000
        await save_model_response(self.database, self.env, "fixture-user", "fixture-operation",
                                  self.envelope, 200, body,
                                  response_headers={"ETag": '"fixture"', "Set-Cookie": "private", "Authorization": "secret"})
        replies, revision = await load_model_replies(self.database, self.env, "fixture-user", "fixture-operation")
        self.assertEqual(revision, "fixture-revision")
        self.assertEqual(replies[0]["body"], body)
        self.assertEqual(replies[0]["headers"], {"etag": '"fixture"'})
        self.assertGreater(self.database.connection.execute("SELECT chunk_count FROM app_job_model_calls").fetchone()[0], 1)

    async def test_empty_304_response_roundtrips(self):
        await save_model_response(self.database, self.env, "fixture-user", "fixture-operation",
                                  self.envelope, 304, b"", response_headers={"etag": '"fixture"'})
        replies, _ = await load_model_replies(self.database, self.env, "fixture-user", "fixture-operation")
        self.assertEqual((replies[0]["status"], replies[0]["body"], replies[0]["headers"]),
                         (304, b"", {"etag": '"fixture"'}))

    def test_legacy_response_format_is_still_readable(self):
        raw = b'{"choices":[{"message":{"content":"fixture"}}]}'
        self.assertEqual(decode_response_record(raw, "legacy-uuid"), (raw, {}))

    def test_incomplete_metadata_is_rejected(self):
        raw = encode_response_record(b"body", {"etag": "version"})
        with self.assertRaises(ValueError):
            decode_response_record(raw[:5], "http1_fixture")


class D1RestoreIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        env_patch = patch.dict("os.environ", {"HOUSEHOLD_BOOKKEEPING_APP_DATA": str(self.root / "app")})
        env_patch.start()
        self.addCleanup(env_patch.stop)
        crypto_patch = patch.dict(sys.modules, {"secret_crypto": fixture_crypto()})
        crypto_patch.start()
        self.addCleanup(crypto_patch.stop)
        from ledger_runtime import LedgerWorkspace, execute_action
        from bookkeeping.storage import Database
        from bookkeeping.github_sync import create_sync_bundle
        from bookkeeping.payment_preferences import PaymentPromptStore
        from bookkeeping.skill_settings import BookkeepingSkillStore
        from bookkeeping.backup_scope import DEFAULT_BACKUP_SCOPE
        self.LedgerWorkspace, self.execute_action = LedgerWorkspace, execute_action
        self.database = PlatformFixtureD1()
        self.addCleanup(self.database.close)
        self.env = SimpleNamespace(TOKEN_ENCRYPTION_KEY="fixture-key")
        source = self.root / "remote.sqlite3"
        db = Database(source)
        try:
            db.initialize()
            db.add_account(name="Synthetic Remote Bank", account_type="bank", currency="JPY",
                           opening_balance="100", opening_date="2026-10-01")
        finally:
            db.close()
        self.bundle = create_sync_bundle(
            source, self.root / "fixture.zip", include_scope=dict(DEFAULT_BACKUP_SCOPE),
            payment_store=PaymentPromptStore(self.root / "payment.json"),
            bookkeeping_skill_store=BookkeepingSkillStore(self.root / "skill.json", default_path=self.root / "absent"),
            food_skill_store=BookkeepingSkillStore(self.root / "food.json", default_path=self.root / "absent"),
            receipt_image_directory=self.root / "images",
        )
        self.sha = hashlib.sha1(f"blob {len(self.bundle)}\0".encode() + self.bundle).hexdigest()
        state = await LedgerWorkspace.open(self.database, "fixture-user")
        try:
            config = await state.load_config(self.env)
            mobile = state.workspace(config, {})
            mobile._env = self.env
            config["cloud"] = {"github": {"token": "ghu_synthetic", "repository": "fixture/private-repo"}}
            mobile.save_config("fixture-user", config)
            await state.commit(mobile)
        finally:
            state.cleanup()
        self.network = patch("urllib.request.urlopen", side_effect=AssertionError("Real network disabled"))
        self.network.start()
        self.addCleanup(self.network.stop)

    async def action(self, name, data):
        replies, revision = [], None
        requests = []
        for _ in range(10):
            try:
                result = await self.execute_action(self.database, self.env, "fixture-user", name, data,
                                                   None, provider_replies=replies, expected_revision=revision)
                return result, requests
            except ModelRequestRequired as request:
                requests.append(request.envelope)
                envelope = request.envelope
                url = envelope["url"]
                if "/contents/household-bookkeeping/snapshot-v1/manifest.json" in url:
                    status, body = 404, b'{"message":"Not Found"}'
                elif any(k.lower() == "if-none-match" and v == '"fixture-version"'
                         for k, v in envelope["headers"].items()):
                    status, body = 304, b""
                elif "/git/blobs/" in url:
                    status, body = 200, self.bundle
                else:
                    status, body = 200, json.dumps({"sha": self.sha, "size": len(self.bundle)}).encode()
                # The same encrypted response format used by durable jobs.
                packed = encode_response_record(body, {"etag": '"fixture-version"'})
                body, headers = decode_response_record(packed, "http1_fixture")
                replies.append({"requestHash": envelope["requestHash"], "status": status,
                                "body": body, "headers": headers})
                revision = envelope["ledgerRevision"]
        self.fail("D1 action did not finish")

    async def assert_restored_ledger_and_backup(self):
        state = await self.LedgerWorkspace.open(self.database, "fixture-user")
        try:
            ledger = state.root / "ledgers/fixture-user.sqlite3"
            with closing(sqlite3.connect(ledger)) as db:
                self.assertEqual(db.execute("SELECT name FROM accounts ORDER BY name").fetchall(), [("Synthetic Remote Bank",)])
                self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            backups = state.workspace(await state.load_config(self.env), {}).backups("fixture-user")
            self.assertTrue(backups, "the restore must preserve a pre-restore backup in D1")
            self.assertGreater(int(backups[0]["size"]), 0)
            # Backup bytes are intentionally deferred; only their metadata is loaded.
            # Find the persisted checkpoint without relying on workspace layout.
            checkpoints = list(state.root.rglob("cloud_pull_state.json"))
            self.assertEqual(len(checkpoints), 1)
            self.assertEqual(PullState(checkpoints[0]).load()["clouds"]["github:fixture/private-repo"]["sha"], self.sha)
        finally:
            state.cleanup()

    async def test_startup_download_restores_and_commits_then_next_login_is_current(self):
        result, requests = await self.action("startup_pull", {})
        self.assertTrue(result["restored"])
        self.assertEqual(len(requests), 4)
        await self.assert_restored_ledger_and_backup()
        result, requests = await self.action("startup_pull", {})
        self.assertEqual(result["status"], "current")
        self.assertEqual(len(requests), 1)

    async def test_explicit_restore_preserves_backup_and_commits_to_d1(self):
        result, requests = await self.action("cloud_restore", {"provider": "github", "confirmed": True})
        self.assertTrue(result.get("backup"))
        self.assertEqual(len(requests), 4)
        await self.assert_restored_ledger_and_backup()

    async def test_restore_replaces_existing_base_and_discards_old_row_deltas(self):
        from bookkeeping.storage import Database
        for name in ("Old Base Bank", "Old Delta Bank"):
            state = await self.LedgerWorkspace.open(self.database, "fixture-user")
            try:
                mobile = state.workspace(await state.load_config(self.env), {})
                mobile._env = self.env
                db = Database(state.root / "ledgers/fixture-user.sqlite3")
                try:
                    db.add_account(name=name, account_type="bank", currency="JPY",
                                   opening_balance="10", opening_date="2026-10-01")
                finally:
                    db.close()
                await state.commit(mobile)
            finally:
                state.cleanup()
        self.assertGreater(self.database.connection.execute("SELECT COUNT(*) FROM user_ledger_row_deltas").fetchone()[0], 0)
        await self.action("cloud_restore", {"provider": "github", "confirmed": True})
        await self.assert_restored_ledger_and_backup()
        self.assertEqual(self.database.connection.execute("SELECT COUNT(*) FROM user_ledger_row_deltas").fetchone()[0], 0)

    async def test_conflict_becomes_persisted_choice_and_keep_does_not_restore(self):
        from bookkeeping.storage import Database
        state = await self.LedgerWorkspace.open(self.database, "fixture-user")
        try:
            mobile = state.workspace(await state.load_config(self.env), {})
            mobile._env = self.env
            path = mobile.db_path("fixture-user")
            PullState(mobile.folder("fixture-user") / "cloud_pull_state.json").synced(
                "github", "fixture/private-repo", "older-sha",
                local_revision(path, **mobile.stores("fixture-user")),
                "2026-10-27T01:00:00+00:00", '"older-etag"',
            )
            db = Database(path)
            try:
                db.add_account(name="Unsent Synthetic Bank", account_type="bank", currency="JPY",
                               opening_balance="10", opening_date="2026-10-01")
            finally:
                db.close()
            await state.commit(mobile)
        finally:
            state.cleanup()
        result, requests = await self.action("startup_pull", {})
        self.assertEqual(result["status"], "conflict")
        self.assertFalse(result["restored"])
        self.assertEqual(len(requests), 1)
        result, requests = await self.action("startup_pull", {})
        self.assertEqual((result["status"], result["reason"], requests), ("choice_required", "conflict", []))
        result, requests = await self.action("keep_local_cloud", {})
        self.assertEqual((result["status"], requests), ("local_kept", []))
        result, requests = await self.action("startup_pull", {})
        self.assertEqual((result["status"], requests), ("local_kept", []))
        state = await self.LedgerWorkspace.open(self.database, "fixture-user")
        try:
            with closing(sqlite3.connect(state.root / "ledgers/fixture-user.sqlite3")) as db:
                self.assertEqual(db.execute("SELECT name FROM accounts").fetchall(), [("Unsent Synthetic Bank",)])
        finally:
            state.cleanup()
        # An explicit later restore is the only action that resumes downloads.
        await self.action("cloud_restore", {"provider": "github", "confirmed": True})
        await self.assert_restored_ledger_and_backup()
        result, requests = await self.action("startup_pull", {})
        self.assertEqual((result["status"], len(requests)), ("current", 1))

    async def test_new_login_credentials_override_stale_mobile_credentials(self):
        from ledger_runtime import load_mobile_config
        fresh = {"token": "ghu_fresh_login", "refresh_token": "ghr_fresh_login",
                 "client_id": "fresh-client-id", "auth_flow": "device",
                 "repository": "fixture/default-repo", "lastSha": None}
        ciphertext = await fixture_crypto().encrypt_text(
            json.dumps(fresh), self.env.TOKEN_ENCRYPTION_KEY, "user:fixture-user:github-sync",
        )
        await self.database.prepare(
            "UPDATE user_secrets SET encrypted_value=? WHERE user_id=? AND secret_name='github-sync'"
        ).bind(ciphertext, "fixture-user").run()
        config = await load_mobile_config(self.database, self.env, "fixture-user")
        github = config["cloud"]["github"]
        self.assertEqual(github["token"], "ghu_fresh_login")
        self.assertEqual(github["refresh_token"], "ghr_fresh_login")
        self.assertEqual((github["client_id"], github["auth_flow"]), ("fresh-client-id", "device"))
        self.assertEqual(github["repository"], "fixture/private-repo")

    async def prepare_agent(self, *, payment_rule=True):
        from bookkeeping.storage import Database
        state = await self.LedgerWorkspace.open(self.database, "fixture-user")
        try:
            config = await state.load_config(self.env)
            config["profiles"] = [{"id": "fixture-model", "api_key": "synthetic-key",
                                   "api_url": "https://api.example.invalid/v1/chat/completions",
                                   "model": "synthetic-model"}]
            config["agents"]["bookkeeping"] = "fixture-model"
            mobile = state.workspace(config, {})
            mobile._env = self.env
            mobile.save_config("fixture-user", config)
            db = Database(mobile.db_path("fixture-user"))
            try:
                db.add_account(name="Synthetic Wallet", account_type="wallet", currency="JPY",
                               opening_balance="10000", opening_date="2026-10-01")
            finally:
                db.close()
            if payment_rule:
                mobile.stores("fixture-user")["payment_store"].save_profiles([{
                    "payment_method": "Synthetic Wallet", "purpose": "所有餐饮消费",
                    "account_order": ["Synthetic Wallet"], "currency": "JPY",
                }])
            await state.commit(mobile)
        finally:
            state.cleanup()

    async def synthetic_agent(self, *, account=None):
        from datetime import datetime, timezone
        # Cross a JST day boundary between Workflow runs. The original job time
        # must keep both the model request hash and yesterday's date stable.
        created_at = datetime(2026, 10, 28, 15, 5, tzinfo=timezone.utc)
        later = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)
        replies, envelopes, revision = [], [], None
        data = {"text": "昨天晚饭990", "agent": "bookkeeping", "language": "zh-CN"}
        for _ in range(4):
            try:
                with patch("bookkeeping.natural_language._now_japan", return_value=later):
                    result = await self.execute_action(
                        self.database, self.env, "fixture-user", "agent", data, None,
                        provider_replies=replies, expected_revision=revision, request_now=created_at,
                    )
                return result, envelopes
            except ModelRequestRequired as request:
                envelope = request.envelope
                envelopes.append(envelope)
                intent = {"action": "expense", "date": "2026-10-30", "amount": "990",
                          "currency": "JPY", "account": account, "to_account": None,
                          "to_amount": None, "category": "餐饮", "description": "晚饭",
                          "memo_only": False, "question": None, "reply": None,
                          "payment_profile_index": 0 if account is None else None}
                body = json.dumps({"choices": [{"message": {
                    "content": json.dumps(intent, ensure_ascii=False)}}]}).encode()
                replies.append({"requestHash": envelope["requestHash"], "status": 200,
                                "body": body, "headers": {}})
                revision = envelope["ledgerRevision"]
        self.fail("Synthetic Agent did not finish; no real provider may be called")

    async def test_agent_replays_model_then_commits_yesterday_expense_once_as_delta(self):
        await self.prepare_agent()
        result, envelopes = await self.synthetic_agent()
        self.assertIn("已记录消费", result["answer"])
        self.assertFalse(result["pending"])
        self.assertEqual(len(result["transactionIds"]), 1)
        self.assertEqual(len(envelopes), 1)
        payload = json.loads(envelopes[0]["body"])
        self.assertIn("2026-10-29T00:05", json.dumps(payload, ensure_ascii=False))
        state = await self.LedgerWorkspace.open(self.database, "fixture-user")
        try:
            with closing(sqlite3.connect(state.root / "ledgers/fixture-user.sqlite3")) as db:
                self.assertEqual(db.execute(
                    "SELECT occurred_on,amount_minor,kind FROM transactions"
                ).fetchall(), [("2026-10-28", 990, "expense")])
                self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        finally:
            state.cleanup()
        self.assertGreater(self.database.connection.execute(
            "SELECT COUNT(*) FROM user_ledger_row_deltas"
        ).fetchone()[0], 0)

    async def test_agent_without_payment_account_asks_instead_of_writing(self):
        await self.prepare_agent(payment_rule=False)
        result, envelopes = await self.synthetic_agent()
        self.assertTrue(result["pending"])
        self.assertEqual(result["transactionIds"], [])
        self.assertEqual(len(envelopes), 1)
        state = await self.LedgerWorkspace.open(self.database, "fixture-user")
        try:
            with closing(sqlite3.connect(state.root / "ledgers/fixture-user.sqlite3")) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM transactions").fetchone()[0], 0)
        finally:
            state.cleanup()

    async def test_combined_refresh_reads_one_revision_without_writing(self):
        from ledger_runtime import workspace_snapshot, bootstrap
        await self.prepare_agent()
        await self.synthetic_agent()
        user = {"id": "fixture-user", "username": "Synthetic User"}
        changes_before = self.database.connection.total_changes
        with patch.object(self.LedgerWorkspace, "open", wraps=self.LedgerWorkspace.open) as opened:
            snapshot = await workspace_snapshot(self.database, user["id"], "zh-CN", env=self.env,
                                                bootstrap_user=user)
            self.assertEqual(opened.await_count, 1)
        self.assertEqual(self.database.connection.total_changes, changes_before)
        self.assertEqual(len(snapshot["transactions"]), 1)
        self.assertEqual(snapshot["transactions"][0]["amount_minor"], "990")
        self.assertEqual(snapshot["bootstrap"]["transactions"][0]["amount_minor"], "990")
        self.assertEqual(snapshot["bootstrap"]["accounts"][0]["balanceMinor"], "9010")
        self.assertNotIn("synthetic-key", json.dumps(snapshot))
        legacy = await bootstrap(self.database, user, "zh-CN", self.env)
        self.assertEqual(legacy, snapshot["bootstrap"])
        with self.assertRaisesRegex(ValueError, "账号隔离"):
            await workspace_snapshot(self.database, user["id"], env=self.env,
                                     bootstrap_user={"id": "different-user"})

    async def test_workspace_revision_reads_only_index_row(self):
        from ledger_runtime import workspace_revision
        expected=tuple(self.database.connection.execute(
            "SELECT revision,updated_at FROM user_state_roots WHERE user_id=?",("fixture-user",)
        ).fetchone())
        queries=[]
        original=self.database.prepare
        def capture(sql):
            queries.append(sql)
            return original(sql)
        with patch.object(self.database,"prepare",side_effect=capture):
            value=await workspace_revision(self.database,"fixture-user")
        self.assertEqual((value["revision"],value["updatedAt"]),expected)
        self.assertEqual(value["configRevision"],expected[0])
        self.assertTrue(value["serverTime"].endswith("+00:00"))
        self.assertEqual(len(queries),1)
        self.assertIn("SELECT revision,updated_at FROM user_state_roots WHERE user_id=?",queries[0])

    async def test_region_setting_change_advances_lightweight_revision(self):
        from ledger_runtime import workspace_revision
        before = await workspace_revision(self.database, "fixture-user")
        state = await self.LedgerWorkspace.open(self.database, "fixture-user")
        try:
            config = await state.load_config(self.env)
            mobile = state.workspace(config, await state.load_conversations())
            mobile._env = self.env
            config["timeZone"] = "America/New_York"
            config["timeZoneConfigured"] = True
            mobile.save_config("fixture-user", config)
            await state.commit(mobile)
        finally:
            state.cleanup()
        after = await workspace_revision(self.database, "fixture-user")
        self.assertNotEqual(after["revision"], before["revision"])
        self.assertEqual(after["configRevision"], after["revision"])

    async def test_import_rebases_schema_before_the_first_post_write_read(self):
        from ledger_runtime import import_ledger, bootstrap
        source = self.root / "remote.sqlite3"
        with closing(sqlite3.connect(source)) as db:
            db.execute("CREATE TABLE synthetic_padding (id INTEGER PRIMARY KEY,payload BLOB)")
            db.execute("INSERT INTO synthetic_padding VALUES (1,?)", (b"synthetic" * 1024,))
            db.commit()
        user = {"id": "fixture-user", "username": "Synthetic User"}
        scheduled = ModuleType("scheduled")
        scheduled.dispatch_queued_backup = AsyncMock()
        with patch.dict(sys.modules, {"scheduled": scheduled}):
            await import_ledger(self.database, self.env, user, source.read_bytes())
        scheduled.dispatch_queued_backup.assert_awaited_once()
        result = await bootstrap(self.database, user, "zh-CN", self.env)
        self.assertEqual(result["accounts"][0]["name"], "Synthetic Remote Bank")


class WorkerFetchBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_returns_304_and_allowed_headers_for_durable_storage(self):
        workers = ModuleType("workers")
        calls = []
        async def fake_fetch(url, **options):
            calls.append((url, options))
            async def body():
                return b""
            return SimpleNamespace(status=304, url=url, bytes=body,
                                   headers={"ETag": '"fixture"', "Set-Cookie": "do-not-store"})
        workers.fetch = fake_fetch
        ledger = ModuleType("ledger_runtime")
        ledger.execute_action = ledger.load_mobile_config = None
        spec = importlib.util.spec_from_file_location("fixture_app_workflow", Path(__file__).resolve().parents[1] / "src/app_workflow.py")
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"workers": workers, "ledger_runtime": ledger}):
            spec.loader.exec_module(module)
        result = await module._provider_fetch({"url": "https://api.github.com/fixture", "method": "GET", "headers": {}, "body": b""})
        self.assertEqual(result, (304, b"", {"etag": '"fixture"'}))
        self.assertEqual(calls[0][1]["redirect"], "follow")


if __name__ == "__main__":
    unittest.main()
