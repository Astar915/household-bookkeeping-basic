from __future__ import annotations

import tempfile
import unittest
import json
import os
import time
from pathlib import Path

from bookkeeping.payment_preferences import (
    PaymentPromptSettingsConflict,
    PaymentPromptSettingsError,
    PaymentPromptStore,
)


class PaymentPromptStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "payment_prompts.json"
        self.store = PaymentPromptStore(self.path)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_missing_file_has_no_default(self) -> None:
        self.assertEqual(self.store.load(), {"profiles": [], "default_index": None})
        self.assertIsNone(self.store.selected_profile())

    def test_saves_multiple_profiles_and_selected_default(self) -> None:
        profiles = [
            {"payment_method": "PayPay钱包", "purpose": "日常小额消费"},
            {"payment_method": "Mercari Card", "purpose": "Mercari购物"},
        ]

        self.store.save(profiles, 1)

        self.assertEqual(self.store.load(), {"profiles": profiles, "default_index": 1})
        self.assertEqual(self.store.selected_profile(), profiles[1])

    def test_save_keeps_previous_version_as_backup(self) -> None:
        original = [{"payment_method": "PayPay钱包", "purpose": "外食"}]
        self.store.save_profiles(original)

        self.store.save_profiles([])

        self.assertEqual(
            self.store._load_file(self.store.backup_path)["profiles"], original
        )
        self.assertEqual(self.store.load(), {"profiles": [], "default_index": None})

    def test_load_restores_missing_file_from_backup(self) -> None:
        profiles = [{"payment_method": "瑞穗银行", "purpose": "所有信用卡还款"}]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.store.backup_path.write_text(
            '{"version": 1, "profiles": '
            '[{"payment_method": "瑞穗银行", "purpose": "所有信用卡还款"}], '
            '"default_index": null}',
            encoding="utf-8",
        )

        self.assertEqual(
            self.store.load(), {"profiles": profiles, "default_index": None}
        )
        self.assertTrue(self.path.exists())

    def test_load_falls_back_to_backup_when_primary_is_corrupt(self) -> None:
        profiles = [{"payment_method": "瑞穗银行", "purpose": "所有信用卡还款"}]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("{broken", encoding="utf-8")
        self.store.backup_path.write_text(
            '{"version": 1, "profiles": '
            '[{"payment_method": "瑞穗银行", "purpose": "所有信用卡还款"}], '
            '"default_index": null}',
            encoding="utf-8",
        )

        self.assertEqual(
            self.store.load(), {"profiles": profiles, "default_index": None}
        )
        self.assertEqual(self.store._load_file(self.path)["profiles"], profiles)

    def test_load_promotes_newer_valid_backup_over_stale_primary(self) -> None:
        old_profiles = [{"payment_method": "旧账户", "purpose": "旧规则"}]
        current_profiles = [
            {
                "payment_method": "Rakuten Pay",
                "purpose": "水费，电费",
                "currency": "JPY",
                "account_order": ["Rakuten积分", "Rakuten Pay", "Rakuten Card"],
            }
        ]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"version": 1, "profiles": old_profiles, "default_index": None}),
            encoding="utf-8",
        )
        self.store.backup_path.write_text(
            json.dumps({"version": 2, "profiles": current_profiles, "default_index": None}),
            encoding="utf-8",
        )
        old_time = time.time() - 120
        os.utime(self.path, (old_time, old_time))

        self.assertEqual(self.store.all_profiles(), current_profiles)
        self.assertEqual(self.store._load_file(self.path)["profiles"], current_profiles)
        self.assertEqual(self.store._load_file(self.store.backup_path)["profiles"], old_profiles)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["revision"], 1)
        later_time = time.time() + 120
        os.utime(self.store.backup_path, (later_time, later_time))
        self.assertEqual(self.store.all_profiles(), current_profiles)

    def test_stale_editor_cannot_overwrite_newer_payment_rules(self) -> None:
        original = [{"payment_method": "旧账户", "purpose": "旧用途"}]
        latest = [{"payment_method": "新账户", "purpose": "新用途"}]
        self.store.save_profiles(original)
        _settings, stale_revision = self.store.load_snapshot()

        self.store.save_profiles(latest)

        with self.assertRaises(PaymentPromptSettingsConflict):
            self.store.save_profiles(original, expected_revision=stale_revision)
        self.assertEqual(self.store.all_profiles(), latest)

    def test_requires_a_nonempty_method_and_valid_default(self) -> None:
        with self.assertRaises(PaymentPromptSettingsError):
            self.store.save([{"payment_method": "", "purpose": "用途"}], 0)
        with self.assertRaises(PaymentPromptSettingsError):
            self.store.save([{"payment_method": "PayPay钱包", "purpose": ""}], None)

    def test_currency_scope_round_trips_and_rejects_unsupported_codes(self) -> None:
        profiles = [
            {
                "payment_method": "工行储蓄卡",
                "purpose": "默认所有消费由本卡付款",
                "currency": "cny",
            },
            {"payment_method": "Rakuten Card", "purpose": "外食", "currency": "JPY"},
        ]

        self.store.save_profiles(profiles)

        self.assertEqual(
            self.store.all_profiles(),
            [
                {**profiles[0], "currency": "CNY"},
                profiles[1],
            ],
        )
        with self.assertRaises(PaymentPromptSettingsError):
            self.store.save_profiles(
                [{"payment_method": "PayPay", "purpose": "用途", "currency": "USD"}]
            )

    def test_legacy_profiles_without_currency_remain_unrestricted(self) -> None:
        legacy = [{"payment_method": "Rakuten Card", "purpose": "外食"}]

        self.store.save_profiles(legacy)

        self.assertEqual(self.store.all_profiles(), legacy)


if __name__ == "__main__":
    unittest.main()
