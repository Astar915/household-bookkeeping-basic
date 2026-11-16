"""Regression checks for account-local dates and timed repayments."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bookkeeping.credit_management import process_due_credit_repayments, save_credit_repayment_schedule
from bookkeeping.region_time import (
    DEFAULT_TIME_ZONE,
    normalize_time_zone,
    region_timezone,
)
from bookkeeping.storage import Database, parse_date


class RegionTimeTests(unittest.TestCase):
    def test_supported_regions_and_fallback(self):
        self.assertEqual(DEFAULT_TIME_ZONE, "Asia/Tokyo")
        self.assertEqual(normalize_time_zone("America/New_York"), "America/New_York")
        self.assertEqual(normalize_time_zone("unknown/region"), DEFAULT_TIME_ZONE)

    def test_daylight_saving_offsets_follow_region_rules(self):
        summer = datetime(2026, 7, 1, 12, tzinfo=timezone.utc)
        winter = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
        self.assertEqual(summer.astimezone(region_timezone("America/New_York")).strftime("%z"), "-0400")
        self.assertEqual(winter.astimezone(region_timezone("America/New_York")).strftime("%z"), "-0500")
        self.assertEqual(summer.astimezone(region_timezone("Asia/Tokyo")).strftime("%z"), "+0900")

    def test_month_only_dates_use_the_selected_region_year(self):
        just_after_utc_new_year = datetime(2027, 1, 1, 1, tzinfo=timezone.utc)
        with patch(
            "bookkeeping.region_time.regional_now",
            side_effect=lambda zone: just_after_utc_new_year.astimezone(region_timezone(zone)),
        ):
            self.assertEqual(parse_date("12月", "America/Los_Angeles").isoformat(), "2026-12-01")
            self.assertEqual(parse_date("12月", "Asia/Tokyo").isoformat(), "2027-12-01")

    def test_credit_repayment_uses_local_nine_am_and_posts_once(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "isolated-ledger.sqlite3")
            try:
                database.initialize()
                database.time_zone = "America/New_York"
                database.add_account(
                    name="Synthetic bank", account_type="bank", currency="JPY",
                    opening_balance="1000", opening_date="2020-01-01",
                )
                database.add_account(
                    name="Synthetic card", account_type="credit", currency="JPY",
                    opening_balance="0", opening_date="2020-01-01",
                )
                schedule_id = save_credit_repayment_schedule(
                    database, card_name="Synthetic card", source_account_name="Synthetic bank",
                    first_due_date="2026-07-01", amount="100", today_value="2026-07-01",
                )
                rule = database.connection.execute(
                    "SELECT due_time FROM credit_repayment_rules WHERE id=?", (schedule_id,)
                ).fetchone()
                self.assertEqual(rule["due_time"], "09:00")

                just_before_nine_local = datetime(2026, 7, 1, 12, 59, tzinfo=timezone.utc)
                with patch(
                    "bookkeeping.credit_management.regional_now",
                    return_value=just_before_nine_local.astimezone(region_timezone("America/New_York")),
                ):
                    self.assertEqual(process_due_credit_repayments(database, "2026-07-01"), [])

                at_nine_local = datetime(2026, 7, 1, 13, 0, tzinfo=timezone.utc)
                with patch(
                    "bookkeeping.credit_management.regional_now",
                    return_value=at_nine_local.astimezone(region_timezone("America/New_York")),
                ):
                    events = process_due_credit_repayments(database, "2026-07-01")
                self.assertEqual([event["status"] for event in events], ["posted"])
                self.assertEqual(
                    database.connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0], 1
                )
                with patch(
                    "bookkeeping.credit_management.regional_now",
                    return_value=at_nine_local.astimezone(region_timezone("America/New_York")),
                ):
                    self.assertEqual(process_due_credit_repayments(database, "2026-07-01"), [])
                self.assertEqual(
                    database.connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0], 1
                )
            finally:
                database.close()


if __name__ == "__main__":
    unittest.main()
