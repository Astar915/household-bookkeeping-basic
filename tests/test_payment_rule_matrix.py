from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from bookkeeping.natural_language import NaturalLanguageSession
from bookkeeping.payment_preferences import PaymentPromptStore
from bookkeeping.storage import Database, seed_demo_data


PAYMENT_PROFILES = [
    {
        "payment_method": "瑞穗银行",
        "purpose": "所有信用卡还款",
        "currency": "JPY",
        "account_order": ["瑞穗银行"],
    },
    {
        "payment_method": "Rakuten Pay",
        "purpose": "水费，电费",
        "currency": "JPY",
        "account_order": ["Rakuten积分", "Rakuten Pay", "Rakuten Card"],
    },
    {
        "payment_method": "Rakuten Card",
        "purpose": "默认所有除外食之外的消费均由此账户扣款",
        "currency": "JPY",
        "account_order": ["Rakuten Card"],
    },
    {
        "payment_method": "PayPay钱包",
        "purpose": "默认所有外食以及煤气费由此账户扣款",
        "currency": "JPY",
        "account_order": ["PayPay券", "PayPay钱包", "PayPay Card"],
    },
    {
        "payment_method": "Mercari Card",
        "purpose": "煤炉上的交易均由此账户付款",
        "currency": "JPY",
        "account_order": ["Mercari积分", "Mercari Card"],
    },
    {
        "payment_method": "工商储蓄卡",
        "purpose": "默认所有人民币交易由本卡付款",
        "currency": "CNY",
        "account_order": ["工商储蓄卡"],
    },
    {
        "payment_method": "PASMO",
        "purpose": "交通出行默认使用此卡",
        "currency": "JPY",
        "account_order": ["PASMO"],
    },
]


class FakeClient:
    def __init__(self, intent: dict[str, object]) -> None:
        self.intent = intent

    def complete(self, _messages: list[dict[str, object]], **_options: object) -> str:
        return json.dumps(self.intent, ensure_ascii=False)


def intent(
    *,
    action: str = "expense",
    amount: str = "100",
    currency: str = "JPY",
    category: str | None = "日用品",
    description: str = "测试交易",
    account: str | None = None,
    to_account: str | None = None,
    payment_profile_index: int | None = None,
    question: str | None = None,
) -> dict[str, object]:
    return {
        "action": action,
        "date": "2026-10-21",
        "amount": amount,
        "currency": currency,
        "account": account,
        "to_account": to_account,
        "to_amount": None,
        "category": category,
        "description": description,
        "memo_only": False,
        "question": question,
        "reply": None,
        "payment_profile_index": payment_profile_index,
    }


class PaymentRuleMatrixTests(unittest.TestCase):
    def _run_case(self, message: str, parsed_intent: dict[str, object]) -> tuple[str, list[tuple[str, str, int]]]:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            database = Database(root / "ledger.sqlite3")
            try:
                database.initialize()
                seed_demo_data(database)
                database.add_account(
                    name="工商储蓄卡",
                    account_type="bank",
                    currency="CNY",
                    opening_balance="5000",
                    opening_date="2026-10-15",
                )
                # Exercise the same persisted-config -> backend-session path as
                # the GUI: save rules, reload them, then start an isolated session.
                store = PaymentPromptStore(root / "payment_prompts.json")
                store.save_profiles(PAYMENT_PROFILES)
                loaded_profiles = store.all_profiles()
                session = NaturalLanguageSession(
                    database,
                    FakeClient(parsed_intent),  # type: ignore[arg-type]
                    payment_hints=loaded_profiles,
                )
                answer = session.handle(message)
                rows = database.connection.execute(
                    "SELECT t.kind,a.name,t.amount_minor FROM transactions t "
                    "JOIN accounts a ON a.id=t.account_id "
                    "WHERE t.source='natural_language_api' ORDER BY t.id"
                ).fetchall()
                return answer, [(str(row["kind"]), str(row["name"]), int(row["amount_minor"])) for row in rows]
            finally:
                database.close()

    def test_twenty_payment_rule_scenarios_use_only_isolated_ledgers(self) -> None:
        cases = [
            ("01 水费走 Rakuten Pay 三段顺序", "今天交水费1000日元", intent(amount="1000", category="通信与账单", description="水费", payment_profile_index=2), [("expense", "Rakuten积分", 300), ("expense", "Rakuten Pay", 700)]),
            ("02 电费走 Rakuten Pay 三段顺序", "今天交电费500日元", intent(amount="500", category="通信与账单", description="电费", payment_profile_index=2), [("expense", "Rakuten积分", 300), ("expense", "Rakuten Pay", 200)]),
            ("03 午饭先用剩余券余额再拆到钱包", "今天午饭800日元", intent(amount="800", category="餐饮", description="午饭", payment_profile_index=4), [("expense", "PayPay券", 800)]),
            ("04 晚饭按剩余券余额拆到钱包", "今天晚饭1500日元", intent(amount="1500", category="餐饮", description="晚饭", payment_profile_index=4), [("expense", "PayPay券", 800), ("expense", "PayPay钱包", 700)]),
            ("05 煤气费走 PayPay 场景并按余额拆分", "今天交煤气费900日元", intent(amount="900", category="通信与账单", description="煤气费", payment_profile_index=4), [("expense", "PayPay券", 800), ("expense", "PayPay钱包", 100)]),
            ("06 食材命中非外食通用规则", "今天超市买牛奶600日元", intent(amount="600", category="食材", description="牛奶", payment_profile_index=3), [("expense", "Rakuten Card", 600)]),
            ("07 日用品命中非外食通用规则", "今天买洗发水800日元", intent(amount="800", category="日用品", description="洗发水", payment_profile_index=3), [("expense", "Rakuten Card", 800)]),
            ("08 新干线走 PASMO", "今天新干线车票3000日元", intent(amount="3000", category="交通", description="新干线车票", payment_profile_index=7), [("expense", "PASMO", 3000)]),
            ("09 地铁费用走 PASMO", "今天地铁费用400日元", intent(amount="400", category="交通", description="地铁费用", payment_profile_index=7), [("expense", "PASMO", 400)]),
            ("10 Mercari 商品按积分再信用卡", "今天在Mercari买衣服1200日元", intent(amount="1200", category="日用品", description="Mercari衣服", payment_profile_index=5), [("expense", "Mercari积分", 600), ("expense", "Mercari Card", 600)]),
            ("11 Mercari 小额交易先用积分", "今天Mercari买收纳盒350日元", intent(amount="350", category="日用品", description="Mercari收纳盒", payment_profile_index=5), [("expense", "Mercari积分", 350)]),
            ("12 人民币食材走工商卡", "今天买菜100元人民币", intent(amount="100", currency="CNY", category="食材", description="买菜", payment_profile_index=6), [("expense", "工商储蓄卡", 10000)]),
            ("13 人民币餐饮仍走工商卡", "今天午餐80元人民币", intent(amount="80", currency="CNY", category="餐饮", description="午餐", payment_profile_index=6), [("expense", "工商储蓄卡", 8000)]),
            ("14 JPY 交易拒绝 CNY 规则并回落到 Rakuten Card", "今天买文具700日元", intent(amount="700", currency="JPY", category="日用品", description="文具", payment_profile_index=6), [("expense", "Rakuten Card", 700)]),
            ("15 明确交通场景纠正误选的通用卡", "今天坐地铁1000日元", intent(amount="1000", category="交通", description="地铁", payment_profile_index=3), [("expense", "PASMO", 1000)]),
            ("16 午饭排除 Rakuten Card 并命中 PayPay", "今天午饭450日元", intent(amount="450", category="餐饮", description="午饭", payment_profile_index=3), [("expense", "PayPay券", 450)]),
            ("17 本次明确账户优先于通用规则", "今天买药300日元，使用瑞穗银行", intent(amount="300", category="日用品", description="药品", account="瑞穗银行", payment_profile_index=3), [("expense", "瑞穗银行", 300)]),
            ("18 用户说不清支付账户时不猜测", "今天午饭500日元，但我不确定用哪个账户", intent(amount="500", category="餐饮", description="午饭", payment_profile_index=4, question="请确认实际付款账户。"), []),
            ("19 信用卡还款作为转账，不套消费顺序", "今天从瑞穗银行还1000日元到Rakuten Card", intent(action="transfer", amount="1000", category=None, description="信用卡还款", account="瑞穗银行", to_account="Rakuten Card"), [("transfer", "瑞穗银行", 1000)]),
            ("20 工资收入不应用消费支付规则", "今天工资到账10000日元到瑞穗银行", intent(action="income", amount="10000", category="工资", description="工资", account="瑞穗银行"), [("income", "瑞穗银行", 10000)]),
        ]

        self.assertEqual(len(cases), 20)
        for label, message, parsed_intent, expected in cases:
            with self.subTest(case=label):
                answer, actual = self._run_case(message, parsed_intent)
                self.assertEqual(actual, expected, f"{label}: {answer}")

    def test_seven_bare_lunch_amounts_follow_dining_rule_sequentially(self) -> None:
        amounts = ["200", "250", "300", "400", "500", "600", "1000"]

        class SequenceFakeClient:
            def __init__(self) -> None:
                self.responses = [
                    # Deliberately return an incomplete account question and a
                    # wrong category: local scene matching should resolve both.
                    intent(
                        amount=amount,
                        category="其他",
                        description="午饭",
                        question="请问这笔消费使用哪个账户？",
                    )
                    for amount in amounts
                ]

            def complete(self, _messages: list[dict[str, object]], **_options: object) -> str:
                return json.dumps(self.responses.pop(0), ensure_ascii=False)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            database = Database(root / "ledger.sqlite3")
            try:
                database.initialize()
                seed_demo_data(database)
                store = PaymentPromptStore(root / "payment_prompts.json")
                store.save_profiles(PAYMENT_PROFILES)
                session = NaturalLanguageSession(
                    database,
                    SequenceFakeClient(),  # type: ignore[arg-type]
                    payment_hints=store.all_profiles(),
                )

                answers = [session.handle(f"今天午饭{amount}日元") for amount in amounts]
                self.assertTrue(all("已记录消费" in answer for answer in answers), answers)
                rows = database.connection.execute(
                    "SELECT a.name,c.name AS category,t.amount_minor "
                    "FROM transactions t JOIN accounts a ON a.id=t.account_id "
                    "JOIN categories c ON c.id=t.category_id "
                    "WHERE t.source='natural_language_api' ORDER BY t.id"
                ).fetchall()
                actual = [
                    (str(row["name"]), str(row["category"]), int(row["amount_minor"]))
                    for row in rows
                ]
                self.assertEqual(
                    actual,
                    [
                        ("PayPay券", "餐饮", 200),
                        ("PayPay券", "餐饮", 250),
                        ("PayPay券", "餐饮", 300),
                        ("PayPay券", "餐饮", 50),
                        ("PayPay钱包", "餐饮", 350),
                        ("PayPay钱包", "餐饮", 500),
                        ("PayPay钱包", "餐饮", 600),
                        ("PayPay钱包", "餐饮", 550),
                        ("PayPay Card", "餐饮", 450),
                    ],
                )
            finally:
                database.close()


if __name__ == "__main__":
    unittest.main()
