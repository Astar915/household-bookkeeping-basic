from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bookkeeping.food_categories import classify_food_name
from bookkeeping.storage import Database


class FoodCategoryTests(unittest.TestCase):
    def test_multilingual_product_name_rules(self) -> None:
        cases = {
            "牛乳": "meat_eggs_dairy",
            "卵": "meat_eggs_dairy",
            "雪印北海道バター": "meat_eggs_dairy",
            "キャベツ": "vegetables_fruits",
            "苹果": "vegetables_fruits",
            "食パン": "grains_staples",
            "燕麦": "grains_staples",
            "スコーン": "snacks",
            "さきいか": "snacks",
            "カロリーメイト ブロック チーズ味": "snacks",
            "SOYJOY ブルーベリー": "snacks",
            "inゼリー エネルギー": "beverages",
            "骨取り塩さば": "seafood",
            "野菜生活マンゴー": "beverages",
            "コカ・コーラプラス": "beverages",
            "三島炊き込みわかめ": "seasonings_dry_goods",
            "豆腐": "beans_tofu",
            "冷凍餃子": "prepared_frozen",
            "レジ袋（大）": "other",
            "恵ブルベリーいちご": "unclassified",
            "ご飯ガスム": "unclassified",
            "unrecognized seasonal item": "unclassified",
        }
        for name, expected in cases.items():
            with self.subTest(name=name):
                self.assertEqual(classify_food_name(name), expected)

    def test_new_purchase_items_are_classified_and_user_can_override(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "ledger.sqlite3")
            try:
                database.initialize()
                ids = database.add_food_purchases(
                    "2026-10-17", [("牛乳", "1瓶"), ("レジ袋（大）", "1枚"), ("季节限定商品", "")]
                )
                rows = database.connection.execute(
                    "SELECT id,classification,food_group FROM food_purchase_items ORDER BY id"
                ).fetchall()
                self.assertEqual(
                    [(row["classification"], row["food_group"]) for row in rows],
                    [
                        ("ingredient", "meat_eggs_dairy"),
                        ("other", "other"),
                        ("ingredient", "unclassified"),
                    ],
                )

                database.set_food_purchase_group(ids[0], "snacks")
                row = database.connection.execute(
                    "SELECT classification,food_group FROM food_purchase_items WHERE id=?",
                    (ids[0],),
                ).fetchone()
                self.assertEqual((row["classification"], row["food_group"]), ("ingredient", "snacks"))
                self.assertEqual(database.auto_classify_food_purchase(ids[0]), "meat_eggs_dairy")
                database.set_food_purchase_group(ids[0], "unclassified")
                database.initialize()
                row = database.connection.execute(
                    "SELECT classification,food_group FROM food_purchase_items WHERE id=?",
                    (ids[0],),
                ).fetchone()
                self.assertEqual(
                    (row["classification"], row["food_group"]),
                    ("unclassified", "unclassified"),
                )
            finally:
                database.close()

    def test_existing_unclassified_rows_are_backfilled_during_schema_upgrade(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.sqlite3"
            database = Database(path)
            database.initialize()
            database.connection.execute(
                """INSERT INTO food_purchase_items
                   (transaction_id,purchase_date,item_name,quantity_text,classification,food_group,
                    source,line_number,created_at)
                   VALUES (NULL,'2026-10-17','牛乳','1本','unclassified','unclassified',
                           'imported',1,'2026-10-17 00:00:00')"""
            )
            database.connection.commit()
            database.connection.execute("ALTER TABLE food_purchase_items DROP COLUMN food_group")
            database.close()

            migrated = Database(path)
            try:
                migrated.initialize()
                row = migrated.connection.execute(
                    "SELECT classification,food_group FROM food_purchase_items"
                ).fetchone()
                self.assertEqual((row["classification"], row["food_group"]), ("ingredient", "meat_eggs_dairy"))
                backups = list((path.parent / "backups").glob("*-before-food-tracking-*.sqlite3"))
                self.assertTrue(backups, "schema migration must keep a recoverable database copy")
            finally:
                migrated.close()


if __name__ == "__main__":
    unittest.main()
