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


def _cached_rate(database: Any, requested_date: date, currency: str = "CNY") -> JpyRate | None:
    row = database.connection.execute(
        "SELECT rate,rate_date,source FROM fx_rates "
        "WHERE base_currency=? AND quote_currency='JPY' AND rate_date<=? "
        "ORDER BY rate_date DESC LIMIT 1",
        (currency.upper(), requested_date.isoformat()),
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


def _download_ecb_cross_rates(start: date, end: date, *, opener=None) -> list[dict[str, str]]:
    query = urlencode(
        {
            "base": "EUR",
            "quotes": "CNY,JPY,USD",
            "from": start.isoformat(),
            "to": end.isoformat(),
        }
    )
    request = Request(
        f"{ECB_RATES_URL}?{query}",
        headers={"Accept": "application/json", "User-Agent": "HouseholdBookkeeping/1.0"},
    )
    try:
        with (opener or urlopen)(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            body = response.read(256_000)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise FxRateUnavailable("无法取得交易日参考汇率。请检查网络后重试。") from exc
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
        if quote not in {"CNY", "JPY", "USD"}:
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
    """Resolve the daily JPY equivalent for one currency and transaction date.

    CNY/JPY and USD/JPY cross rates are derived from the ECB's daily EUR reference
    rates. If the transaction falls on a non-publication day, the latest prior
    publication is applied and its effective date is saved with the transaction.
    """
    code = currency.upper()
    requested_date = date.fromisoformat(occurred_on)
    if code == "JPY":
        return JpyRate(Decimal("1"), requested_date.isoformat(), "同币种（JPY）")
    if code not in {"CNY", "USD"}:
        raise FxRateUnavailable(f"当前没有配置{code}到JPY的报表汇率。")

    today_jst = datetime.now(timezone(timedelta(hours=9))).date()
    if requested_date > today_jst:
        raise FxRateUnavailable("未来日期尚无交易日参考汇率；请在实际交易日期记账。")

    cached_exact = database.connection.execute(
        "SELECT rate,rate_date,source FROM fx_rates "
        "WHERE base_currency=? AND quote_currency='JPY' AND rate_date=?",
        (code, requested_date.isoformat()),
    ).fetchone()
    if cached_exact is not None:
        try:
            rate = Decimal(str(cached_exact["rate"]))
            if rate > 0:
                return JpyRate(rate, str(cached_exact["rate_date"]), str(cached_exact["source"]))
        except InvalidOperation:
            pass

    cached = _cached_rate(database, requested_date, code)
    if cached is not None:
        return cached

    first_day = requested_date - timedelta(days=MAX_CACHED_AGE_DAYS)
    try:
        opener = getattr(database, "external_opener", None)
        observations = (_download_ecb_cross_rates(first_day, requested_date, opener=opener)
                        if opener is not None else _download_ecb_cross_rates(first_day, requested_date))
    except FxRateUnavailable:
        cached = _cached_rate(database, requested_date, code)
        if cached is not None:
            return cached
        raise

    by_date: dict[str, dict[str, Decimal]] = {}
    for item in observations:
        try:
            by_date.setdefault(item["date"], {})[item["quote"]] = Decimal(item["rate"])
        except InvalidOperation:
            continue

    valid_rates: dict[str, list[tuple[str, str]]] = {"CNY": [], "USD": []}
    for rate_date, values in by_date.items():
        jpy_per_eur = values.get("JPY")
        if jpy_per_eur is None or jpy_per_eur <= 0:
            continue
        for quote in ("CNY", "USD"):
            quote_per_eur = values.get(quote)
            if quote_per_eur is None or quote_per_eur <= 0:
                continue
            with localcontext() as context:
                context.prec = 32
                cross_rate = jpy_per_eur / quote_per_eur
            valid_rates[quote].append((rate_date, _canonical_rate(cross_rate)))
    cached_rates = [
        (quote, rate_date, rate)
        for quote, observations_for_quote in valid_rates.items()
        for rate_date, rate in observations_for_quote
    ]
    if cached_rates:
        with database.connection:
            database.connection.executemany(
                "INSERT OR REPLACE INTO fx_rates "
                "(base_currency,quote_currency,rate_date,rate,source,retrieved_at) "
                "VALUES (?, 'JPY', ?, ?, ?, ?)",
                [
                    (quote, rate_date, rate, ECB_SOURCE, datetime.now(timezone.utc).isoformat(timespec="seconds"))
                    for quote, rate_date, rate in cached_rates
                ],
            )
        applicable = [item for item in valid_rates[code] if item[0] <= requested_date.isoformat()]
        if applicable:
            rate_date, rate_text = max(applicable, key=lambda item: item[0])
            return JpyRate(Decimal(rate_text), rate_date, ECB_SOURCE)

    cached = _cached_rate(database, requested_date, code)
    if cached is not None:
        return cached
    raise FxRateUnavailable(f"该日期没有可用的{code}/JPY参考汇率，账本未写入。")


def resolve_exchange_rate(
    database: Any,
    source_currency: str,
    target_currency: str,
    occurred_on: str,
) -> ExchangeRate:
    """Resolve the daily reference conversion rate from source to target currency.

    Supported currencies share ECB EUR reference observations, cached as
    currency-to-JPY cross rates. Cross-currency amounts use the matching daily
    reference date for both legs.
    """
    source = source_currency.upper()
    target = target_currency.upper()
    requested_date = date.fromisoformat(occurred_on)
    if source == target:
        return ExchangeRate(Decimal("1"), requested_date.isoformat(), "同币种")
    if source not in {"JPY", "CNY", "USD"} or target not in {"JPY", "CNY", "USD"}:
        raise FxRateUnavailable(f"暂不支持{source}与{target}之间的参考汇率换算。")
    source_to_jpy = resolve_jpy_rate(database, source, requested_date.isoformat())
    target_to_jpy = resolve_jpy_rate(database, target, requested_date.isoformat())
    if source != "JPY" and target != "JPY" and source_to_jpy.rate_date != target_to_jpy.rate_date:
        # A pre-existing one-currency cache may be older than the second leg.
        # Resolving both again uses the paired observations cached by the refresh.
        source_to_jpy = resolve_jpy_rate(database, source, requested_date.isoformat())
        target_to_jpy = resolve_jpy_rate(database, target, requested_date.isoformat())
    if source != "JPY" and target != "JPY" and source_to_jpy.rate_date != target_to_jpy.rate_date:
        raise FxRateUnavailable(f"{source}/{target}参考汇率日期不一致，暂不能安全换算。")
    with localcontext() as context:
        context.prec = 32
        rate = source_to_jpy.rate / target_to_jpy.rate
    effective = source_to_jpy if source != "JPY" else target_to_jpy
    return ExchangeRate(
        rate=Decimal(_canonical_rate(rate)),
        rate_date=effective.rate_date,
        source=effective.source,
    )
