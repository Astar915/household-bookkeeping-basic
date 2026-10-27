from __future__ import annotations

import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from bookkeeping.food_review import (
    PURCHASES_AS_EATEN_SETTING,
    build_food_review_answer,
    is_food_review_query,
    resolve_food_review_period,
)
from bookkeeping.natural_language import NaturalLanguageSession
from bookkeeping.storage import Database


class _UnexpectedClient:
    def complete(self, _messages):
        raise AssertionError("food history questions should use local records")


class FoodReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp_dir.name) / "ledger.sqlite3")
        self.database.initialize()

    def tearDown(self) -> None:
        self.database.close()
        self.temp_dir.cleanup()

    def test_food_review_query_detection_and_twenty_day_default(self) -> None:
        self.assertEqual(self.database.get_setting(PURCHASES_AS_EATEN_SETTING, "0"), "0")
        self.assertTrue(is_food_review_query("最近20天都吃了什么？"))
        self.assertTrue(is_food_review_query("这段期间饮食情况怎么样，缺什么营养？"))
        self.assertFalse(is_food_review_query("今天买了牛奶，花了200日元"))
        self.assertFalse(is_food_review_query("给我一些一般营养建议"))
        self.assertEqual(
            resolve_food_review_period("这段期间都吃了什么", date(2026, 10, 18)),
            (date(2026, 9, 29), date(2026, 10, 18)),
        )

    def test_relative_and_explicit_periods(self) -> None:
        today = date(2026, 10, 18)
        self.assertEqual(
            resolve_food_review_period("最近三天吃了什么", today),
            (date(2026, 10, 16), today),
        )
        self.assertEqual(
            resolve_food_review_period("2026年10月1日至2026年10月5日饮食记录", today),
            (date(2026, 10, 1), date(2026, 10, 5)),
        )

    def test_report_uses_consumption_only_and_recommends_unrecorded_groups(self) -> None:
        self.database.add_food_purchases("2026-10-18", [("牛奶", "1瓶")])
        self.database.add_food_consumptions(
            "2026-10-18",
            [("米饭", "1碗"), ("菠菜", "一份"), ("未识别的复合菜名", "")],
            meal="晚餐",
        )

        answer = build_food_review_answer(
            self.database, "最近20天都吃了什么？", date(2026, 10, 18)
        )

        self.assertIn("2026-09-29 至 2026-10-18（20天）", answer)
        self.assertIn("米饭（1碗）", answer)
        self.assertIn("菠菜（一份）", answer)
        self.assertNotIn("牛奶（1瓶）", answer)
        self.assertIn("主食粮食：1/20 天", answer)
        self.assertIn("蔬菜：1/20 天", answer)
        self.assertIn("蛋白质来源：0/20 天", answer)
        self.assertIn("不能证明你实际没有吃或身体缺乏", answer)
        self.assertIn("未纳入五类营养覆盖统计的名称：未识别的复合菜名", answer)

    def test_empty_food_log_is_explained_without_guessing(self) -> None:
        self.database.add_food_purchases("2026-10-17", [("牛乳", "1瓶")])
        answer = build_food_review_answer(
            self.database, "这段期间都吃了什么？", date(2026, 10, 18)
        )
        self.assertIn("没有找到已保存的食用记录", answer)
        self.assertIn("采购清单只代表买过", answer)
        self.assertIn("牛乳（肉蛋奶），1瓶", answer)
        self.assertIn("没有计入已吃食物或营养覆盖", answer)
        self.assertNotIn("奶类：", answer)
        self.assertNotIn("缺少维生素", answer)

    def test_purchase_as_eaten_preference_counts_food_but_not_other_goods(self) -> None:
        self.database.set_setting(PURCHASES_AS_EATEN_SETTING, "1")
        self.database.add_food_purchases(
            "2026-10-18",
            [("牛乳", "1瓶"), ("レジ袋（大）", "1枚"), ("季节限定商品", "")],
        )
        self.database.add_food_consumptions("2026-10-18", [("牛乳", "1瓶")])

        answer = build_food_review_answer(
            self.database, "我最近都吃了什么食材", date(2026, 10, 18)
        )

        # Milk is already logged; unknown products and non-food goods must
        # not be counted as additional food intake.
        self.assertIn("食用日志 1 条；按设置把 0 条已分类食品采购计作已吃", answer)
        self.assertIn("牛乳（1瓶）", answer)
        self.assertNotIn("季节限定商品（按采购计入已吃·待识别）", answer)
        self.assertNotIn("レジ袋", answer)
        self.assertIn("奶类：1/20 天", answer)
        self.assertIn("“其他商品”和“待识别”均不计入", answer)

    def test_natural_language_session_answers_without_calling_model_or_writing_ledger(self) -> None:
        self.database.add_food_consumptions("2026-10-18", [("苹果", "1个")])
        session = NaturalLanguageSession(self.database, _UnexpectedClient())
        fixed_now = datetime(2026, 10, 18, 12, 0, tzinfo=timezone(timedelta(hours=9)))
        with patch("bookkeeping.natural_language._now_japan", return_value=fixed_now):
            answer = session.handle("这段时间我都吃了什么，有什么食材建议？")

        self.assertIn("苹果（1个）", answer)
        self.assertIn("水果", answer)
        self.assertEqual(
            self.database.connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0],
            0,
        )
        self.assertEqual(
            self.database.connection.execute(
                "SELECT COUNT(*) FROM food_consumption_records"
            ).fetchone()[0],
            1,
        )


if __name__ == "__main__":
    unittest.main()
