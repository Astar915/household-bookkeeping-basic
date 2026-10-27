from __future__ import annotations

import http.cookiejar
import json
import sqlite3
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch, MagicMock

from bookkeeping.storage import Database, LedgerError
from bookkeeping.web import BookkeepingWebServer, BookkeepingRequestHandler, WebError


class GitHubSignInTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.server = BookkeepingWebServer(("127.0.0.1", 0), Path(self.temp.name))
        self.auth = self.server.github_sign_in
        self.handler = object.__new__(BookkeepingRequestHandler)
        self.handler.server = self.server
        self.handler.client_address = ("synthetic-test", 0)
        self.challenge = {"device_code": "private-device-code", "user_code": "ABCD-EFGH",
            "verification_uri": "https://github.com/login/device", "interval": 5, "expires_in": 600}
        self.model = MagicMock()
        self.model.current_user.return_value = {"id": 123456, "login": "synthetic-github", "type": "User"}

    def tearDown(self):
        self.server.server_close()
        self.temp.cleanup()

    def legacy(self):
        user, _ = self.handler._register({"username": "legacy-test", "password": "SyntheticLegacy2026!"})
        return user

    def start(self, **options):
        with patch("bookkeeping.web_github_auth.request_device_code", return_value=self.challenge), \
             patch("bookkeeping.web_github_auth.poll_device_token", return_value={"access_token": "private-token", "refresh_token": "private-refresh"}), \
             patch("bookkeeping.web_github_auth.GitHubClient", return_value=self.model):
            result, cookie = self.auth.start("synthetic-test", **options)
            deadline = time.monotonic() + 3
            while self.auth.status(cookie, result["flowId"])["state"] == "pending" and time.monotonic() < deadline:
                time.sleep(.01)
        return result, cookie

    def test_first_login_creates_private_ledger_and_rename_keeps_stable_owner(self):
        original = self.auth._resolve_identity({"subject": "123", "login": "original-login"})
        renamed = self.auth._resolve_identity({"subject": "123", "login": "new-login"})
        self.assertEqual(original["id"], renamed["id"])
        self.assertEqual(renamed["username"], "new-login")
        self.assertEqual(renamed["authProvider"], "github")
        self.assertTrue((self.server.ledger_dir / f'{original["id"]}.sqlite3').is_file())
        self.assertEqual(self.server.workspace.config(original["id"])["cloud"], {})

    def test_login_name_alone_never_merges_accounts(self):
        a = self.auth._resolve_identity({"subject": "100", "login": "same-login"})
        b = self.auth._resolve_identity({"subject": "101", "login": "same-login"})
        self.assertNotEqual(a["id"], b["id"])

    def test_browser_cookie_is_required_and_result_has_no_tokens(self):
        challenge, cookie = self.start()
        encoded = json.dumps(challenge) + json.dumps(self.auth.status(cookie, challenge["flowId"]))
        self.assertNotIn("private-device-code", encoded)
        self.assertNotIn("private-token", encoded)
        with self.assertRaises(LedgerError):
            self.auth.finish(challenge["flowId"] + ".wrong-secret", challenge["flowId"])
        with self.assertRaises(LedgerError):
            self.auth.status(cookie, "another-flow")
        user = self.auth.finish(cookie, challenge["flowId"])
        self.assertEqual(user["username"], "synthetic-github")
        self.assertNotIn('private-token', json.dumps(user))
        cfg = self.server.workspace.config(user['id'])
        self.assertEqual(cfg['cloud']['github']['token'], 'private-token')
        self.assertNotIn('private-token', json.dumps(self.server.workspace.public_settings(user['id'])))
        with self.assertRaises(LedgerError):
            self.auth.finish(cookie, challenge["flowId"])

    def test_cancel_and_expiry_cannot_create_an_account(self):
        challenge, cookie = self.start()
        self.auth.cancel(cookie, challenge["flowId"])
        with self.assertRaises(LedgerError):
            self.auth.finish(cookie, challenge["flowId"])
        challenge, cookie = self.start()
        self.auth.flows[challenge["flowId"]]["expires"] = time.monotonic() - 1
        with self.assertRaises(LedgerError):
            self.auth.finish(cookie, challenge["flowId"])
        self.assertEqual(list(self.server.ledger_dir.glob("*.sqlite3")), [])

    def test_pending_flow_cannot_finish_before_github_identity_verification(self):
        self.model.current_user.return_value = {"login": "no-numeric-id"}
        challenge, cookie = self.start()
        self.assertEqual(self.auth.status(cookie, challenge["flowId"])["state"], "failed")
        with self.assertRaises(LedgerError):
            self.auth.finish(cookie, challenge["flowId"])
        self.assertEqual(list(self.server.ledger_dir.glob("*.sqlite3")), [])

    def test_link_preserves_ledger_and_retires_old_password(self):
        legacy = self.legacy()
        path = self.server.ledger_dir / f'{legacy["id"]}.sqlite3'
        db = Database(path)
        db.add_account(name="Legacy bank", account_type="bank", currency="JPY", opening_balance="980", opening_date="2026-10-22")
        db.close()
        challenge, cookie = self.start(link_user=legacy["id"])
        with self.assertRaises(LedgerError):
            self.auth.finish(cookie, challenge["flowId"], current_user=None)
        linked = self.auth.finish(cookie, challenge["flowId"], current_user=legacy["id"])
        self.assertEqual(linked["id"], legacy["id"])
        db = Database(path)
        self.assertEqual(db.account("Legacy bank")["opening_balance_minor"], 980)
        db.close()
        with self.assertRaises(WebError):
            self.handler._login({"username": "legacy-test", "password": "SyntheticLegacy2026!"})

    def test_conflicting_identity_keeps_both_ledgers(self):
        existing = self.auth._resolve_identity({"subject": "123456", "login": "synthetic-github"})
        legacy = self.legacy()
        with self.assertRaises(LedgerError):
            self.auth._resolve_identity({"subject": "123456", "login": "synthetic-github"}, legacy["id"])
        self.assertTrue((self.server.ledger_dir / f'{legacy["id"]}.sqlite3').exists())
        self.assertTrue((self.server.ledger_dir / f'{existing["id"]}.sqlite3').exists())

    def test_cannot_rebind_an_existing_ledger_to_another_github(self):
        user = self.auth._resolve_identity({"subject": "200", "login": "first-user"})
        with self.assertRaises(LedgerError):
            self.auth._resolve_identity({"subject": "201", "login": "second-user"}, user["id"])

    def test_untrusted_verification_url_is_not_shown(self):
        with patch("bookkeeping.web_github_auth.request_device_code", return_value={**self.challenge, "verification_uri": "https://evil.invalid"}):
            with self.assertRaises(LedgerError):
                self.auth.start("synthetic-test")

    def test_schema_upgrade_backs_up_existing_accounts_and_preserves_ledger(self):
        legacy = self.legacy()
        self.server.server_close()
        connection = sqlite3.connect(self.server.auth_path)
        connection.execute("DROP TABLE web_identities")
        connection.commit()
        connection.close()
        upgraded = BookkeepingWebServer(("127.0.0.1", 0), Path(self.temp.name))
        try:
            copies = list((Path(self.temp.name) / "auth-backups").glob("*.sqlite3"))
            self.assertEqual(len(copies), 1)
            connection = sqlite3.connect(copies[0])
            self.assertEqual(connection.execute("SELECT id FROM web_users").fetchone()[0], legacy["id"])
            connection.close()
            linked = upgraded.github_sign_in._resolve_identity({"subject": "321", "login": "migrated"}, legacy["id"])
            self.assertEqual(linked["id"], legacy["id"])
            self.assertTrue((upgraded.ledger_dir / f'{legacy["id"]}.sqlite3').exists())
        finally:
            upgraded.server_close()

    def test_two_simultaneous_first_logins_use_one_ledger(self):
        results, errors = [], []
        def resolve():
            try:
                results.append(self.auth._resolve_identity({"subject": "765", "login": "concurrent"}))
            except Exception as error:
                errors.append(error)
        threads = [threading.Thread(target=resolve) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(5)
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["id"], results[1]["id"])
        self.assertEqual(len(list(self.server.ledger_dir.glob("*.sqlite3"))), 1)

    def test_http_browser_binding_session_and_disabled_registration(self):
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{self.server.server_port}"
        browser = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        outsider = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

        def post(opener, route, data, origin=None):
            request = urllib.request.Request(base + route, data=json.dumps(data).encode(), headers={"Content-Type": "application/json", "Origin": origin or base})
            with opener.open(request) as response:
                return json.load(response)
        try:
            with self.assertRaises(urllib.error.HTTPError) as error:
                post(browser, "/api/register", {})
            self.assertEqual(error.exception.code, 410)
            error.exception.close()
            with self.assertRaises(urllib.error.HTTPError) as error:
                post(browser, "/api/auth/github/start", {}, "https://untrusted.invalid")
            self.assertEqual(error.exception.code, 403)
            error.exception.close()
            with patch("bookkeeping.web_github_auth.request_device_code", return_value=self.challenge), \
                 patch("bookkeeping.web_github_auth.poll_device_token", return_value={"access_token": "private-token"}), \
                 patch("bookkeeping.web_github_auth.GitHubClient", return_value=self.model):
                challenge = post(browser, "/api/auth/github/start", {})
                for _ in range(100):
                    status = post(browser, "/api/auth/github/status", {"flowId": challenge["flowId"]})
                    if status["state"] != "pending":
                        break
                    time.sleep(.01)
                self.assertEqual(status["state"], "authorized")
                with self.assertRaises(urllib.error.HTTPError) as error:
                    post(outsider, "/api/auth/github/finish", {"flowId": challenge["flowId"]})
                error.exception.close()
                user = post(browser, "/api/auth/github/finish", {"flowId": challenge["flowId"]})["user"]
            with browser.open(base + "/api/session") as response:
                session = json.load(response)
            self.assertEqual(session["user"]["id"], user["id"])
            self.assertEqual(session["user"]["authProvider"], "github")
            self.assertEqual(session["user"]["username"], "synthetic-github")
            self.assertTrue(session["csrfToken"])
            wrong_owner = urllib.request.Request(base + "/api/workspace", headers={"X-Ledger-Owner": "stale-account"})
            with self.assertRaises(urllib.error.HTTPError) as error:
                browser.open(wrong_owner)
            self.assertEqual(error.exception.code, 409)
            error.exception.close()
            operation = {"operations": [{"opId": "synthetic-operation-12345", "type": "account",
                "ownerId": "stale-account", "data": {"name": "Wrong owner account"}}]}
            request = urllib.request.Request(base + "/api/sync", data=json.dumps(operation).encode(),
                headers={"Content-Type": "application/json", "Origin": base,
                    "X-CSRF-Token": session["csrfToken"], "X-Ledger-Owner": user["id"]})
            with browser.open(request) as response:
                result = json.load(response)
            self.assertFalse(result["results"][0]["ok"])
            self.assertIn("另一个账号", result["results"][0]["error"])
            db = Database(self.server.ledger_dir / f'{user["id"]}.sqlite3')
            self.assertEqual(db.connection.execute("SELECT COUNT(*) FROM accounts").fetchone()[0], 0)
            db.close()
        finally:
            self.server.shutdown()
            thread.join(3)


if __name__ == "__main__":
    unittest.main()
