from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from .storage import (
    Database,
    LedgerError,
    account_currency_label,
    format_account_amount,
    minor_to_text,
    parse_date,
    to_minor_allow_zero,
)


CASH_ACCOUNTS = {
    "JPY": "现金（日元）",
    "CNY": "现金（人民币）",
}
MANAGED_ACCOUNT_TYPES = ("bank", "wallet", "prepaid", "transit", "points")


def managed_balances(database: Database) -> list[dict[str, Any]]:
    """Return all non-credit balances plus uninitialized physical-cash rows."""
    query = """SELECT a.id,a.name,a.account_type,a.currency,a.opening_date,
                     a.balance_completeness,c.minor_digits
              FROM accounts a JOIN currencies c ON c.code=a.currency
              WHERE a.account_type IN ('bank','wallet','prepaid','transit','points')
              ORDER BY CASE a.account_type
                       WHEN 'bank' THEN 0 WHEN 'wallet' THEN 1 WHEN 'prepaid' THEN 2
                       WHEN 'transit' THEN 3 WHEN 'points' THEN 4 ELSE 5 END,
                       a.name"""
    account_rows = database.connection.execute(query).fetchall()
    rows: list[dict[str, Any]] = []
    existing_names: set[str] = set()
    cash_name_to_currency = {name: code for code, name in CASH_ACCOUNTS.items()}
    for row in account_rows:
        existing_names.add(row["name"])
        account_type = row["account_type"]
        if row["name"] in cash_name_to_currency:
            expected_currency = cash_name_to_currency[row["name"]]
            if account_type != "wallet" or row["currency"] != expected_currency:
                raise LedgerError(f"账户“{row['name']}”已存在，但类型或币种不符合现金账户设置。")
            account_type = "cash"
        rows.append({
            "account_id": int(row["id"]),
            "account_name": row["name"],
            "account_type": account_type,
            "currency": row["currency"],
            "display_currency": account_currency_label(account_type, row["currency"]),
            "minor_digits": int(row["minor_digits"]),
            "balance_minor": database.account_balance_minor(row["id"]),
            "initialized": True,
            "completeness": row["balance_completeness"],
            "opening_date": row["opening_date"],
        })

    # Physical cash is separate from the user's wallets, transit cards, and points.
    # Show its first-count rows by default, unless the user explicitly deleted one.
    cash_rows = []
    for code, name in CASH_ACCOUNTS.items():
        if name in existing_names:
            continue
        if database.get_setting(f"cash_management_hidden_default_cash_{code}") == "1":
            continue
        currency = database.currency(code)
        cash_rows.append({
            "account_id": None,
            "account_name": name,
            "account_type": "cash",
            "currency": code,
            "display_currency": code,
            "minor_digits": int(currency["minor_digits"]),
            "balance_minor": None,
            "initialized": False,
            "completeness": None,
            "opening_date": None,
        })
    ordered = cash_rows + rows
    cash_order = {name: index for index, name in enumerate(CASH_ACCOUNTS.values())}
    return sorted(
        ordered,
        key=lambda row: (0, cash_order[row["account_name"]])
        if row["account_name"] in cash_order
        else (1, 0),
    )


def sort_managed_balances(
    rows: list[dict[str, Any]], sort_mode: str = "default"
) -> list[dict[str, Any]]:
    """Keep the canonical account order or group accounts by currency."""
    if sort_mode == "default":
        return list(rows)
    if sort_mode == "currency":
        # Python's stable sort preserves the existing type/name ordering within
        # each internal currency group; points appear in JPY with a visible points label.
        return sorted(rows, key=lambda row: row["currency"])
    raise LedgerError(f"不支持的账户排序方式：{sort_mode}")


def cash_balances(database: Database) -> list[dict[str, Any]]:
    """Compatibility helper returning only the physical-cash rows."""
    cash_names = set(CASH_ACCOUNTS.values())
    return [row for row in managed_balances(database) if row["account_name"] in cash_names]


def _category_for_adjustment(account: Mapping[str, Any], surplus: bool) -> tuple[str, str]:
    if account["account_type"] == "cash":
        group = "现金"
    elif account["account_type"] == "points":
        group = "积分"
    else:
        group = "余额"
    return ("income" if surplus else "expense", f"{group}盘{'盈' if surplus else '亏'}")


def reconcile_account_balances(
    database: Database,
    counted_amounts: Mapping[str, str | int | Decimal],
    occurred_on: str,
    *,
    post_differences: bool = True,
) -> list[dict[str, Any]]:
    """Reconcile managed balances, optionally posting differences as transactions."""
    date_text = parse_date(occurred_on).isoformat()
    # Resolve FX before taking the write lock. A CNY adjustment is a single CNY
    # ledger posting with a saved JPY reporting equivalent, not a second posting.
    pre_rows = {row["account_name"]: row for row in managed_balances(database)}
    cny_rate = None
    if post_differences and any(
        (pre_rows.get(name) or {}).get("currency") == "CNY"
        and (pre_rows.get(name) or {}).get("initialized")
        for name in counted_amounts
    ):
        from .fx_rates import FxRateUnavailable, resolve_jpy_rate

        try:
            cny_rate = resolve_jpy_rate(database, "CNY", date_text)
        except FxRateUnavailable as exc:
            raise LedgerError(str(exc)) from exc
    results: list[dict[str, Any]] = []
    connection = database.connection
    try:
        # Lock before reading balances so a concurrent ledger write cannot make the
        # count comparison stale between the read and the adjustment posting.
        connection.execute("BEGIN IMMEDIATE")
        available = {row["account_name"]: row for row in managed_balances(database)}
        prepared: list[dict[str, Any]] = []
        for account_name, amount in counted_amounts.items():
            row = available.get(account_name)
            if row is None:
                raise LedgerError(f"“{account_name}”不是可调整的资金或积分账户。")
            counted_minor = to_minor_allow_zero(amount, row["currency"], row["minor_digits"])
            existing = None
            if row["account_id"] is not None:
                existing = database.connection.execute(
                    "SELECT id,account_type,currency,opening_date FROM accounts WHERE id=?",
                    (row["account_id"],),
                ).fetchone()
            if existing is not None and date_text < existing["opening_date"]:
                raise LedgerError(f"盘点日期早于账户“{account_name}”的期初日期：{existing['opening_date']}")
            book_before = row["balance_minor"] if row["initialized"] else None
            difference = counted_minor - book_before if book_before is not None else None
            prepared.append({
                **row,
                "counted_minor": counted_minor,
                "existing": existing,
                "book_before_minor": book_before,
                "difference_minor": difference,
            })

        for item in prepared:
            account_name = item["account_name"]
            code = item["currency"]
            counted_minor = item["counted_minor"]
            existing = item["existing"]
            snapshot_id = None
            if existing is None:
                if item["account_type"] != "cash":
                    raise LedgerError(f"账户“{account_name}”已不存在，无法调整。")
                cursor = connection.execute(
                    "INSERT INTO accounts "
                    "(name,account_type,currency,opening_balance_minor,opening_date,balance_completeness,opening_note) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (account_name, "wallet", code, counted_minor, date_text, "known", "现金管理表首次盘点设定的期初余额"),
                )
                account_id = int(cursor.lastrowid)
                is_opening = True
                difference = None
                transaction_id = None
                category_name = None
            else:
                account_id = int(existing["id"])
                is_opening = False
                difference = int(item["difference_minor"])
                transaction_id = None
                category_name = None
                if difference:
                    if not post_differences:
                        cutoff = int(connection.execute(
                            "SELECT COALESCE(MAX(id),0) FROM transactions"
                        ).fetchone()[0])
                        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")
                        cursor = connection.execute(
                            """INSERT INTO account_balance_snapshots
                               (account_id,snapshot_date,balance_minor,transaction_id_cutoff,note,created_at)
                               VALUES (?,?,?,?,?,?)""",
                            (account_id, date_text, counted_minor, cutoff,
                             "余额管理校准；差额未计入账本流水", now),
                        )
                        snapshot_id = int(cursor.lastrowid)
                    else:
                        kind, category_name = _category_for_adjustment(item, difference > 0)
                        category = database.category(category_name, kind)
                        book_text = format_account_amount(
                            item["book_before_minor"], item["minor_digits"], code, item["account_type"]
                        )
                        counted_text = format_account_amount(
                            counted_minor, item["minor_digits"], code, item["account_type"]
                        )
                        group = "积分" if item["account_type"] == "points" else (
                            "现金" if item["account_type"] == "cash" else "余额"
                        )
                        source = "cash_reconciliation" if group == "现金" else "balance_reconciliation"
                        if code == "CNY":
                            if cny_rate is None:
                                raise LedgerError("人民币余额调整缺少交易日JPY汇率，未修改余额。")
                            from .fx_rates import convert_minor_to_jpy_minor

                            jpy_equiv_minor = convert_minor_to_jpy_minor(
                                abs(difference), item["minor_digits"], cny_rate.rate
                            )
                            fx_values = (
                                jpy_equiv_minor,
                                format(cny_rate.rate, "f"),
                                cny_rate.rate_date,
                                cny_rate.source,
                            )
                        else:
                            fx_values = (None, None, None, None)
                        cursor = connection.execute(
                            "INSERT INTO transactions "
                            "(occurred_on,kind,amount_minor,currency,account_id,to_account_id,to_amount_minor,category_id,"
                            "description,balance_effect,jpy_equiv_minor,fx_rate,fx_rate_date,fx_source,needs_review,source) "
                            "VALUES (?,?,?,?,?,NULL,NULL,?,?, 'posted',?,?,?,?,0,?)",
                            (
                                date_text, kind, abs(difference), code, account_id, category["id"],
                                f"{group}盘点调整：账面{book_text}，实盘{counted_text}",
                                *fx_values, source,
                            ),
                        )
                        transaction_id = int(cursor.lastrowid)

            results.append({
                "account_name": account_name,
                "account_type": item["account_type"],
                "currency": code,
                "minor_digits": item["minor_digits"],
                "opening_balance": is_opening,
                "book_before_minor": item["book_before_minor"],
                "counted_minor": counted_minor,
                "difference_minor": difference,
                "transaction_id": transaction_id,
                "snapshot_id": snapshot_id,
                "difference_posted": bool(difference and post_differences),
                "category_name": category_name,
                "account_id": account_id,
            })

        for result in results:
            result["balance_minor"] = database.account_balance_minor(result["account_id"])
            result.pop("account_id")
        connection.commit()
    except sqlite3.IntegrityError as exc:
        connection.rollback()
        raise LedgerError(f"余额盘点分录未保存：{exc}") from exc
    except Exception:
        connection.rollback()
        raise
    return results


def reconcile_cash_balance(
    database: Database,
    currency_code: str,
    counted_amount: str | int | Decimal,
    occurred_on: str,
    *,
    post_differences: bool = True,
) -> dict[str, Any]:
    """Reconcile one physical-cash currency using the shared account path."""
    return reconcile_cash_balances(
        database, {currency_code: counted_amount}, occurred_on,
        post_differences=post_differences,
    )[0]


def reconcile_cash_balances(
    database: Database,
    counted_amounts: Mapping[str, str | int | Decimal],
    occurred_on: str,
    *,
    post_differences: bool = True,
) -> list[dict[str, Any]]:
    """Compatibility helper for the JPY/CNY physical-cash rows."""
    account_amounts: dict[str, str | int | Decimal] = {}
    for raw_code, amount in counted_amounts.items():
        code = raw_code.upper()
        if code not in CASH_ACCOUNTS:
            raise LedgerError("实体现金盘点仅支持JPY和CNY。")
        account_amounts[CASH_ACCOUNTS[code]] = amount
    return reconcile_account_balances(
        database, account_amounts, occurred_on, post_differences=post_differences
    )
