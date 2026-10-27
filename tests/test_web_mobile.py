from __future__ import annotations

import http.cookiejar
import importlib.util
import json
import io
import ssl
import zipfile
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from bookkeeping.request_worker import merge_isolated_database, RequestMergeError
from bookkeeping.storage import Database, LedgerError
from bookkeeping.web import BookkeepingWebServer, BookkeepingRequestHandler


class MobileWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.server = BookkeepingWebServer(("127.0.0.1", 0), self.root / "service")
        self.ws = self.server.workspace
        self.uid, self.other = str(uuid.uuid4()), str(uuid.uuid4())
        for uid in (self.uid, self.other):
            db = Database(self.ws.db_path(uid))
            db.initialize()
            db.add_account(name="Test bank", account_type="bank", currency="JPY", opening_balance="20000", opening_date="2026-01-01")
            db.add_account(name="Test card", account_type="credit", currency="JPY", opening_balance="0", opening_date="2026-01-01")
            db.add_credit_limit_snapshot("Test card", "2026-10-01", "10000", "10000")
            db.close()

    def tearDown(self):
        self.server.server_close()
        self.temp.cleanup()

    def action(self, name, data, uid=None, opid=None):
        uid, opid = uid or self.uid, opid or uuid.uuid4().hex
        job = self.ws.start(uid, name, data, opid)
        until = time.monotonic() + 15
        while job["state"] == "running" and time.monotonic() < until:
            time.sleep(.02)
            job = self.ws.job(uid, opid)
        self.assertEqual(job["state"], "done", job)
        return job

    def test_text_skills_persist_and_accounts_are_isolated(self):
        self.action("settings", {"skills": {"bookkeeping": "# pasted test rule\nLunch means dining", "food_health": "# My food rules"}})
        self.assertIn("pasted test rule", self.ws.public_settings(self.uid)["skills"]["bookkeeping"])
        self.assertNotIn("pasted test rule", self.ws.public_settings(self.other)["skills"]["bookkeeping"])
        self.assertNotIn("10kg", self.ws.public_settings(self.other)["skills"]["food_health"])

    def test_default_scope_all_selected(self):
        scope = self.ws.public_settings(self.uid)["scope"]
        self.assertEqual(len(scope), 7)
        self.assertTrue(all(scope.values()))

    def test_mobile_can_edit_transaction_and_keeps_pre_edit_backup(self):
        db_path = self.ws.db_path(self.uid)
        db = Database(db_path)
        transaction_id = db.add_transaction(
            occurred_on="2026-10-22", kind="expense", amount="12",
            currency="JPY", description="Before edit", category_name="餐饮",
            account_name="Test bank",
        )
        db.close()

        result = self.action("edit_transaction", {
            "id": transaction_id, "date": "2026-10-23", "kind": "expense",
            "amount": "30", "currency": "JPY", "description": "Corrected entry",
            "category_name": "餐饮", "account_name": "Test bank",
            "needs_review": False,
        })["result"]

        db = Database(db_path)
        row = db.connection.execute(
            "SELECT occurred_on,amount_minor,description FROM transactions WHERE id=?",
            (transaction_id,),
        ).fetchone()
        db.close()
        self.assertEqual(tuple(row), ("2026-10-23", 30, "Corrected entry"))
        self.assertTrue(result["backup"].endswith(".sqlite3"))
        self.assertTrue((db_path.parent / "backups" / result["backup"]).is_file())

    def test_migrated_skills_use_current_account_files(self):
        folder = self.ws.folder(self.uid)
        restored = folder / "restored_skills"
        restored.mkdir()
        for settings, name in (("bookkeeping_skill.json", "bookkeeping.md"), ("food_skill.json", "food_health.md")):
            (restored / name).write_text("# migrated " + name, encoding="utf-8")
            (folder / settings).write_text(json.dumps({"version": 1, "path": "C:\\OldComputer\\old-user\\restored_skills\\" + name}), encoding="utf-8")
        snapshot = self.ws.snapshot(self.uid)
        self.assertEqual(snapshot["preferences"]["skills"]["bookkeeping"], "# migrated bookkeeping.md")
        self.assertFalse(snapshot["preferences"]["skillErrors"])

    def test_missing_skill_does_not_hide_ledger_or_settings(self):
        (self.ws.folder(self.uid) / "bookkeeping_skill.json").write_text(
            json.dumps({"version": 1, "path": str(self.root / "missing.md")}), encoding="utf-8")
        snapshot = self.ws.snapshot(self.uid)
        self.assertTrue(snapshot["preferences"]["skillErrors"]["bookkeeping"])
        self.assertEqual(snapshot["preferences"]["skills"]["bookkeeping"], "")
        self.assertTrue(snapshot["cash"])
        # Saving another preference without new Skill text preserves the
        # failed selection; explicit repair through the editor remains possible.
        from bookkeeping.skill_settings import BookkeepingSkillError
        with self.assertRaises(BookkeepingSkillError):
            self.ws.stores(self.uid)["bookkeeping_skill_store"].load()

    def test_encrypted_credentials_are_redacted_and_retained(self):
        profile = {"id": "test-profile", "name": "Test API", "api_url": "https://example.com/v1", "model": "test", "api_key": "test-secret-never-output"}
        with patch.object(self.ws, "_check_endpoint"):
            self.action("settings", {"profiles": [profile]})
            public = self.ws.public_settings(self.uid)
            self.assertTrue(public["profiles"][0]["keyPresent"])
            self.assertNotIn("test-secret", json.dumps(public))
            profile["api_key"] = ""
            self.action("settings", {"profiles": [profile]})
        self.assertEqual(self.ws.config(self.uid)["profiles"][0]["api_key"], "test-secret-never-output")
        raw = (self.ws.folder(self.uid) / "settings.enc").read_bytes()
        self.assertNotIn(b"test-secret", raw)
        _, bundle = self.ws.backup(self.uid)
        with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
            self.assertNotIn(b"test-secret-never-output", b"".join(archive.read(name) for name in archive.namelist()))

    def test_backup_restore_preserves_skills_and_ledger_in_account_folder(self):
        self.action("settings", {"skills": {"bookkeeping": "# account-specific pasted rule"}})
        name, body = self.ws.backup(self.uid)
        self.action("credit_snapshot", {"account": "Test card", "date": "2026-10-22", "limit": "12000", "available": "9000"})
        self.action("settings", {"skills": {"bookkeeping": "# modified"}})
        self.ws.restore(self.uid, body)
        self.assertEqual(self.ws.public_settings(self.uid)["skills"]["bookkeeping"], "# account-specific pasted rule")
        restored = self.ws.stores(self.uid)["bookkeeping_skill_store"].current_path()
        self.assertTrue(restored.is_relative_to(self.ws.folder(self.uid)))
        cards = self.ws.snapshot(self.uid)["cards"]
        self.assertEqual(cards[0]["limit_minor"], "10000")
        self.assertNotIn("account-specific", self.ws.public_settings(self.other)["skills"]["bookkeeping"])
        self.assertTrue(self.ws.backup_file(self.uid, name).is_file())

    def test_idempotent_job_does_not_create_second_snapshot(self):
        data = {"account": "Test card", "date": "2026-10-22", "limit": "12000", "available": "9000"}
        opid = uuid.uuid4().hex
        self.action("credit_snapshot", data, opid=opid)
        self.action("credit_snapshot", data, opid=opid)
        db = Database(self.ws.db_path(self.uid))
        count = db.connection.execute("SELECT COUNT(*) FROM credit_limit_snapshots").fetchone()[0]
        db.close()
        self.assertEqual(count, 2)
        with self.assertRaises(LedgerError):
            self.ws.start(self.uid, "credit_snapshot", {**data, "limit": "13000"}, opid)

    def test_jobs_cannot_be_read_from_another_account(self):
        job = self.action("backup", {})
        with self.assertRaises(LedgerError):
            self.ws.job(self.other, job["id"])
        with self.assertRaises(LedgerError):
            self.ws.backup_file(self.other, job["result"]["name"])

    def test_bad_bundle_does_not_modify_live_data(self):
        before = self.ws.snapshot(self.uid)["cards"]
        with self.assertRaises(Exception):
            self.ws.restore(self.uid, b"invalid ZIP")
        self.assertEqual(before, self.ws.snapshot(self.uid)["cards"])

    def test_asset_food_recurring_budget_and_categories_share_desktop_services(self):
        self.action("asset", {"name": "Test laptop", "month": "2026-10", "cost": "120000", "currency": "JPY", "months": "36", "included": True})
        self.action("food_purchase", {"date": "2026-10-22", "items": [["牛奶", "1"]]})
        self.action("food_eaten", {"date": "2026-10-22", "items": [["鸡蛋", "2"]], "meal": "lunch"})
        self.action("category", {"name": "Test category", "kind": "expense", "en-US": "Test category"})
        self.action("budget", {"total": "80000", "items": {"餐饮": "10000"}, "goal": "20000"})
        self.action("recurring", {"name": "Test monthly", "kind": "expense", "amount": "50", "account": "Test bank", "category": "通信与账单", "frequency": "monthly", "date": "2099-01-01", "currency": "JPY"})
        snapshot = self.ws.snapshot(self.uid)
        self.assertEqual(snapshot["assets"][0]["name"], "Test laptop")
        self.assertEqual(snapshot["food"][0]["item_name"], "牛奶")
        self.assertEqual(snapshot["eaten"][0]["item_name"], "鸡蛋")
        self.assertEqual(snapshot["settings"]["monthly_jpy_budget_minor"], "80000")
        self.assertEqual(snapshot["recurring"][0]["name"], "Test monthly")

    def test_rule_editor_saves_order_and_rejects_stale_revision(self):
        revision = self.ws.public_settings(self.uid)["paymentRevision"]
        rules = [{"payment_method": "Test bank", "purpose": "Test scenario", "currency": "JPY", "account_order": ["Test bank", "Test card"]}]
        self.action("payment_rules", {"profiles": rules, "revision": revision})
        self.assertEqual(self.ws.public_settings(self.uid)["paymentRules"], rules)
        job = self.ws.start(self.uid, "payment_rules", {"profiles": rules, "revision": revision}, uuid.uuid4().hex)
        until = time.monotonic() + 5
        while job["state"] == "running" and time.monotonic() < until:
            time.sleep(.02)
            job = self.ws.job(self.uid, job["id"])
        self.assertEqual(job["state"], "failed")

    def test_cloud_connect_never_overwrites_existing_backup(self):
        fake = unittest.mock.MagicMock()
        fake.token = "synthetic-cloud-token"
        fake.refresh_token = ""
        fake.current_user.return_value = {"login": "synthetic"}
        fake.ensure_private_repository.return_value = ("synthetic/private-test", False)
        fake.bundle_sha.return_value = "existing-sha"
        with patch("bookkeeping.web_features.GiteeClient", return_value=fake):
            self.action("cloud_connect", {"provider": "gitee", "token": "synthetic-cloud-token"})
        fake.upload_bundle.assert_not_called()
        self.assertTrue(self.ws.public_settings(self.uid)["cloud"]["gitee"]["connected"])
        self.assertNotIn("synthetic-cloud-token", json.dumps(self.ws.public_settings(self.uid)))

    def test_credit_plan_and_reconcile(self):
        self.action("credit_plan", {"card": "Test card", "source": "Test bank", "date": "2099-01-01", "amount": "500"})
        self.action("credit_plan_toggle", {"card": "Test card", "enabled": False})
        self.assertEqual(self.ws.snapshot(self.uid)["repaymentPlans"][0]["enabled"], "0")
        self.action("reconcile", {"date": "2026-10-22", "amounts": {"Test bank": "19000"}, "postDifferences": True})
        self.assertEqual(len(self.ws.snapshot(self.uid)["transactions"]), 1)

    def test_agent_process_posts_once_and_receives_pasted_skill(self):
        received = []
        intent = {"action": "expense", "date": "2026-10-22", "amount": "980", "currency": "JPY",
                  "account": "Test card", "to_account": None, "to_amount": None, "category": "餐饮",
                  "description": "synthetic lunch", "memo_only": False, "question": None,
                  "reply": None, "payment_profile_index": None, "purchase_items": [], "transactions": None}

        class FakeModel(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                body = json.dumps({"choices": [{"message": {"content": json.dumps(intent)}}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        model = ThreadingHTTPServer(("127.0.0.1", 0), FakeModel)
        thread = threading.Thread(target=model.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.dict("os.environ", {"HOUSEHOLD_WEB_ALLOW_LOCAL_API": "1"}):
                self.action("settings", {"profiles": [{"id": "fake", "name": "Synthetic model", "model": "synthetic",
                    "api_url": f"http://127.0.0.1:{model.server_port}/v1/chat/completions", "api_key": ""}],
                    "agents": {"bookkeeping": "fake", "food_health": "fake"},
                    "skills": {"bookkeeping": "# synthetic pasted skill marker"}})
                result = self.action("agent", {"agent": "bookkeeping", "text": "午饭980日元，用Test card支付", "language": "zh-CN"})
            self.assertEqual(len(result["result"]["transactionIds"]), 1)
            self.assertIn("synthetic pasted skill marker", json.dumps(received))
            data = self.ws.snapshot(self.uid)
            self.assertEqual(data["transactions"][0]["amount_minor"], "980")
            self.assertEqual(data["cards"][0]["available_minor"], "9020")
        finally:
            model.shutdown()
            model.server_close()
            thread.join(3)

    def test_worker_merges_card_recovery_points_with_expense(self):
        baseline, candidate = self.root / "base.sqlite3", self.root / "candidate.sqlite3"
        db = Database(self.ws.db_path(self.uid))
        db.backup(baseline)
        db.backup(candidate)
        db.close()
        db = Database(candidate)
        db.add_transaction(occurred_on="2026-10-22", kind="expense", amount="980", currency="JPY", account_name="Test card", category_name="餐饮", description="synthetic lunch")
        expected = db.connection.execute("SELECT COUNT(*) FROM credit_limit_recovery_points").fetchone()[0]
        self.assertGreater(expected, 0)
        db.close()
        merge_isolated_database(self.ws.db_path(self.uid), baseline, candidate)
        db = Database(self.ws.db_path(self.uid))
        self.assertEqual(db.connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0], 1)
        self.assertEqual(db.connection.execute("SELECT COUNT(*) FROM credit_limit_recovery_points").fetchone()[0], expected)
        db.close()

    def test_worker_rejects_unrelated_settings_change(self):
        baseline, candidate = self.root / "base.sqlite3", self.root / "candidate.sqlite3"
        db = Database(self.ws.db_path(self.uid))
        db.backup(baseline)
        db.backup(candidate)
        db.close()
        db = Database(candidate)
        db.connection.execute("UPDATE settings SET value='1'")
        db.connection.commit()
        db.close()
        with self.assertRaises(RequestMergeError):
            merge_isolated_database(self.ws.db_path(self.uid), baseline, candidate)

    def test_http_mobile_routes_auth_csrf_and_static(self):
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{self.server.server_port}"
            opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
            for file in ("/mobile.js", "/mobile.css", "/apple-touch-icon.png", "/sw.js"):
                with opener.open(base + file) as response:
                    self.assertEqual(response.status, 200)
            with self.assertRaises(urllib.error.HTTPError) as denied:
                opener.open(base + "/api/workspace")
            denied.exception.close()
            legacy = object.__new__(BookkeepingRequestHandler)
            legacy.server = self.server
            legacy._register({"username": "synthetic-user", "password": "SyntheticPass2026!"})
            request = urllib.request.Request(base + "/api/login", data=json.dumps({"username": "synthetic-user", "password": "SyntheticPass2026!"}).encode(), headers={"Content-Type": "application/json", "Origin": base})
            with opener.open(request) as response:
                result = json.load(response)
            with opener.open(base + "/api/workspace") as response:
                data = json.load(response)
                self.assertIn("skills", data["preferences"])
                self.assertNotIn("Test bank", json.dumps(data))
            bad = urllib.request.Request(base + "/api/action", data=b'{"action":"backup","data":{},"opId":"abcdefghijkl"}', headers={"Content-Type": "application/json", "Origin": "https://untrusted.invalid"})
            with self.assertRaises(urllib.error.HTTPError) as error:
                opener.open(bad)
            self.assertEqual(error.exception.code, 403)
            error.exception.close()
        finally:
            self.server.shutdown()
            thread.join(3)

    def test_cloud_runtime_is_reported_to_the_mobile_install_screen(self):
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{self.server.server_port}"
            with patch.dict("os.environ", {"HOUSEHOLD_WEB_CLOUD_RUNTIME": "1"}):
                with urllib.request.urlopen(base + "/api/config") as response:
                    config = json.load(response)
            self.assertEqual(config["deploymentMode"], "cloud")
        finally:
            self.server.shutdown()
            thread.join(3)

    def test_wifi_certificate_validates_with_strict_tls_and_profile_has_no_private_key(self):
        path = Path(__file__).resolve().parents[1] / "scripts" / "start_mobile_test.py"
        spec = importlib.util.spec_from_file_location("mobile_test_launcher", path)
        launcher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(launcher)
        folder = self.root / "certificate"
        launcher.prepare(folder, "127.0.0.1")
        self.assertNotIn(b"PRIVATE KEY", (folder / "iphone-test.mobileconfig").read_bytes())
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.load_cert_chain(folder / "server.pem", folder / "server-key.pem")
        self.server.socket = tls.wrap_socket(self.server.socket, server_side=True)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        try:
            context = ssl.create_default_context(cafile=str(folder / "ca.pem"))
            with urllib.request.urlopen(f"https://127.0.0.1:{self.server.server_port}/api/config", context=context) as response:
                self.assertEqual(response.status, 200)
        finally:
            self.server.shutdown()
            thread.join(3)


if __name__ == "__main__":
    unittest.main()
