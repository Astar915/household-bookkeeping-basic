from __future__ import annotations

import json
import csv
import io
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from typing import Any

from .region_time import DEFAULT_TIME_ZONE, regional_now


FRANKFURTER_ECB_RATES_URL = "https://api.frankfurter.dev/v2/providers/ecb/rates"
FRANKFURTER_V1_RATES_URL = "https://api.frankfurter.dev/v1"
ECB_SDMX_RATES_URL = "https://data-api.ecb.europa.eu/service/data/EXR/D.CNY+JPY+USD.EUR.SP00.A"
ECB_90D_XML_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist-90d.xml"
ECB_XML_NAMESPACE = "http://www.ecb.int/vocabulary/2002-08-01/eurofxref"
ECB_SOURCE = "欧洲央行日次参考汇率"
REQUEST_TIMEOUT_SECONDS = 8
MAX_RATE_LOOKBACK_DAYS = 14
MAX_ECB_XML_BYTES = 256_000


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
        f"{FRANKFURTER_ECB_RATES_URL}?{query}",
        headers={"Accept": "application/json", "User-Agent": "HouseholdBookkeeping/1.0"},
    )
    try:
        with (opener or urlopen)(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            body = response.read(256_000)
    except HTTPError as exc:
        raise FxRateUnavailable(f"Frankfurter ECB HTTP {exc.code}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise FxRateUnavailable(f"Frankfurter ECB connection failed ({type(exc).__name__})") from exc
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


def _download_frankfurter_v1_cross_rates(start: date, end: date, *, opener=None) -> list[dict[str, str]]:
    """Fallback to Frankfurter's durable v1 historical-series route."""
    query = urlencode({"from": "EUR", "to": "CNY,JPY,USD"})
    request = Request(
        f"{FRANKFURTER_V1_RATES_URL}/{start.isoformat()}..{end.isoformat()}?{query}",
        headers={"Accept": "application/json", "User-Agent": "HouseholdBookkeeping/1.0"},
    )
    try:
        with (opener or urlopen)(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            body = response.read(256_000)
    except HTTPError as exc:
        raise FxRateUnavailable(f"Frankfurter v1 HTTP {exc.code}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise FxRateUnavailable(f"Frankfurter v1 connection failed ({type(exc).__name__})") from exc
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FxRateUnavailable("备用汇率服务返回格式无法识别。") from exc
    rates = payload.get("rates") if isinstance(payload, dict) else None
    if not isinstance(rates, dict):
        raise FxRateUnavailable("备用汇率服务返回格式无法识别。")
    parsed: list[dict[str, str]] = []
    for raw_date, currencies in rates.items():
        if not isinstance(currencies, dict):
            continue
        try:
            rate_date = date.fromisoformat(str(raw_date))
        except ValueError:
            continue
        if not start <= rate_date <= end:
            continue
        for quote in ("CNY", "JPY", "USD"):
            value = currencies.get(quote)
            try:
                rate = Decimal(str(value))
            except (InvalidOperation, TypeError, ValueError):
                continue
            if rate > 0:
                parsed.append({"date": rate_date.isoformat(), "quote": quote, "rate": format(rate, "f")})
    return parsed


def _download_official_ecb_cross_rates(start: date, end: date, *, opener=None) -> list[dict[str, str]]:
    """Independent fallback from the ECB's last-90-days XML publication."""
    request = Request(
        ECB_90D_XML_URL,
        headers={"Accept": "application/xml", "User-Agent": "HouseholdBookkeeping/1.0"},
    )
    try:
        with (opener or urlopen)(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            body = response.read(MAX_ECB_XML_BYTES + 1)
    except HTTPError as exc:
        raise FxRateUnavailable(f"ECB HTTP {exc.code}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise FxRateUnavailable("ECB connection failed") from exc
    if len(body) > MAX_ECB_XML_BYTES:
        raise FxRateUnavailable("ECB response exceeded the size limit")
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise FxRateUnavailable("ECB XML response was invalid") from exc

    cube_tag = f"{{{ECB_XML_NAMESPACE}}}Cube"
    parsed: list[dict[str, str]] = []
    for day_cube in root.iter(cube_tag):
        raw_date = day_cube.attrib.get("time")
        if not raw_date:
            continue
        try:
            rate_date = date.fromisoformat(raw_date)
        except ValueError:
            continue
        if not start <= rate_date <= end:
            continue
        for currency_cube in day_cube.findall(cube_tag):
            quote = currency_cube.attrib.get("currency")
            if quote not in {"CNY", "JPY", "USD"}:
                continue
            try:
                rate = Decimal(currency_cube.attrib["rate"])
            except (KeyError, InvalidOperation):
                continue
            if rate > 0:
                parsed.append({"date": rate_date.isoformat(), "quote": quote, "rate": format(rate, "f")})
    return parsed


def _download_ecb_sdmx_cross_rates(start: date, end: date, *, opener=None) -> list[dict[str, str]]:
    """Read ECB's official Data Portal CSV endpoint on its separate API host."""
    query = urlencode({
        "startPeriod": start.isoformat(),
        "endPeriod": end.isoformat(),
        "format": "csvdata",
        "detail": "dataonly",
    })
    request = Request(
        f"{ECB_SDMX_RATES_URL}?{query}",
        headers={"Accept": "text/csv", "User-Agent": "HouseholdBookkeeping/1.0"},
    )
    try:
        with (opener or urlopen)(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            body = response.read(MAX_ECB_XML_BYTES + 1)
    except HTTPError as exc:
        raise FxRateUnavailable(f"ECB Data Portal HTTP {exc.code}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise FxRateUnavailable(f"ECB Data Portal connection failed ({type(exc).__name__})") from exc
    if len(body) > MAX_ECB_XML_BYTES:
        raise FxRateUnavailable("ECB Data Portal response exceeded the size limit")
    try:
        rows = csv.DictReader(io.StringIO(body.decode("utf-8-sig")))
    except UnicodeDecodeError as exc:
        raise FxRateUnavailable("ECB Data Portal CSV response was invalid") from exc
    if not {"TIME_PERIOD", "CURRENCY", "OBS_VALUE"}.issubset(set(rows.fieldnames or ())):
        raise FxRateUnavailable("ECB Data Portal CSV response was invalid")

    parsed: list[dict[str, str]] = []
    for item in rows:
        quote = str(item.get("CURRENCY", "")).upper()
        if quote not in {"CNY", "JPY", "USD"}:
            continue
        try:
            rate_date = date.fromisoformat(str(item["TIME_PERIOD"]))
            rate = Decimal(str(item["OBS_VALUE"]))
        except (KeyError, ValueError, InvalidOperation):
            continue
        if start <= rate_date <= end and rate > 0:
            parsed.append({"date": rate_date.isoformat(), "quote": quote, "rate": format(rate, "f")})
    return parsed


def _has_usable_cross_rate(observations: list[dict[str, str]], currency: str, end: date) -> bool:
    by_date: dict[str, set[str]] = {}
    for item in observations:
        try:
            rate_date = date.fromisoformat(str(item["date"]))
        except (KeyError, TypeError, ValueError):
            continue
        if rate_date <= end:
            by_date.setdefault(rate_date.isoformat(), set()).add(str(item.get("quote", "")))
    return any({"JPY", currency}.issubset(quotes) for quotes in by_date.values())


def resolve_jpy_rate(
    database: Any,
    currency: str,
    occurred_on: str,
    *,
    fetch_if_missing: bool = True,
) -> JpyRate:
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

    today_local = regional_now(getattr(database, "time_zone", DEFAULT_TIME_ZONE)).date()
    if requested_date > today_local:
        raise FxRateUnavailable("未来日期尚无交易日参考汇率；请在实际交易日期记账。")

    first_day = requested_date - timedelta(days=MAX_RATE_LOOKBACK_DAYS)
    cached = database.connection.execute(
        "SELECT rate,rate_date,source FROM fx_rates "
        "WHERE base_currency=? AND quote_currency='JPY' AND rate_date<=? AND rate_date>=? "
        "ORDER BY rate_date DESC LIMIT 1",
        (code, requested_date.isoformat(), first_day.isoformat()),
    ).fetchone()
    if cached is not None:
        try:
            rate = Decimal(str(cached["rate"]))
            if rate > 0:
                return JpyRate(rate, str(cached["rate_date"]), str(cached["source"]))
        except InvalidOperation:
            pass

    if not fetch_if_missing:
        raise FxRateUnavailable(f"暂无缓存的{code}/JPY参考汇率。")

    opener = getattr(database, "external_opener", None)
    observations = None
    providers = (
        _download_ecb_cross_rates,
        _download_frankfurter_v1_cross_rates,
        _download_ecb_sdmx_cross_rates,
        _download_official_ecb_cross_rates,
    )
    for download in providers:
        source_name = getattr(download, "__name__", download.__class__.__name__)
        try:
            candidate = download(first_day, requested_date, opener=opener)
        except FxRateUnavailable as exc:
            # These diagnostics deliberately exclude URLs, request bodies,
            # ledger content, and credentials; they only identify the source
            # and a safe status/transport reason for Cloudflare logs.
            print(f"FX rate source unavailable ({source_name}: {str(exc)[:80]}).")
            continue
        if _has_usable_cross_rate(candidate, code, requested_date):
            observations = candidate
            break
        print(f"FX rate source returned no paired rates ({source_name}).")
    if observations is None:
        raise FxRateUnavailable("汇率服务暂时没有返回可用的人民币/日元参考汇率，账本未写入；请稍后重试。")

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

    raise FxRateUnavailable(f"该日期没有可用的{code}/JPY参考汇率，账本未写入。")


def resolve_exchange_rate(
    database: Any,
    source_currency: str,
    target_currency: str,
    occurred_on: str,
    *,
    fetch_if_missing: bool = True,
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
    source_to_jpy = resolve_jpy_rate(
        database, source, requested_date.isoformat(), fetch_if_missing=fetch_if_missing
    )
    target_to_jpy = resolve_jpy_rate(
        database, target, requested_date.isoformat(), fetch_if_missing=fetch_if_missing
    )
    if source != "JPY" and target != "JPY" and source_to_jpy.rate_date != target_to_jpy.rate_date:
        # A pre-existing one-currency cache may be older than the second leg.
        # Resolving both again uses the paired observations cached by the refresh.
        source_to_jpy = resolve_jpy_rate(
            database, source, requested_date.isoformat(), fetch_if_missing=fetch_if_missing
        )
        target_to_jpy = resolve_jpy_rate(
            database, target, requested_date.isoformat(), fetch_if_missing=fetch_if_missing
        )
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
