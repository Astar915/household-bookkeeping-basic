from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from typing import Any


ECB_RATES_URL = "https://api.frankfurter.dev/v2/providers/ecb/rates"
ECB_SOURCE = "ECB日次参考汇率（Frankfurter）"
REQUEST_TIMEOUT_SECONDS = 8
MAX_CACHED_AGE_DAYS = 14


class FxRateUnavailable(RuntimeError):
    """A transaction-date reference rate could not be obtained safely."""


@dataclass(frozen=True)
class JpyRate:
    rate: Decimal
    rate_date: str
    source: str


@dataclass(frozen=True)
class ExchangeRate:
    """A reference rate expressed as target currency units per source unit."""

    rate: Decimal
    rate_date: str
    source: str


def _canonical_rate(value: Decimal) -> str:
    with localcontext() as context:
        context.prec = 32
        rounded = value.quantize(Decimal("0.000000000001"), rounding=ROUND_HALF_UP)
    return format(rounded, "f")


def convert_minor_to_jpy_minor(
    amount_minor: int,
    currency_minor_digits: int,
    jpy_per_unit: Decimal,
) -> int:
    """Convert an integer minor-unit amount to rounded whole JPY, without floats."""
    if amount_minor < 0 or currency_minor_digits < 0 or jpy_per_unit <= 0:
        raise FxRateUnavailable("汇率或金额无效，无法计算日元等值。")
    with localcontext() as context:
        context.prec = 32
        major_amount = Decimal(amount_minor).scaleb(-currency_minor_digits)
        return int((major_amount * jpy_per_unit).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def convert_minor_at_rate(
    amount_minor: int,
    source_minor_digits: int,
    target_minor_digits: int,
    target_units_per_source_unit: Decimal,
) -> int:
    """Convert between integer minor-unit amounts without floating-point math."""
    if (
        amount_minor < 0
        or source_minor_digits < 0
        or target_minor_digits < 0
        or target_units_per_source_unit <= 0
    ):
        raise FxRateUnavailable("汇率、币种精度或金额无效，无法换算。")
    with localcontext() as context:
        context.prec = 32
        source_major = Decimal(amount_minor).scaleb(-source_minor_digits)
        target_minor = source_major * target_units_per_source_unit * (Decimal(10) ** target_minor_digits)
        return int(target_minor.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _cached_rate(database: Any, requested_date: date) -> JpyRate | None:
    row = database.connection.execute(
        "SELECT rate,rate_date,source FROM fx_rates "
        "WHERE base_currency='CNY' AND quote_currency='JPY' AND rate_date<=? "
        "ORDER BY rate_date DESC LIMIT 1",
        (requested_date.isoformat(),),
    ).fetchone()
    if row is None:
        return None
    try:
        rate_date = date.fromisoformat(str(row["rate_date"]))
        rate = Decimal(str(row["rate"]))
    except (ValueError, InvalidOperation):
        return None
    if (requested_date - rate_date).days > MAX_CACHED_AGE_DAYS or rate <= 0:
        return None
    return JpyRate(rate=rate, rate_date=rate_date.isoformat(), source=str(row["source"]))


def _download_ecb_cross_rates(start: date, end: date) -> list[dict[str, str]]:
    query = urlencode(
        {
            "base": "EUR",
            "quotes": "CNY,JPY",
            "from": start.isoformat(),
            "to": end.isoformat(),
        }
    )
    request = Request(
        f"{ECB_RATES_URL}?{query}",
        headers={"Accept": "application/json", "User-Agent": "HouseholdBookkeeping/1.0"},
    )
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            body = response.read(256_000)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise FxRateUnavailable("无法取得人民币的交易日参考汇率。请检查网络后重试。") from exc
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FxRateUnavailable("汇率服务返回格式无法识别，账本未写入。") from exc
    if not isinstance(payload, list):
        raise FxRateUnavailable("汇率服务返回格式无法识别，账本未写入。")
    parsed: list[dict[str, str]] = []
    for item in payload:
        if not isinstance(item, dict) or item.get("base") != "EUR":
            continue
        quote = item.get("quote")
        if quote not in {"CNY", "JPY"}:
            continue
        try:
            rate_date = date.fromisoformat(str(item["date"]))
            rate = Decimal(str(item["rate"]))
        except (KeyError, ValueError, InvalidOperation):
            continue
        if start <= rate_date <= end and rate > 0:
            parsed.append({"date": rate_date.isoformat(), "quote": str(quote), "rate": format(rate, "f")})
    return parsed


def resolve_jpy_rate(database: Any, currency: str, occurred_on: str) -> JpyRate:
    """Resolve the recorded daily JPY equivalent for one currency and transaction date.

    CNY/JPY cross rates are derived from the ECB's daily EUR reference rates. If
    the transaction falls on a non-publication day, the latest prior publication
    is applied and its effective date is saved with the transaction.
    """
    code = currency.upper()
    requested_date = date.fromisoformat(occurred_on)
    if code == "JPY":
        return JpyRate(Decimal("1"), requested_date.isoformat(), "同币种（JPY）")
    if code != "CNY":
        raise FxRateUnavailable(f"当前没有配置{code}到JPY的报表汇率。")

    today_jst = datetime.now(timezone(timedelta(hours=9))).date()
    if requested_date > today_jst:
        raise FxRateUnavailable("未来日期尚无交易日参考汇率；请在实际交易日期记账。")

    cached_exact = database.connection.execute(
        "SELECT rate,rate_date,source FROM fx_rates "
        "WHERE base_currency='CNY' AND quote_currency='JPY' AND rate_date=?",
        (requested_date.isoformat(),),
    ).fetchone()
    if cached_exact is not None:
        try:
            rate = Decimal(str(cached_exact["rate"]))
            if rate > 0:
                return JpyRate(rate, str(cached_exact["rate_date"]), str(cached_exact["source"]))
        except InvalidOperation:
            pass

    first_day = requested_date - timedelta(days=MAX_CACHED_AGE_DAYS)
    try:
        observations = _download_ecb_cross_rates(first_day, requested_date)
    except FxRateUnavailable:
        cached = _cached_rate(database, requested_date)
        if cached is not None:
            return cached
        raise

    by_date: dict[str, dict[str, Decimal]] = {}
    for item in observations:
        try:
            by_date.setdefault(item["date"], {})[item["quote"]] = Decimal(item["rate"])
        except InvalidOperation:
            continue

    valid_rates: list[tuple[str, str]] = []
    for rate_date, values in by_date.items():
        cny_per_eur = values.get("CNY")
        jpy_per_eur = values.get("JPY")
        if cny_per_eur is None or jpy_per_eur is None or cny_per_eur <= 0 or jpy_per_eur <= 0:
            continue
        with localcontext() as context:
            context.prec = 32
            cross_rate = jpy_per_eur / cny_per_eur
        valid_rates.append((rate_date, _canonical_rate(cross_rate)))
    if valid_rates:
        with database.connection:
            database.connection.executemany(
                "INSERT OR REPLACE INTO fx_rates "
                "(base_currency,quote_currency,rate_date,rate,source,retrieved_at) "
                "VALUES ('CNY','JPY',?,?,?,?)",
                [
                    (rate_date, rate, ECB_SOURCE, datetime.now(timezone.utc).isoformat(timespec="seconds"))
                    for rate_date, rate in valid_rates
                ],
            )
        applicable = [item for item in valid_rates if item[0] <= requested_date.isoformat()]
        if applicable:
            rate_date, rate_text = max(applicable, key=lambda item: item[0])
            return JpyRate(Decimal(rate_text), rate_date, ECB_SOURCE)

    cached = _cached_rate(database, requested_date)
    if cached is not None:
        return cached
    raise FxRateUnavailable("该日期没有可用的人民币/日元参考汇率，账本未写入。")


def resolve_exchange_rate(
    database: Any,
    source_currency: str,
    target_currency: str,
    occurred_on: str,
) -> ExchangeRate:
    """Resolve the daily reference conversion rate from source to target currency.

    JPY/CNY conversions share the cached ECB cross rate. The reciprocal is used
    for JPY-to-CNY payments so the effective reference date and source stay the
    same in both directions.
    """
    source = source_currency.upper()
    target = target_currency.upper()
    requested_date = date.fromisoformat(occurred_on)
    if source == target:
        return ExchangeRate(Decimal("1"), requested_date.isoformat(), "同币种")
    if {source, target} != {"JPY", "CNY"}:
        raise FxRateUnavailable(f"暂不支持{source}与{target}之间的参考汇率换算。")
    cny_to_jpy = resolve_jpy_rate(database, "CNY", requested_date.isoformat())
    if source == "CNY":
        rate = cny_to_jpy.rate
    else:
        with localcontext() as context:
            context.prec = 32
            rate = Decimal("1") / cny_to_jpy.rate
    return ExchangeRate(
        rate=Decimal(_canonical_rate(rate)),
        rate_date=cny_to_jpy.rate_date,
        source=cny_to_jpy.source,
    )
