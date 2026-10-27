from __future__ import annotations

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from bookkeeping.cash_management import (
    cash_balances,
    managed_balances,
    reconcile_account_balances,
    reconcile_cash_balance,
    reconcile_cash_balances,
    sort_managed_balances,
)
from bookkeeping.storage import Database, LedgerError, seed_demo_data
from bookkeeping.fx_rates import ECB_SOURCE, JpyRate


class CashManagementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp.name) / "ledger.sqlite3")
        self.db.initialize()
        seed_demo_data(self.db)

    def tearDown(self) -> None:
        self.db.close()
        self.temp.cleanup()

    def test_cash_table_is_uninitialized_until_first_count(self) -> None:
        rows = cash_balances(self.db)
        self.assertEqual([row["currency"] for row in rows], ["JPY", "CNY"])
        self.assertTrue(all(not row["initialized"] for row in rows))
        self.assertTrue(all(row["balance_minor"] is None for row in rows))

    def test_management_table_includes_existing_accounts_and_points_but_not_credit_cards(self) -> None:
        rows = managed_balances(self.db)
        by_name = {row["account_name"]: row for row in rows}

        self.assertEqual(by_name["瑞穗银行"]["balance_minor"], 200000)
        self.assertEqual(by_name["PayPay钱包"]["balance_minor"], 2000)
        self.assertEqual(by_name["PayPay券"]["balance_minor"], 800)
        self.assertEqual(by_name["Mercari积分"]["currency"], "JPY")
        self.assertEqual(by_name["Mercari积分"]["display_currency"], "PTS（JPY等值）")
        self.assertEqual(by_name["Mercari积分"]["balance_minor"], 600)
        self.assertEqual(by_name["d积分"]["balance_minor"], 1000)
        self.assertNotIn("Rakuten Card", by_name)
        self.assertNotIn("PayPay Card", by_name)
        self.assertNotIn("Mercari Card", by_name)

    def test_management_table_can_preserve_default_order_or_group_by_currency(self) -> None:
        rows = managed_balances(self.db)

        self.assertEqual(sort_managed_balances(rows), rows)
        currency_sorted = sort_managed_balances(rows, "currency")
        currencies = [row["currency"] for row in currency_sorted]
        self.assertEqual(currencies, sorted(currencies))
        self.assertEqual(set(currencies), {"CNY", "JPY"})

    def test_points_adjustment_posts_separate_points_category(self) -> None:
        result = reconcile_account_balances(self.db, {"d积分": "982"}, "2026-10-16")[0]

        row = self.db.connection.execute(
            "SELECT t.kind,t.amount_minor,t.currency,t.source,c.name AS category "
            "FROM transactions t JOIN categories c ON c.id=t.category_id WHERE t.id=?",
            (result["transaction_id"],),
        ).fetchone()
        self.assertEqual(result["difference_minor"], -18)
        self.assertEqual(result["balance_minor"], 982)
        self.assertEqual((row["kind"], row["amount_minor"], row["currency"], row["source"], row["category"]),
                         ("expense", 18, "JPY", "balance_reconciliation", "积分盘亏"))

    def test_wallet_adjustment_posts_balance_surplus_category(self) -> None:
        result = reconcile_account_balances(self.db, {"PayPay钱包": "2074"}, "2026-10-16")[0]

        row = self.db.connection.execute(
            "SELECT t.kind,t.amount_minor,t.currency,c.name AS category "
            "FROM transactions t JOIN categories c ON c.id=t.category_id WHERE t.id=?",
            (result["transaction_id"],),
        ).fetchone()
        self.assertEqual(result["difference_minor"], 74)
        self.assertEqual((row["kind"], row["amount_minor"], row["currency"], row["category"]),
                         ("income", 74, "JPY", "余额盘盈"))

    def test_first_count_sets_opening_balance_without_fabricating_income(self) -> None:
        before = self.db.connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]

        result = reconcile_cash_balance(self.db, "JPY", "12000", "2026-10-15")

        self.assertTrue(result["opening_balance"])
        self.assertIsNone(result["transaction_id"])
        self.assertEqual(result["balance_minor"], 12000)
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0], before)
        self.assertEqual(cash_balances(self.db)[0]["balance_minor"], 12000)

    def test_positive_difference_is_posted_as_cash_surplus_income(self) -> None:
        reconcile_cash_balance(self.db, "JPY", "12000", "2026-10-15")

        result = reconcile_cash_balance(self.db, "JPY", "12500", "2026-10-16")

        row = self.db.connection.execute(
            "SELECT t.kind,t.amount_minor,t.currency,t.source,c.name AS category "
            "FROM transactions t JOIN categories c ON c.id=t.category_id "
            "WHERE t.id=?",
            (result["transaction_id"],),
        ).fetchone()
        self.assertEqual(result["difference_minor"], 500)
        self.assertEqual(result["balance_minor"], 12500)
        self.assertEqual((row["kind"], row["amount_minor"], row["currency"], row["source"], row["category"]),
                         ("income", 500, "JPY", "cash_reconciliation", "现金盘盈"))

    def test_negative_difference_is_posted_as_cash_shortage_expense(self) -> None:
        reconcile_cash_balance(self.db, "JPY", "12000", "2026-10-15")

        result = reconcile_cash_balance(self.db, "JPY", "11700", "2026-10-16")

        row = self.db.connection.execute(
            "SELECT t.kind,t.amount_minor,t.currency,t.source,c.name AS category "
            "FROM transactions t JOIN categories c ON c.id=t.category_id "
            "WHERE t.id=?",
            (result["transaction_id"],),
        ).fetchone()
        self.assertEqual(result["difference_minor"], -300)
        self.assertEqual(result["balance_minor"], 11700)
        self.assertEqual((row["kind"], row["amount_minor"], row["currency"], row["source"], row["category"]),
                         ("expense", 300, "JPY", "cash_reconciliation", "现金盘亏"))

    def test_no_difference_does_not_create_a_duplicate_entry(self) -> None:
        reconcile_cash_balance(self.db, "JPY", "12000", "2026-10-15")
        before = self.db.connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]

        result = reconcile_cash_balance(self.db, "JPY", "12000", "2026-10-16")

        self.assertEqual(result["difference_minor"], 0)
        self.assertIsNone(result["transaction_id"])
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0], before)

    def test_cny_cash_is_kept_separate_and_allows_two_decimal_places(self) -> None:
        rate = JpyRate(Decimal("23.6"), "2026-10-16", ECB_SOURCE)
        with patch("bookkeeping.fx_rates.resolve_jpy_rate", return_value=rate):
            reconcile_cash_balance(self.db, "CNY", "123.45", "2026-10-15")
            result = reconcile_cash_balance(self.db, "CNY", "100.00", "2026-10-16")

        self.assertEqual(result["difference_minor"], -2345)
        self.assertEqual(result["balance_minor"], 10000)
        self.assertEqual(cash_balances(self.db)[0]["balance_minor"], None)
        self.assertEqual(cash_balances(self.db)[1]["balance_minor"], 10000)

    def test_jpy_cash_rejects_fractional_yen(self) -> None:
        with self.assertRaisesRegex(LedgerError, "最多允许0位小数"):
            reconcile_cash_balance(self.db, "JPY", "1.5", "2026-10-15")

    def test_batch_adjustment_validation_failure_leaves_every_currency_unchanged(self) -> None:
        reconcile_cash_balance(self.db, "JPY", "500", "2026-10-15")
        before_transactions = self.db.connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]

        with self.assertRaises(LedgerError):
            reconcile_cash_balances(
                self.db,
                {"JPY": "600", "CNY": "1.234"},
                "2026-10-16",
            )

        rows = cash_balances(self.db)
        self.assertEqual(rows[0]["balance_minor"], 500)
        self.assertFalse(rows[1]["initialized"])
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0], before_transactions)


if __name__ == "__main__":
    unittest.main()
