"""Run real-model receipt checks sequentially against disposable ledger copies."""
from __future__ import annotations

import argparse
import json
import sqlite3
import tempfile
import time
from pathlib import Path

from bookkeeping.natural_language import NaturalLanguageSession, OpenAICompatibleClient, load_image_attachment
from bookkeeping.payment_preferences import PaymentPromptStore
from bookkeeping.secure_settings import ApiProfileStore
from bookkeeping.storage import Database, to_minor


class ProbeClient(OpenAICompatibleClient):
    def extract_local_receipt_fields(self, attachment):
        result = super().extract_local_receipt_fields(attachment)
        print("EXTRACTED_FIELDS", json.dumps(result, ensure_ascii=False), flush=True)
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--profile-id")
    parser.add_argument("--expect-amount", required=True)
    parser.add_argument("--expect-date", required=True)
    args = parser.parse_args()
    settings = ApiProfileStore().load()
    route = args.profile_id or settings.get("agent_vision_profile_ids", {}).get(
        "bookkeeping", settings.get("agent_profile_ids", {}).get("bookkeeping")
    )
    profile = next(p for p in settings["profiles"] if p["id"] == route)
    image = load_image_attachment(args.image)
    source_path = Path(__file__).resolve().parents[1] / "data" / "household_bookkeeping.sqlite3"
    print(json.dumps({"service": profile["name"], "model": profile["model"], "isolated_ledger": True}, ensure_ascii=False), flush=True)
    for run in range(1, args.repeat + 1):
        started = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="receipt-integration-") as temporary:
            destination = Path(temporary) / "ledger.sqlite3"
            source = sqlite3.connect(f"file:{source_path.as_posix()}?mode=ro", uri=True)
            target = sqlite3.connect(destination)
            try:
                source.backup(target)
            finally:
                target.close()
                source.close()
            database = Database(destination)
            try:
                database.initialize()
                before = database.connection.execute("SELECT count(*) FROM transactions").fetchone()[0]
                max_id = database.connection.execute("SELECT coalesce(max(id),0) FROM transactions").fetchone()[0]
                client = ProbeClient(
                    str(profile.get("api_key", "")), api_url=profile["api_url"], model=profile["model"],
                    thinking_enabled=profile.get("thinking_enabled", False),
                    reasoning_effort=profile.get("reasoning_effort", "low"), timeout=180,
                )
                session = NaturalLanguageSession(database, client, payment_hints=PaymentPromptStore().all_profiles())
                draft = session.handle(
                    "请把附件中状态明确为已完成的购买解析成一笔消费并记账；状态、账户或金额不确定时先追问，不要猜测。",
                    images=[image],
                )
                print(f"RUN {run} DRAFT\n{draft}", flush=True)
                assert database.connection.execute("SELECT count(*) FROM transactions").fetchone()[0] == before, "Image posted without confirmation"
                assert session.pending_state and session.pending_state.get("awaiting_slot") == "image_confirmation", "No reviewable draft"
                usage_before = client.usage_snapshot()
                answer = session.handle("确认记账")
                assert client.usage_snapshot() == usage_before, "Confirmation unexpectedly called a model"
                rows = database.connection.execute("SELECT * FROM transactions WHERE id>?", (max_id,)).fetchall()
                assert rows and all(row["occurred_on"] == args.expect_date for row in rows), "Wrong date"
                assert sum(row["amount_minor"] for row in rows) == to_minor(args.expect_amount, "JPY", 0), "Wrong paid amount"
                items = database.connection.execute(
                    "SELECT item_name FROM food_purchase_items WHERE transaction_id>?", (max_id,)
                ).fetchall()
                assert items, "Food item was not recognized"
                print(json.dumps({"run": run, "passed": True, "seconds": round(time.monotonic()-started, 1),
                                  "answer": answer, "food_items": [row[0] for row in items],
                                  "usage": client.usage_snapshot()}, ensure_ascii=False), flush=True)
            finally:
                database.close()


if __name__ == "__main__":
    main()
