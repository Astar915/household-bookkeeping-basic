from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bookkeeping.credit_management import (
    credit_card_overview,
    delete_credit_repayment_schedule,
    process_due_credit_repayments,
    save_credit_repayment_schedule,
)
from bookkeeping.storage import Database, seed_demo_data


class CreditRepaymentScheduleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp.name) / "schedule-test.sqlite3")
        self.db.initialize()
        seed_demo_data(self.db)

    def tearDown(self) -> None:
        self.db.close()
        self.temp.cleanup()

    def _save(self, *, due_time: str = "09:00", due_date: str = "2026-11-16") -> None:
        save_credit_repayment_schedule(
            self.db,
            card_name="Mercari Card",
            source_account_name="瑞穗银行",
            first_due_date=due_date,
            due_time=due_time,
            amount="1000",
            today_value="2026-11-16",
        )

    def test_configured_time_controls_local_posting_and_prevents_duplicate(self) -> None:
        self._save(due_time="09:00")
        schedule = credit_card_overview(self.db)[0]["repayment_schedule"]
        self.assertEqual(schedule["due_time"], "09:00")

        self.assertEqual(process_due_credit_repayments(
            self.db, "2026-11-16", current_time="08:59"
        ), [])
        events = process_due_credit_repayments(
            self.db, "2026-11-16", current_time="09:00"
        )
        self.assertEqual([event["status"] for event in events], ["posted"])
        self.assertEqual(self.db.connection.execute(
            "SELECT COUNT(*) FROM transactions WHERE source='scheduled_card_repayment'"
        ).fetchone()[0], 1)
        self.assertEqual(process_due_credit_repayments(
            self.db, "2026-11-16", current_time="09:01"
        ), [])

    def test_delete_hides_plan_cancels_pending_amount_and_can_be_recreated(self) -> None:
        self._save(due_date="2026-11-17")
        delete_credit_repayment_schedule(self.db, card_name="Mercari Card")

        cards = {row["name"]: row for row in credit_card_overview(self.db)}
        self.assertIsNone(cards["Mercari Card"]["repayment_schedule"])
        self.assertEqual(self.db.connection.execute(
            "SELECT status FROM credit_repayment_periods ORDER BY id DESC LIMIT 1"
        ).fetchone()[0], "cancelled")
        self.assertEqual(self.db.connection.execute(
            "SELECT COUNT(*) FROM transactions WHERE source='scheduled_card_repayment'"
        ).fetchone()[0], 0)

        self._save(due_date="2026-11-17")
        cards = {row["name"]: row for row in credit_card_overview(self.db)}
        self.assertTrue(cards["Mercari Card"]["repayment_schedule"]["enabled"])

    def test_invalid_local_time_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self._save(due_time="9:00")

    def test_database_validation_checks_saved_repayment_time(self) -> None:
        self._save(due_time="09:00")
        self.db.connection.execute(
            "UPDATE credit_repayment_rules SET due_time='9:00' WHERE card_account_id=?",
            (self.db.account("Mercari Card")["id"],),
        )
        self.db.connection.commit()
        errors, _ = self.db.validate()
        self.assertTrue(any("时间无效" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
