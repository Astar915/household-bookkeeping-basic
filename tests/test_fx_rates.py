from __future__ import annotations

import tempfile
import importlib.util
import json
import sys
import unittest
from contextlib import redirect_stdout
from decimal import Decimal
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from bookkeeping.cli import _report
from bookkeeping.fx_rates import (
    ECB_SOURCE,
    JpyRate,
    convert_minor_to_jpy_minor,
    resolve_jpy_rate,
)
from bookkeeping.storage import Database, seed_demo_data


class FxRateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp.name) / "ledger.sqlite3")
        self.db.initialize()
        seed_demo_data(self.db)

    def tearDown(self) -> None:
        self.db.close()
        self.temp.cleanup()

    def test_weekend_uses_latest_published_ecb_rate_and_caches_it(self) -> None:
        observations = [
            {"date": "2026-10-09", "quote": "CNY", "rate": "7.5"},
            {"date": "2026-10-09", "quote": "JPY", "rate": "177"},
        ]
        with patch("bookkeeping.fx_rates._download_ecb_cross_rates", return_value=observations):
            rate = resolve_jpy_rate(self.db, "CNY", "2026-10-11")

        self.assertEqual(rate, JpyRate(Decimal("23.6"), "2026-10-09", ECB_SOURCE))
        cached = self.db.connection.execute(
            "SELECT rate,rate_date,source FROM fx_rates WHERE base_currency='CNY'"
        ).fetchone()
        self.assertEqual(tuple(cached), ("23.600000000000", "2026-10-09", ECB_SOURCE))
        self.assertEqual(convert_minor_to_jpy_minor(100, 2, rate.rate), 24)

    def test_cny_expense_stores_original_amount_and_transaction_date_jpy_equivalent(self) -> None:
        self.db.add_account(
            name="人民币钱包", account_type="wallet", currency="CNY",
            opening_balance="100.00", opening_date="2026-10-14",
        )
        rate = JpyRate(Decimal("23.6"), "2026-10-15", ECB_SOURCE)

        with patch("bookkeeping.fx_rates.resolve_jpy_rate", return_value=rate):
            transaction_id = self.db.add_transaction(
                occurred_on="2026-10-15", kind="expense", amount="1.00", currency="CNY",
                account_name="人民币钱包", category_name="日用品", description="淘宝购物",
                source="natural_language_api",
            )

        row = self.db.connection.execute(
            "SELECT amount_minor,currency,jpy_equiv_minor,fx_rate,fx_rate_date,fx_source "
            "FROM transactions WHERE id=?",
            (transaction_id,),
        ).fetchone()
        self.assertEqual(tuple(row), (100, "CNY", 24, "23.6", "2026-10-15", ECB_SOURCE))
        from bookkeeping.financial_statements import build_profit_statement

        report = build_profit_statement(self.db, "2026-10-15")
        self.assertEqual(report["currencies"]["CNY"]["expense_minor"], 100)
        self.assertEqual(report["jpy_equivalent"]["expense_minor"], 724)
        self.assertEqual(report["jpy_equivalent"]["missing_conversion_count"], 0)

        printed = StringIO()
        with redirect_stdout(printed):
            _report(self.db, "2026-10-15", "2026-10-15", None)
        self.assertIn("JPY合并口径（JPY原币 + CNY按交易日汇率折算）", printed.getvalue())
        self.assertIn("费用：-724 JPY", printed.getvalue())

    def test_worker_fx_fetch_yields_to_and_replays_durable_fetch(self) -> None:
        project = Path(__file__).resolve().parents[1]
        worker_src = project / "cloudflare-full" / "python-d1" / "src"

        def load_module(name: str, path: Path):
            spec = importlib.util.spec_from_file_location(name, path)
            self.assertIsNotNone(spec)
            module = importlib.util.module_from_spec(spec)
            assert spec and spec.loader
            sys.modules[name] = module
            spec.loader.exec_module(module)
            return module

        worker_fx = load_module("worker_fx_rates_under_test", worker_src / "bookkeeping" / "fx_rates.py")
        worker_jobs = load_module("worker_model_jobs_under_test", worker_src / "model_jobs.py")
        first = worker_jobs.ReplayOpener([], "stable-ledger-revision")
        self.db.external_opener = first

        with self.assertRaises(worker_jobs.ModelRequestRequired) as requested:
            worker_fx.resolve_jpy_rate(self.db, "CNY", "2026-10-27")

        envelope = requested.exception.envelope
        payload = json.dumps([
            {"base": "EUR", "quote": "CNY", "date": "2026-10-26", "rate": "7.5"},
            {"base": "EUR", "quote": "JPY", "date": "2026-10-26", "rate": "177"},
        ]).encode("utf-8")
        self.db.external_opener = worker_jobs.ReplayOpener([{
            "requestHash": envelope["requestHash"], "status": 200, "body": payload,
        }], "stable-ledger-revision")
        resolved = worker_fx.resolve_jpy_rate(self.db, "CNY", "2026-10-27")

        self.assertEqual(resolved.rate, Decimal("23.6"))
        self.assertEqual(resolved.rate_date, "2026-10-26")


if __name__ == "__main__":
    unittest.main()
