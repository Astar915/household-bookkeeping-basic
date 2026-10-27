from __future__ import annotations

import calendar
import sqlite3
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from .fx_rates import convert_minor_at_rate, resolve_exchange_rate
from .storage import Database, LedgerError, parse_date, to_minor


FREQUENCY_LABELS = {
    "daily": "每天",
    "weekly": "每周",
    "monthly": "每月",
    "yearly": "每年",
}
FREQUENCY_UNITS = {
    "daily": "天",
    "weekly": "周",
    "monthly": "个月",
    "yearly": "年",
}


def list_recurring_schedules(database: Database) -> list[sqlite3.Row]:
    return database.connection.execute(
        """SELECT s.*,a.name AS account_name,a.account_type,a.currency AS account_currency,
                  c.name AS category_name,
                  cur.minor_digits
           FROM recurring_transaction_schedules s
           JOIN accounts a ON a.id=s.account_id
           JOIN categories c ON c.id=s.category_id
           JOIN currencies cur ON cur.code=s.currency
           ORDER BY s.enabled DESC,s.next_due_date,s.id"""
    ).fetchall()


def save_recurring_schedule(
    database: Database,
    *,
    name: str,
    kind: str,
    amount: str | int | Decimal,
    account_name: str,
    category_name: str,
    frequency: str,
    interval_count: int,
    first_date: str,
    currency_code: str | None = None,
    schedule_id: int | None = None,
) -> int:
    if kind not in {"income", "expense"}:
        raise LedgerError("收支方向必须是收入或支出")
    if frequency not in FREQUENCY_LABELS:
        raise LedgerError("不支持的定期周期")
    try:
        interval = int(interval_count)
    except (TypeError, ValueError) as exc:
        raise LedgerError("周期间隔必须是正整数") from exc
    if interval < 1 or interval > 365:
        raise LedgerError("周期间隔须为1至365")
    clean_name = name.strip()
    if not clean_name:
        raise LedgerError("项目名称不能为空")
    due = parse_date(first_date)
    account = database.account(account_name)
    category = database.category(category_name, kind)
    if account["currency"] == "PTS" or account["account_type"] == "points":
        raise LedgerError("定期收支暂不支持积分账户，请选择实际资金账户")
    if due.isoformat() < str(account["opening_date"]):
        raise LedgerError(f"首次日期早于账户期初日期：{account['opening_date']}")
    account_currency = str(account["currency"])
    currency = database.currency(currency_code or account_currency)
    if currency["code"] not in {"JPY", "CNY"} or account_currency not in {"JPY", "CNY"}:
        raise LedgerError(
            "定期收支目前支持JPY和CNY账户与账单币种；其他币种暂不能自动换算。"
        )
    amount_minor = to_minor(amount, str(currency["code"]), int(currency["minor_digits"]))
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")
    if schedule_id is not None:
        existing = database.connection.execute(
            "SELECT next_due_date,anchor_day,anchor_month,enabled FROM recurring_transaction_schedules WHERE id=?",
            (schedule_id,),
        ).fetchone()
        if existing is None:
            raise LedgerError("找不到要编辑的定期收支规则")
        existing_due = str(existing["next_due_date"])
        if due.isoformat() != existing_due:
            occurrence = database.connection.execute(
                "SELECT 1 FROM recurring_transaction_occurrences WHERE schedule_id=? AND due_date=?",
                (schedule_id, due.isoformat()),
            ).fetchone()
            if occurrence is not None:
                raise LedgerError("所选下次日期已为这条规则生成账目，不能重复安排")
            anchor_day, anchor_month = due.day, due.month
        else:
            anchor_day = int(existing["anchor_day"])
            anchor_month = int(existing["anchor_month"])
        status = "等待到期" if bool(existing["enabled"]) else "已暂停"
        with database.connection:
            cursor = database.connection.execute(
                """UPDATE recurring_transaction_schedules
                   SET name=?,kind=?,amount_minor=?,currency=?,account_id=?,category_id=?,frequency=?,
                       interval_count=?,next_due_date=?,anchor_day=?,anchor_month=?,last_status=?,updated_at=?
                   WHERE id=?""",
                (clean_name, kind, amount_minor, currency["code"], account["id"], category["id"],
                 frequency, interval, due.isoformat(), anchor_day, anchor_month, status, now, schedule_id),
            )
        if cursor.rowcount != 1:
            raise LedgerError("找不到要编辑的定期收支规则")
        return schedule_id

    cursor = database.connection.execute(
        """INSERT INTO recurring_transaction_schedules
           (name,kind,amount_minor,currency,account_id,category_id,frequency,interval_count,
            next_due_date,anchor_day,anchor_month,enabled,last_status,created_at,updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,1,'等待到期',?,?)""",
        (clean_name, kind, amount_minor, currency["code"], account["id"], category["id"],
         frequency, interval, due.isoformat(), due.day, due.month, now, now),
    )
    database.connection.commit()
    return int(cursor.lastrowid)


def set_recurring_schedule_enabled(database: Database, schedule_id: int, enabled: bool) -> None:
    status = "等待到期" if enabled else "已暂停"
    database.connection.execute(
        "UPDATE recurring_transaction_schedules SET enabled=?,last_status=?,updated_at=? WHERE id=?",
        (int(enabled), status, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f"), schedule_id),
    )
    database.connection.commit()


def delete_recurring_schedule(database: Database, schedule_id: int) -> None:
    database.connection.execute(
        "DELETE FROM recurring_transaction_schedules WHERE id=?", (schedule_id,)
    )
    database.connection.commit()


def _next_due_date(due: date, frequency: str, interval: int, anchor_day: int, anchor_month: int) -> date:
    if frequency == "daily":
        return due + timedelta(days=interval)
    if frequency == "weekly":
        return due + timedelta(days=7 * interval)
    if frequency == "monthly":
        month_index = due.year * 12 + due.month - 1 + interval
        year, month_zero = divmod(month_index, 12)
        month = month_zero + 1
        return date(year, month, min(anchor_day, calendar.monthrange(year, month)[1]))
    if frequency == "yearly":
        year = due.year + interval
        return date(year, anchor_month, min(anchor_day, calendar.monthrange(year, anchor_month)[1]))
    raise LedgerError(f"不支持的定期周期：{frequency}")


def process_due_recurring_transactions(database: Database, today: str) -> list[dict[str, Any]]:
    today_date = parse_date(today)
    schedules = database.connection.execute(
        """SELECT s.*,a.name AS account_name,a.currency AS account_currency,
                  c.name AS category_name
           FROM recurring_transaction_schedules s
           JOIN accounts a ON a.id=s.account_id
           JOIN categories c ON c.id=s.category_id
           WHERE s.enabled=1 AND s.next_due_date<=?
           ORDER BY s.next_due_date,s.id""",
        (today_date.isoformat(),),
    ).fetchall()
    events: list[dict[str, Any]] = []
    for initial in schedules:
        schedule_id = int(initial["id"])
        posted_for_schedule = 0
        while True:
            schedule = database.connection.execute(
                """SELECT s.*,a.name AS account_name,a.currency AS account_currency,
                          c.name AS category_name
                   FROM recurring_transaction_schedules s
                   JOIN accounts a ON a.id=s.account_id
                   JOIN categories c ON c.id=s.category_id
                   WHERE s.id=? AND s.enabled=1""",
                (schedule_id,),
            ).fetchone()
            if schedule is None:
                break
            due = parse_date(str(schedule["next_due_date"]))
            if due > today_date:
                break
            if posted_for_schedule >= 100:
                events.append({"status": "catchup_limited", "name": schedule["name"], "due_date": due.isoformat()})
                break

            source = f"recurring_schedule:{schedule_id}"
            matched = database.connection.execute(
                """SELECT id FROM transactions
                   WHERE source=? AND occurred_on=? AND kind=? AND amount_minor=?
                     AND currency=? AND account_id=? AND category_id=? AND description=?
                   ORDER BY id LIMIT 1""",
                (source, due.isoformat(), schedule["kind"], schedule["amount_minor"],
                 schedule["currency"], schedule["account_id"], schedule["category_id"], schedule["name"]),
            ).fetchone()
            try:
                bill_currency = str(schedule["currency"])
                account_currency = str(schedule["account_currency"])
                account_amount_minor: int | None = None
                account_fx_rate: str | None = None
                account_fx_rate_date: str | None = None
                account_fx_source: str | None = None
                if bill_currency != account_currency and matched is None:
                    exchange_rate = resolve_exchange_rate(
                        database, bill_currency, account_currency, due.isoformat()
                    )
                    account_amount_minor = convert_minor_at_rate(
                        int(schedule["amount_minor"]),
                        int(database.currency(bill_currency)["minor_digits"]),
                        int(database.currency(account_currency)["minor_digits"]),
                        exchange_rate.rate,
                    )
                    if account_amount_minor <= 0:
                        raise LedgerError("汇率换算后的账户扣款金额不足最小货币单位，未记账。")
                    account_fx_rate = format(exchange_rate.rate, "f")
                    account_fx_rate_date = exchange_rate.rate_date
                    account_fx_source = exchange_rate.source
                transaction_id = (
                    int(matched["id"])
                    if matched is not None
                    else database.add_transaction(
                        occurred_on=due.isoformat(),
                        kind=str(schedule["kind"]),
                        amount=Decimal(int(schedule["amount_minor"])).scaleb(
                            -int(database.currency(str(schedule["currency"]))["minor_digits"])
                        ),
                        currency=str(schedule["currency"]),
                        description=str(schedule["name"]),
                        category_name=str(schedule["category_name"]),
                        account_name=str(schedule["account_name"]),
                        source=source,
                        account_amount_minor=account_amount_minor,
                        account_fx_rate=account_fx_rate,
                        account_fx_rate_date=account_fx_rate_date,
                        account_fx_source=account_fx_source,
                    )
                )
            except (LedgerError, sqlite3.Error, OSError, RuntimeError) as exc:
                database.connection.execute(
                    "UPDATE recurring_transaction_schedules SET last_status=?,updated_at=? WHERE id=?",
                    (f"处理失败：{exc}"[:500], datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f"), schedule_id),
                )
                database.connection.commit()
                events.append({"status": "failed", "name": schedule["name"], "due_date": due.isoformat(), "error": str(exc)})
                break

            next_due = _next_due_date(
                due, str(schedule["frequency"]), int(schedule["interval_count"]),
                int(schedule["anchor_day"]), int(schedule["anchor_month"]),
            )
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")
            with database.connection:
                database.connection.execute(
                    """INSERT OR IGNORE INTO recurring_transaction_occurrences
                       (schedule_id,due_date,status,transaction_id,created_at) VALUES (?,?,?,?,?)""",
                    (schedule_id, due.isoformat(), "matched" if matched is not None else "posted", transaction_id, now),
                )
                database.connection.execute(
                    """UPDATE recurring_transaction_schedules
                       SET next_due_date=?,last_status=?,updated_at=? WHERE id=?""",
                    (next_due.isoformat(), "已自动记账" if matched is None else "已匹配已有流水", now, schedule_id),
                )
            events.append({
                "status": "matched" if matched is not None else "posted",
                "name": schedule["name"], "due_date": due.isoformat(),
                "amount_minor": int(schedule["amount_minor"]), "currency": str(schedule["currency"]),
                "account_amount_minor": account_amount_minor,
                "account_currency": account_currency,
                "account_fx_rate": account_fx_rate,
                "account_fx_rate_date": account_fx_rate_date,
                "account_fx_source": account_fx_source,
                "transaction_id": transaction_id,
            })
            posted_for_schedule += 1
    return events
