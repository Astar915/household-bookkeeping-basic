from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from bookkeeping.storage import Database, LedgerError


class LocalPointRewardCompatibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp.name) / "ledger.sqlite3")
        self.database.initialize()
        self.payment_id = self.database.add_account(
            name="Test Card", account_type="credit", currency="JPY",
            opening_balance=0, opening_date="2026-01-01",
        )
        self.points_id = self.database.add_account(
            name="Test Points", account_type="points", currency="JPY",
            opening_balance=0, opening_date="2026-01-01",
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

    def test_downloaded_rule_creates_and_tracks_reward_through_edit_and_delete(self) -> None:
        transaction_id = self.add_expense("1599")
        reward = self.reward_rows(transaction_id)
        self.assertEqual(len(reward), 1)
        self.assertEqual(int(reward[0]["amount_minor"]), 15)
        self.assertEqual(int(reward[0]["account_id"]), self.points_id)
        self.assertEqual(self.database.account_balance_minor(self.points_id), 15)

        backup = self.database.update_transaction_with_backup(
            transaction_id, occurred_on="2026-11-10", kind="expense", amount="2099",
            currency="JPY", account_name="Test Card", category_name="餐饮",
            description="Edited purchase",
        )
        self.assertTrue(backup.exists())
        reward = self.reward_rows(transaction_id)
        self.assertEqual(len(reward), 1)
        self.assertEqual(int(reward[0]["amount_minor"]), 20)
        self.assertEqual(self.database.account_balance_minor(self.points_id), 20)

        with self.assertRaisesRegex(LedgerError, "对应消费"):
            self.database.delete_transaction_with_backup(int(reward[0]["id"]))
        self.database.delete_transaction_with_backup(transaction_id)
        self.assertEqual(self.reward_rows(transaction_id), [])
        self.assertEqual(self.database.account_balance_minor(self.points_id), 0)

    def test_reviewed_purchase_accrues_only_when_confirmed(self) -> None:
        transaction_id = self.add_expense("2500", needs_review=True)
        self.assertEqual(self.reward_rows(transaction_id), [])
        self.database.confirm_transaction_review(transaction_id)
        reward = self.reward_rows(transaction_id)
        self.assertEqual(len(reward), 1)
        self.assertEqual(int(reward[0]["amount_minor"]), 25)

    def test_split_purchase_applies_each_web_rule_to_its_payment_account(self) -> None:
        wallet_id = self.database.add_account(
            name="Test Wallet", account_type="wallet", currency="JPY",
            opening_balance="5000", opening_date="2026-01-01",
        )
        self.database.set_setting("point_reward_rules_v1", json.dumps([
            {"payment_account_id": self.payment_id, "points_account_id": self.points_id, "rate_bps": 100},
            {"payment_account_id": wallet_id, "points_account_id": self.points_id, "rate_bps": 200},
        ]))
        transaction_ids = self.database.add_split_expense(
            occurred_on="2026-11-10", amount="3000", currency="JPY",
            allocations=[("Test Card", 1500), ("Test Wallet", 1500)],
            category_name="餐饮", descriptions=["Card portion", "Wallet portion"],
        )
        rewards = [row for transaction_id in transaction_ids for row in self.reward_rows(transaction_id)]
        self.assertEqual([int(row["amount_minor"]) for row in rewards], [15, 30])
        self.assertEqual(self.database.account_balance_minor(self.points_id), 45)


if __name__ == "__main__":
    unittest.main()
