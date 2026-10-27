from __future__ import annotations

import tempfile
import sqlite3
import unittest
from pathlib import Path

from bookkeeping.credit_management import (
    credit_card_overview,
    recent_credit_repayments,
    record_credit_card_repayment,
)
from bookkeeping.storage import Database, LedgerError, seed_demo_data


class CreditManagementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp.name) / "ledger.sqlite3")
        self.db.initialize()
        seed_demo_data(self.db)

    def tearDown(self) -> None:
        self.db.close()
        self.temp.cleanup()

    def test_overview_estimates_current_debt_from_limit_and_available_credit(self) -> None:
        cards = {row["name"]: row for row in credit_card_overview(self.db)}

        mercari = cards["Mercari Card"]
        self.assertEqual(mercari["limit_minor"], 100000)
        self.assertEqual(mercari["available_minor"], 40000)
        self.assertEqual(mercari["debt_estimate_minor"], 60000)
        self.assertNotIn("book_debt_minor", mercari)

    def test_available_credit_tracks_expenses_refunds_and_repayments_after_snapshot(self) -> None:
        self.db.add_transaction(
            occurred_on="2026-10-16", kind="expense", amount="7375", currency="JPY",
            account_name="Mercari Card", category_name="娱乐", description="信用卡消费",
        )
        self.db.add_transaction(
            occurred_on="2026-10-16", kind="income", amount="2000", currency="JPY",
            account_name="Mercari Card", category_name="退款/返现", description="信用卡退款",
        )
        record_credit_card_repayment(
            self.db, card_name="Mercari Card", source_account_name="瑞穗银行",
            amount="45500", occurred_on="2026-10-16",
        )

        cards = {row["name"]: row for row in credit_card_overview(self.db)}
        self.assertEqual(cards["Mercari Card"]["available_minor"], 40000 - 7375 + 2000 + 45500)
        snapshot = self.db.latest_credit_snapshot(self.db.account("Mercari Card")["id"])
        self.assertEqual(snapshot["available_minor"], 40000)

    def test_available_credit_is_bounded_by_zero_and_total_limit(self) -> None:
        self.db.add_transaction(
            occurred_on="2026-10-16", kind="expense", amount="50000", currency="JPY",
            account_name="Mercari Card", category_name="娱乐", description="超过剩余额度的记录",
        )
        self.db.add_transaction(
            occurred_on="2026-10-16", kind="transfer", amount="200000", currency="JPY",
            account_name="瑞穗银行", to_account_name="Mercari Card", description="还款",
        )
        cards = {row["name"]: row for row in credit_card_overview(self.db)}
        self.assertEqual(cards["Mercari Card"]["available_minor"], 100000)

    def test_transactions_before_snapshot_do_not_change_available_credit(self) -> None:
        self.db.connection.execute(
            "UPDATE accounts SET opening_date='2026-10-14' WHERE name='Mercari Card'"
        )
        self.db.connection.commit()
        self.db.add_transaction(
            occurred_on="2026-10-14", kind="expense", amount="1000", currency="JPY",
            account_name="Mercari Card", category_name="娱乐", description="快照前消费",
        )
        cards = {row["name"]: row for row in credit_card_overview(self.db)}
        self.assertEqual(cards["Mercari Card"]["available_minor"], 40000)

        self.db.add_transaction(
            occurred_on="2026-10-15", kind="expense", amount="1000", currency="JPY",
            account_name="Mercari Card", category_name="娱乐", description="快照日之后记录的消费",
        )
        cards = {row["name"]: row for row in credit_card_overview(self.db)}
        self.assertEqual(cards["Mercari Card"]["available_minor"], 39000)

    def test_legacy_snapshot_migration_anchors_same_day_activity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "legacy.sqlite3"
            connection = sqlite3.connect(path)
            connection.executescript(
                """CREATE TABLE currencies (
                       code TEXT PRIMARY KEY, name TEXT NOT NULL,
                       minor_digits INTEGER NOT NULL, is_monetary INTEGER NOT NULL
                   );
                   CREATE TABLE accounts (
                       id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE,
                       account_type TEXT NOT NULL, currency TEXT NOT NULL,
                       opening_balance_minor INTEGER NOT NULL, opening_date TEXT NOT NULL,
                       balance_completeness TEXT NOT NULL DEFAULT 'known', opening_note TEXT NOT NULL DEFAULT '',
                       created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                   );
                   CREATE TABLE credit_limit_snapshots (
                       id INTEGER PRIMARY KEY, account_id INTEGER NOT NULL, snapshot_date TEXT NOT NULL,
                       limit_minor INTEGER NOT NULL, available_minor INTEGER NOT NULL, note TEXT NOT NULL DEFAULT '',
                       UNIQUE(account_id, snapshot_date)
                   );
                   INSERT INTO currencies VALUES ('JPY','Japanese yen',0,1);
                   INSERT INTO accounts(id,name,account_type,currency,opening_balance_minor,opening_date)
                       VALUES (1,'Mercari Card','credit','JPY',0,'2026-10-15');
                   INSERT INTO credit_limit_snapshots(account_id,snapshot_date,limit_minor,available_minor)
                       VALUES (1,'2026-10-15',100000,40000);"""
            )
            connection.close()

            migrated = Database(path)
            try:
                migrated.initialize()
                snapshot = migrated.latest_credit_snapshot(1)
                self.assertEqual(snapshot["created_at"], "2026-10-15 00:00:00.000000")
                migrated.add_transaction(
                    occurred_on="2026-10-15", kind="expense", amount="7375", currency="JPY",
                    account_name="Mercari Card", category_name="娱乐", description="快照当日卡消费",
                )
                card = {row["name"]: row for row in credit_card_overview(migrated)}["Mercari Card"]
                self.assertEqual(card["available_minor"], 40000 - 7375)
            finally:
                migrated.close()

    def test_repayment_is_a_transfer_and_changes_only_the_card_ledger_balance(self) -> None:
        self.db.add_transaction(
            occurred_on="2026-10-16", kind="expense", amount="20000", currency="JPY",
            account_name="Mercari Card", category_name="娱乐", description="已确认卡消费",
        )
        expense_count_before = self.db.connection.execute(
            "SELECT COUNT(*) FROM transactions WHERE kind='expense'"
        ).fetchone()[0]

        transaction_id = record_credit_card_repayment(
            self.db,
            card_name="Mercari Card",
            source_account_name="瑞穗银行",
            amount="5000",
            occurred_on="2026-10-16",
            description="煤炉卡还款",
        )

        transaction = self.db.connection.execute(
            "SELECT kind,amount_minor,account_id,to_account_id,source FROM transactions WHERE id=?",
            (transaction_id,),
        ).fetchone()
        self.assertEqual(transaction["kind"], "transfer")
        self.assertEqual(transaction["amount_minor"], 5000)
        self.assertEqual(transaction["source"], "gui_card_repayment")
        self.assertEqual(self.db.account_balance_minor(self.db.account("Mercari Card")["id"]), 15000)
        cards = {row["name"]: row for row in credit_card_overview(self.db)}
        self.assertEqual(cards["Mercari Card"]["available_minor"], 40000 - 20000 + 5000)
        self.assertEqual(
            self.db.connection.execute("SELECT COUNT(*) FROM transactions WHERE kind='expense'").fetchone()[0],
            expense_count_before,
        )
        self.assertEqual(recent_credit_repayments(self.db)[0]["id"], transaction_id)

    def test_repayment_requires_a_monetary_asset_source_and_credit_destination(self) -> None:
        with self.assertRaisesRegex(LedgerError, "不是信用卡账户"):
            record_credit_card_repayment(
                self.db, card_name="瑞穗银行", source_account_name="PayPay钱包",
                amount="1", occurred_on="2026-10-16",
            )
        with self.assertRaisesRegex(LedgerError, "转出账户必须是"):
            record_credit_card_repayment(
                self.db, card_name="Mercari Card", source_account_name="Mercari积分",
                amount="1", occurred_on="2026-10-16",
            )


if __name__ == "__main__":
    unittest.main()
