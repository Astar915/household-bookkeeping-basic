from __future__ import annotations

import importlib
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

from bookkeeping.storage import Database as DesktopDatabase
from bookkeeping.sync_snapshot import materialize_snapshot_bundle


PACKAGE_NAME = "web_desktop_snapshot_under_test"
WORKER_SOURCE = Path(__file__).resolve().parents[1] / "cloudflare-full" / "python-d1" / "src"
WORKER_BOOKKEEPING = WORKER_SOURCE / "bookkeeping"
sys.path.insert(0, str(WORKER_SOURCE))
if PACKAGE_NAME not in sys.modules:
    package = types.ModuleType(PACKAGE_NAME)
    package.__path__ = [str(WORKER_BOOKKEEPING)]
    sys.modules[PACKAGE_NAME] = package
worker_storage = importlib.import_module(f"{PACKAGE_NAME}.storage")
worker_snapshots = importlib.import_module(f"{PACKAGE_NAME}.sync_snapshot")
worker_scope = importlib.import_module(f"{PACKAGE_NAME}.backup_scope")
worker_payments = importlib.import_module(f"{PACKAGE_NAME}.payment_preferences")
worker_skills = importlib.import_module(f"{PACKAGE_NAME}.skill_settings")
worker_rates = importlib.import_module(f"{PACKAGE_NAME}.fx_rates")
sys.path.remove(str(WORKER_SOURCE))


class WebDesktopSnapshotCompatibilityTests(unittest.TestCase):
    def test_web_snapshot_restores_to_desktop_and_keeps_shared_backend_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            web_path = root / "web.sqlite3"
            web_db = worker_storage.Database(web_path)
            web_db.initialize()
            payment_id = web_db.add_account(
                name="Web Card", account_type="credit", currency="JPY",
                opening_balance=0, opening_date="2026-01-01",
            )
            points_id = web_db.add_account(
                name="Web Points", account_type="points", currency="JPY",
                opening_balance=0, opening_date="2026-01-01",
            )
            web_db.set_setting("time_zone", "America/Los_Angeles", "Portable region")
            web_db.set_setting("billing_cycle_start_day", "15", "Cycle setting")
            web_db.set_setting("base_currency", "JPY", "Base currency")
            web_db.set_setting("point_reward_rules_v1", json.dumps([{
                "payment_account_id": payment_id,
                "points_account_id": points_id,
                "rate_bps": 100,
                "enabled": True,
            }]))
            purchase_id = web_db.add_transaction(
                occurred_on="2026-11-10", kind="expense", amount="1599", currency="JPY",
                account_name="Web Card", category_name="餐饮", description="Web purchase",
            )
            self.assertEqual(web_db.account_balance_minor(points_id), 15)
            web_db.close()

            plan = worker_snapshots.build_snapshot(
                web_path,
                payment_store=worker_payments.PaymentPromptStore(root / "payment.json"),
                bookkeeping_skill_store=worker_skills.BookkeepingSkillStore(
                    root / "bookkeeping.json", default_path=root / "bookkeeping.md"
                ),
                food_skill_store=worker_skills.BookkeepingSkillStore(
                    root / "food.json", default_path=root / "food.md"
                ),
                receipt_image_directory=root / "receipts",
                include_scope=dict(worker_scope.DEFAULT_BACKUP_SCOPE),
            )
            bundle = materialize_snapshot_bundle(plan.manifest, plan.files)
            archive_path = root / "web-snapshot-restore.sqlite3"
            import io
            import zipfile
            with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
                archive_path.write_bytes(archive.read("ledger.sqlite3"))

            desktop_db = DesktopDatabase(archive_path)
            try:
                desktop_db.initialize()
                self.assertEqual(desktop_db.get_time_zone(), "America/Los_Angeles")
                self.assertEqual(desktop_db.get_billing_cycle_start_day(), 15)
                self.assertEqual(json.loads(desktop_db.get_setting("point_reward_rules_v1"))[0]["rate_bps"], 100)
                reward = desktop_db.connection.execute(
                    "SELECT amount_minor FROM transactions WHERE source LIKE ?",
                    (f"auto_point_reward:{purchase_id}:%",),
                ).fetchone()
                self.assertEqual(int(reward["amount_minor"]), 15)

                desktop_db.update_transaction_with_backup(
                    purchase_id, occurred_on="2026-11-10", kind="expense", amount="2099",
                    currency="JPY", account_name="Web Card", category_name="餐饮",
                    description="Edited on desktop",
                )
                updated_reward = desktop_db.connection.execute(
                    "SELECT amount_minor FROM transactions WHERE source LIKE ?",
                    (f"auto_point_reward:{purchase_id}:%",),
                ).fetchone()
                self.assertEqual(int(updated_reward["amount_minor"]), 20)
            finally:
                desktop_db.close()


if __name__ == "__main__":
    unittest.main()
