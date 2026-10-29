from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bookkeeping.storage import Database, LedgerError, billing_cycle, seed_demo_data


class BookkeepingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = Database(self.root / "ledger.sqlite3")
        self.db.initialize()
        seed_demo_data(self.db)

    def tearDown(self) -> None:
        self.db.close()
        self.temp.cleanup()

    def account_id(self, name: str) -> int:
        return self.db.account(name)["id"]

    def test_billing_cycle_boundaries(self) -> None:
        self.assertEqual(tuple(d.isoformat() for d in billing_cycle("2026-10-14")), ("2026-09-15", "2026-10-14"))
        self.assertEqual(tuple(d.isoformat() for d in billing_cycle("2026-10-15")), ("2026-10-15", "2026-11-14"))
        self.assertEqual(tuple(d.isoformat() for d in billing_cycle("2027-01-14")), ("2026-12-15", "2027-01-14"))

    def test_custom_billing_cycle_start_day_and_short_months(self) -> None:
        self.assertEqual(
            tuple(d.isoformat() for d in billing_cycle("2026-10-09", start_day=10)),
            ("2026-09-10", "2026-10-09"),
        )
        self.assertEqual(
            tuple(d.isoformat() for d in billing_cycle("2026-02-27", start_day=31)),
            ("2026-01-31", "2026-02-27"),
        )
        self.assertEqual(
            tuple(d.isoformat() for d in billing_cycle("2026-02-28", start_day=31)),
            ("2026-02-28", "2026-03-30"),
        )

    def test_billing_cycle_setting_defaults_and_validates(self) -> None:
        self.assertEqual(self.db.get_billing_cycle_start_day(), 15)
        self.db.set_billing_cycle_start_day(10)
        self.assertEqual(self.db.get_billing_cycle_start_day(), 10)
        with self.assertRaises(LedgerError):
            self.db.set_billing_cycle_start_day(32)

    def test_seed_reproduces_known_asset_snapshots_without_double_counting(self) -> None:
        expected = {
            "瑞穗银行": 200000,
            "PayPay钱包": 2000,
            "Rakuten Pay": 1000,
            "Suica": 800,
            "PASMO": 5000,
            "PayPay券": 800,
        }
        for name, amount in expected.items():
            with self.subTest(name=name):
                self.assertEqual(self.db.account_balance_minor(self.account_id(name)), amount)
        rows = self.db.report_rows("2026-10-15", "2026-10-15", "JPY")
        expenses = sum(row["amount_minor"] for row in rows if row["kind"] == "expense")
        income = sum(row["amount_minor"] for row in rows if row["kind"] == "income")
        self.assertEqual(expenses, 700)
        self.assertEqual(income, 100000)
        self.assertEqual(sum(1 for row in rows if row["kind"] == "expense" and row["amount_minor"] == 700), 0)

    def test_points_are_stored_as_jpy_equivalents_and_legacy_pts_migrates_without_changing_balances(self) -> None:
        points = self.db.account("Rakuten积分")
        self.assertEqual(points["currency"], "JPY")
        initial_balance = self.db.account_balance_minor(points["id"])
        transaction_id = self.db.add_transaction(
            occurred_on="2026-10-16", kind="expense", amount=10, currency="JPY",
            account_name="Rakuten积分", category_name="娱乐", description="积分测试消费",
        )
        balance_before_migration = self.db.account_balance_minor(points["id"])
        with self.db.connection:
            self.db.connection.execute("UPDATE accounts SET currency='PTS' WHERE id=?", (points["id"],))
            self.db.connection.execute("UPDATE transactions SET currency='PTS' WHERE id=?", (transaction_id,))

        self.db.initialize()

        migrated = self.db.account("Rakuten积分")
        row = self.db.connection.execute(
            "SELECT currency,amount_minor FROM transactions WHERE id=?", (transaction_id,)
        ).fetchone()
        self.assertEqual(migrated["currency"], "JPY")
        self.assertEqual(row["currency"], "JPY")
        self.assertEqual(row["amount_minor"], 10)
        self.assertEqual(self.db.account_balance_minor(migrated["id"]), balance_before_migration)
        self.assertEqual(balance_before_migration, initial_balance - 10)
        self.assertTrue(list((self.root / "backups").glob("*-before-points-jpy-*.sqlite3")))
        self.assertEqual(self.db.validate()[0], [])

    def test_legacy_pts_input_is_normalized_for_points_accounts(self) -> None:
        transaction_id = self.db.add_transaction(
            occurred_on="2026-10-16", kind="income", amount=1, currency="PTS",
            account_name="Rakuten积分", category_name="其他收入", description="积分到期补录",
        )
        row = self.db.connection.execute(
            "SELECT currency,amount_minor FROM transactions WHERE id=?", (transaction_id,)
        ).fetchone()
        self.assertEqual((row["currency"], row["amount_minor"]), ("JPY", 1))

    def test_credit_payment_is_transfer_and_not_another_expense(self) -> None:
        self.db.add_transaction(
            occurred_on="2026-10-16", kind="expense", amount=2500, currency="JPY",
            account_name="Rakuten Card", category_name="日用品", description="卡消费",
        )
        self.db.add_transaction(
            occurred_on="2026-10-20", kind="transfer", amount=1000, currency="JPY",
            account_name="瑞穗银行", to_account_name="Rakuten Card", description="还款",
        )
        self.assertEqual(self.db.account_balance_minor(self.account_id("瑞穗银行")), 199000)
        self.assertEqual(self.db.account_balance_minor(self.account_id("Rakuten Card")), 1500)
        rows = self.db.report_rows("2026-10-15", "2026-11-14", "JPY")
        expense_total = sum(row["amount_minor"] for row in rows if row["kind"] == "expense")
        self.assertEqual(expense_total, 3200)
        self.assertEqual(sum(1 for row in rows if row["kind"] == "transfer"), 0)

    def test_cross_currency_transfer_keeps_ledgers_separate(self) -> None:
        self.db.add_account(
            name="人民币钱包", account_type="wallet", currency="CNY", opening_balance=0,
            opening_date="2026-10-15", completeness="partial", note="余额尚未核对",
        )
        self.db.add_transaction(
            occurred_on="2026-10-16", kind="transfer", amount=10000, currency="JPY",
            account_name="瑞穗银行", to_account_name="人民币钱包", to_amount="481.25",
            description="用户确认的换汇",
        )
        self.assertEqual(self.db.account_balance_minor(self.account_id("瑞穗银行")), 190000)
        self.assertEqual(self.db.account_balance_minor(self.account_id("人民币钱包")), 48125)

    def test_unallocated_other_loss_does_not_change_cash_balance(self) -> None:
        self.assertEqual(self.db.account_balance_minor(self.account_id("瑞穗银行")), 200000)
        row = self.db.connection.execute(
            "SELECT balance_effect,account_id,amount_minor FROM transactions WHERE description='Example memo-only expense'"
        ).fetchone()
        self.assertEqual(row["balance_effect"], "memo")
        self.assertIsNone(row["account_id"])
        self.assertEqual(row["amount_minor"], 200)

    def test_credit_limit_is_not_used_as_debt(self) -> None:
        card = self.db.account("Rakuten Card")
        self.assertEqual(self.db.account_balance_minor(card["id"]), 0)
        self.assertEqual(card["balance_completeness"], "partial")
        snapshot = self.db.latest_credit_snapshot(card["id"])
        self.assertEqual(snapshot["available_minor"], 50000)
        self.assertEqual(snapshot["limit_minor"], 100000)

    def test_validation_and_sqlite_backup(self) -> None:
        errors, warnings = self.db.validate()
        self.assertEqual(errors, [])
        self.assertTrue(any("Example memo-only expense" in warning for warning in warnings))
        destination = self.root / "backups" / "ledger-copy.sqlite3"
        self.db.backup(destination)
        backup_db = Database(destination)
        try:
            backup_db.initialize()
            self.assertEqual(backup_db.account_balance_minor(backup_db.account("瑞穗银行")["id"]), 200000)
        finally:
            backup_db.close()

    def test_cannot_seed_nonempty_database(self) -> None:
        with self.assertRaises(LedgerError):
            seed_demo_data(self.db)


if __name__ == "__main__":
    unittest.main()
