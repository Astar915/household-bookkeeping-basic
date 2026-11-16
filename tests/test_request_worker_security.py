from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from bookkeeping.request_worker import RequestMergeError, merge_isolated_database
from bookkeeping.storage import Database


class RequestWorkerMergeSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.live = self.root / "live.sqlite3"
        self.baseline = self.root / "baseline.sqlite3"
        self.candidate = self.root / "candidate.sqlite3"
        database = Database(self.live)
        database.initialize()
        database.backup(self.baseline)
        database.close()
        shutil.copyfile(self.baseline, self.candidate)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _candidate_setting(self, key: str, value: str, note: str) -> None:
        import sqlite3

        connection = sqlite3.connect(self.candidate)
        try:
            connection.execute(
                "INSERT INTO settings(key,value,note) VALUES(?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value,note=excluded.note",
                (key, value, note),
            )
            connection.commit()
        finally:
            connection.close()

    def test_only_bounded_product_category_memory_can_be_merged(self) -> None:
        setting = [{
            "aliases": ["高原の詩"],
            "category": "食材",
            "kind": "expense",
            "updatedAt": "2026-11-16T00:00:00+00:00",
        }]
        self._candidate_setting(
            "agent_product_category_memory_v1",
            json.dumps(setting, ensure_ascii=False),
            "Agent product category corrections for this account",
        )
        merge_isolated_database(
            self.live, self.baseline, self.candidate, allow_agent_product_memory=True
        )
        database = Database(self.live)
        try:
            database.initialize()
            self.assertEqual(
                json.loads(database.get_setting("agent_product_category_memory_v1"))[0]["category"],
                "食材",
            )
        finally:
            database.close()

    def test_unrelated_settings_change_is_rejected(self) -> None:
        self._candidate_setting("base_currency", "USD", "Currency used for combined report totals.")
        with self.assertRaises(RequestMergeError):
            merge_isolated_database(
                self.live, self.baseline, self.candidate, allow_agent_product_memory=True
            )


if __name__ == "__main__":
    unittest.main()
