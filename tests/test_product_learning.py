from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bookkeeping.product_learning import retrieve_category_correction
from bookkeeping.storage import Database, seed_demo_data


class ProductLearningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp.name) / "learning-test.sqlite3")
        self.db.initialize()
        seed_demo_data(self.db)

    def tearDown(self) -> None:
        self.db.close()
        self.temp.cleanup()

    def test_explicit_category_edit_teaches_product_name_for_future_entries(self) -> None:
        transaction_id = self.db.add_transaction(
            occurred_on="2026-11-10",
            kind="expense",
            amount="498",
            currency="JPY",
            account_name="瑞穗银行",
            category_name="其他",
            description="高原の詩 498",
        )
        backup = self.db.update_transaction_with_backup(
            transaction_id,
            occurred_on="2026-11-10",
            kind="expense",
            amount="498",
            currency="JPY",
            account_name="瑞穗银行",
            category_name="食材",
            description="高原の詩 498",
        )
        self.assertTrue(backup.exists())
        self.assertEqual(
            retrieve_category_correction(self.db, ["高原の詩"]),
            "食材",
        )

    def test_unrelated_product_does_not_match_learned_category(self) -> None:
        transaction_id = self.db.add_transaction(
            occurred_on="2026-11-10",
            kind="expense",
            amount="498",
            currency="JPY",
            account_name="瑞穗银行",
            category_name="其他",
            description="高原の詩 498",
        )
        self.db.update_transaction_with_backup(
            transaction_id,
            occurred_on="2026-11-10",
            kind="expense",
            amount="498",
            currency="JPY",
            account_name="瑞穗银行",
            category_name="食材",
            description="高原の詩 498",
        )
        self.assertIsNone(retrieve_category_correction(self.db, ["完全不同的商品"]
        ))


if __name__ == "__main__":
    unittest.main()
