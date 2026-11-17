from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bookkeeping.balance_reconciliation import record_credit_snapshot
from bookkeeping.storage import Database


class CreditSnapshotReconciliationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp.name) / "ledger.sqlite3")
        self.database.initialize()
        self.database.add_account(
            name="Snapshot test card", account_type="credit", currency="JPY",
            opening_balance=0, opening_date="2026-01-01",
        )

    def tearDown(self) -> None:
        self.database.close()
        self.temp.cleanup()

    def test_new_snapshot_posts_only_change_from_previous_available_credit(self) -> None:
        self.database.add_credit_limit_snapshot(
            "Snapshot test card", "2026-11-10", "100000", "7191"
        )
        result = record_credit_snapshot(
            self.database, "Snapshot test card", "100000", "8160", "2026-11-11",
            include_difference=True,
        )
        self.assertEqual(result["previous_available_minor"], 7191)
        self.assertEqual(result["before_minor"], 92809)
        self.assertEqual(result["difference_minor"], -969)
        self.assertEqual(result["category_name"], "余额盘盈")
        transaction = self.database.connection.execute(
            "SELECT kind,amount_minor,description FROM transactions WHERE id=?",
            (result["transaction_id"],),
        ).fetchone()
        self.assertEqual(transaction["kind"], "income")
        self.assertEqual(transaction["amount_minor"], 969)
        self.assertIn("可用额度 7,191 → 8,160 JPY", transaction["description"])


if __name__ == "__main__":
    unittest.main()
