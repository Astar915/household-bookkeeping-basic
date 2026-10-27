from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from bookkeeping.balance_reconciliation import count_amount, is_balance_count_request
from bookkeeping.credit_management import credit_card_overview
from bookkeeping.fx_rates import JpyRate
from bookkeeping.natural_language import NaturalLanguageSession
from bookkeeping.request_worker import merge_isolated_database
from bookkeeping.storage import Database


class NoModel:
    def complete(self, *_args, **_kwargs):
        raise AssertionError("This count is fully specified and should be handled locally")


class ConversationModel:
    def __init__(self):
        self.messages = []

    def complete(self, messages, **_kwargs):
        self.messages.append(messages)
        return json.dumps({"action": "reply", "reply": "好的，我们继续聊。"}, ensure_ascii=False)


class NaturalBalanceCountTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "ledger.sqlite3"
        self.db = Database(self.path)
        self.addCleanup(self.db.close)
        self.db.initialize()
        self.db.add_account(name="Rakuten Card", account_type="credit", currency="JPY",
                            opening_balance="0", opening_date="2026-01-01")
        self.db.add_credit_limit_snapshot("Rakuten Card", "2026-10-27", "10000", "1000")
        self.db.add_account(name="Rakuten Pay", account_type="wallet", currency="JPY",
                            opening_balance="1500", opening_date="2026-01-01")
        self.db.add_account(name="PayPay钱包", account_type="wallet", currency="JPY",
                            opening_balance="1000", opening_date="2026-01-01")
        self.db.add_account(name="人民币钱包", account_type="wallet", currency="CNY",
                            opening_balance="100.00", opening_date="2026-01-01")
        self.now = datetime(2026, 10, 27, 12, 0, tzinfo=timezone(timedelta(hours=9)))
        self.enterContext(patch("bookkeeping.natural_language._now_japan", return_value=self.now))
        self.session = NaturalLanguageSession(self.db, NoModel())

    def transactions(self):
        return self.db.connection.execute(
            "SELECT t.*,c.name AS category_name,a.name AS account_name FROM transactions t "
            "JOIN categories c ON c.id=t.category_id JOIN accounts a ON a.id=t.account_id ORDER BY t.id"
        ).fetchall()

    def credit_available(self):
        return next(row["available_minor"] for row in credit_card_overview(self.db, "2026-10-27")
                    if row["name"] == "Rakuten Card")

    def test_ordinary_chat_keeps_context_without_writing_transactions(self):
        client = ConversationModel()
        session = NaturalLanguageSession(self.db, client)
        session.handle("我今天去散步了")
        session.handle("我刚才说做了什么？")
        contents = [message["content"] for message in client.messages[-1]]
        self.assertIn("我今天去散步了", contents)
        self.assertIn("好的，我们继续聊。", contents)
        self.assertEqual(len(self.transactions()), 0)

    def test_polite_adjustment_of_card_balance(self):
        self.session.handle("能不能帮我把乐天卡可用额度调整到625？")
        self.assertEqual(self.credit_available(), 625)
        self.assertEqual(self.transactions()[0]["amount_minor"], 375)

    def test_chat_dates_do_not_change_later_transaction_date(self):
        class Model:
            def __init__(self):
                self.responses = [
                    {"action": "reply", "reply": "原来你昨天去了那里。"},
                    {"action": "expense", "date": "2026-10-26", "amount": "100",
                     "currency": "JPY", "account": "PayPay钱包", "category": "餐饮",
                     "description": "午饭"},
                ]

            def complete(self, _messages, **_kwargs):
                return json.dumps(self.responses.pop(0), ensure_ascii=False)

        session = NaturalLanguageSession(self.db, Model())
        session.handle("昨天我去散步了")
        session.handle("PayPay钱包午饭100")
        row, = self.transactions()
        self.assertEqual(row["occurred_on"], "2026-10-27")

    def test_explicit_credit_count_posts_only_the_difference(self):
        result = self.session.handle("乐天卡盘点余额仅剩625")
        self.assertIn("Rakuten Card", result)
        self.assertIn("余额盘亏", result)
        self.assertIn("375 JPY", result)
        row, = self.transactions()
        self.assertEqual((row["account_name"], row["kind"], row["category_name"], row["amount_minor"]),
                         ("Rakuten Card", "expense", "余额盘亏", 375))
        self.assertEqual(self.credit_available(), 625)
        self.assertIsNone(self.session.pending_state)
        self.assertEqual(self.db.connection.execute("SELECT count(*) FROM credit_limit_recovery_points").fetchone()[0], 1)

    def test_followup_retains_account_without_asking_again(self):
        question = self.session.handle("乐天卡盘点余额")
        self.assertIn("Rakuten Card", question)
        self.assertEqual(self.session.pending_state["account"], "Rakuten Card")
        # The desktop worker serializes these fields between processes.
        resumed = NaturalLanguageSession(self.db, NoModel())
        resumed.history = list(self.session.history)
        resumed.pending_state = dict(self.session.pending_state)
        result = resumed.handle("盘点后余额为625")
        self.assertIn("已完成", result)
        self.assertEqual(self.credit_available(), 625)
        self.assertEqual(len(self.transactions()), 1)

    def test_missing_account_retains_amount_across_turns(self):
        self.assertIn("哪个账户", self.session.handle("盘点余额仅剩625"))
        result = self.session.handle("乐天卡")
        self.assertIn("已完成", result)
        self.assertEqual(self.credit_available(), 625)

    def test_ambiguous_brand_does_not_turn_balance_into_wallet(self):
        question = self.session.handle("乐天盘点余额625")
        self.assertIn("Rakuten Card", question)
        self.assertIn("Rakuten Pay", question)
        self.assertEqual(self.session.pending_state["amount"], "625")
        self.assertEqual(len(self.transactions()), 0)
        self.session.handle("乐天卡")
        self.assertEqual(self.credit_available(), 625)
        self.assertEqual(self.transactions()[0]["account_name"], "Rakuten Card")

    def test_wallet_count_supports_surplus_shortage_and_zero(self):
        self.session.handle("PayPay钱包盘点余额剩625")
        row, = self.transactions()
        self.assertEqual((row["kind"], row["amount_minor"], row["category_name"]),
                         ("expense", 375, "余额盘亏"))
        wallet = self.db.account("PayPay钱包")
        self.assertEqual(self.db.account_balance_as_of(wallet["id"], "2026-10-27"), 625)
        self.session.handle("PayPay钱包盘点余额为900")
        self.assertEqual(self.transactions()[-1]["category_name"], "余额盘盈")
        self.session.handle("PayPay钱包盘点余额为0")
        self.assertEqual(self.db.account_balance_as_of(wallet["id"], "2026-10-27"), 0)

    def test_no_difference_is_idempotent(self):
        result = self.session.handle("乐天卡盘点余额仅剩1000")
        self.assertIn("没有差额", result)
        self.assertEqual(len(self.transactions()), 0)
        self.assertEqual(self.credit_available(), 1000)

    def test_card_without_snapshot_never_guesses_available_credit(self):
        self.db.add_account(name="Example Card", account_type="credit", currency="JPY",
                            opening_balance="0", opening_date="2026-01-01")
        result = self.session.handle("Example Card盘点余额仅剩625")
        self.assertIn("没有可用额度快照", result)
        self.assertEqual(len(self.transactions()), 0)
        self.assertIsNone(self.session.pending_state)

    def test_later_card_transaction_prevents_unsafe_backdated_reconciliation(self):
        self.db.add_transaction(occurred_on="2026-10-28", kind="expense", amount="20", currency="JPY",
                                account_name="Rakuten Card", category_name="餐饮", description="future")
        before = len(self.transactions())
        result = self.session.handle("乐天卡盘点余额仅剩625")
        self.assertIn("之后已有流水", result)
        self.assertEqual(len(self.transactions()), before)

    def test_invalid_currency_can_be_corrected_without_losing_account(self):
        result = self.session.handle("乐天卡盘点余额仅剩625人民币")
        self.assertIn("币种", result)
        self.assertEqual(len(self.transactions()), 0)
        self.assertEqual(self.session.pending_state["account"], "Rakuten Card")
        self.session.handle("625日元")
        self.assertEqual(self.credit_available(), 625)

    def test_cny_adjustment_keeps_original_currency_and_jpy_reference(self):
        rate = JpyRate(Decimal("20"), "2026-10-27", "test rate")
        with patch("bookkeeping.fx_rates.resolve_jpy_rate", return_value=rate):
            result = self.session.handle("人民币钱包盘点余额仅剩70.00人民币")
        self.assertIn("余额盘亏", result)
        row, = self.transactions()
        self.assertEqual((row["currency"], row["amount_minor"], row["jpy_equiv_minor"]),
                         ("CNY", 3000, 600))

    def test_differences_and_negative_values_are_not_guessed_as_final_count(self):
        self.assertEqual(count_amount("乐天卡盘点余额少了100"), (None, None))
        self.assertEqual(count_amount("乐天卡盘点余额-625"), (None, None))
        result = self.session.handle("乐天卡盘点余额少了100")
        self.assertIn("实际剩余多少", result)
        self.assertEqual(len(self.transactions()), 0)
        self.session.handle("取消这笔")
        self.assertIsNone(self.session.pending_state)

    def test_question_and_hypothetical_do_not_trigger_count(self):
        self.assertFalse(is_balance_count_request("余额怎么盘点？"))
        self.assertFalse(is_balance_count_request("如果乐天卡盘点余额625会怎样"))

    def test_worker_merge_preserves_reconciliation_and_credit_history(self):
        baseline = Path(self.temp.name) / "baseline.sqlite3"
        candidate = Path(self.temp.name) / "candidate.sqlite3"
        copy = Database(baseline)
        try:
            self.db.connection.backup(copy.connection)
        finally:
            copy.close()
        shutil.copyfile(baseline, candidate)
        worker = Database(candidate)
        try:
            worker_session = NaturalLanguageSession(worker, NoModel())
            worker_session.handle("乐天卡盘点余额仅剩625")
        finally:
            worker.close()
        inserted = merge_isolated_database(self.path, baseline, candidate)
        self.assertEqual(len(inserted), 1)
        self.assertEqual(self.credit_available(), 625)
        self.assertEqual(self.transactions()[0]["amount_minor"], 375)
        self.assertEqual(self.db.connection.execute("SELECT count(*) FROM credit_limit_snapshots").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
