from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from typing import Any


_PRICE_TABLE_CNY_PER_MILLION = {
    "deepseek-flash": {"peak": (0.04, 2.0, 8.0), "offpeak": (0.02, 1.0, 4.0)},
    "deepseek-v4-flash": {"peak": (0.04, 2.0, 8.0), "offpeak": (0.02, 1.0, 4.0)},
    "deepseek-v4-flash-vision-exp": {
        "peak": (0.04, 2.0, 8.0), "offpeak": (0.02, 1.0, 4.0)
    },
    "deepseek-v4-pro": {"peak": (0.30, 9.0, 27.0), "offpeak": (0.15, 4.5, 13.5)},
}


def _is_peak_period(at: datetime | None = None) -> bool:
    china_time = timezone(timedelta(hours=8))
    local = (at or datetime.now(china_time)).astimezone(china_time)
    return local.weekday() < 5 and (
        9 <= local.hour < 12 or 14 <= local.hour < 18
    )


def estimate_deepseek_cost_cny(
    usage: dict[str, Any] | None,
    api_url: str,
    model: str,
    *,
    at: datetime | None = None,
) -> dict[str, float] | None:
    """Estimate the current request cost in CNY using the website's price model."""
    try:
        endpoint = urlsplit(str(api_url))
    except ValueError:
        return None
    if (endpoint.hostname or "").lower() != "api.deepseek.com":
        return None
    rates = _PRICE_TABLE_CNY_PER_MILLION.get(str(model).strip().lower())
    if not rates or not isinstance(usage, dict):
        return None
    period = rates["peak" if _is_peak_period(at) else "offpeak"]

    def count(name: str) -> int:
        value = usage.get(name, 0)
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0

    hit = count("cache_hit_tokens")
    miss = count("cache_miss_tokens")
    if not miss:
        miss = max(0, count("prompt_tokens") - hit)
    output = count("completion_tokens")
    return {
        "hit_cny": hit * period[0] / 1_000_000,
        "miss_cny": miss * period[1] / 1_000_000,
        "output_cny": output * period[2] / 1_000_000,
    }


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch_deepseek_balance(api_key: str, *, timeout: float = 6.0) -> list[dict[str, str]] | None:
    """Read only the public balance payload; never return provider errors or secrets."""
    token = str(api_key or "").strip()
    if not token:
        return None
    request = Request(
        "https://api.deepseek.com/user/balance",
        headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
        method="GET",
    )
    try:
        with build_opener(_NoRedirect()).open(request, timeout=timeout) as response:
            status = int(response.status)
            if not 200 <= status < 300:
                return None
            body = response.read(64 * 1024 + 1)
        if len(body) > 64 * 1024:
            return None
        payload = json.loads(body.decode("utf-8"))
        if not isinstance(payload, dict) or not payload.get("is_available"):
            return []
        rows = payload.get("balance_infos")
        result: list[dict[str, str]] = []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            currency = str(row.get("currency") or "").upper()
            raw_total = row.get("total_balance")
            if currency not in {"CNY", "USD"} or not isinstance(raw_total, (str, int, float)):
                continue
            try:
                total = Decimal(str(raw_total))
            except InvalidOperation:
                continue
            if total.is_finite() and total >= 0:
                result.append({"currency": currency, "total": format(total, "f")})
        return result
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
        return None
