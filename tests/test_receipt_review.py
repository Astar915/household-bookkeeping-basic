from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bookkeeping.natural_language import ImageAttachment, NaturalLanguageSession, _receipt_amount_check
from bookkeeping.receipt_ocr import completed_receipt, grounded_fields, printed_date, printed_total
from bookkeeping.storage import Database, seed_demo_data
from tests.test_natural_language import ReceiptAwareFakeClient


class ReceiptEvidenceTests(unittest.TestCase):
    def document(self, *texts: str) -> dict:
        return {"lines": [{"text": text, "x": 0, "y": n * 30, "height": 20, "width": 200}
                          for n, text in enumerate(texts)]}

    def test_total_excludes_tax_and_subtotal(self) -> None:
        self.assertEqual(printed_total(self.document("小計 100", "税額合計 8", "合計 108")), "108")
        self.assertEqual(printed_total(self.document("Subtotal 20", "Total 21.50")), "21.50")

    def test_column_geometry_joins_payment_amount_without_inferring_account(self) -> None:
        document = self.document("ク レ ジ ッ ト")
        document["lines"].append({"text": "¥108", "x": 300, "y": 2, "height": 20, "width": 80})
        self.assertEqual(printed_total(document), "108")
        self.assertNotIn("account", grounded_fields({"items": [], "merchant": None}, document))

    def test_different_paid_amounts_and_unpaid_status_are_not_guessed(self) -> None:
        self.assertIsNone(printed_total(self.document("現金 50", "クレジット 100")))
        self.assertFalse(completed_receipt(self.document("receipt", "unpaid")))
        self.assertIsNone(printed_date(self.document("2026/10/18", "2026/10/19")))

    def test_printed_fields_override_invented_amount_date_and_merchant(self) -> None:
        document = self.document("新しい店", "2026年10月18日", "りんご", "合計 108", "領収書")
        fields = grounded_fields({"amount": "999", "date": "2000-01-01", "merchant": "Invented Store",
                                  "items": ["りんご", "unrelated food"]}, document)
        self.assertEqual(fields["amount"], "108")
        self.assertEqual(fields["date"], "2026-10-18")
        self.assertIsNone(fields["merchant"])
        self.assertEqual(fields["items"], ["りんご"])

    def test_japanese_product_survives_small_ocr_errors_without_accepting_unrelated_item(self) -> None:
        # Windows Japanese OCR misreads several characters in this receipt's
        # product line, but retains two distinctive fragments from the name.
        document = self.document(
            "2026 年 10 月 18 日 ( 日 ) 20 : 44",
            "A* 加 リ ー メ イ ト ア ロ ッ ク チ ー 心 ア シ 。 \\ 178",
            "8 % 税 額 \\ 14",
            "合 計 \\ 192",
            "ク レ ジ ッ ト \\ 192",
            "お 買 上 点 数 1 点",
            "ク レ ジ ッ ト 売 上 票",
            "お 客 様 控 え",
        )
        fields = grounded_fields({
            "amount": "999",
            "date": "2000-01-01",
            "merchant": "ドン・キホーテ 竹の塚店",
            "items": ["カロリーメイト ブロック チーズ味", "キッチン洗剤"],
        }, document)

        self.assertIsNotNone(fields)
        self.assertEqual(fields["amount"], "192")
        self.assertEqual(fields["date"], "2026-10-18")
        self.assertTrue(fields["completed"])
        self.assertEqual(fields["items"], ["カロリーメイト ブロック チーズ味"])

    def test_tax_arithmetic_respects_tax_inclusive_and_exclusive_subtotals(self) -> None:
        self.assertEqual(_receipt_amount_check({"subtotal": "100", "tax": "8", "discount": "0", "tax_included": False}, "108"), "matched")
        self.assertEqual(_receipt_amount_check({"subtotal": "108", "tax": "8", "discount": "0", "tax_included": True}, "108"), "matched")
        self.assertEqual(_receipt_amount_check({"subtotal": "100", "tax": "8", "discount": "0", "tax_included": False}, "999"), "mismatch")
        self.assertEqual(_receipt_amount_check({"subtotal": "100", "tax": "8"}, "108"), "unavailable")


class ImageDraftTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp.name) / "ledger.sqlite3")
        self.database.initialize()
        seed_demo_data(self.database)
        self.fields = {"merchant": "テスト店舗", "date": "2026-10-18", "amount": "100",
                       "currency": "JPY", "completed": True, "items": ["卵"]}
        self.fake = ReceiptAwareFakeClient([], self.fields)
        self.fake.model = "any-provider-model"
        self.session = NaturalLanguageSession(self.database, self.fake)
        self.image = ImageAttachment("arbitrary-receipt.jpg", "image/jpeg", b"synthetic")
        self.request = "请把附件中已完成的购买记录为一笔消费，付款账户是 Rakuten Card。"

    def tearDown(self) -> None:
        self.database.close()
        self.temp.cleanup()

    def count(self) -> int:
        return self.database.connection.execute("SELECT count(*) FROM transactions").fetchone()[0]

    def test_image_always_previews_before_writing_and_confirmation_needs_no_model(self) -> None:
        before = self.count()
        draft = self.session.handle(self.request, images=[self.image])
        self.assertIn("any-provider-model", draft)
        self.assertEqual(self.count(), before)
        self.assertEqual(self.session.pending_state["awaiting_slot"], "image_confirmation")
        self.assertIn("已记录消费", self.session.handle("确认记账"))
        self.assertEqual(self.count(), before + 1)
        self.assertEqual(self.fake.messages, [])
        self.assertIsNone(self.session.pending_state)

    def test_correction_requires_fresh_confirmation(self) -> None:
        before = self.count()
        self.session.handle(self.request, images=[self.image])
        draft = self.session.handle("金额改为200日元")
        self.assertIn("200 JPY", draft)
        self.assertEqual(self.count(), before)
        self.session.handle("确认记账")
        row = self.database.connection.execute("SELECT amount_minor FROM transactions ORDER BY id DESC LIMIT 1").fetchone()
        self.assertEqual(row[0], 200)

    def test_cancel_drops_draft_without_changing_ledger(self) -> None:
        before = self.count()
        self.session.handle(self.request, images=[self.image])
        self.session.handle("cancel")
        self.assertEqual(self.count(), before)
        self.assertIsNone(self.session.pending_state)

    def test_merchant_and_item_corrections_update_review_without_model_calls(self) -> None:
        before = self.count()
        self.session.handle(self.request, images=[self.image])
        self.assertIn("商家：任意新店", self.session.handle("商家改为任意新店"))
        self.assertIn("牛乳", self.session.handle("商品改为牛乳"))
        self.assertEqual(self.count(), before)
        self.assertEqual(self.fake.messages, [])
        self.assertIn("已记录消费", self.session.handle("确认记账"))
        item = self.database.connection.execute("SELECT item_name FROM food_purchase_items ORDER BY id DESC LIMIT 1").fetchone()
        self.assertEqual(item[0], "牛乳")
        description = self.database.connection.execute("SELECT description FROM transactions ORDER BY id DESC LIMIT 1").fetchone()[0]
        self.assertIn("任意新店", description)

    def test_new_image_cannot_replace_unconfirmed_draft(self) -> None:
        self.session.handle(self.request, images=[self.image])
        signature = self.session.pending_state["intent"]["_image_review_signature"]
        self.assertIn("已有待确认", self.session.handle(self.request, images=[self.image]))
        self.assertEqual(self.session.pending_state["intent"]["_image_review_signature"], signature)

    def test_pending_prompt_does_not_expose_approval_control_fields(self) -> None:
        self.session.handle(self.request, images=[self.image])
        prompt = self.session._pending_prompt_block()
        self.assertNotIn("_image_review_signature", prompt)
        self.assertNotIn("_image_confirmed_signature", prompt)

    def test_new_duplicate_after_preview_requires_another_review(self) -> None:
        self.session.handle(self.request, images=[self.image])
        self.database.add_transaction(occurred_on="2026-10-18", kind="expense", amount="100", currency="JPY",
                                      account_name="Rakuten Card", category_name="食材", description="another entry")
        before = self.count()
        response = self.session.handle("确认记账")
        self.assertIn("疑似重复", response)
        self.assertEqual(self.count(), before)
        self.assertIn("已记录消费", self.session.handle("确认记账"))

    def test_review_is_localized_and_confirms_in_japanese_and_english(self) -> None:
        for language, marker, command in [("ja-JP", "未記帳", "記帳を確定"), ("en-US", "not saved", "confirm entry")]:
            with self.subTest(language=language):
                session = NaturalLanguageSession(self.database, self.fake, response_language=language)
                draft = session.handle(self.request, images=[self.image])
                self.assertIn(marker, draft)
                self.assertIn("已记录消费", session.handle(command))


if __name__ == "__main__":
    unittest.main()
