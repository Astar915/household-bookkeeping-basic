import json
import tempfile
import unittest
from pathlib import Path

from bookkeeping.natural_language import NaturalLanguageSession
from bookkeeping.payment_preferences import PaymentPromptStore
from bookkeeping.storage import Database, seed_demo_data


class ParsedWaterBill:
    def complete(self, _messages, **_options):
        return json.dumps({
            "action": "expense", "amount": "4241", "currency": "JPY",
            "category": "通信与账单", "description": "水费",
            "account": None, "payment_profile_index": 1,
        })


class PaymentOrderBalancesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = Database(self.root / "ledger.sqlite3")
        self.db.initialize()
        seed_demo_data(self.db)
        for name, kind, balance in (
            ("Example积分", "points", "150"),
            ("Example Point", "points", "3150"),
            ("Example Pay", "wallet", "1709"),
        ):
            self.db.add_account(name=name, account_type=kind, currency="JPY",
                                opening_balance=balance, opening_date="2026-10-15")
        self.store = PaymentPromptStore(self.root / "payments.json")

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def session(self, point_name):
        self.store.save_profiles([{
            "payment_method": "Example Pay", "currency": "JPY", "purpose": "水费，电费",
            "account_order": [point_name, "Example Pay"],
        }])
        return NaturalLanguageSession(self.db, ParsedWaterBill(), payment_hints=self.store.all_profiles())

    def posted(self):
        return [tuple(row) for row in self.db.connection.execute(
            "SELECT a.name,t.amount_minor FROM transactions t JOIN accounts a ON a.id=t.account_id "
            "WHERE t.source='natural_language_api' ORDER BY t.id")]

    def test_insufficient_selected_account_does_not_use_similar_unselected_account(self):
        result = self.session("Example积分").handle("水费4241")
        for value in ("Example积分", "150", "Example Pay", "1,709", "2,382"):
            self.assertIn(value, result)
        self.assertNotIn("Example Point", result)
        self.assertEqual(self.posted(), [])

    def test_reloaded_corrected_order_splits_full_amount_without_credit_fallback(self):
        result = self.session("Example Point").handle("水费4241")
        self.assertIn("已记录消费", result)
        self.assertEqual(self.posted(), [("Example Point", 3150), ("Example Pay", 1091)])

    def test_diagnostics_distinguish_missing_account_and_currency_mismatch(self):
        session = self.session("Example积分")
        self.db.add_account(name="Foreign", account_type="bank", currency="CNY",
                            opening_balance="500", opening_date="2026-10-15")
        profile = {"account_order": ["Missing", "Foreign", "Example Pay"]}
        result = session._payment_order_shortage(profile, "4241", "JPY")
        self.assertIn("Missing：账户未登记", result)
        self.assertIn("Foreign：币种不符", result)
        self.assertIn("2,532", result)
        self.assertEqual(self.posted(), [])
