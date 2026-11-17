from __future__ import annotations

import json
import importlib
import tempfile
import sys
import types
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


PACKAGE_NAME = "web_point_rewards_under_test"
WORKER_SOURCE = Path(__file__).resolve().parents[1] / "cloudflare-full" / "python-d1" / "src"
WORKER_BOOKKEEPING = WORKER_SOURCE / "bookkeeping"
sys.path.insert(0, str(WORKER_SOURCE))
if PACKAGE_NAME not in sys.modules:
    package = types.ModuleType(PACKAGE_NAME)
    package.__path__ = [str(WORKER_BOOKKEEPING)]
    sys.modules[PACKAGE_NAME] = package
worker_storage = importlib.import_module(f"{PACKAGE_NAME}.storage")
worker_fx_rates = importlib.import_module(f"{PACKAGE_NAME}.fx_rates")
worker_web_features = importlib.import_module(f"{PACKAGE_NAME}.web_features")
sys.path.remove(str(WORKER_SOURCE))
Database = worker_storage.Database
LedgerError = worker_storage.LedgerError
ECB_SOURCE = worker_fx_rates.ECB_SOURCE
JpyRate = worker_fx_rates.JpyRate


class AutomaticPointRewardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp.name) / "points-test.sqlite3")
        self.database.initialize()
        self.payment_id = self.database.add_account(
            name="Test Card", account_type="credit", currency="JPY",
            opening_balance=0, opening_date="2026-01-01",
        )
        self.points_id = self.database.add_account(
            name="Test Points", account_type="points", currency="JPY",
            opening_balance=0, opening_date="2026-01-01",
        )
        self.database.add_account(
            name="Test Wallet", account_type="wallet", currency="JPY",
            opening_balance="5000", opening_date="2026-01-01",
        )
        self.database.set_setting("point_reward_rules_v1", json.dumps([{
            "payment_account_id": self.payment_id,
            "points_account_id": self.points_id,
            "rate_bps": 100,
        }]))

    def tearDown(self) -> None:
        self.database.close()
        self.temp.cleanup()

    def reward_rows(self, transaction_id: int):
        return self.database.connection.execute(
            "SELECT * FROM transactions WHERE source LIKE ? ORDER BY id",
            (f"auto_point_reward:{transaction_id}:%",),
        ).fetchall()

    def add_expense(self, amount: str, *, needs_review: bool = False) -> int:
        return self.database.add_transaction(
            occurred_on="2026-11-10", kind="expense", amount=amount, currency="JPY",
            account_name="Test Card", category_name="餐饮", description="Reward test purchase",
            needs_review=needs_review,
        )

    def test_purchase_creates_one_reward_and_edit_delete_keep_it_linked(self) -> None:
        transaction_id = self.add_expense("1599")
        rewards = self.reward_rows(transaction_id)
        self.assertEqual(len(rewards), 1)
        self.assertEqual((rewards[0]["amount_minor"], rewards[0]["account_id"], rewards[0]["category_id"]),
                         (15, self.points_id, self.database.category("积分返还", "income")["id"]))

        backup = self.database.update_transaction_with_backup(
            transaction_id, occurred_on="2026-11-10", kind="expense", amount="2099",
            currency="JPY", account_name="Test Card", category_name="餐饮",
            description="Reward test purchase edited",
        )
        self.assertTrue(backup.exists())
        rewards = self.reward_rows(transaction_id)
        self.assertEqual(len(rewards), 1)
        self.assertEqual(rewards[0]["amount_minor"], 20)
        self.assertEqual(self.database.account_balance_minor(self.points_id), 20)

        self.database.delete_transaction_with_backup(transaction_id)
        self.assertEqual(self.reward_rows(transaction_id), [])
        self.assertEqual(self.database.account_balance_minor(self.points_id), 0)

    def test_reviewed_purchase_accrues_only_after_confirmation(self) -> None:
        transaction_id = self.add_expense("2500", needs_review=True)
        self.assertEqual(self.reward_rows(transaction_id), [])
        self.database.confirm_transaction_review(transaction_id)
        rewards = self.reward_rows(transaction_id)
        self.assertEqual(len(rewards), 1)
        self.assertEqual(rewards[0]["amount_minor"], 25)

    def test_split_purchase_rewards_each_payment_account_at_its_own_rate(self) -> None:
        wallet_id = self.database.account("Test Wallet")["id"]
        self.database.set_setting("point_reward_rules_v1", json.dumps([
            {"payment_account_id": self.payment_id, "points_account_id": self.points_id, "rate_bps": 100},
            {"payment_account_id": wallet_id, "points_account_id": self.points_id, "rate_bps": 200},
        ]))
        transaction_ids = self.database.add_split_expense(
            occurred_on="2026-11-10", amount="3000", currency="JPY",
            allocations=[("Test Card", 1500), ("Test Wallet", 1500)],
            category_name="餐饮", descriptions=["Card share", "Wallet share"],
        )
        rewards = [reward for transaction_id in transaction_ids for reward in self.reward_rows(transaction_id)]
        self.assertEqual([row["amount_minor"] for row in rewards], [15, 30])
        self.assertEqual(self.database.account_balance_minor(self.points_id), 45)

    def test_rule_change_does_not_backfill_but_edit_uses_current_rate(self) -> None:
        transaction_id = self.add_expense("1000")
        self.database.set_setting("point_reward_rules_v1", json.dumps([{
            "payment_account_id": self.payment_id,
            "points_account_id": self.points_id,
            "rate_bps": 200,
        }]))
        # Saving a new rate alone does not retroactively rewrite old rewards.
        self.assertEqual(self.reward_rows(transaction_id)[0]["amount_minor"], 10)
        self.database.update_transaction_with_backup(
            transaction_id, occurred_on="2026-11-10", kind="expense", amount="2000",
            currency="JPY", account_name="Test Card", category_name="餐饮",
            description="Edited after rule change",
        )
        rewards = self.reward_rows(transaction_id)
        self.assertEqual(len(rewards), 1)
        self.assertEqual(rewards[0]["amount_minor"], 40)

        # Removing the rule then editing the source removes its generated reward.
        self.database.set_setting("point_reward_rules_v1", "[]")
        self.database.update_transaction_with_backup(
            transaction_id, occurred_on="2026-11-10", kind="expense", amount="2000",
            currency="JPY", account_name="Test Card", category_name="餐饮",
            description="Edited with reward disabled",
        )
        self.assertEqual(self.reward_rows(transaction_id), [])

    def test_foreign_currency_purchase_uses_saved_jpy_equivalent(self) -> None:
        self.database.add_account(
            name="Test CNY Wallet", account_type="wallet", currency="CNY",
            opening_balance="100.00", opening_date="2026-01-01",
        )
        cny_payment_id = self.database.account("Test CNY Wallet")["id"]
        self.database.set_setting("point_reward_rules_v1", json.dumps([{
            "payment_account_id": cny_payment_id,
            "points_account_id": self.points_id,
            "rate_bps": 1000,
        }]))
        with patch(f"{PACKAGE_NAME}.fx_rates.resolve_jpy_rate", return_value=JpyRate(
            rate=Decimal("20"), rate_date="2026-11-09", source=ECB_SOURCE,
        )):
            transaction_id = self.database.add_transaction(
                occurred_on="2026-11-10", kind="expense", amount="10.00", currency="CNY",
                account_name="Test CNY Wallet", category_name="餐饮", description="CNY purchase",
            )
        rewards = self.reward_rows(transaction_id)
        self.assertEqual(len(rewards), 1)
        self.assertEqual(rewards[0]["amount_minor"], 20)

    def test_auto_reward_cannot_be_edited_or_deleted_independently(self) -> None:
        transaction_id = self.add_expense("1000")
        reward = self.reward_rows(transaction_id)[0]
        with self.assertRaisesRegex(LedgerError, "对应消费"):
            self.database.delete_transaction_with_backup(int(reward["id"]))

    def test_web_action_validates_and_saves_reward_rules_to_ledger_settings(self) -> None:
        uid = "a" * 32
        workspace = object.__new__(worker_web_features.MobileWorkspace)
        workspace.server = SimpleNamespace(ledger_dir=Path(self.temp.name))
        workspace.locks = {}
        workspace.after_write = lambda _uid: None
        web_database = Database(workspace.db_path(uid))
        try:
            web_database.initialize()
            payment_id = web_database.add_account(
                name="Web Card", account_type="credit", currency="JPY",
                opening_balance=0, opening_date="2026-01-01",
            )
            points_id = web_database.add_account(
                name="Web Points", account_type="points", currency="JPY",
                opening_balance=0, opening_date="2026-01-01",
            )
        finally:
            web_database.close()

        result = workspace._action(uid, "point_rewards", {"rules": [{
            "payment_account_id": payment_id,
            "points_account_id": points_id,
            "rate_bps": 125,
        }]})
        self.assertEqual(result["count"], 1)
        saved = Database(workspace.db_path(uid))
        try:
            self.assertEqual(json.loads(saved.get_setting("point_reward_rules_v1")), [{
                "payment_account_id": payment_id,
                "points_account_id": points_id,
                "rate_bps": 125,
                "enabled": True,
            }])
        finally:
            saved.close()

        with self.assertRaisesRegex(LedgerError, "返还比例"):
            workspace._action(uid, "point_rewards", {"rules": [{
                "payment_account_id": payment_id,
                "points_account_id": points_id,
                "rate_bps": 10001,
            }]})


if __name__ == "__main__":
    unittest.main()
