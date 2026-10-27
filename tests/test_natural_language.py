from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError
from unittest.mock import patch

from bookkeeping.natural_language import (
    ImageAttachment,
    NaturalLanguageError,
    NaturalLanguageSession,
    OpenAICompatibleClient,
    _image_system_prompt,
    _local_receipt_ocr_images,
    _local_ollama_image_bytes,
    _explicit_transaction_segment_count,
    _parse_intent,
    _system_prompt,
    load_image_attachment,
)
from bookkeeping.storage import Database, LedgerError, seed_demo_data


class FakeClient:
    def __init__(self, responses: list[dict[str, object]]) -> None:
        self.responses = list(responses)
        self.messages: list[list[dict[str, object]]] = []
        self.complete_options: list[dict[str, object]] = []

    def complete(self, messages: list[dict[str, object]], **options: object) -> str:
        self.messages.append(messages)
        self.complete_options.append(options)
        return json.dumps(self.responses.pop(0), ensure_ascii=False)


class ReceiptAwareFakeClient(FakeClient):
    def __init__(self, responses: list[dict[str, object]], fields: dict[str, object]) -> None:
        super().__init__(responses)
        self.fields = fields

    def extract_local_receipt_fields(self, attachment: ImageAttachment) -> dict[str, object]:
        return self.fields


def expense_intent(*, account: str | None, question: str | None = None) -> dict[str, object]:
    return {
        "action": "expense",
        "date": "2026-10-15",
        "amount": "1",
        "currency": "JPY",
        "account": account,
        "to_account": None,
        "to_amount": None,
        "category": "餐饮",
        "description": "糖",
        "memo_only": False,
        "question": question,
        "reply": None,
        "payment_profile_index": None,
    }


class NaturalLanguageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = Database(self.root / "ledger.sqlite3")
        self.db.initialize()
        seed_demo_data(self.db)

    def tearDown(self) -> None:
        self.db.close()
        self.temp.cleanup()

    def confirm_image_draft(self, session: NaturalLanguageSession, answer: str) -> str:
        self.assertIn("图片记账草稿（尚未入账）", answer)
        self.assertEqual(session.pending_state["awaiting_slot"], "image_confirmation")
        calls_before = len(session.client.messages)
        result = session.handle("确认记账")
        self.assertEqual(len(session.client.messages), calls_before)
        return result

    def test_nvidia_client_sends_non_streaming_chat_completion(self) -> None:
        captured: dict[str, object] = {}

        class Response:
            def __enter__(self) -> Response:
                return self

            def __exit__(self, *_: object) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps({"choices": [{"message": {"content": "{}"}}]}).encode()

        def opener(request: object, timeout: float) -> Response:
            captured["url"] = request.full_url  # type: ignore[attr-defined]
            captured["authorization"] = request.get_header("Authorization")  # type: ignore[attr-defined]
            captured["payload"] = json.loads(request.data.decode("utf-8"))  # type: ignore[attr-defined]
            captured["timeout"] = timeout
            return Response()

        test_url = "https://api.example.invalid/v1/chat/completions"
        client = OpenAICompatibleClient(
            "test-only-key", api_url=test_url, model="test-model", opener=opener
        )
        output = client.complete([{"role": "user", "content": "买糖1日元"}])
        self.assertEqual(output, "{}")
        self.assertEqual(captured["url"], test_url)
        self.assertEqual(captured["authorization"], "Bearer test-only-key")
        payload = captured["payload"]
        self.assertEqual(payload["model"], "test-model")  # type: ignore[index]
        self.assertFalse(payload["stream"])  # type: ignore[index]
        self.assertEqual(payload["messages"][0]["content"], "买糖1日元")  # type: ignore[index]

    def test_openai_compatible_client_encodes_image_as_data_url(self) -> None:
        captured: dict[str, object] = {}

        class Response:
            def __enter__(self) -> Response:
                return self

            def __exit__(self, *_: object) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps({"choices": [{"message": {"content": "{}"}}]}).encode()

        def opener(request: object, timeout: float) -> Response:
            captured["payload"] = json.loads(request.data.decode("utf-8"))  # type: ignore[attr-defined]
            return Response()

        client = OpenAICompatibleClient(
            "test-only-key",
            api_url="https://api.example.invalid/v1/chat/completions",
            model="vision-model",
            opener=opener,
        )
        image = ImageAttachment("receipt.png", "image/png", b"test-image-bytes")
        client.complete([{"role": "user", "content": "识别这张收据", "images": [image]}])

        sent_message = captured["payload"]["messages"][0]  # type: ignore[index]
        self.assertEqual(sent_message["content"][0], {"type": "text", "text": "识别这张收据"})
        self.assertEqual(sent_message["content"][1]["type"], "image_url")
        self.assertTrue(
            sent_message["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")
        )
        self.assertNotIn("images", sent_message)

    def test_ollama_client_sends_image_bytes_in_native_images_field(self) -> None:
        captured: dict[str, object] = {}

        class Response:
            def __enter__(self) -> Response:
                return self

            def __exit__(self, *_: object) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps({"message": {"content": "{}"}, "done_reason": "stop"}).encode()

        def opener(request: object, timeout: float) -> Response:
            captured["payload"] = json.loads(request.data.decode("utf-8"))  # type: ignore[attr-defined]
            return Response()

        image = ImageAttachment("receipt.jpg", "image/jpeg", b"jpeg-image-bytes")
        client = OpenAICompatibleClient(
            "", api_url="http://127.0.0.1:11434/v1/chat/completions", model="qwen3.5:4b", opener=opener
        )
        client.complete([{"role": "user", "content": "请识别", "images": [image]}])

        sent_message = captured["payload"]["messages"][0]  # type: ignore[index]
        self.assertEqual(sent_message["content"], "请识别")
        self.assertEqual(sent_message["images"], ["anBlZy1pbWFnZS1ieXRlcw=="])
        self.assertEqual(captured["payload"]["options"]["num_ctx"], 16384)  # type: ignore[index]
        self.assertEqual(captured["payload"]["options"]["num_predict"], 768)  # type: ignore[index]

    def test_local_ollama_image_copy_is_downscaled_without_mutating_attachment(self) -> None:
        from PIL import Image

        source = BytesIO()
        Image.new("RGB", (2000, 1000), "white").save(source, format="JPEG")
        original = source.getvalue()
        attachment = ImageAttachment("receipt.jpg", "image/jpeg", original)

        resized = _local_ollama_image_bytes(attachment)

        with Image.open(BytesIO(resized)) as image:
            self.assertEqual(image.size, (1600, 800))
        self.assertEqual(attachment.data, original)

    def test_image_api_error_includes_server_reason_and_redacts_key(self) -> None:
        def opener(request: object, timeout: float) -> object:
            raise HTTPError(
                "http://127.0.0.1:11434/api/chat",
                400,
                "Bad Request",
                {},
                BytesIO(b'{"error":"invalid image nvapi-1234567890abcdefghijk"}'),
            )

        client = OpenAICompatibleClient(
            "", api_url="http://127.0.0.1:11434/v1/chat/completions", model="qwen3.5:4b", opener=opener
        )
        image = ImageAttachment("receipt.png", "image/png", b"test-image-bytes")
        with self.assertRaises(NaturalLanguageError) as raised:
            client.complete([{"role": "user", "content": "识别图片", "images": [image]}])

        self.assertIn("HTTP 400", str(raised.exception))
        self.assertIn("invalid image", str(raised.exception))
        self.assertNotIn("nvapi-1234567890", str(raised.exception))

    def test_model_timeout_is_not_reported_as_a_network_failure(self) -> None:
        def opener(request: object, timeout: float) -> object:
            raise TimeoutError()

        client = OpenAICompatibleClient(
            "", api_url="http://127.0.0.1:11434/v1/chat/completions", model="qwen3.5:4b", opener=opener
        )
        image = ImageAttachment("receipt.png", "image/png", b"test-image-bytes")
        with self.assertRaises(NaturalLanguageError) as raised:
            client.complete([{"role": "user", "content": "识别图片", "images": [image]}])

        self.assertIn("模型处理超时", str(raised.exception))
        self.assertNotIn("请检查网络", str(raised.exception))

    def test_image_loader_checks_supported_format_and_size(self) -> None:
        from PIL import Image as PillowImage

        image_path = self.root / "receipt.png"
        buffer = BytesIO()
        PillowImage.new("RGB", (8, 8), "white").save(buffer, format="PNG")
        image_path.write_bytes(buffer.getvalue())
        attachment = load_image_attachment(image_path)
        self.assertEqual(attachment.name, "receipt.png")
        self.assertEqual(attachment.media_type, "image/png")
        with PillowImage.open(BytesIO(attachment.data)) as normalized:
            self.assertEqual(normalized.size, (8, 8))
            self.assertEqual(normalized.mode, "RGB")

        unsupported_path = self.root / "receipt.heic"
        unsupported_path.write_bytes(b"ftypheic")
        with self.assertRaisesRegex(NaturalLanguageError, "暂不支持此图片格式"):
            load_image_attachment(unsupported_path)

        with patch("bookkeeping.natural_language.MAX_IMAGE_BYTES", 8):
            with self.assertRaisesRegex(NaturalLanguageError, "单张图片上限"):
                load_image_attachment(image_path)

    def test_large_image_is_downscaled_before_model_submission(self) -> None:
        from PIL import Image as PillowImage

        image_path = self.root / "large_receipt.jpg"
        PillowImage.new("RGB", (4000, 2000), "white").save(image_path, format="JPEG")
        attachment = load_image_attachment(image_path)
        with PillowImage.open(BytesIO(attachment.data)) as image:
            self.assertEqual(image.size, (2560, 1280))
        self.assertEqual(attachment.media_type, "image/jpeg")

    def test_image_is_retained_until_local_account_clarification_is_resolved(self) -> None:
        first_intent = expense_intent(account=None, question="这笔消费使用哪个账户？")
        first_intent["description"] = "收据上的消费"
        fake = FakeClient([first_intent])
        session = NaturalLanguageSession(self.db, fake)  # type: ignore[arg-type]
        image = ImageAttachment("receipt.png", "image/png", b"image-in-memory")

        answer = session.handle("请识别这张收据", images=[image])
        self.assertIn("使用哪个账户", answer)
        self.assertEqual(session.history[0]["images"], [image])

        answer = session.handle("PayPay券")
        answer = self.confirm_image_draft(session, answer)
        self.assertIn("已记录消费", answer)
        prior_user_message = next(
            message for message in fake.messages[0]
            if message["role"] == "user" and message.get("images")
        )
        self.assertEqual(prior_user_message["images"], [image])
        image_prompt = str(fake.messages[0][0]["content"])
        self.assertIn("最终实付总额", image_prompt)
        self.assertLess(len(image_prompt), len(_system_prompt(self.db)))
        self.assertEqual(len(fake.messages), 1)

    def test_image_response_with_extra_model_fields_still_records_valid_transaction(self) -> None:
        intent = expense_intent(account="PayPay券")
        intent.update({
            # Smaller vision models sometimes use the generic API verb shown
            # by the failure report instead of the schema's expense enum.
            "action": "create",
            "date": "2026-10-19",
            "amount": "1200",
            "category": "餐饮",
            "description": "午饭",
            "merchant_name": "模型补充的商家名",
            "image_description": "模型补充的图片说明",
        })
        fake = FakeClient([intent])
        session = NaturalLanguageSession(self.db, fake)  # type: ignore[arg-type]

        answer = session.handle(
            "请把附件中状态明确为已完成的购买解析成一笔消费，提取可确认的日期、含税实付总额、商品类别和支付账户；"
            "状态、账户或金额不确定时先追问，不要猜测。今天午饭1200日元，使用PayPay券。",
            images=[ImageAttachment("receipt.png", "image/png", b"image-in-memory")],
        )

        answer = self.confirm_image_draft(session, answer)
        self.assertIn("已记录消费", answer)
        row = self.db.connection.execute(
            "SELECT t.amount_minor, a.name, c.name AS category "
            "FROM transactions t JOIN accounts a ON a.id=t.account_id "
            "JOIN categories c ON c.id=t.category_id "
            "WHERE t.source='natural_language_api'"
        ).fetchone()
        self.assertEqual((row["amount_minor"], row["name"], row["category"]), (1200, "PayPay券", "餐饮"))

    def test_local_receipt_ocr_fields_override_model_guesses_and_date_falls_back_today(self) -> None:
        intent = expense_intent(account=None, question="这笔消费使用哪个账户？")
        intent.update({
            "action": "reply", "date": "2000-01-01", "amount": "1", "currency": "JPY",
            "category": None, "description": None,
            "question": "无法确认金额和付款账户。", "reply": "无法确认金额和付款账户。",
        })
        fake = ReceiptAwareFakeClient(
            [intent],
            {"date": None, "amount": "1350", "currency": "JPY", "completed": True, "items": ["辛ラーメン"]},
        )
        session = NaturalLanguageSession(self.db, fake)  # type: ignore[arg-type]
        fixed_now = datetime(2026, 10, 17, 9, 0, tzinfo=timezone(timedelta(hours=9)))

        with patch("bookkeeping.natural_language._now_japan", return_value=fixed_now):
            answer = session.handle(
                "请识别附件里的收据，不确定的信息先问我。",
                images=[ImageAttachment("receipt.jpg", "image/jpeg", b"not-redecoded-by-fake")],
            )

        self.assertIn("使用哪个账户", answer)
        request_user = next(message for message in fake.messages[0] if message["role"] == "user")
        self.assertNotIn("images", request_user)
        self.assertIn('"amount": "1350"', request_user["content"])
        self.assertIn("辛ラーメン", request_user["content"])

        answer = session.handle("Rakuten Card")
        answer = self.confirm_image_draft(session, answer)
        self.assertIn("已记录消费", answer)
        row = self.db.connection.execute(
            "SELECT t.occurred_on, t.amount_minor, t.account_id, c.name AS category "
            "FROM transactions t JOIN categories c ON c.id=t.category_id "
            "WHERE t.source='natural_language_api'"
        ).fetchone()
        self.assertEqual(row["occurred_on"], "2026-10-17")
        self.assertEqual(row["amount_minor"], 1350)
        self.assertEqual(row["account_id"], self.db.account("Rakuten Card")["id"])
        self.assertEqual(row["category"], "食材")

    def test_confirmed_credit_receipt_uses_ocr_fields_without_second_parse(self) -> None:
        fake = ReceiptAwareFakeClient(
            [],
            {
                "date": "2026-10-16",
                "amount": "1350",
                "currency": "JPY",
                "completed": True,
                "items": ["辛ラーメン", "チャルメラ宮崎辛麺"],
            },
        )
        session = NaturalLanguageSession(self.db, fake)  # type: ignore[arg-type]
        fixed_now = datetime(2026, 10, 17, 9, 0, tzinfo=timezone(timedelta(hours=9)))

        with patch("bookkeeping.natural_language._now_japan", return_value=fixed_now):
            answer = session.handle(
                "请把附件中状态明确为已完成的购买记录为一笔消费；"
                "付款账户是 Rakuten Card，如果模型读不出来小票日期就按当前日期记账。",
                images=[ImageAttachment("receipt.jpg", "image/jpeg", b"test-image")],
            )

        answer = self.confirm_image_draft(session, answer)
        self.assertIn("已记录消费", answer)
        self.assertEqual(fake.messages, [])
        row = self.db.connection.execute(
            "SELECT t.occurred_on,t.amount_minor,t.account_id,c.name AS category "
            "FROM transactions t JOIN categories c ON c.id=t.category_id "
            "WHERE t.source='natural_language_api'"
        ).fetchone()
        self.assertEqual(row["occurred_on"], "2026-10-16")
        self.assertEqual(row["amount_minor"], 1350)
        self.assertEqual(row["account_id"], self.db.account("Rakuten Card")["id"])
        self.assertEqual(row["category"], "食材")

    def test_unverified_image_receipt_without_items_does_not_post_other_expense(self) -> None:
        intent = expense_intent(account="Rakuten Card")
        intent.update({
            "date": "2026-10-18",
            "amount": "261",
            "category": "其他",
            "description": "ディスクユニオン 竹の塚店",
            "purchase_items": [],
        })
        fake = FakeClient([intent])
        session = NaturalLanguageSession(self.db, fake)  # type: ignore[arg-type]
        transactions_before = self.db.connection.execute(
            "SELECT COUNT(*) FROM transactions"
        ).fetchone()[0]

        answer = session.handle(
            "请把附件中状态明确为已完成的购买解析成一笔消费，提取可确认的日期、含税实付总额、商品类别和支付账户；"
            "状态、账户或金额不确定时先追问，不要猜测。",
            images=[ImageAttachment("receipt.jpg", "image/jpeg", b"test-image")],
        )

        self.assertIn("没有识别出商品", answer)
        self.assertIn("最终实付金额", answer)
        self.assertEqual(
            self.db.connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0],
            transactions_before,
        )
        self.assertIsNotNone(session.pending_state)
        self.assertIsNone(session.pending_state["intent"]["amount"])
        self.assertIsNone(session.pending_state["intent"]["category"])

    def test_remote_deepseek_receipt_retries_when_plausible_category_and_amount_have_no_items(self) -> None:
        wrong_vision_result = expense_intent(account="Rakuten Card")
        wrong_vision_result.update({
            "date": "2026-10-18",
            "amount": "261",
            "category": "日用品",
            "description": "ディスカウントショップ タケヤ 竹の塚店",
            "purchase_items": [],
        })

        class RemoteReceiptFakeClient(FakeClient):
            api_url = "https://api.deepseek.com/v1/chat/completions"

            def __init__(self) -> None:
                super().__init__([
                    {
                        "merchant": "ドン・キホーテ 竹の塚店",
                        "date": "2026-10-18",
                        "total": "192",
                        "currency": "JPY",
                        "completed": True,
                        "items": ["カロリーメイト ブロック チーズ味"],
                    },
                    wrong_vision_result,
                ])

        fake = RemoteReceiptFakeClient()
        session = NaturalLanguageSession(self.db, fake)  # type: ignore[arg-type]
        transactions_before = self.db.connection.execute(
            "SELECT COUNT(*) FROM transactions"
        ).fetchone()[0]

        answer = session.handle(
            "请把附件中状态明确为已完成的购买解析成一笔消费并记账；"
            "付款账户是 Rakuten Card；状态、账户或金额不确定时先追问，不要猜测。",
            images=[ImageAttachment("receipt.jpg", "image/jpeg", b"test-image")],
        )

        answer = self.confirm_image_draft(session, answer)
        self.assertIn("已记录消费", answer)
        self.assertEqual(len(fake.messages), 1)
        self.assertEqual(fake.complete_options[0]["max_tokens"], 2048)
        self.assertFalse(fake.complete_options[0]["structured_output"])
        self.assertIn("所有商品行", fake.messages[0][1]["content"])
        self.assertEqual(
            self.db.connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0],
            transactions_before + 1,
        )
        row = self.db.connection.execute(
            "SELECT t.occurred_on,t.amount_minor,t.description,a.name AS account,c.name AS category "
            "FROM transactions t JOIN accounts a ON a.id=t.account_id "
            "JOIN categories c ON c.id=t.category_id "
            "WHERE t.source='natural_language_api'"
        ).fetchone()
        self.assertEqual(
            tuple(row),
            (
                "2026-10-18",
                192,
                "收据商品：カロリーメイト ブロック チーズ味",
                "Rakuten Card",
                "食材",
            ),
        )
        food_item = self.db.connection.execute(
            "SELECT item_name,classification,food_group FROM food_purchase_items WHERE transaction_id=("
            "SELECT id FROM transactions WHERE source='natural_language_api')"
        ).fetchone()
        self.assertEqual(
            tuple(food_item),
            ("カロリーメイト ブロック チーズ味", "ingredient", "snacks"),
        )

    def test_remote_receipt_item_survives_actual_style_japanese_os_ocr_errors(self) -> None:
        vision_result = expense_intent(account="Rakuten Card")
        vision_result.update({
            "date": "2026-10-18",
            "amount": "192",
            "category": None,
            "description": None,
            "purchase_items": [],
        })
        receipt_fields = {
            "merchant": "ドン・キホーテ 竹の塚店",
            "date": "2026-10-18",
            "total": "192",
            "currency": "JPY",
            "completed": True,
            "items": ["カロリーメイト ブロック チーズ味"],
        }

        class RemoteReceiptFakeClient(FakeClient):
            api_url = "https://api.deepseek.com/v1/chat/completions"

            def __init__(self) -> None:
                # The remote receipt OCR runs before the intent parser. Its
                # item name is valid, but Windows OCR has several character
                # substitutions on the same printed line.
                super().__init__([receipt_fields, vision_result])

        from PIL import Image

        ocr_document = {
            "language": "ja",
            "lines": [
                {"text": "2026 年 10 月 18 日 ( 日 ) 20 : 44", "x": 10, "y": 10, "width": 300, "height": 20},
                {"text": "A* 加 リ ー メ イ ト ア ロ ッ ク チ ー 心 ア シ 。 \\ 178", "x": 10, "y": 40, "width": 300, "height": 20},
                {"text": "8 % 税 額 \\ 14", "x": 10, "y": 70, "width": 300, "height": 20},
                {"text": "合 計 \\ 192", "x": 10, "y": 100, "width": 300, "height": 20},
                {"text": "ク レ ジ ッ ト \\ 192", "x": 10, "y": 130, "width": 300, "height": 20},
                {"text": "お 買 上 点 数 1 点", "x": 10, "y": 160, "width": 300, "height": 20},
                {"text": "ク レ ジ ッ ト 売 上 票", "x": 10, "y": 190, "width": 300, "height": 20},
                {"text": "お 客 様 控 え", "x": 10, "y": 220, "width": 300, "height": 20},
            ],
        }
        image_bytes = BytesIO()
        Image.new("RGB", (400, 300), "white").save(image_bytes, format="JPEG")
        image = ImageAttachment("receipt.jpg", "image/jpeg", image_bytes.getvalue())
        fake = RemoteReceiptFakeClient()
        session = NaturalLanguageSession(self.db, fake)  # type: ignore[arg-type]

        with patch("bookkeeping.natural_language.read_printed_text", return_value=ocr_document):
            answer = session.handle(
                "请把附件中状态明确为已完成的购买解析成一笔消费并记账；"
                "付款账户是 Rakuten Card；状态、账户或金额不确定时先追问，不要猜测。",
                images=[image],
            )

        self.assertIn("类别：食材", answer)
        self.assertIn("カロリーメイト ブロック チーズ味", answer)
        answer = self.confirm_image_draft(session, answer)
        self.assertIn("已记录消费", answer)
        row = self.db.connection.execute(
            "SELECT t.occurred_on,t.amount_minor,a.name AS account,c.name AS category "
            "FROM transactions t JOIN accounts a ON a.id=t.account_id "
            "JOIN categories c ON c.id=t.category_id WHERE t.source='natural_language_api'"
        ).fetchone()
        self.assertEqual(tuple(row), ("2026-10-18", 192, "Rakuten Card", "食材"))
        item = self.db.connection.execute(
            "SELECT item_name,classification,food_group FROM food_purchase_items WHERE transaction_id=("
            "SELECT id FROM transactions WHERE source='natural_language_api')"
        ).fetchone()
        self.assertEqual(tuple(item), ("カロリーメイト ブロック チーズ味", "ingredient", "snacks"))

    def test_remote_deepseek_receipt_recovers_from_unsupported_create_action(self) -> None:
        class RemoteReceiptFakeClient(FakeClient):
            api_url = "https://api.deepseek.com/v1/chat/completions"

            def __init__(self) -> None:
                super().__init__([
                    {"total": None, "completed": None, "items": []},
                    {"action": "create"},
                    {
                        "merchant": "ドン・キホーテ 竹の塚店",
                        "date": "2026-10-18",
                        "total": "192",
                        "currency": "JPY",
                        "completed": True,
                        "items": ["カロリーメイト ブロック チーズ味"],
                    },
                ])

        fake = RemoteReceiptFakeClient()
        session = NaturalLanguageSession(self.db, fake)  # type: ignore[arg-type]

        answer = session.handle(
            "请把附件中状态明确为已完成的购买解析成一笔消费并记账；"
            "付款账户是 Rakuten Card；状态、账户或金额不确定时先追问，不要猜测。",
            images=[ImageAttachment("receipt.jpg", "image/jpeg", b"test-image")],
        )

        answer = self.confirm_image_draft(session, answer)
        self.assertIn("已记录消费", answer)
        self.assertEqual(len(fake.messages), 3)
        row = self.db.connection.execute(
            "SELECT t.amount_minor,c.name AS category FROM transactions t "
            "JOIN categories c ON c.id=t.category_id "
            "WHERE t.source='natural_language_api'"
        ).fetchone()
        self.assertEqual(tuple(row), (192, "食材"))

    def test_unclassified_receipt_items_use_semantic_category_then_unique_payment_rule(self) -> None:
        fields = {
            "date": "2026-10-17",
            "amount": "2755",
            "currency": "JPY",
            "completed": True,
            "items": ["製品A-410", "製品B-520"],
        }
        intent = expense_intent(account=None, question="这笔交易使用哪个账户？")
        intent.update({"date": None, "amount": None, "category": "食材", "description": None})
        fake = ReceiptAwareFakeClient([intent], fields)
        profiles = [
            {"payment_method": "乐天card", "purpose": "默认所有除外食之外的消费均由此账户扣款"},
            {
                "payment_method": "paypay系",
                "purpose": "默认所有外食以及煤气费由此账户扣款，扣款顺序：PayPay券 → PayPay钱包 → PayPay Card",
            },
        ]
        session = NaturalLanguageSession(self.db, fake, payment_hints=profiles)  # type: ignore[arg-type]

        answer = session.handle(
            "请把附件中状态明确为已完成的购买解析成一笔消费并记账；"
            "状态、账户或金额不确定时先追问，不要猜测。",
            images=[ImageAttachment("receipt.jpg", "image/jpeg", b"test-image")],
        )

        answer = self.confirm_image_draft(session, answer)
        self.assertIn("已记录消费", answer)
        self.assertEqual(len(fake.messages), 1)
        row = self.db.connection.execute(
            "SELECT a.name AS account,c.name AS category,t.amount_minor "
            "FROM transactions t JOIN accounts a ON a.id=t.account_id "
            "JOIN categories c ON c.id=t.category_id "
            "WHERE t.source='natural_language_api'"
        ).fetchone()
        self.assertEqual((row["account"], row["category"], row["amount_minor"]), ("Rakuten Card", "食材", 2755))

    def test_missing_receipt_category_uses_clear_category_alias_in_purchase_item(self) -> None:
        intent = expense_intent(account="Rakuten Card")
        intent.update({
            "date": "2026-10-18",
            "amount": "192",
            "category": None,
            "description": "收据商品：カロリーメイト ブロック チーズ味",
            "purchase_items": ["カロリーメイト ブロック チーズ味"],
        })
        fake = FakeClient([intent])
        session = NaturalLanguageSession(self.db, fake)  # type: ignore[arg-type]

        answer = session.handle(
            "请把附件中状态明确为已完成的购买解析成一笔消费并记账；"
            "付款账户是 Rakuten Card。",
            images=[ImageAttachment("receipt.jpg", "image/jpeg", b"test-image")],
        )

        self.assertIn("类别：食材", answer)
        answer = self.confirm_image_draft(session, answer)
        self.assertIn("已记录消费", answer)
        row = self.db.connection.execute(
            "SELECT c.name AS category,t.amount_minor FROM transactions t "
            "JOIN categories c ON c.id=t.category_id "
            "WHERE t.source='natural_language_api'"
        ).fetchone()
        self.assertEqual((row["category"], row["amount_minor"]), ("食材", 192))

    def test_japanese_grocery_item_aliases_resolve_generic_credit_receipt(self) -> None:
        fake = ReceiptAwareFakeClient(
            [],
            {
                "date": "2026-10-17",
                "amount": "2755",
                "currency": "JPY",
                "completed": True,
                "items": [
                    "レジ袋（大）", "コカ・コーラプラス", "恵ブルーベリーいちご", "さきいか",
                    "三島炊き込みわかめ", "ご飯がススム", "おやつスナック", "骨取り塩さば",
                ],
            },
        )
        profiles = [
            {"payment_method": "乐天card", "purpose": "默认所有除外食之外的消费均由此账户扣款"},
            {
                "payment_method": "paypay系",
                "purpose": "默认所有外食以及煤气费由此账户扣款，扣款顺序：PayPay券 → PayPay钱包 → PayPay Card",
            },
        ]
        session = NaturalLanguageSession(self.db, fake, payment_hints=profiles)  # type: ignore[arg-type]

        answer = session.handle(
            "请把附件中状态明确为已完成的购买解析成一笔消费，提取可确认的日期、含税实付总额、商品类别和支付账户；"
            "状态、账户或金额不确定时先追问，不要猜测。",
            images=[ImageAttachment("receipt.jpg", "image/jpeg", b"test-image")],
        )

        answer = self.confirm_image_draft(session, answer)
        self.assertIn("已记录消费", answer)
        self.assertEqual(fake.messages, [])
        row = self.db.connection.execute(
            "SELECT a.name AS account,c.name AS category,t.occurred_on,t.amount_minor "
            "FROM transactions t JOIN accounts a ON a.id=t.account_id "
            "JOIN categories c ON c.id=t.category_id "
            "WHERE t.source='natural_language_api'"
        ).fetchone()
        self.assertEqual(
            (row["account"], row["category"], row["occurred_on"], row["amount_minor"]),
            ("Rakuten Card", "食材", "2026-10-17", 2755),
        )

    def test_tamago_receipt_uses_saved_payment_rule_and_ignores_printed_payment_label(self) -> None:
        fake = ReceiptAwareFakeClient(
            [],
            {
                "date": "2026-10-18",
                "amount": "433",
                "currency": "JPY",
                "completed": True,
                "items": ["たまご"],
                "printed_payment": "現金",
            },
        )
        profiles = [
            {"payment_method": "Rakuten Card", "purpose": "默认所有除外食之外的消费均由此账户扣款"},
        ]
        session = NaturalLanguageSession(self.db, fake, payment_hints=profiles)  # type: ignore[arg-type]

        answer = session.handle(
            "请把附件中状态明确为已完成的购买解析成一笔消费并记账；"
            "状态、账户或金额不确定时先追问，不要猜测。",
            images=[ImageAttachment("receipt.jpg", "image/jpeg", b"test-image")],
        )

        answer = self.confirm_image_draft(session, answer)
        self.assertIn("已记录消费", answer)
        self.assertEqual(fake.messages, [])
        row = self.db.connection.execute(
            "SELECT a.name AS account,c.name AS category,t.occurred_on,t.amount_minor "
            "FROM transactions t JOIN accounts a ON a.id=t.account_id "
            "JOIN categories c ON c.id=t.category_id "
            "WHERE t.source='natural_language_api'"
        ).fetchone()
        self.assertEqual(
            (row["account"], row["category"], row["occurred_on"], row["amount_minor"]),
            ("Rakuten Card", "食材", "2026-10-18", 433),
        )

    def test_local_receipt_ocr_returns_completion_without_payment_account_field(self) -> None:
        from PIL import Image

        source = BytesIO()
        Image.new("RGB", (120, 320), "white").save(source, format="JPEG")
        calls: list[dict[str, object]] = []
        responses = [
            {
                "merchant": "CanDo",
                "date": "2026��10��18��(��) 20:06",
                "items": ["たまご", "2個 X 単198", "����商品"],
            },
            {"total": "{220}", "completed": True},
        ]

        class Response:
            def __init__(self, payload: dict[str, object]) -> None:
                self.payload = payload

            def __enter__(self) -> Response:
                return self

            def __exit__(self, *_: object) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps({"message": {"content": json.dumps(self.payload)}}).encode()

        def opener(request: object, timeout: float) -> Response:
            calls.append(json.loads(request.data.decode("utf-8")))  # type: ignore[attr-defined]
            return Response(responses.pop(0))

        client = OpenAICompatibleClient(
            "", api_url="http://127.0.0.1:11434/v1/chat/completions", model="qwen3.5:4b", opener=opener
        )
        fields = client.extract_local_receipt_fields(
            ImageAttachment("receipt.jpg", "image/jpeg", source.getvalue())
        )

        self.assertEqual(fields, {
            "merchant": "CanDo", "date": "2026-10-18", "amount": "220", "currency": "JPY",
            "completed": True, "items": ["たまご"],
            "amount_check": "unavailable",
        })
        self.assertEqual(len(calls), 2)
        total_format = calls[1]["format"]  # type: ignore[index]
        self.assertEqual(total_format["required"], ["total", "completed"])
        self.assertNotIn("payment", total_format["properties"])
        total_prompt = calls[1]["messages"][0]["content"]  # type: ignore[index]
        self.assertIn("合計/合计", total_prompt)
        self.assertIn("不要读取支付方式", total_prompt)

    def test_known_receipt_merchant_uses_unique_saved_rule_when_item_ocr_is_unreadable(self) -> None:
        fake = ReceiptAwareFakeClient(
            [],
            {
                "merchant": "CanDo",
                "date": "2026-10-18",
                "amount": "220",
                "currency": "JPY",
                "completed": True,
                "items": [],
                "printed_payment": "credit card",
            },
        )
        profiles = [
            {"payment_method": "Rakuten Card", "purpose": "默认所有除外食之外的消费均由此账户扣款"},
        ]
        session = NaturalLanguageSession(self.db, fake, payment_hints=profiles)  # type: ignore[arg-type]

        answer = session.handle(
            "请把附件中状态明确为已完成的购买解析成一笔消费，提取可确认的日期、含税实付总额、商品类别和支付账户；"
            "状态、账户或金额不确定时先追问，不要猜。",
            images=[ImageAttachment("receipt.jpg", "image/jpeg", b"test-image")],
        )

        answer = self.confirm_image_draft(session, answer)
        self.assertIn("已记录消费", answer)
        self.assertIn("Rakuten Card", answer)
        self.assertEqual(fake.messages, [])
        row = self.db.connection.execute(
            "SELECT a.name AS account,c.name AS category,t.occurred_on,t.amount_minor,t.description "
            "FROM transactions t JOIN accounts a ON a.id=t.account_id "
            "JOIN categories c ON c.id=t.category_id "
            "WHERE t.source='natural_language_api'"
        ).fetchone()
        self.assertEqual(
            (row["account"], row["category"], row["occurred_on"], row["amount_minor"]),
            ("Rakuten Card", "其他", "2026-10-18", 220),
        )
        self.assertIn("CanDo", row["description"])

    def test_local_receipt_preprocessing_crops_a_confident_paper_region(self) -> None:
        from PIL import Image, ImageDraw

        photo = Image.new("RGB", (1800, 2400), (120, 105, 88))
        draw = ImageDraw.Draw(photo)
        draw.rectangle((340, 120, 1460, 2270), fill=(238, 237, 232))
        for y in range(300, 2200, 140):
            draw.line((460, y, 1300, y), fill=(40, 40, 40), width=8)
        source = BytesIO()
        photo.save(source, format="JPEG")

        content, summary = _local_receipt_ocr_images(
            ImageAttachment("receipt.jpg", "image/jpeg", source.getvalue())
        )

        with Image.open(BytesIO(content.data)) as cropped:
            self.assertLess(cropped.width * cropped.height, 1800 * 2400 * 0.9)
            self.assertEqual(max(cropped.size), 1280)
            self.assertGreater(cropped.width, 500)
            self.assertGreater(cropped.height, 900)
            content_height = cropped.height
        self.assertTrue(summary.name.endswith("#summary"))
        with Image.open(BytesIO(summary.data)) as focused_total:
            self.assertEqual(max(focused_total.size), 1280)
            self.assertLess(focused_total.height, content_height)

    def test_local_receipt_preprocessing_crops_portrait_receipt_from_landscape_photo(self) -> None:
        from PIL import Image, ImageDraw

        photo = Image.new("RGB", (2400, 1800), (118, 103, 88))
        draw = ImageDraw.Draw(photo)
        draw.rectangle((800, 90, 1600, 1710), fill=(239, 238, 233))
        for y in range(260, 1650, 120):
            draw.line((900, y, 1480, y), fill=(35, 35, 35), width=7)
        source = BytesIO()
        photo.save(source, format="JPEG")

        content, summary = _local_receipt_ocr_images(
            ImageAttachment("landscape-receipt.jpg", "image/jpeg", source.getvalue())
        )

        with Image.open(BytesIO(content.data)) as cropped:
            self.assertLess(cropped.width * cropped.height, 2400 * 1800 * 0.9)
            self.assertEqual(max(cropped.size), 1280)
            self.assertGreater(cropped.height, cropped.width)
        with Image.open(BytesIO(summary.data)) as cropped_summary:
            self.assertLess(cropped_summary.width * cropped_summary.height, 2400 * 1800 * 0.9)
            self.assertEqual(max(cropped_summary.size), 1280)

    def test_receipt_with_unresolved_category_asks_category_before_payment_account(self) -> None:
        fake = ReceiptAwareFakeClient(
            [expense_intent(account=None, question="这笔交易使用哪个账户？")],
            {
                "date": "2026-10-17",
                "amount": "2755",
                "currency": "JPY",
                "completed": True,
                "items": ["未收录的商品甲", "未收录的商品乙"],
            },
        )
        intent = fake.responses[0]
        intent["category"] = None
        profiles = [
            {"payment_method": "乐天card", "purpose": "默认所有除外食之外的消费均由此账户扣款"},
        ]
        session = NaturalLanguageSession(self.db, fake, payment_hints=profiles)  # type: ignore[arg-type]

        answer = session.handle(
            "请把附件中状态明确为已完成的购买解析成一笔消费并记账。",
            images=[ImageAttachment("receipt.jpg", "image/jpeg", b"test-image")],
        )

        self.assertIn("商品类别", answer)
        self.assertNotIn("账户？", answer)
        self.assertEqual(
            self.db.connection.execute(
                "SELECT COUNT(*) FROM transactions WHERE source='natural_language_api'"
            ).fetchone()[0],
            0,
        )

    def test_confirmed_credit_receipt_records_when_items_are_unreadable_but_user_supplies_category(self) -> None:
        fake = ReceiptAwareFakeClient(
            [],
            {
                "date": None,
                "amount": "1350",
                "currency": "JPY",
                "completed": True,
                "items": [],
            },
        )
        session = NaturalLanguageSession(self.db, fake)  # type: ignore[arg-type]
        fixed_now = datetime(2026, 10, 17, 9, 0, tzinfo=timezone(timedelta(hours=9)))

        with patch("bookkeeping.natural_language._now_japan", return_value=fixed_now):
            answer = session.handle(
                "请把附件中状态明确为已完成且已付款的购买解析成一笔消费并记账；"
                "类别是食材，支付账户是 Rakuten Card；如果模型读不出来小票日期的话，就按照当前日期记账。",
                images=[ImageAttachment("receipt.jpg", "image/jpeg", b"test-image")],
            )

        answer = self.confirm_image_draft(session, answer)
        self.assertIn("已记录消费", answer)
        self.assertEqual(fake.messages, [])
        row = self.db.connection.execute(
            "SELECT t.occurred_on,t.amount_minor,t.account_id,t.description,c.name AS category "
            "FROM transactions t JOIN categories c ON c.id=t.category_id "
            "WHERE t.source='natural_language_api'"
        ).fetchone()
        self.assertEqual(row["occurred_on"], "2026-10-17")
        self.assertEqual(row["amount_minor"], 1350)
        self.assertEqual(row["account_id"], self.db.account("Rakuten Card")["id"])
        self.assertEqual(row["category"], "食材")
        self.assertEqual(row["description"], "收据消费（商品未识别）")

    def test_receipt_instruction_to_parse_as_one_expense_avoids_batch_model_failure(self) -> None:
        fake = ReceiptAwareFakeClient(
            [],
            {
                "date": "2026-10-16",
                "amount": "1350",
                "currency": "JPY",
                "completed": True,
                "items": ["辛ラーメン", "チャルメラ宮崎辛麺", "辛ラーメンキムチ", "とろけるM200g", "明星一平ちゃん"],
                "printed_payment": "クレジットカード",
            },
        )
        session = NaturalLanguageSession(self.db, fake)  # type: ignore[arg-type]

        answer = session.handle(
            "请把附件中状态明确为已完成的购买解析成一笔消费，提取可确认的日期、含税实付总额、商品类别和支付账户；"
            "状态、账户或金额不确定时先追问，不要猜测。",
            images=[ImageAttachment("receipt.jpg", "image/jpeg", b"test-image")],
        )

        self.assertIn("账户", answer)
        self.assertEqual(fake.messages, [])
        self.assertEqual(
            self.db.connection.execute(
                "SELECT COUNT(*) FROM transactions WHERE source='natural_language_api'"
            ).fetchone()[0],
            0,
        )

    def test_image_request_uses_compact_prompt_with_accounts_rules_and_skill(self) -> None:
        profiles = [{"payment_method": "PayPay", "purpose": "外食", "currency": "CNY"}]
        skill = "未说明币种时默认JPY。"
        fake = FakeClient([expense_intent(account=None, question="请确认付款账户。")])
        session = NaturalLanguageSession(
            self.db,
            fake,  # type: ignore[arg-type]
            payment_hints=profiles,
            loaded_skill=skill,
        )
        session.handle("请识别这张收据", images=[ImageAttachment("receipt.png", "image/png", b"test")])

        prompt = str(fake.messages[0][0]["content"])
        regular_prompt = _system_prompt(self.db, payment_hints=profiles, loaded_skill=skill)
        self.assertLess(len(prompt), len(regular_prompt))
        self.assertIn("最终实付总额", prompt)
        self.assertIn("账户列表", prompt)
        self.assertIn("PayPay", prompt)
        self.assertIn('"currency": "CNY"', prompt)
        self.assertIn("currency字段是规则适用的交易币种", prompt)
        self.assertIn(skill, prompt)

    def test_ollama_uses_native_api_with_thinking_disabled(self) -> None:
        captured: dict[str, object] = {}

        class Response:
            def __enter__(self) -> Response:
                return self

            def __exit__(self, *_: object) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps(
                    {"message": {"content": "{}"}, "done_reason": "stop"}
                ).encode()

        def opener(request: object, timeout: float) -> Response:
            captured["url"] = request.full_url  # type: ignore[attr-defined]
            captured["payload"] = json.loads(request.data.decode("utf-8"))  # type: ignore[attr-defined]
            return Response()

        client = OpenAICompatibleClient(
            "", api_url="http://127.0.0.1:11434/v1/chat/completions", model="qwen3.5:4b", opener=opener
        )
        self.assertEqual(client.complete([{"role": "user", "content": "午饭1元"}]), "{}")
        self.assertEqual(captured["url"], "http://127.0.0.1:11434/api/chat")
        payload = captured["payload"]
        self.assertFalse(payload["think"])  # type: ignore[index]
        self.assertEqual(payload["options"]["num_predict"], 1024)  # type: ignore[index]
        self.assertEqual(payload["options"]["temperature"], 0)  # type: ignore[index]
        self.assertEqual(payload["options"]["num_ctx"], 16384)  # type: ignore[index]
        self.assertEqual(payload["format"]["type"], "object")  # type: ignore[index]
        self.assertIn("payment_profile_index", payload["format"]["required"])  # type: ignore[index]

    def test_prompt_includes_current_japan_local_time(self) -> None:
        from datetime import datetime, timezone, timedelta

        fixed_now = datetime(2026, 10, 16, 0, 5, 30, tzinfo=timezone(timedelta(hours=9)))
        with patch("bookkeeping.natural_language._now_japan", return_value=fixed_now):
            prompt = _system_prompt(self.db)

        self.assertIn("2026-10-16T00:05:30+09:00", prompt)
        self.assertIn("date必须返回null", prompt)
        self.assertIn("大创/大創/ダイソー/DAISO", prompt)
        self.assertIn("遇到未识别的店名也不得仅凭店名推断餐饮", prompt)
        self.assertIn("收据/发票图片", prompt)
        self.assertIn("含税实付总额", prompt)
        self.assertIn("忽略图片上印出的支付方式", prompt)

    def test_image_prompt_treats_credit_card_sales_slip_as_purchase_expense(self) -> None:
        from datetime import datetime, timezone, timedelta

        fixed_now = datetime(2026, 10, 16, 12, 0, tzinfo=timezone(timedelta(hours=9)))
        prompt = _image_system_prompt(self.db, [], "", fixed_now)

        self.assertIn("クレジットカード売上票", prompt)
        self.assertIn("付款方式凭证，不是还款或账户间转账", prompt)
        self.assertIn("标签`合計`旁有清楚金额时必须填写amount", prompt)
        self.assertIn("忽略图片上印出的支付方式", prompt)
        self.assertIn("唯一匹配的已保存支付规则", prompt)

    def test_receipt_date_from_image_is_not_replaced_by_today(self) -> None:
        from datetime import datetime, timezone, timedelta

        intent = expense_intent(account="PayPay券")
        intent["amount"] = "1350"
        intent["date"] = "2026-10-16"
        session = NaturalLanguageSession(self.db, FakeClient([intent]))  # type: ignore[arg-type]
        fixed_now = datetime(2026, 10, 17, 0, 5, 30, tzinfo=timezone(timedelta(hours=9)))

        with patch("bookkeeping.natural_language._now_japan", return_value=fixed_now):
            answer = session.handle(
                "请按收据记账，用PayPay券支付",
                images=[ImageAttachment("receipt.jpg", "image/jpeg", b"test-image")],
            )

        answer = self.confirm_image_draft(session, answer)
        self.assertIn("已记录消费", answer)
        row = self.db.connection.execute(
            "SELECT occurred_on FROM transactions WHERE source='natural_language_api'"
        ).fetchone()
        self.assertEqual(row["occurred_on"], "2026-10-16")

    def test_missing_date_is_filled_by_program_local_date(self) -> None:
        from datetime import datetime, timezone, timedelta

        intent = expense_intent(account="PayPay券")
        intent["date"] = None
        fake = FakeClient([intent])
        session = NaturalLanguageSession(self.db, fake)  # type: ignore[arg-type]
        fixed_now = datetime(2026, 10, 16, 0, 5, 30, tzinfo=timezone(timedelta(hours=9)))

        with patch("bookkeeping.natural_language._now_japan", return_value=fixed_now):
            answer = session.handle("买糖1日元，用PayPay券")

        self.assertIn("已记录消费", answer)
        row = self.db.connection.execute(
            "SELECT occurred_on FROM transactions WHERE source='natural_language_api'"
        ).fetchone()
        self.assertEqual(row["occurred_on"], "2026-10-16")

    def test_model_cannot_override_program_date_when_user_omits_date(self) -> None:
        from datetime import datetime, timezone, timedelta

        intent = expense_intent(account="PayPay券")
        intent["date"] = "2020-01-01"
        fake = FakeClient([intent])
        session = NaturalLanguageSession(self.db, fake)  # type: ignore[arg-type]
        fixed_now = datetime(2026, 10, 16, 0, 5, 30, tzinfo=timezone(timedelta(hours=9)))

        with patch("bookkeeping.natural_language._now_japan", return_value=fixed_now):
            answer = session.handle("买糖1日元，用PayPay券")

        self.assertIn("已记录消费", answer)
        row = self.db.connection.execute(
            "SELECT occurred_on FROM transactions WHERE source='natural_language_api'"
        ).fetchone()
        self.assertEqual(row["occurred_on"], "2026-10-16")

    def test_relative_date_is_resolved_from_japan_clock(self) -> None:
        from datetime import datetime, timezone, timedelta

        fixed_now = datetime(2026, 10, 16, 0, 5, 30, tzinfo=timezone(timedelta(hours=9)))
        intent = expense_intent(account="PayPay券")
        intent["date"] = "2026-10-16"
        fake = FakeClient([intent])
        session = NaturalLanguageSession(self.db, fake)  # type: ignore[arg-type]

        with patch("bookkeeping.natural_language._now_japan", return_value=fixed_now):
            answer = session.handle("昨天买糖1日元，用PayPay券")

        self.assertIn("已记录消费", answer)
        row = self.db.connection.execute(
            "SELECT occurred_on FROM transactions WHERE source='natural_language_api'"
        ).fetchone()
        self.assertEqual(row["occurred_on"], "2026-10-15")

    def test_profile_match_automatically_uses_first_available_payment_source(self) -> None:
        profiles = [
            {
                "payment_method": "PayPay",
                "purpose": "通常用于外食，外食归餐饮。付款优先顺序：PayPay券 → PayPay积分 → PayPay钱包 → PayPay Card。",
            },
            {"payment_method": "Rakuten Pay", "purpose": "通常用于水费、电费。"},
            {"payment_method": "Rakuten Card", "purpose": "通常用于日常一般消费。"},
        ]
        fake = FakeClient([expense_intent(account=None, question="这笔交易使用哪个账户？")])
        session = NaturalLanguageSession(self.db, fake, payment_hints=profiles)  # type: ignore[arg-type]
        answer = session.handle("午饭1日元")

        self.assertIn("已记录消费", answer)
        self.assertIn("PayPay券", answer)
        self.assertIn("默认顺序自动选择", answer)
        self.assertNotIn("PayPay积分", answer)
        row = self.db.connection.execute(
            "SELECT account_id FROM transactions WHERE source='natural_language_api'"
        ).fetchone()
        self.assertEqual(self.db.account("PayPay券")["id"], row["account_id"])

    def test_utility_category_synonym_uses_matching_saved_payment_priority(self) -> None:
        profiles = [
            {
                "payment_method": "PayPay",
                "purpose": "通常用于外食和煤气费。付款优先顺序：PayPay券 → PayPay积分 → PayPay余额 → PayPay信用支付/PayPay Card。外食归餐饮，煤气归水电燃气。",
            },
            {
                "payment_method": "Rakuten Pay",
                "purpose": "通常用于水费、电费。付款优先顺序：Rakuten积分 → Rakuten Pay余额 → Rakuten Card。",
            },
            {
                "payment_method": "Rakuten Card",
                "purpose": "通常用于日常一般消费。付款优先顺序：Rakuten积分 → Rakuten Card。直接刷卡时不经过 Rakuten Pay 余额。",
            },
            {
                "payment_method": "瑞穗银行账户",
                "purpose": "所有信用卡还款；从瑞穗银行账户转出到本次明确提到的信用卡。",
            },
        ]
        intent = expense_intent(account=None, question="这笔消费使用哪个账户？")
        intent["amount"] = "6200"
        intent["category"] = "其他"
        intent["description"] = "煤气费"
        session = NaturalLanguageSession(
            self.db, FakeClient([intent]), payment_hints=profiles  # type: ignore[arg-type]
        )

        self.assertEqual(session._canonical_category_name("公用事业", "expense"), "通信与账单")
        answer = session.handle("今天交煤气费6200日元")

        self.assertIn("已记录消费", answer)
        self.assertIn("PayPay券", answer)
        rows = self.db.connection.execute(
            "SELECT a.name account_name,c.name category_name,t.amount_minor "
            "FROM transactions t JOIN accounts a ON a.id=t.account_id "
            "JOIN categories c ON c.id=t.category_id "
            "WHERE t.source='natural_language_api' ORDER BY t.id"
        ).fetchall()
        self.assertEqual(
            [(row["account_name"], row["category_name"], row["amount_minor"]) for row in rows],
            [
                ("PayPay券", "通信与账单", 800),
                ("PayPay钱包", "通信与账单", 2000),
                ("PayPay Card", "通信与账单", 3400),
            ],
        )

        water_intent = expense_intent(account=None, question="请确认付款账户。")
        water_intent["amount"] = "3500"
        water_intent["category"] = "通信与账单"
        water_intent["description"] = "水费"
        water_session = NaturalLanguageSession(
            self.db, FakeClient([water_intent]), payment_hints=profiles  # type: ignore[arg-type]
        )
        water_answer = water_session.handle("今天交水费3500日元")
        self.assertIn("Rakuten Pay", water_answer)
        self.assertIn("已记录消费", water_answer)
        water_rows = self.db.connection.execute(
            "SELECT a.name account_name,c.name category_name,t.amount_minor "
            "FROM transactions t JOIN accounts a ON a.id=t.account_id "
            "JOIN categories c ON c.id=t.category_id "
            "WHERE t.source='natural_language_api' AND t.description LIKE '水费%' ORDER BY t.id"
        ).fetchall()
        self.assertEqual(
            [(row["account_name"], row["category_name"], row["amount_minor"]) for row in water_rows],
            [("Rakuten积分", "通信与账单", 300), ("Rakuten Pay", "通信与账单", 1000),
             ("Rakuten Card", "通信与账单", 2200)],
        )

    def test_payment_priority_with_order_before_sequence_suffix_is_allocated(self) -> None:
        profile = {
            "payment_method": "乐天PAY",
            "purpose": "水费，电费，按照乐天point→乐天pay余额→乐天card的顺序扣款",
            "currency": "JPY",
        }
        intent = expense_intent(account=None, question="请确认付款账户。")
        intent.update(
            {
                "amount": "2500",
                "category": "通信与账单",
                "description": "水费",
            }
        )
        session = NaturalLanguageSession(
            self.db,
            FakeClient([intent]),  # type: ignore[arg-type]
            payment_hints=[profile],
        )

        answer = session.handle("今天交水费2500日元")

        self.assertIn("已记录消费", answer)
        rows = self.db.connection.execute(
            "SELECT a.name account_name,t.amount_minor "
            "FROM transactions t JOIN accounts a ON a.id=t.account_id "
            "WHERE t.source='natural_language_api' ORDER BY t.id"
        ).fetchall()
        self.assertEqual(
            [(row["account_name"], row["amount_minor"]) for row in rows],
            [("Rakuten积分", 300), ("Rakuten Pay", 1000), ("Rakuten Card", 1200)],
        )

    def test_composite_generic_expense_category_maps_to_supported_category(self) -> None:
        session = NaturalLanguageSession(
            self.db, FakeClient([])  # type: ignore[arg-type]
        )

        self.assertEqual(
            session._canonical_category_name(
                "日常一般消费/普通消费/一般消费", "expense"
            ),
            "日用品",
        )

    def test_unknown_expense_category_asks_with_available_choices_without_writing(self) -> None:
        intent = expense_intent(account="工商储蓄卡")
        intent.update(
            {
                "amount": "55",
                "currency": "CNY",
                "category": "模型臆造的类别",
                "description": "给妈妈买东西",
            }
        )
        session = NaturalLanguageSession(
            self.db, FakeClient([intent])  # type: ignore[arg-type]
        )

        answer = session.handle("给妈妈买东西55元人民币")

        self.assertIn("无法匹配到已启用的支出类别", answer)
        self.assertIn("日用品", answer)
        count = self.db.connection.execute(
            "SELECT COUNT(*) AS count FROM transactions WHERE source='natural_language_api'"
        ).fetchone()["count"]
        self.assertEqual(count, 0)

    def test_general_daily_spending_rule_is_a_fallback_for_grocery_expenses(self) -> None:
        profiles = [
            {
                "payment_method": "PayPay",
                "purpose": "通常用于外食和煤气费。付款优先顺序：PayPay券 → PayPay积分 → PayPay余额 → PayPay信用支付/PayPay Card。",
            },
            {
                "payment_method": "Rakuten Pay",
                "purpose": "通常用于水费、电费。付款优先顺序：Rakuten积分 → Rakuten Pay余额 → Rakuten Card。",
            },
            {
                "payment_method": "Rakuten Card",
                "purpose": "通常用于日常一般消费。付款优先顺序：Rakuten积分 → Rakuten Card。",
            },
        ]
        intent = expense_intent(account=None, question="请确认付款账户。")
        intent["amount"] = "630"
        intent["category"] = "食材"
        intent["description"] = "鸡蛋和牛奶"
        session = NaturalLanguageSession(
            self.db, FakeClient([intent]), payment_hints=profiles  # type: ignore[arg-type]
        )

        answer = session.handle("今天超市买鸡蛋和牛奶630日元")

        self.assertIn("已记录消费", answer)
        self.assertIn("Rakuten Card", answer)
        rows = self.db.connection.execute(
            "SELECT a.name account_name,c.name category_name,t.amount_minor "
            "FROM transactions t JOIN accounts a ON a.id=t.account_id "
            "JOIN categories c ON c.id=t.category_id "
            "WHERE t.source='natural_language_api' ORDER BY t.id"
        ).fetchall()
        self.assertEqual(
            [(row["account_name"], row["category_name"], row["amount_minor"]) for row in rows],
            [("Rakuten积分", "食材", 300), ("Rakuten Card", "食材", 330)],
        )

    def test_all_spending_rule_is_a_fallback_for_grocery_expenses(self) -> None:
        intent = expense_intent(account=None, question="这笔交易使用哪个账户？")
        intent["amount"] = "630"
        intent["category"] = "食材"
        intent["description"] = "鸡蛋和牛奶"
        session = NaturalLanguageSession(
            self.db,
            FakeClient([intent]),  # type: ignore[arg-type]
            payment_hints=[{"payment_method": "乐天card", "purpose": "所有消费"}],
        )

        answer = session.handle("请把附件中已完成的消费记账：超市购买鸡蛋和牛奶630日元")

        self.assertIn("已记录消费", answer)
        self.assertIn("Rakuten Card", answer)
        row = self.db.connection.execute(
            "SELECT a.name account_name,c.name category_name,t.amount_minor "
            "FROM transactions t JOIN accounts a ON a.id=t.account_id "
            "JOIN categories c ON c.id=t.category_id "
            "WHERE t.source='natural_language_api'"
        ).fetchone()
        self.assertEqual((row["account_name"], row["category_name"], row["amount_minor"]),
                         ("Rakuten Card", "食材", 630))

    def test_all_spending_rule_still_respects_explicit_category_exclusion(self) -> None:
        intent = expense_intent(account=None)
        intent["category"] = "餐饮"
        session = NaturalLanguageSession(
            self.db,
            FakeClient([intent]),  # type: ignore[arg-type]
            payment_hints=[
                {"payment_method": "乐天card", "purpose": "所有消费，餐饮除外"}
            ],
        )

        self.assertIsNone(session._payment_profile_for_intent(intent, "今天午饭500日元"))

    def test_cny_scoped_payment_rule_overrides_model_selected_jpy_catchall(self) -> None:
        from decimal import Decimal

        from bookkeeping.fx_rates import JpyRate

        self.db.add_account(
            name="工商储蓄卡",
            account_type="bank",
            currency="CNY",
            opening_balance="1000",
            opening_date="2026-10-01",
        )
        profiles = [
            {
                "payment_method": "Rakuten Card",
                "purpose": "默认所有除外食之外的消费均由此账户扣款。",
            },
            {
                "payment_method": "工行储蓄卡",
                "purpose": "默认所有人民币交易由本卡付款。",
            },
        ]
        intent = expense_intent(account="Rakuten Card")
        intent.update(
            {
                "amount": "55",
                "currency": "CNY",
                "category": "日常一般消费/普通消费/一般消费",
                "description": "给妈妈买东西",
                "payment_profile_index": 1,
            }
        )
        session = NaturalLanguageSession(
            self.db, FakeClient([intent]), payment_hints=profiles  # type: ignore[arg-type]
        )

        with patch(
            "bookkeeping.fx_rates.resolve_jpy_rate",
            return_value=JpyRate(Decimal("20"), "2026-10-18", "test fixture"),
        ):
            answer = session.handle("给妈妈买东西55元人民币")

        self.assertIn("已记录消费", answer)
        self.assertIn("工商储蓄卡", answer)
        self.assertNotIn("Rakuten Card", answer)
        row = self.db.connection.execute(
            "SELECT a.name account_name,c.name category_name,t.currency,t.amount_minor "
            "FROM transactions t JOIN accounts a ON a.id=t.account_id "
            "JOIN categories c ON c.id=t.category_id "
            "WHERE t.source='natural_language_api'"
        ).fetchone()
        self.assertEqual(
            (row["account_name"], row["category_name"], row["currency"], row["amount_minor"]),
            ("工商储蓄卡", "日用品", "CNY", 5500),
        )

    def test_selected_payment_rules_respect_configured_currency(self) -> None:
        from decimal import Decimal

        from bookkeeping.fx_rates import JpyRate

        self.db.add_account(
            name="工商储蓄卡",
            account_type="bank",
            currency="CNY",
            opening_balance="1000",
            opening_date="2026-10-01",
        )
        profiles = [
            {
                "payment_method": "Rakuten Card",
                "purpose": "默认所有消费，外食除外",
                "currency": "JPY",
            },
            {
                "payment_method": "工行储蓄卡",
                "purpose": "默认所有消费由本卡付款",
                "currency": "CNY",
            },
        ]
        intent = expense_intent(account="Rakuten Card")
        intent.update(
            {
                "amount": "55",
                "currency": "CNY",
                "category": "日用品",
                "description": "给妈妈买东西",
                "payment_profile_index": 1,
            }
        )
        session = NaturalLanguageSession(
            self.db, FakeClient([intent]), payment_hints=profiles  # type: ignore[arg-type]
        )

        with patch(
            "bookkeeping.fx_rates.resolve_jpy_rate",
            return_value=JpyRate(Decimal("20"), "2026-10-18", "test fixture"),
        ):
            answer = session.handle("给妈妈买东西55元人民币")

        self.assertIn("已记录消费", answer)
        self.assertIn("工商储蓄卡", answer)
        self.assertNotIn("Rakuten Card", answer)
        row = self.db.connection.execute(
            "SELECT a.name account_name,t.currency,t.amount_minor "
            "FROM transactions t JOIN accounts a ON a.id=t.account_id "
            "WHERE t.source='natural_language_api'"
        ).fetchone()
        self.assertEqual((row["account_name"], row["currency"], row["amount_minor"]),
                         ("工商储蓄卡", "CNY", 5500))

        intent["currency"] = "JPY"
        intent["payment_profile_index"] = 2
        self.assertEqual(
            session._payment_profile_for_intent(intent, "日用品"),
            session.payment_hints[0],
        )

    def test_explicit_bank_to_transit_recharge_is_normalized_to_internal_transfer(self) -> None:
        intent = expense_intent(account=None)
        intent["amount"] = "3000"
        intent["category"] = "交通"
        intent["description"] = "Suica充值"
        session = NaturalLanguageSession(
            self.db, FakeClient([intent])  # type: ignore[arg-type]
        )

        answer = session.handle("今天从瑞穗银行给Suica充值3000日元")

        self.assertIn("已记录转账/还款", answer)
        row = self.db.connection.execute(
            "SELECT t.kind,t.amount_minor,a.name source_name,d.name target_name "
            "FROM transactions t JOIN accounts a ON a.id=t.account_id "
            "JOIN accounts d ON d.id=t.to_account_id "
            "WHERE t.source='natural_language_api'"
        ).fetchone()
        self.assertEqual(tuple(row), ("transfer", 3000, "瑞穗银行", "Suica"))

    def test_generic_clarification_instruction_is_not_payment_uncertainty(self) -> None:
        self.assertFalse(
            NaturalLanguageSession._payment_method_is_uncertain(
                "状态、账户或金额不确定时先追问，不要猜测。"
            )
        )
        self.assertTrue(
            NaturalLanguageSession._payment_method_is_uncertain(
                "这笔午饭我不确定用哪个账户支付。"
            )
        )

    def test_lunch_does_not_match_a_rule_that_excludes_dining(self) -> None:
        profiles = [
            {
                "payment_method": "paypay系",
                "purpose": "默认所有外食以及煤气费由此账户扣款；付款顺序：PayPay券 → PayPay钱包 → PayPay Card。",
            },
            {
                "payment_method": "乐天card",
                "purpose": "默认所有除餐饮之外的消费均由此账户扣款。",
            },
        ]
        intent = expense_intent(account=None)
        # Simulate a model selecting the broad rule despite its explicit exclusion.
        intent["payment_profile_index"] = 2
        session = NaturalLanguageSession(
            self.db, FakeClient([intent]), payment_hints=profiles  # type: ignore[arg-type]
        )

        answer = session.handle("午饭1元")

        self.assertIn("已记录消费", answer)
        self.assertIn("paypay系", answer)
        row = self.db.connection.execute(
            "SELECT account_id,category_id FROM transactions WHERE source='natural_language_api'"
        ).fetchone()
        self.assertEqual(self.db.account("PayPay券")["id"], row["account_id"])
        self.assertEqual("餐饮", self.db.connection.execute(
            "SELECT name FROM categories WHERE id=?", (row["category_id"],)
        ).fetchone()["name"])

    def test_grocery_expense_uses_universal_rule_excluding_only_dining(self) -> None:
        profiles = [
            {
                "payment_method": "paypay系",
                "purpose": "默认所有外食以及煤气费由此账户扣款；付款顺序：PayPay券 → PayPay钱包 → PayPay Card。",
            },
            {
                "payment_method": "乐天card",
                "purpose": "默认所有除外食之外的消费均由此账户扣款。",
            },
        ]
        intent = expense_intent(account=None)
        intent["category"] = "食材"
        intent["description"] = "超市买菜"
        intent["payment_profile_index"] = None
        session = NaturalLanguageSession(
            self.db, FakeClient([intent]), payment_hints=profiles  # type: ignore[arg-type]
        )

        answer = session.handle("超市买菜1元")

        self.assertIn("已记录消费", answer)
        self.assertIn("Rakuten Card", answer)
        row = self.db.connection.execute(
            "SELECT account_id,category_id FROM transactions WHERE source='natural_language_api'"
        ).fetchone()
        self.assertEqual(self.db.account("Rakuten Card")["id"], row["account_id"])
        self.assertEqual("食材", self.db.connection.execute(
            "SELECT name FROM categories WHERE id=?", (row["category_id"],)
        ).fetchone()["name"])

    def test_explicit_gas_scene_overrides_broad_non_dining_rule(self) -> None:
        profiles = [
            {
                "payment_method": "paypay系",
                "purpose": "默认用于外食和煤气费；付款顺序：PayPay券 → PayPay钱包 → PayPay Card。",
            },
            {
                "payment_method": "乐天card",
                "purpose": "默认所有除外食之外的消费均由此账户扣款。",
            },
        ]
        intent = expense_intent(account=None)
        intent["category"] = "通信与账单"
        intent["description"] = "煤气费"
        # Even if the model points at the broad rule, the explicit gas scene wins.
        intent["payment_profile_index"] = 2
        session = NaturalLanguageSession(
            self.db, FakeClient([intent]), payment_hints=profiles  # type: ignore[arg-type]
        )

        answer = session.handle("煤气费1元")

        self.assertIn("已记录消费", answer)
        row = self.db.connection.execute(
            "SELECT account_id FROM transactions WHERE source='natural_language_api'"
        ).fetchone()
        self.assertEqual(self.db.account("PayPay券")["id"], row["account_id"])

    def test_universal_exclusion_detection_handles_common_language_forms(self) -> None:
        cases = (
            ("默认所有除外食之外的消费均由此账户扣款", True),
            ("默认所有外食以外的消费均由此账户扣款", True),
            ("所有消费，餐饮除外", True),
            ("all purchases except dining", True),
            ("全ての支出（外食を除く）", True),
            ("默认所有外食以及煤气费由此账户扣款", False),
            ("所有外食消费，除非另有说明", False),
            ("日常消费，除非另有说明", False),
        )
        for purpose, expected in cases:
            with self.subTest(purpose=purpose):
                self.assertEqual(
                    expected,
                    NaturalLanguageSession._is_universal_exclusion_rule(purpose),
                )

    def test_model_selected_specific_rule_can_cover_new_unmapped_category(self) -> None:
        profiles = [
            {"payment_method": "宠物专用卡", "purpose": "宠物医疗和用品消费。"},
            {"payment_method": "乐天card", "purpose": "所有除餐饮之外的消费。"},
        ]
        session = NaturalLanguageSession(
            self.db, FakeClient([]), payment_hints=profiles  # type: ignore[arg-type]
        )
        intent = expense_intent(account=None)
        intent["category"] = "宠物医疗"
        intent["payment_profile_index"] = 1

        self.assertEqual(profiles[0], session._payment_profile_for_intent(intent))

    def test_multiple_matching_specific_rules_remain_ambiguous(self) -> None:
        profiles = [
            {"payment_method": "PayPay", "purpose": "超市购物和买菜使用。"},
            {"payment_method": "Rakuten Card", "purpose": "食材采购使用。"},
        ]
        intent = expense_intent(account=None)
        intent["category"] = "食材"
        intent["description"] = "超市买菜"
        intent["payment_profile_index"] = 1
        session = NaturalLanguageSession(
            self.db, FakeClient([intent]), payment_hints=profiles  # type: ignore[arg-type]
        )

        answer = session.handle("超市买菜1元")

        self.assertIn("使用哪个账户", answer)
        self.assertEqual(0, self.db.connection.execute(
            "SELECT COUNT(*) FROM transactions WHERE source='natural_language_api'"
        ).fetchone()[0])

    def test_daiso_only_merchant_is_not_misclassified_as_dining_or_paypay(self) -> None:
        profiles = [
            {
                "payment_method": "paypay系",
                "purpose": "默认所有外食以及煤气费由此账户扣款；付款顺序：PayPay券 → PayPay钱包 → PayPay Card。",
            },
            {
                "payment_method": "乐天card",
                "purpose": "默认所有除外食之外的消费均由此账户扣款。",
            },
        ]
        intent = expense_intent(account=None)
        intent["category"] = "餐饮"
        intent["description"] = "大创消费"
        intent["payment_profile_index"] = 1
        session = NaturalLanguageSession(
            self.db, FakeClient([intent]), payment_hints=profiles  # type: ignore[arg-type]
        )

        answer = session.handle("大创消费1元")

        self.assertIn("已记录消费", answer)
        self.assertIn("其他", answer)
        self.assertIn("Rakuten Card", answer)
        self.assertNotIn("PayPay券", answer)
        row = self.db.connection.execute(
            "SELECT account_id,category_id FROM transactions WHERE source='natural_language_api'"
        ).fetchone()
        self.assertEqual(self.db.account("Rakuten Card")["id"], row["account_id"])
        self.assertEqual("其他", self.db.connection.execute(
            "SELECT name FROM categories WHERE id=?", (row["category_id"],)
        ).fetchone()["name"])

    def test_japanese_supermarket_name_only_uses_grocery_category_hint(self) -> None:
        intent = expense_intent(account=None)
        intent["category"] = "餐饮"
        intent["description"] = "ライフ"
        session = NaturalLanguageSession(
            self.db,
            FakeClient([intent]),  # type: ignore[arg-type]
            payment_hints=[
                {"payment_method": "乐天card", "purpose": "所有外食之外的消费。"}
            ],
        )

        answer = session.handle("ライフ消费1元")

        self.assertIn("已记录消费", answer)
        self.assertIn("食材", answer)
        row = self.db.connection.execute(
            "SELECT category_id FROM transactions WHERE source='natural_language_api'"
        ).fetchone()
        self.assertEqual("食材", self.db.connection.execute(
            "SELECT name FROM categories WHERE id=?", (row["category_id"],)
        ).fetchone()["name"])

    def test_named_item_or_meal_overrides_store_type_fallback(self) -> None:
        profiles = [
            {
                "payment_method": "paypay系",
                "purpose": "外食场景使用；付款顺序：PayPay券 → PayPay钱包 → PayPay Card。",
            },
            {
                "payment_method": "乐天card",
                "purpose": "所有除外食之外的消费。",
            },
        ]
        intent = expense_intent(account=None)
        intent["category"] = "日用品"
        intent["description"] = "大创纸巾"
        intent["payment_profile_index"] = 2
        session = NaturalLanguageSession(
            self.db, FakeClient([intent]), payment_hints=profiles  # type: ignore[arg-type]
        )

        answer = session.handle("大创纸巾1元")

        self.assertIn("已记录消费", answer)
        row = self.db.connection.execute(
            "SELECT category_id FROM transactions WHERE source='natural_language_api'"
        ).fetchone()
        self.assertEqual("日用品", self.db.connection.execute(
            "SELECT name FROM categories WHERE id=?", (row["category_id"],)
        ).fetchone()["name"])

    def test_explicit_lunch_at_a_mixed_retailer_still_counts_as_dining(self) -> None:
        profiles = [
            {
                "payment_method": "paypay系",
                "purpose": "外食场景使用；付款顺序：PayPay券 → PayPay钱包 → PayPay Card。",
            },
            {
                "payment_method": "乐天card",
                "purpose": "所有除外食之外的消费。",
            },
        ]
        intent = expense_intent(account=None)
        intent["category"] = "其他"
        intent["description"] = "ダイソー昼食"
        intent["payment_profile_index"] = 2
        session = NaturalLanguageSession(
            self.db, FakeClient([intent]), payment_hints=profiles  # type: ignore[arg-type]
        )

        answer = session.handle("ダイソーで昼食1円")

        self.assertIn("已记录消费", answer)
        self.assertIn("PayPay券", answer)
        row = self.db.connection.execute(
            "SELECT account_id,category_id FROM transactions WHERE source='natural_language_api'"
        ).fetchone()
        self.assertEqual(self.db.account("PayPay券")["id"], row["account_id"])
        self.assertEqual("餐饮", self.db.connection.execute(
            "SELECT name FROM categories WHERE id=?", (row["category_id"],)
        ).fetchone()["name"])

    def test_deduction_order_keyword_routes_paypay_profile(self) -> None:
        profile = {
            "payment_method": "paypay系",
            "purpose": "默认所有外食以及煤气费由此账户扣款，扣款顺序：paypay券 → paypay余额 → paypay card",
        }
        intent = expense_intent(account=None, question="请问这笔交易使用哪个账户？")
        session = NaturalLanguageSession(
            self.db, FakeClient([intent]), payment_hints=[profile]  # type: ignore[arg-type]
        )

        answer = session.handle("午饭1元")

        self.assertIn("已记录消费", answer)
        self.assertIn("PayPay券", answer)
        row = self.db.connection.execute(
            "SELECT account_id FROM transactions WHERE source='natural_language_api'"
        ).fetchone()
        self.assertEqual(self.db.account("PayPay券")["id"], row["account_id"])

    def test_chinese_rakuten_card_alias_resolves_to_canonical_account(self) -> None:
        intent = expense_intent(account="乐天信用卡")
        intent["category"] = "日用品"
        intent["description"] = "文具"
        session = NaturalLanguageSession(self.db, FakeClient([intent]))  # type: ignore[arg-type]

        answer = session.handle("买文具1日元，用乐天信用卡")

        self.assertIn("已记录消费", answer)
        row = self.db.connection.execute(
            "SELECT account_id FROM transactions WHERE source='natural_language_api'"
        ).fetchone()
        self.assertEqual(self.db.account("Rakuten Card")["id"], row["account_id"])

    def test_explicit_localized_points_account_overrides_saved_card_rule_and_model_guess(self) -> None:
        intent = expense_intent(account="Rakuten Card")
        intent.update({
            "amount": "300",
            "category": "日用品",
            "description": "USB转换器",
            "payment_profile_index": 1,
        })
        session = NaturalLanguageSession(
            self.db,
            FakeClient([intent]),  # type: ignore[arg-type]
            payment_hints=[{
                "payment_method": "Rakuten Card",
                "purpose": "默认所有日用品由此账户扣款。",
            }],
        )

        for alias in ("煤炉point", "煤炉积分", "Mercari point", "Mercari积分", "メルカリポイント"):
            with self.subTest(alias=alias):
                self.assertEqual(
                    "Mercari积分",
                    session._explicit_account_in_current_message(f"买USB转换器300日元，用了{alias}"),
                )

        answer = session.handle("买了个USB转换器300日元，用的煤炉point")

        self.assertIn("已记录消费", answer)
        self.assertIn("Mercari积分", answer)
        self.assertNotIn("Rakuten Card", answer)
        row = self.db.connection.execute(
            "SELECT account_id,amount_minor FROM transactions WHERE source='natural_language_api'"
        ).fetchone()
        self.assertEqual(
            (self.db.account("Mercari积分")["id"], 300),
            (row["account_id"], row["amount_minor"]),
        )

    def test_new_card_with_english_product_name_accepts_chinese_or_japanese_card_term(self) -> None:
        self.db.add_account(
            name="JCB Card", account_type="credit", currency="JPY",
            opening_balance=0, opening_date="2026-10-15", completeness="partial",
        )
        intent = expense_intent(account="JCB信用卡")
        intent["category"] = "日用品"
        intent["description"] = "文具"
        session = NaturalLanguageSession(self.db, FakeClient([intent]))  # type: ignore[arg-type]

        answer = session.handle("买文具1日元，用JCB信用卡")

        self.assertIn("已记录消费", answer)
        row = self.db.connection.execute(
            "SELECT account_id FROM transactions WHERE source='natural_language_api'"
        ).fetchone()
        self.assertEqual(self.db.account("JCB Card")["id"], row["account_id"])

    def test_chinese_rakuten_card_payment_rule_routes_to_registered_card(self) -> None:
        intent = expense_intent(account=None)
        intent["category"] = "日用品"
        intent["description"] = "文具"
        intent["payment_profile_index"] = 1
        profile = {
            "payment_method": "乐天card",
            "purpose": "默认所有除餐饮之外的消费均由此账户扣款。",
        }
        session = NaturalLanguageSession(
            self.db, FakeClient([intent]), payment_hints=[profile]  # type: ignore[arg-type]
        )

        answer = session.handle("买文具1日元")

        self.assertIn("已记录消费", answer)
        row = self.db.connection.execute(
            "SELECT account_id FROM transactions WHERE source='natural_language_api'"
        ).fetchone()
        self.assertEqual(self.db.account("Rakuten Card")["id"], row["account_id"])

    def test_registered_points_account_is_used_when_it_is_first_and_sufficient(self) -> None:
        profile = {
            "payment_method": "Rakuten Pay",
            "purpose": "水电费。付款优先顺序：Rakuten积分 → Rakuten Pay余额 → Rakuten Card。",
        }
        intent = expense_intent(account=None)
        intent["amount"] = "100"
        intent["payment_profile_index"] = 1
        session = NaturalLanguageSession(
            self.db,
            FakeClient([intent]),  # type: ignore[arg-type]
            payment_hints=[profile],
        )

        answer = session.handle("水费100日元")

        self.assertIn("已记录消费", answer)
        self.assertIn("100点（100 JPY等值）", answer)
        self.assertIn("Rakuten积分", answer)
        row = self.db.connection.execute(
            "SELECT account_id,currency,amount_minor FROM transactions WHERE source='natural_language_api'"
        ).fetchone()
        self.assertEqual(self.db.account("Rakuten积分")["id"], row["account_id"])
        self.assertEqual((row["currency"], row["amount_minor"]), ("JPY", 100))

    def test_explicit_points_income_is_reported_as_points_but_saved_as_jpy(self) -> None:
        intent = expense_intent(account="Rakuten积分")
        intent.update({
            "action": "income",
            "amount": "1",
            "currency": "PTS",
            "category": "其他收入",
            "description": "积分奖励",
        })
        session = NaturalLanguageSession(self.db, FakeClient([intent]))  # type: ignore[arg-type]

        answer = session.handle("获得乐天积分1点")

        self.assertIn("已记录收入", answer)
        self.assertIn("1点（1 JPY等值）", answer)
        row = self.db.connection.execute(
            "SELECT currency,amount_minor FROM transactions WHERE source='natural_language_api'"
        ).fetchone()
        self.assertEqual((row["currency"], row["amount_minor"]), ("JPY", 1))

    def test_partial_points_balance_splits_into_later_jpy_wallet_and_credit(self) -> None:
        intent = expense_intent(account=None)
        intent["amount"] = "1000"
        intent["payment_profile_index"] = 1
        profile = {
            "payment_method": "Rakuten Pay",
            "purpose": "水电费。付款优先顺序：Rakuten积分 → Rakuten Pay余额 → Rakuten Card。",
        }
        session = NaturalLanguageSession(
            self.db, FakeClient([intent]), payment_hints=[profile]  # type: ignore[arg-type]
        )

        answer = session.handle("电费1000日元")

        self.assertIn("已记录消费", answer)
        self.assertIn("300点（300 JPY等值）", answer)
        rows = self.db.connection.execute(
            """SELECT a.name,t.amount_minor,t.currency FROM transactions t
               JOIN accounts a ON a.id=t.account_id
               WHERE t.source='natural_language_api' ORDER BY t.id"""
        ).fetchall()
        self.assertEqual(
            [(row["name"], row["amount_minor"], row["currency"]) for row in rows],
            [("Rakuten积分", 300, "JPY"), ("Rakuten Pay", 700, "JPY")],
        )
        self.assertEqual(sum(row["amount_minor"] for row in rows), 1000)

    def test_saved_priority_overrides_unstated_model_account(self) -> None:
        intent = expense_intent(account="PayPay Card")
        intent["payment_profile_index"] = 1
        profile = {
            "payment_method": "PayPay",
            "purpose": "外食用。付款优先顺序：PayPay券 → PayPay积分 → PayPay钱包 → PayPay Card。",
        }
        fake = FakeClient([intent])
        session = NaturalLanguageSession(self.db, fake, payment_hints=[profile])  # type: ignore[arg-type]
        answer = session.handle("午饭1日元")

        self.assertIn("已记录消费", answer)
        row = self.db.connection.execute(
            "SELECT account_id FROM transactions WHERE source='natural_language_api'"
        ).fetchone()
        self.assertEqual(self.db.account("PayPay券")["id"], row["account_id"])

    def test_priority_splits_partial_voucher_and_wallet_balance_atomically(self) -> None:
        intent = expense_intent(account=None)
        intent["amount"] = "1000"
        intent["payment_profile_index"] = 1
        profile = {
            "payment_method": "PayPay",
            "purpose": "外食用。付款优先顺序：PayPay券 → PayPay积分 → PayPay钱包 → PayPay Card。",
        }
        session = NaturalLanguageSession(
            self.db, FakeClient([intent]), payment_hints=[profile]  # type: ignore[arg-type]
        )

        answer = session.handle("午饭1000日元")

        self.assertIn("已记录消费", answer)
        rows = self.db.connection.execute(
            """SELECT t.amount_minor,a.name account_name FROM transactions t
               JOIN accounts a ON a.id=t.account_id
               WHERE t.source='natural_language_api' ORDER BY t.id"""
        ).fetchall()
        self.assertEqual(
            [(row["account_name"], row["amount_minor"]) for row in rows],
            [("PayPay券", 800), ("PayPay钱包", 200)],
        )
        self.assertEqual(sum(row["amount_minor"] for row in rows), 1000)
        self.assertEqual(self.db.account_balance_minor(self.db.account("PayPay券")["id"]), 0)
        self.assertEqual(self.db.account_balance_minor(self.db.account("PayPay钱包")["id"]), 1800)
        self.assertIn("默认顺序分摊", answer)

    def test_reported_825_yen_lunch_splits_coupon_and_wallet(self) -> None:
        intent = expense_intent(account=None)
        intent.update({
            "date": "2026-10-16",
            "amount": "825",
            "description": "午饭",
            "payment_profile_index": 1,
        })
        profile = {
            "payment_method": "PayPay",
            "purpose": "通常用于外食。付款优先顺序：PayPay券 → PayPay积分 → PayPay钱包 → PayPay Card。",
        }
        session = NaturalLanguageSession(
            self.db, FakeClient([intent]), payment_hints=[profile]  # type: ignore[arg-type]
        )

        answer = session.handle("午饭825")

        self.assertIn("800 JPY", answer)
        self.assertIn("25 JPY", answer)
        rows = self.db.connection.execute(
            """SELECT t.amount_minor,a.name account_name FROM transactions t
               JOIN accounts a ON a.id=t.account_id
               WHERE t.source='natural_language_api' ORDER BY t.id"""
        ).fetchall()
        self.assertEqual(
            [(row["account_name"], row["amount_minor"]) for row in rows],
            [("PayPay券", 800), ("PayPay钱包", 25)],
        )
        self.assertEqual(sum(row["amount_minor"] for row in rows), 825)

    def test_split_writer_rechecks_balances_and_rolls_back_all_rows(self) -> None:
        before = self.db.connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]

        with self.assertRaisesRegex(LedgerError, "当前余额已变化"):
            self.db.add_split_expense(
                occurred_on="2026-10-16",
                amount="1000",
                currency="JPY",
                allocations=[("PayPay券", 801), ("PayPay钱包", 199)],
                category_name="餐饮",
                descriptions=["午饭（券）", "午饭（钱包）"],
                source="test",
            )

        after = self.db.connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        self.assertEqual(after, before)

    def test_priority_does_not_write_partial_expense_when_total_funds_are_insufficient(self) -> None:
        intent = expense_intent(account=None)
        intent["amount"] = "50000"
        intent["payment_profile_index"] = 1
        profile = {
            "payment_method": "PayPay",
            "purpose": "外食用。付款优先顺序：PayPay券 → PayPay积分 → PayPay钱包 → PayPay Card。",
        }
        session = NaturalLanguageSession(
            self.db, FakeClient([intent]), payment_hints=[profile]  # type: ignore[arg-type]
        )
        before = self.db.connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]

        answer = session.handle("午饭50000日元")

        self.assertNotIn("已记录消费", answer)
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0], before)

    def test_ollama_empty_length_limited_response_has_specific_error(self) -> None:
        class Response:
            def __enter__(self) -> Response:
                return self

            def __exit__(self, *_: object) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps(
                    {"message": {"content": "", "thinking": "..."}, "done_reason": "length"}
                ).encode()

        client = OpenAICompatibleClient(
            "", api_url="http://localhost:11434/v1/chat/completions", model="qwen3.5:4b", opener=lambda *_args, **_kwargs: Response()
        )
        with self.assertRaisesRegex(NaturalLanguageError, "输出最终答案前达到长度上限"):
            client.complete([{"role": "user", "content": "午饭1元"}])

    def test_missing_payment_account_asks_before_writing(self) -> None:
        fake = FakeClient([expense_intent(account=None, question="糖是用哪个账户支付的？")])
        session = NaturalLanguageSession(self.db, fake)  # type: ignore[arg-type]
        before = self.db.connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]

        answer = session.handle("买糖1日元")

        self.assertIn("哪个账户", answer)
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0], before)

    def test_account_clarification_then_records_one_expense(self) -> None:
        fake = FakeClient([expense_intent(account=None, question="糖是用哪个账户支付的？")])
        session = NaturalLanguageSession(self.db, fake)  # type: ignore[arg-type]

        self.assertIn("哪个账户", session.handle("买糖1日元"))
        answer = session.handle("PayPay券")

        self.assertIn("已记录消费", answer)
        row = self.db.connection.execute(
            "SELECT kind,amount_minor,account_id,source FROM transactions WHERE source='natural_language_api'"
        ).fetchone()
        self.assertEqual((row["kind"], row["amount_minor"], row["source"]), ("expense", 1, "natural_language_api"))
        self.assertEqual(self.db.account("PayPay券")["id"], row["account_id"])
        self.assertEqual(self.db.account_balance_minor(self.db.account("PayPay券")["id"]), 799)
        self.assertEqual(len(fake.messages), 1)

    def test_unknown_model_account_does_not_write(self) -> None:
        fake = FakeClient([expense_intent(account="猜测出来的账户")])
        session = NaturalLanguageSession(self.db, fake)  # type: ignore[arg-type]
        before = self.db.connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]

        answer = session.handle("买糖1日元，用猜测出来的账户")

        self.assertIn("找不到账户", answer)
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0], before)

    def test_model_cannot_invent_an_unmentioned_payment_account(self) -> None:
        fake = FakeClient([expense_intent(account="PayPay券")])
        session = NaturalLanguageSession(self.db, fake)  # type: ignore[arg-type]
        before = self.db.connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]

        answer = session.handle("买糖1日元")

        self.assertIn("明确告诉我使用哪个账户", answer)
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0], before)

    def test_model_cannot_choose_a_negated_account(self) -> None:
        fake = FakeClient([expense_intent(account="PayPay券")])
        session = NaturalLanguageSession(self.db, fake)  # type: ignore[arg-type]
        before = self.db.connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]

        answer = session.handle("别用PayPay券，买糖1日元")

        self.assertIn("明确告诉我使用哪个账户", answer)
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0], before)

    def test_recognition_word_does_not_negate_a_later_account_mention(self) -> None:
        session = NaturalLanguageSession(self.db, FakeClient([]))  # type: ignore[arg-type]
        self.assertFalse(
            session._account_is_negated_in_text(
                "PayPay券", "请识别附件中的收据，再使用PayPay券支付。"
            )
        )

    def test_selected_default_payment_hint_can_fill_an_unstated_expense_account(self) -> None:
        fake = FakeClient([expense_intent(account="PayPay券")])
        session = NaturalLanguageSession(
            self.db,
            fake,  # type: ignore[arg-type]
            payment_hint={"payment_method": "PayPay券", "purpose": "小额零食"},
        )

        answer = session.handle("买糖1日元")

        self.assertIn("已记录消费", answer)
        row = self.db.connection.execute(
            "SELECT account_id FROM transactions WHERE source='natural_language_api'"
        ).fetchone()
        self.assertEqual(self.db.account("PayPay券")["id"], row["account_id"])
        prompt = fake.messages[0][0]["content"]
        self.assertIn("PayPay券", prompt)
        self.assertIn("小额零食", prompt)

    def test_explicit_payment_method_overrides_default_hint(self) -> None:
        fake = FakeClient([expense_intent(account="PayPay券")])
        session = NaturalLanguageSession(
            self.db,
            fake,  # type: ignore[arg-type]
            payment_hint={"payment_method": "PayPay券", "purpose": "小额零食"},
        )
        before = self.db.connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]

        answer = session.handle("买糖1日元，用PayPay钱包付")

        self.assertIn("已记录消费", answer)
        row = self.db.connection.execute(
            "SELECT account_id FROM transactions WHERE source='natural_language_api'"
        ).fetchone()
        self.assertEqual(self.db.account("PayPay钱包")["id"], row["account_id"])
        self.assertEqual(self.db.connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0], before + 1)

    def test_default_payment_hint_does_not_fill_income_account(self) -> None:
        intent = expense_intent(account="PayPay券")
        intent.update({"action": "income", "category": "退款/返现", "description": "积分返还"})
        fake = FakeClient([intent])
        session = NaturalLanguageSession(
            self.db,
            fake,  # type: ignore[arg-type]
            payment_hint={"payment_method": "PayPay券", "purpose": "小额零食"},
        )

        answer = session.handle("收到返现1日元")

        self.assertIn("明确告诉我使用哪个账户", answer)

    def test_friend_gift_paypay_incoming_is_saved_even_when_model_says_transfer(self) -> None:
        # Reproduce the exact request and model error from the screenshot: the
        # deterministic transaction checks correct the model's transfer label.
        incomplete_transfer = {
            "action": "transfer",
            "date": "2026-10-16",
            "amount": "2100",
            "currency": "JPY",
            "account": None,
            "to_account": None,
            "to_amount": None,
            "category": None,
            "description": "朋友转账赠与paypay收款2100",
            "memo_only": False,
            "question": "这笔来自朋友的2100日元转账，是赠与、报销还是借款？另外，请确认收款账户。",
            "reply": None,
            "payment_profile_index": None,
        }
        session = NaturalLanguageSession(
            self.db, FakeClient([incomplete_transfer])  # type: ignore[arg-type]
        )

        answer = session.handle("朋友转账赠与paypay收款2100")

        self.assertIn("已记录收入", answer)
        self.assertIsNone(session.pending_state)
        self.assertEqual(session.history, [])
        row = self.db.connection.execute(
            "SELECT t.kind,t.amount_minor,t.currency,a.name AS account_name,c.name AS category_name "
            "FROM transactions t JOIN accounts a ON a.id=t.account_id "
            "JOIN categories c ON c.id=t.category_id WHERE t.source='natural_language_api'"
        ).fetchone()
        self.assertEqual(
            tuple(row),
            ("income", 2100, "JPY", "PayPay钱包", "其他收入"),
        )

    def test_generic_income_category_is_mapped_from_explicit_gift_nature(self) -> None:
        intent = expense_intent(account="PayPay钱包")
        intent.update({
            "action": "income",
            "amount": "2100",
            "category": "收入",
            "description": "朋友赠与",
        })
        session = NaturalLanguageSession(
            self.db, FakeClient([intent])  # type: ignore[arg-type]
        )

        answer = session.handle("朋友把2100日元礼金转到PayPay钱包，明确是赠与且不用偿还")

        self.assertIn("已记录收入", answer)
        row = self.db.connection.execute(
            "SELECT t.kind,t.amount_minor,t.currency,a.name account_name,c.name category_name "
            "FROM transactions t JOIN accounts a ON a.id=t.account_id "
            "JOIN categories c ON c.id=t.category_id WHERE t.source='natural_language_api'"
        ).fetchone()
        self.assertEqual(tuple(row), ("income", 2100, "JPY", "PayPay钱包", "其他收入"))

    def test_gift_nature_reply_can_also_resolve_paypay_wallet_from_context(self) -> None:
        incomplete_income = {
            "action": "income",
            "date": "2026-10-16",
            "amount": "2100",
            "currency": "JPY",
            "account": None,
            "to_account": None,
            "to_amount": None,
            "category": None,
            "description": "朋友给我转账2100到PayPay",
            "memo_only": False,
            "question": "这笔转账是赠与、报销还是借款？请确认收款账户。",
            "reply": None,
            "payment_profile_index": None,
        }
        session = NaturalLanguageSession(
            self.db, FakeClient([incomplete_income])  # type: ignore[arg-type]
        )

        first_answer = session.handle("朋友转账给我2100到PayPay")

        self.assertIn("款项性质", first_answer)
        self.assertEqual(session.pending_state["awaiting_slot"], "income_nature")  # type: ignore[index]
        second_answer = session.handle("赠与 余额")

        self.assertIn("已记录收入", second_answer)
        self.assertIsNone(session.pending_state)
        row = self.db.connection.execute(
            "SELECT t.kind,t.amount_minor,t.currency,a.name AS account_name,c.name AS category_name "
            "FROM transactions t JOIN accounts a ON a.id=t.account_id "
            "JOIN categories c ON c.id=t.category_id WHERE t.source='natural_language_api'"
        ).fetchone()
        self.assertEqual(
            tuple(row),
            ("income", 2100, "JPY", "PayPay钱包", "其他收入"),
        )

    def test_friend_incoming_transfer_asks_nature_not_an_outgoing_account(self) -> None:
        mistaken_transfer = {
            "action": "transfer",
            "date": "2026-10-16",
            "amount": "2100",
            "currency": "JPY",
            "account": None,
            "to_account": None,
            "to_amount": None,
            "category": None,
            "description": "PayPay接受朋友转账2100",
            "memo_only": False,
            "question": "请补充转出账户。",
            "reply": None,
            "payment_profile_index": None,
        }
        session = NaturalLanguageSession(
            self.db, FakeClient([mistaken_transfer])  # type: ignore[arg-type]
        )

        first_answer = session.handle("PayPay接受朋友转账2100")

        self.assertIn("收款账户为PayPay钱包", first_answer)
        self.assertIn("不需要提供对方的转出账户", first_answer)
        self.assertIn("款项性质", first_answer)
        self.assertEqual(session.pending_state["intent"]["action"], "income")  # type: ignore[index]
        self.assertEqual(session.pending_state["awaiting_slot"], "income_nature")  # type: ignore[index]
        self.assertEqual(
            self.db.connection.execute(
                "SELECT COUNT(*) FROM transactions WHERE source='natural_language_api'"
            ).fetchone()[0],
            0,
        )

        answer_after_combined_reply = session.handle("赠与 余额")

        self.assertIn("已记录收入", answer_after_combined_reply)
        row = self.db.connection.execute(
            "SELECT t.kind,t.amount_minor,t.currency,a.name AS account_name,c.name AS category_name "
            "FROM transactions t JOIN accounts a ON a.id=t.account_id "
            "JOIN categories c ON c.id=t.category_id WHERE t.source='natural_language_api'"
        ).fetchone()
        self.assertEqual(
            tuple(row),
            ("income", 2100, "JPY", "PayPay钱包", "其他收入"),
        )

    def test_old_pending_incoming_transfer_converts_when_user_rejects_source_account(self) -> None:
        session = NaturalLanguageSession(self.db, FakeClient([]))  # type: ignore[arg-type]
        original = "PayPay接受朋友转账2100"
        session.history = [
            {"role": "user", "content": original},
            {"role": "assistant", "content": "请补充转出账户。"},
        ]
        session.pending_state = {
            "intent": {
                "action": "transfer",
                "date": "2026-10-16",
                "amount": "2100",
                "currency": "JPY",
                "account": None,
                "to_account": "PayPay钱包",
                "to_amount": None,
                "category": None,
                "description": original,
                "memo_only": False,
                "question": "请补充转出账户。",
                "reply": None,
                "payment_profile_index": None,
            },
            "original_text": original,
            "question": "请补充转出账户。",
            "awaiting_slot": "account",
        }

        answer = session.handle("不需要转出")

        self.assertIn("收款账户为PayPay钱包", answer)
        self.assertIn("款项性质", answer)
        self.assertNotIn("请说完整账户名称", answer)
        self.assertNotIn("请补充转出账户", answer)
        self.assertNotIn("请从账户列表中选择", answer)
        self.assertEqual(session.pending_state["intent"]["action"], "income")  # type: ignore[index]
        self.assertEqual(session.pending_state["awaiting_slot"], "income_nature")  # type: ignore[index]
        self.assertEqual(
            self.db.connection.execute(
                "SELECT COUNT(*) FROM transactions WHERE source='natural_language_api'"
            ).fetchone()[0],
            0,
        )

    def test_external_incoming_detector_does_not_reclassify_user_to_friend_transfer(self) -> None:
        self.assertTrue(
            NaturalLanguageSession._is_external_incoming_transfer("朋友转账给我2100到PayPay")
        )
        self.assertFalse(
            NaturalLanguageSession._is_external_incoming_transfer("我给朋友转账2100")
        )
        self.assertFalse(
            NaturalLanguageSession._is_external_incoming_transfer("朋友转账2100")
        )

    def test_natural_language_repayment_is_transfer_only(self) -> None:
        transfer = {
            "action": "transfer",
            "date": "2026-10-16",
            "amount": "1000",
            "currency": "JPY",
            "account": "瑞穗银行",
            "to_account": "Rakuten Card",
            "to_amount": None,
            "category": None,
            "description": "信用卡还款",
            "memo_only": False,
            "question": None,
            "reply": None,
        }
        fake = FakeClient([transfer])
        session = NaturalLanguageSession(self.db, fake)  # type: ignore[arg-type]
        before_expenses = self.db.connection.execute(
            "SELECT COUNT(*) FROM transactions WHERE kind='expense'"
        ).fetchone()[0]

        answer = session.handle("2026-10-16 瑞穗银行还1000日元到Rakuten Card")

        self.assertIn("已记录转账/还款", answer)
        self.assertEqual(self.db.connection.execute(
            "SELECT COUNT(*) FROM transactions WHERE source='natural_language_api' AND kind='transfer'"
        ).fetchone()[0], 1)
        self.assertEqual(self.db.connection.execute(
            "SELECT COUNT(*) FROM transactions WHERE kind='expense'"
        ).fetchone()[0], before_expenses)
        self.assertEqual(session.history, [])

    def test_mercari_card_chinese_alias_is_accepted_as_registered_credit_account(self) -> None:
        transfer = {
            "action": "transfer",
            "date": "2026-10-16",
            "amount": "45500",
            "currency": "JPY",
            "account": "瑞穗银行",
            "to_account": "煤炉card",
            "to_amount": None,
            "category": None,
            "description": "煤炉卡还款",
            "memo_only": False,
            "question": None,
            "reply": None,
        }
        session = NaturalLanguageSession(self.db, FakeClient([transfer]))  # type: ignore[arg-type]

        answer = session.handle("今天瑞穗银行还煤炉卡45500日元")

        self.assertIn("已记录转账/还款", answer)
        row = self.db.connection.execute(
            "SELECT a.account_type,d.account_type,d.name FROM transactions t "
            "JOIN accounts a ON a.id=t.account_id JOIN accounts d ON d.id=t.to_account_id "
            "WHERE t.source='natural_language_api' AND t.kind='transfer'"
        ).fetchone()
        self.assertEqual(tuple(row), ("bank", "credit", "Mercari Card"))

    def test_card_repayment_uses_unique_saved_rule_even_if_model_mislabels_and_reverses_it(self) -> None:
        reversed_transfer = {
            "action": "expense",
            "date": None,
            "amount": "45500",
            "currency": "JPY",
            "account": "Mercari Card",
            "to_account": "瑞穗银行账户",
            "to_amount": None,
            "category": "餐饮",
            "description": "煤炉卡还款",
            "memo_only": False,
            "question": "请确认转出和转入账户",
            "reply": None,
            "payment_profile_index": None,
        }
        session = NaturalLanguageSession(
            self.db,
            FakeClient([reversed_transfer]),  # type: ignore[arg-type]
            payment_hints=[{
                "payment_method": "瑞穗银行账户",
                "purpose": "所有信用卡还款",
            }],
        )

        answer = session.handle("今天煤炉卡还款45500日元")

        self.assertIn("已记录转账/还款", answer)
        self.assertIn("按已保存的还款规则选择", answer)
        row = self.db.connection.execute(
            "SELECT a.name,d.name FROM transactions t "
            "JOIN accounts a ON a.id=t.account_id JOIN accounts d ON d.id=t.to_account_id "
            "WHERE t.source='natural_language_api' AND t.kind='transfer'"
        ).fetchone()
        self.assertEqual(tuple(row), ("瑞穗银行", "Mercari Card"))
        self.assertEqual(self.db.connection.execute(
            "SELECT COUNT(*) FROM transactions WHERE source='natural_language_api' AND kind='expense'"
        ).fetchone()[0], 0)

    def test_card_repayment_without_source_rule_asks_only_for_source_account(self) -> None:
        incomplete_transfer = {
            "action": "transfer",
            "date": None,
            "amount": "45500",
            "currency": "JPY",
            "account": None,
            "to_account": None,
            "to_amount": None,
            "category": None,
            "description": "煤炉卡还款",
            "memo_only": False,
            "question": "请告诉我转入账户和转出账户",
            "reply": None,
            "payment_profile_index": None,
        }
        session = NaturalLanguageSession(self.db, FakeClient([incomplete_transfer]))  # type: ignore[arg-type]

        answer = session.handle("今天煤炉卡还款45500日元")

        self.assertIn("Mercari Card", answer)
        self.assertIn("转出资金账户", answer)
        self.assertNotIn("转入账户", answer)
        self.assertEqual(self.db.connection.execute(
            "SELECT COUNT(*) FROM transactions WHERE source='natural_language_api'"
        ).fetchone()[0], 0)

    def test_explicit_repayment_source_overrides_saved_all_card_rule(self) -> None:
        incomplete_transfer = {
            "action": "transfer",
            "date": None,
            "amount": "1000",
            "currency": "JPY",
            "account": "瑞穗银行账户",
            "to_account": "煤炉card",
            "to_amount": None,
            "category": None,
            "description": "煤炉卡还款",
            "memo_only": False,
            "question": None,
            "reply": None,
            "payment_profile_index": None,
        }
        session = NaturalLanguageSession(
            self.db,
            FakeClient([incomplete_transfer]),  # type: ignore[arg-type]
            payment_hints=[{
                "payment_method": "瑞穗银行账户",
                "purpose": "所有信用卡还款",
            }],
        )

        answer = session.handle("今天PayPay钱包还煤炉卡1000日元")

        self.assertIn("已记录转账/还款", answer)
        self.assertNotIn("按已保存的还款规则选择", answer)
        row = self.db.connection.execute(
            "SELECT a.name,d.name FROM transactions t "
            "JOIN accounts a ON a.id=t.account_id JOIN accounts d ON d.id=t.to_account_id "
            "WHERE t.source='natural_language_api' AND t.kind='transfer'"
        ).fetchone()
        self.assertEqual(tuple(row), ("PayPay钱包", "Mercari Card"))

    def test_invalid_json_never_reaches_database(self) -> None:
        with self.assertRaises(NaturalLanguageError):
            _parse_intent("这不是JSON")
        with self.assertRaises(NaturalLanguageError):
            _parse_intent('{"action":"delete_everything"}')

    def test_missing_or_generic_action_uses_only_an_explicit_supported_hint(self) -> None:
        intent = expense_intent(account="PayPay券")
        intent["action"] = "purchase"
        self.assertEqual(
            _parse_intent(json.dumps(intent, ensure_ascii=False))["action"], "expense"
        )

        intent["action"] = "receipt"
        self.assertEqual(
            _parse_intent(
                json.dumps(intent, ensure_ascii=False), fallback_action="expense"
            )["action"],
            "expense",
        )

        intent["action"] = "create"
        self.assertEqual(
            _parse_intent(
                json.dumps(intent, ensure_ascii=False), fallback_action="expense"
            )["action"],
            "expense",
        )

        intent.pop("action")
        intent["transaction_type"] = "purchase"
        self.assertEqual(
            _parse_intent(
                json.dumps(intent, ensure_ascii=False), fallback_action="expense"
            )["action"],
            "expense",
        )

        intent["transaction_type"] = "delete_everything"
        with self.assertRaisesRegex(NaturalLanguageError, "记账类型无法识别"):
            _parse_intent(
                json.dumps(intent, ensure_ascii=False), fallback_action="expense"
            )

    def test_wrapped_or_array_expense_intents_are_normalized(self) -> None:
        wrapped = expense_intent(account="PayPay券")
        wrapped.pop("action")
        wrapped["type"] = "purchase"
        parsed_wrapper = _parse_intent(
            json.dumps({"result": wrapped}, ensure_ascii=False)
        )
        self.assertEqual((parsed_wrapper["action"], parsed_wrapper["amount"]), ("expense", "1"))

        array_item = expense_intent(account="PayPay券")
        array_item["action"] = "record_expense"
        parsed_array = _parse_intent(json.dumps([array_item], ensure_ascii=False))
        self.assertEqual((parsed_array["action"], parsed_array["amount"]), ("expense", "1"))

    def test_invalid_intent_field_types_are_rejected(self) -> None:
        intent = expense_intent(account="PayPay券")
        intent["memo_only"] = "false"
        with self.assertRaisesRegex(NaturalLanguageError, "备查状态格式不正确"):
            _parse_intent(json.dumps(intent, ensure_ascii=False))

    def test_model_metadata_fields_are_ignored_without_becoming_ledger_data(self) -> None:
        intent = expense_intent(account="PayPay券")
        intent["merchant_name"] = "模型补充的商家说明"
        intent["image_description"] = "模型补充的图片说明"

        parsed = _parse_intent(json.dumps(intent, ensure_ascii=False))

        self.assertEqual(parsed["amount"], "1")
        self.assertEqual(parsed["account"], "PayPay券")
        self.assertNotIn("merchant_name", parsed)
        self.assertNotIn("image_description", parsed)

    def test_batch_model_metadata_fields_are_ignored(self) -> None:
        item = {
            **expense_intent(account="PayPay券"),
            "source_text": "午饭1200日元",
            "visual_summary": "模型生成的摘要",
        }
        intent = {
            **expense_intent(account=None),
            "action": "batch",
            "model_notes": "额外说明",
            "transactions": [item],
        }

        parsed = _parse_intent(json.dumps(intent, ensure_ascii=False))

        self.assertEqual(parsed["action"], "batch")
        self.assertEqual(len(parsed["transactions"]), 1)
        self.assertEqual(parsed["transactions"][0]["amount"], "1")
        self.assertNotIn("visual_summary", parsed["transactions"][0])
        self.assertNotIn("model_notes", parsed)

    def test_single_transaction_array_is_normalized_when_it_matches_top_level(self) -> None:
        intent = expense_intent(account=None)
        intent.update({
            "date": None,
            "amount": None,
            "currency": None,
            "category": None,
            "description": None,
            "payment_profile_index": None,
        })
        item = expense_intent(account="PayPay钱包")
        item["category"] = "餐饮"
        item["description"] = "午饭"
        item["payment_profile_index"] = 2
        intent["transactions"] = [{**item, "source_text": "午饭825日元"}]

        parsed = _parse_intent(json.dumps(intent, ensure_ascii=False))

        self.assertEqual(parsed["action"], "expense")
        self.assertEqual(parsed["amount"], "1")
        self.assertEqual(parsed["account"], "PayPay钱包")
        self.assertEqual(parsed["description"], "午饭")
        self.assertEqual(parsed["payment_profile_index"], 2)
        self.assertIsNone(parsed["transactions"])

    def test_single_transaction_array_conflicts_and_multiple_items_are_rejected(self) -> None:
        intent = expense_intent(account="PayPay券")
        conflicting_item = expense_intent(account="PayPay券")
        conflicting_item["amount"] = "2"
        intent["transactions"] = [{**conflicting_item, "source_text": "午饭2日元"}]
        with self.assertRaisesRegex(NaturalLanguageError, "amount信息冲突"):
            _parse_intent(json.dumps(intent, ensure_ascii=False))

        intent = expense_intent(account="PayPay券")
        intent["transactions"] = [
            {**expense_intent(account="PayPay券"), "source_text": "一笔1日元"},
            {**expense_intent(account="PayPay券"), "source_text": "另一笔1日元"},
        ]
        with self.assertRaisesRegex(NaturalLanguageError, "多笔交易标成单笔"):
            _parse_intent(json.dumps(intent, ensure_ascii=False))

    def test_batch_retries_when_model_marks_enumerated_items_as_single_transaction(self) -> None:
        text = (
            "今天在Life超市分别购买牛奶218日元、吐司158日元、苹果398日元、"
            "青菜328日元、豆腐168日元。五笔各自独立消费。"
        )
        self.assertEqual(_explicit_transaction_segment_count(text), 5)

        item_data = [
            ("牛奶", "218", "牛奶218日元"),
            ("吐司", "158", "吐司158日元"),
            ("苹果", "398", "苹果398日元"),
            ("青菜", "328", "青菜328日元"),
            ("豆腐", "168", "豆腐168日元"),
        ]
        malformed_single = expense_intent(account="Rakuten Card")
        malformed_single.update({
            "account": None, "category": "食材", "description": "牛奶",
            "payment_profile_index": 1,
        })
        malformed_single["transactions"] = [
            {
                **expense_intent(account=None),
                "amount": amount,
                "category": "食材",
                "description": description,
                "payment_profile_index": 1,
                "source_text": source_text,
            }
            for description, amount, source_text in item_data
        ]

        items = [
            {
                **expense_intent(account=None),
                "date": "2026-10-16",
                "amount": amount,
                "category": "食材",
                "description": description,
                "payment_profile_index": 1,
                "source_text": source_text,
            }
            for description, amount, source_text in item_data
        ]
        batch = {
            "action": "batch", "date": None, "amount": None, "currency": None,
            "account": None, "to_account": None, "to_amount": None,
            "category": None, "description": None, "memo_only": False,
            "question": None, "reply": None, "payment_profile_index": None,
            "transactions": items,
        }
        fake = FakeClient([malformed_single, batch])
        session = NaturalLanguageSession(
            self.db,
            fake,  # type: ignore[arg-type]
            payment_hints=[{
                "payment_method": "Rakuten Card",
                "purpose": "食材采购付款顺序：Rakuten积分 → Rakuten Card",
            }],
        )

        answer = session.handle(text)

        self.assertEqual(len(fake.messages), 2)
        self.assertIn("批量完整性重试", str(fake.messages[1][0]["content"]))
        self.assertEqual(answer.count("已记录消费"), 5, answer)
        rows = self.db.connection.execute(
            "SELECT t.amount_minor,t.description,a.name FROM transactions t "
            "JOIN accounts a ON a.id=t.account_id "
            "WHERE t.source='natural_language_api' ORDER BY t.id"
        ).fetchall()
        self.assertEqual(sum(row["amount_minor"] for row in rows), 1270)
        items_seen = {
            item for item in ("牛奶", "吐司", "苹果", "青菜", "豆腐")
            if any(row["description"].startswith(item) for row in rows)
        }
        self.assertEqual(items_seen, {"牛奶", "吐司", "苹果", "青菜", "豆腐"})
        self.assertTrue(all(row["name"] in {"Rakuten积分", "Rakuten Card"} for row in rows))

    def test_batch_message_posts_every_transaction_and_keeps_cny_once_with_jpy_reporting(self) -> None:
        from decimal import Decimal

        from bookkeeping.fx_rates import ECB_SOURCE, JpyRate
        from bookkeeping.financial_statements import build_profit_statement

        self.db.add_account(
            name="人民币钱包", account_type="wallet", currency="CNY",
            opening_balance="100.00", opening_date="2026-10-15",
        )
        item_defaults = {
            "date": "2026-10-16",
            "to_account": None,
            "to_amount": None,
            "memo_only": False,
            "question": None,
            "reply": None,
            "payment_profile_index": None,
        }
        transactions = [
            {
                **item_defaults,
                "action": "expense", "amount": None, "currency": None,
                "account": "Rakuten Card", "category": "食材", "description": "鸡蛋",
                "payment_profile_index": 1, "source_text": "鸡蛋1元",
            },
            {
                **item_defaults,
                "action": "expense", "amount": "1", "currency": "JPY",
                "account": "PayPay券", "category": "餐饮", "description": "午饭",
                "payment_profile_index": 2, "source_text": "午饭1元",
            },
            {
                **item_defaults,
                "action": "expense", "amount": "1", "currency": "JPY",
                "account": "Mercari Card", "category": "娱乐", "description": "出去玩电玩",
                "payment_profile_index": 3, "source_text": "出去玩电玩1元",
            },
            {
                **item_defaults,
                "action": "expense", "amount": "1", "currency": "CNY",
                "account": "人民币钱包", "category": "日用品", "description": "淘宝买东西",
                "payment_profile_index": 4, "source_text": "淘宝买东西1人民币",
            },
        ]
        response = {
            "action": "batch", "date": None, "amount": None, "currency": None,
            "account": None, "to_account": None, "to_amount": None, "category": None,
            "description": None, "memo_only": False, "question": None, "reply": None,
            "payment_profile_index": None, "transactions": transactions,
        }
        # Simulate a local model returning a malformed empty batch. The
        # program must ask for a complete structured retry before posting.
        incomplete_batch = {
            "action": "batch", "date": None, "amount": None, "currency": None,
            "account": None, "to_account": None, "to_amount": None, "category": None,
            "description": None, "memo_only": False, "question": None, "reply": None,
            "payment_profile_index": None, "transactions": [],
        }
        fake = FakeClient([incomplete_batch, response])
        session = NaturalLanguageSession(
            self.db,
            fake,  # type: ignore[arg-type]
            payment_hints=[
                {"payment_method": "Rakuten Card", "purpose": "食材"},
                {"payment_method": "PayPay券", "purpose": "午饭 餐饮"},
                {"payment_method": "Mercari Card", "purpose": "电玩 娱乐"},
                {"payment_method": "人民币钱包", "purpose": "日用品"},
            ],
        )
        rate = JpyRate(Decimal("23.6"), "2026-10-16", ECB_SOURCE)

        with patch("bookkeeping.fx_rates.resolve_jpy_rate", return_value=rate):
            answer = session.handle(
                "2026年10月16日鸡蛋1元，午饭1元，出去玩电玩1元，淘宝买东西1人民币"
            )

        self.assertEqual(answer.count("已记录消费"), 4, answer)
        self.assertIn("第4笔", answer)
        self.assertEqual(len(fake.messages), 2)
        self.assertIn("批量完整性重试", str(fake.messages[1][0]["content"]))
        rows = self.db.connection.execute(
            "SELECT t.amount_minor,t.currency,t.jpy_equiv_minor,t.fx_rate,t.fx_rate_date,a.name "
            "FROM transactions t JOIN accounts a ON a.id=t.account_id "
            "WHERE t.source='natural_language_api' ORDER BY t.id"
        ).fetchall()
        self.assertEqual(len(rows), 4)
        self.assertEqual([row["name"] for row in rows], [
            "Rakuten Card", "PayPay券", "Mercari Card", "人民币钱包",
        ])
        self.assertEqual([(row["amount_minor"], row["currency"]) for row in rows], [
            (1, "JPY"), (1, "JPY"), (1, "JPY"), (100, "CNY"),
        ])
        self.assertEqual((rows[-1]["jpy_equiv_minor"], rows[-1]["fx_rate"], rows[-1]["fx_rate_date"]),
                         (24, "23.6", "2026-10-16"))
        self.assertIsNone(rows[0]["jpy_equiv_minor"])

        report = build_profit_statement(self.db, "2026-10-16")
        self.assertEqual(report["currencies"]["JPY"]["expense_minor"], 703)
        self.assertEqual(report["currencies"]["CNY"]["expense_minor"], 100)
        self.assertEqual(report["jpy_equivalent"]["expense_minor"], 727)
        self.assertEqual(report["jpy_equivalent"]["missing_conversion_count"], 0)


if __name__ == "__main__":
    unittest.main()
