from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bookkeeping.financial_statements import build_balance_sheet, build_profit_statement
from bookkeeping.storage import Database, seed_demo_data


class FinancialStatementsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp.name) / "ledger.sqlite3")
        self.database.initialize()
        seed_demo_data(self.database)

    def tearDown(self) -> None:
        self.database.close()
        self.temp.cleanup()

    def test_balance_sheet_groups_currencies_and_estimates_card_debt_from_limits(self) -> None:
        statement = build_balance_sheet(self.database, "2026-10-15")
        self.assertEqual(statement["assets"]["JPY"], 209600)
        self.assertEqual(statement["assets"]["CNY"], 0)
        self.assertEqual(statement["bank_deposits"]["JPY"], 200000)
        self.assertEqual(statement["known_liabilities"]["JPY"], 0)
        self.assertEqual(statement["estimated_liabilities"]["JPY"], 135000)
        self.assertEqual(statement["unknown_liability_count"], 0)
        points_row = next(row for row in statement["rows"] if row["name"] == "Rakuten积分")
        self.assertEqual(points_row["currency"], "PTS（JPY等值）")
        self.assertEqual(points_row["amount_text"], "300点（300 JPY等值）")
        mercari = next(row for row in statement["rows"] if row["name"] == "Mercari Card")
        self.assertEqual(mercari["amount_minor"], 60000)
        self.assertEqual(mercari["amount_text"], "60,000 JPY")
        self.assertEqual(mercari["status"], "额度差额·已核对")

    def test_profit_statement_summarizes_cycle_and_separates_memo_expense(self) -> None:
        self.database.add_transaction(
            occurred_on="2026-10-20", kind="income", amount=100, currency="JPY",
            account_name="瑞穗银行", category_name="退款/返现", description="未来入账测试",
        )
        statement = build_profit_statement(self.database, "2026-10-16")
        self.assertEqual((statement["start"], statement["end"]), ("2026-10-15", "2026-11-14"))
        self.assertEqual(statement["through"], "2026-10-16")
        jpy = statement["currencies"]["JPY"]
        self.assertEqual(jpy["income_minor"], 100000)
        self.assertEqual(jpy["expense_minor"], 700)
        self.assertEqual(jpy["posted_expense_minor"], 500)
        self.assertEqual(jpy["memo_expense_minor"], 200)
        self.assertEqual(jpy["net_minor"], 99300)
        self.assertEqual(jpy["categories"]["其他损耗"], 200)

    def test_balance_sheet_does_not_include_future_dated_transactions(self) -> None:
        self.database.add_transaction(
            occurred_on="2026-10-20", kind="income", amount=100, currency="JPY",
            account_name="瑞穗银行", category_name="退款/返现", description="未来入账测试",
        )
        bank = self.database.account("瑞穗银行")
        self.assertEqual(
            self.database.account_balance_as_of(bank["id"], "2026-10-16"), 200000
        )
        self.assertEqual(
            self.database.account_balance_as_of(bank["id"], "2026-10-20"), 200100
        )
        statement = build_balance_sheet(self.database, "2026-10-16")
        self.assertEqual(statement["bank_deposits"]["JPY"], 200000)

    def test_inferred_card_debt_is_not_reported_as_confirmed(self) -> None:
        self.database.add_account(
            name="推算信用卡", account_type="credit", currency="JPY",
            opening_balance=2000, opening_date="2026-10-15", completeness="inferred",
        )
        statement = build_balance_sheet(self.database, "2026-10-16")
        # The three seeded cards have usable limit snapshots; only this new
        # card lacks enough information to estimate its liability.
        self.assertEqual(statement["unknown_liability_count"], 1)
        card = next(row for row in statement["rows"] if row["name"] == "推算信用卡")
        self.assertEqual(card["amount_text"], "无法估算")


if __name__ == "__main__":
    unittest.main()
