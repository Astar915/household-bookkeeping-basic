from __future__ import annotations

import calendar
from datetime import date, datetime, timezone
from typing import Any

from .storage import Database, LedgerError, parse_date, to_minor


REPAYMENT_SOURCE_TYPES = {"bank", "wallet", "prepaid", "transit"}


def credit_card_overview(database: Database, as_of: str | None = None) -> list[dict[str, Any]]:
    """Return current availability and user-defined debt estimates from limit snapshots."""
    as_of_text = parse_date(as_of).isoformat() if as_of else None
    cards = database.connection.execute(
        "SELECT * FROM accounts WHERE account_type='credit' ORDER BY name"
    ).fetchall()
    schedules = {
        int(row["card_account_id"]): dict(row)
        for row in database.connection.execute(
            """SELECT r.*,source.name AS source_name,
                      CASE WHEN p.status='pending' THEN p.amount_minor END AS amount_minor,
                      p.status AS amount_status
               FROM credit_repayment_rules r
               JOIN accounts source ON source.id=r.source_account_id
               LEFT JOIN credit_repayment_periods p
                 ON p.rule_id=r.id AND p.due_date=r.next_due_date"""
        )
    }
    overview: list[dict[str, Any]] = []
    for card in cards:
        currency = database.currency(card["currency"])
        snapshot_date_filter = " AND snapshot_date<=?" if as_of_text else ""
        snapshot_params: tuple[Any, ...] = (int(card["id"]),)
        if as_of_text:
            snapshot_params += (as_of_text,)
        snapshot = database.connection.execute(
            f"""SELECT * FROM (
                    SELECT id,account_id,snapshot_date,limit_minor,available_minor,note,created_at,
                           NULL AS transaction_id,'manual' AS snapshot_type
                    FROM credit_limit_snapshots
                    WHERE account_id=?{snapshot_date_filter}
                    UNION ALL
                    SELECT id,account_id,snapshot_date,limit_minor,available_minor,
                           '流水后自动快照' AS note,created_at,transaction_id,'automatic' AS snapshot_type
                    FROM credit_limit_recovery_points
                    WHERE account_id=? AND available_minor IS NOT NULL{snapshot_date_filter}
               ) ORDER BY snapshot_date DESC,created_at DESC,
                         COALESCE(transaction_id,0) DESC,id DESC LIMIT 1""",
            snapshot_params + snapshot_params,
        ).fetchone()
        limit_minor = int(snapshot["limit_minor"]) if snapshot else None
        available_minor = int(snapshot["available_minor"]) if snapshot else None
        if snapshot:
            movements_query = """SELECT id,kind,amount_minor,account_amount_minor,
                                        to_amount_minor,account_id,to_account_id
                   FROM transactions
                   WHERE balance_effect='posted'
                     AND (occurred_on > ? OR (occurred_on = ? AND (
                          created_at > ? OR (created_at = ? AND id > COALESCE(?,0)))))
                     AND (account_id=? OR to_account_id=?)"""
            movement_params: list[Any] = [
                snapshot["snapshot_date"], snapshot["snapshot_date"], snapshot["created_at"],
                snapshot["created_at"], snapshot["transaction_id"], card["id"], card["id"],
            ]
            if as_of_text:
                movements_query += " AND occurred_on<=?"
                movement_params.append(as_of_text)
            movements_query += " ORDER BY created_at,id"
            movements = database.connection.execute(movements_query, movement_params).fetchall()
            adjustment = 0
            for movement in movements:
                if movement["kind"] == "expense" and movement["account_id"] == card["id"]:
                    card_amount = (
                        int(movement["account_amount_minor"])
                        if movement["account_amount_minor"] is not None
                        else int(movement["amount_minor"])
                    )
                    adjustment -= card_amount
                elif movement["kind"] == "income" and movement["account_id"] == card["id"]:
                    card_amount = (
                        int(movement["account_amount_minor"])
                        if movement["account_amount_minor"] is not None
                        else int(movement["amount_minor"])
                    )
                    adjustment += card_amount
                elif movement["kind"] == "transfer":
                    if movement["account_id"] == card["id"]:
                        adjustment -= int(movement["amount_minor"])
                    if movement["to_account_id"] == card["id"]:
                        adjustment += int(movement["to_amount_minor"])
            available_minor = min(limit_minor, max(0, available_minor + adjustment))
        overview.append({
            "account_id": int(card["id"]),
            "name": card["name"],
            "currency": card["currency"],
            "minor_digits": int(currency["minor_digits"]),
            "completeness": card["balance_completeness"],
            "snapshot_date": snapshot["snapshot_date"] if snapshot else None,
            "snapshot_created_at": snapshot["created_at"] if snapshot else None,
            "snapshot_type": snapshot["snapshot_type"] if snapshot else None,
            "limit_minor": limit_minor,
            "available_minor": available_minor,
            "debt_estimate_minor": (
                max(0, limit_minor - available_minor)
                if limit_minor is not None and available_minor is not None else None
            ),
            "repayment_schedule": schedules.get(int(card["id"])),
        })
    return overview


def next_month_due_date(current_due_date: str, due_day: int | None = None) -> str:
    """Advance one calendar month, clamping month-end dates where needed."""
    current = parse_date(current_due_date)
    requested_day = current.day if due_day is None else due_day
    if not 1 <= requested_day <= 31:
        raise LedgerError("每月还款日必须是1至31日")
    year = current.year + (1 if current.month == 12 else 0)
    month = 1 if current.month == 12 else current.month + 1
    day = min(requested_day, calendar.monthrange(year, month)[1])
    return date(year, month, day).isoformat()


def save_credit_repayment_schedule(
    database: Database,
    *,
    card_name: str,
    source_account_name: str,
    first_due_date: str,
    amount: str | int | None = None,
) -> int:
    """Save fixed repayment routing and an optional amount for one due date only."""
    card = database.account(card_name)
    source = database.account(source_account_name)
    if card["account_type"] != "credit":
        raise LedgerError(f"账户“{card_name}”不是信用卡账户")
    if source["account_type"] not in REPAYMENT_SOURCE_TYPES:
        raise LedgerError("自动还款转出账户必须是银行、钱包、券/预付或交通卡账户")
    if source["currency"] != card["currency"]:
        raise LedgerError("自动还款账户与信用卡币种不同；此处不支持自动换汇")
    currency = database.currency(card["currency"])
    amount_text = str(amount).strip() if amount is not None else ""
    amount_minor = (
        to_minor(amount_text, currency["code"], int(currency["minor_digits"]))
        if amount_text else None
    )
    due_date = parse_date(first_due_date)
    if due_date < date.today():
        raise LedgerError("下次还款日期必须是今天或未来日期；过去日期请先核对实际扣款")

    existing = database.connection.execute(
        "SELECT id,due_day,next_due_date FROM credit_repayment_rules WHERE card_account_id=?",
        (card["id"],),
    ).fetchone()
    due_day = due_date.day
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")
    due_date_text = due_date.isoformat()
    with database.connection:
        if existing:
            schedule_id = int(existing["id"])
            old_due_date = existing["next_due_date"]
            if due_date_text == old_due_date or due_date.day == int(existing["due_day"]):
                due_day = int(existing["due_day"])
            if old_due_date != due_date_text:
                old_period = database.connection.execute(
                    "SELECT id,status FROM credit_repayment_periods WHERE rule_id=? AND due_date=?",
                    (schedule_id, old_due_date),
                ).fetchone()
                if old_period and old_period["status"] == "pending":
                    if old_due_date[:7] == due_date_text[:7]:
                        collision = database.connection.execute(
                            "SELECT 1 FROM credit_repayment_periods WHERE rule_id=? AND due_date=?",
                            (schedule_id, due_date_text),
                        ).fetchone()
                        if not collision:
                            database.connection.execute(
                                "UPDATE credit_repayment_periods SET due_date=?,updated_at=? WHERE id=?",
                                (due_date_text, now, old_period["id"]),
                            )
                    else:
                        database.connection.execute(
                            "UPDATE credit_repayment_periods SET status='cancelled',updated_at=? WHERE id=?",
                            (now, old_period["id"]),
                        )
            database.connection.execute(
                """UPDATE credit_repayment_rules
                   SET source_account_id=?,currency=?,due_day=?,next_due_date=?,enabled=1,
                       last_status='等待本期金额或还款日',updated_at=? WHERE id=?""",
                (source["id"], currency["code"], due_day, due_date_text, now, schedule_id),
            )
        else:
            cursor = database.connection.execute(
                """INSERT INTO credit_repayment_rules
                   (card_account_id,source_account_id,currency,due_day,next_due_date,
                    enabled,last_status,created_at,updated_at)
                   VALUES (?,?,?,?,?,1,'等待本期金额或还款日',?,?)""",
                (card["id"], source["id"], currency["code"], due_day,
                 due_date_text, now, now),
            )
            schedule_id = int(cursor.lastrowid)

        period = database.connection.execute(
            "SELECT id,status FROM credit_repayment_periods WHERE rule_id=? AND due_date=?",
            (schedule_id, due_date_text),
        ).fetchone()
        if amount_minor is not None:
            if period and period["status"] == "posted":
                raise LedgerError("这期还款已经记账，不能再修改金额")
            database.connection.execute(
                """INSERT INTO credit_repayment_periods
                   (rule_id,due_date,amount_minor,status,transaction_id,created_at,updated_at)
                   VALUES (?,?,?,'pending',NULL,?,?)
                   ON CONFLICT(rule_id,due_date) DO UPDATE SET
                       amount_minor=excluded.amount_minor,status='pending',transaction_id=NULL,
                       updated_at=excluded.updated_at""",
                (schedule_id, due_date_text, amount_minor, now, now),
            )
            database.connection.execute(
                "UPDATE credit_repayment_rules SET last_status='本期金额已填写，等待还款日' WHERE id=?",
                (schedule_id,),
            )
        elif period and period["status"] == "pending":
            # Clearing the field explicitly cancels this month's amount without deleting its evidence.
            database.connection.execute(
                "UPDATE credit_repayment_periods SET status='cancelled',updated_at=? WHERE id=?",
                (now, period["id"]),
            )
            database.connection.execute(
                "UPDATE credit_repayment_rules SET last_status='本期金额已清除，未安排自动记账' WHERE id=?",
                (schedule_id,),
            )
    return schedule_id


def set_credit_repayment_schedule_enabled(
    database: Database, *, card_name: str, enabled: bool
) -> None:
    card = database.account(card_name)
    if card["account_type"] != "credit":
        raise LedgerError(f"账户“{card_name}”不是信用卡账户")
    cursor = database.connection.execute(
        "UPDATE credit_repayment_rules SET enabled=?,last_status=?,updated_at=? WHERE card_account_id=?",
        (int(enabled), "等待本期金额或还款日" if enabled else "已暂停", date.today().isoformat(), card["id"]),
    )
    if cursor.rowcount == 0:
        raise LedgerError(f"“{card_name}”还没有每月应还计划")
    database.connection.commit()


def credit_repayment_schedules(database: Database) -> list[dict[str, Any]]:
    rows = database.connection.execute(
        """SELECT r.*,card.name AS card_name,card.currency AS card_currency,
                  source.name AS source_name,
                  CASE WHEN p.status='pending' THEN p.amount_minor END AS amount_minor,
                  p.status AS amount_status
           FROM credit_repayment_rules r
           JOIN accounts card ON card.id=r.card_account_id
           JOIN accounts source ON source.id=r.source_account_id
           LEFT JOIN credit_repayment_periods p
             ON p.rule_id=r.id AND p.due_date=r.next_due_date
           ORDER BY card.name"""
    ).fetchall()
    return [dict(row) for row in rows]


def process_due_credit_repayments(database: Database, today: str) -> list[dict[str, Any]]:
    """Post only the entered amount for the current due date; never reuse it next month."""
    today_date = parse_date(today)
    due_schedules = database.connection.execute(
        """SELECT r.*,card.name AS card_name FROM credit_repayment_rules r
           JOIN accounts card ON card.id=r.card_account_id
           WHERE r.enabled=1 AND r.next_due_date<=? ORDER BY r.next_due_date,r.id""",
        (today_date.isoformat(),),
    ).fetchall()
    events: list[dict[str, Any]] = []
    for schedule in due_schedules:
        schedule_id = int(schedule["id"])
        due_date = parse_date(schedule["next_due_date"])
        if due_date < today_date:
            status = "到期日已过，未自动记账；请核对实际扣款"
            following_due_date = next_month_due_date(due_date.isoformat(), int(schedule["due_day"]))
            if database.connection.in_transaction:
                raise LedgerError("账本正在执行其他写入，无法安全处理自动还款")
            with database.connection:
                database.connection.execute(
                    "UPDATE credit_repayment_periods SET status='missed',updated_at=? "
                    "WHERE rule_id=? AND due_date=? AND status='pending'",
                    (today_date.isoformat(), schedule_id, due_date.isoformat()),
                )
                if schedule["last_status"] != status:
                    database.connection.execute(
                        "UPDATE credit_repayment_rules SET next_due_date=?,last_status=?,updated_at=? WHERE id=?",
                        (following_due_date, status, today_date.isoformat(), schedule_id),
                    )
                else:
                    database.connection.execute(
                        "UPDATE credit_repayment_rules SET next_due_date=?,updated_at=? WHERE id=?",
                        (following_due_date, today_date.isoformat(), schedule_id),
                    )
            events.append({"status": "missed", "card_name": schedule["card_name"], "due_date": due_date.isoformat()})
            continue

        if database.connection.in_transaction:
            raise LedgerError("账本正在执行其他写入，无法安全处理自动还款")
        try:
            database.connection.execute("BEGIN IMMEDIATE")
            current = database.connection.execute(
                """SELECT r.*,card.name AS card_name,card.opening_date AS card_opening,
                          card.account_type AS card_type,card.currency AS card_currency,
                          source.name AS source_name,source.opening_date AS source_opening,
                          source.account_type AS source_type,source.currency AS source_currency
                   FROM credit_repayment_rules r
                   JOIN accounts card ON card.id=r.card_account_id
                   JOIN accounts source ON source.id=r.source_account_id
                   WHERE r.id=? AND r.enabled=1""",
                (schedule_id,),
            ).fetchone()
            if current is None:
                database.connection.rollback()
                continue
            due_date_text = due_date.isoformat()
            if (current["card_type"] != "credit" or
                    current["source_type"] not in REPAYMENT_SOURCE_TYPES or
                    current["currency"] != current["card_currency"] or
                    current["currency"] != current["source_currency"]):
                status = "账户设置不匹配，未自动记账"
                database.connection.execute(
                    "UPDATE credit_repayment_rules SET last_status=?,updated_at=? WHERE id=?",
                    (status, today_date.isoformat(), schedule_id),
                )
                database.connection.commit()
                events.append({"status": "invalid", "card_name": current["card_name"], "due_date": due_date_text})
                continue
            if due_date_text < current["card_opening"] or due_date_text < current["source_opening"]:
                status = "账户期初晚于还款日，未自动记账"
                database.connection.execute(
                    "UPDATE credit_repayment_rules SET last_status=?,updated_at=? WHERE id=?",
                    (status, today_date.isoformat(), schedule_id),
                )
                database.connection.commit()
                events.append({"status": "invalid", "card_name": current["card_name"], "due_date": due_date_text})
                continue

            period = database.connection.execute(
                "SELECT * FROM credit_repayment_periods WHERE rule_id=? AND due_date=?",
                (schedule_id, due_date_text),
            ).fetchone()
            if period is None or period["status"] != "pending":
                status = "本期金额未填写，未自动记账"
                if current["last_status"] != status:
                    database.connection.execute(
                        "UPDATE credit_repayment_rules SET last_status=?,updated_at=? WHERE id=?",
                        (status, today_date.isoformat(), schedule_id),
                    )
                database.connection.commit()
                events.append({"status": "amount_missing", "card_name": current["card_name"], "due_date": due_date_text})
                continue

            amount_minor = int(period["amount_minor"])
            existing_rows = database.connection.execute(
                """SELECT id,account_id,to_amount_minor FROM transactions
                   WHERE kind='transfer' AND balance_effect='posted' AND to_account_id=?
                     AND occurred_on=? ORDER BY id""",
                (current["card_account_id"], due_date_text),
            ).fetchall()
            already_paid = sum(int(row["to_amount_minor"]) for row in existing_rows)
            if already_paid:
                if already_paid >= amount_minor:
                    linked_id = (
                        int(existing_rows[0]["id"])
                        if len(existing_rows) == 1
                        and int(existing_rows[0]["account_id"]) == int(current["source_account_id"])
                        and int(existing_rows[0]["to_amount_minor"]) == amount_minor
                        else None
                    )
                    following_due_date = next_month_due_date(due_date_text, int(current["due_day"]))
                    status = "当日已有还款，不重复记账"
                    database.connection.execute(
                        """UPDATE credit_repayment_periods
                           SET status='posted',transaction_id=?,updated_at=? WHERE id=?""",
                        (linked_id, today_date.isoformat(), period["id"]),
                    )
                    database.connection.execute(
                        """UPDATE credit_repayment_rules SET next_due_date=?,last_status=?,updated_at=?
                           WHERE id=?""",
                        (following_due_date, status, today_date.isoformat(), schedule_id),
                    )
                    database.connection.commit()
                    events.append({"status": "already_paid", "card_name": current["card_name"], "due_date": due_date_text})
                else:
                    status = "当日已有部分还款，未自动补差；请核对"
                    if current["last_status"] != status:
                        database.connection.execute(
                            "UPDATE credit_repayment_rules SET last_status=?,updated_at=? WHERE id=?",
                            (status, today_date.isoformat(), schedule_id),
                        )
                    database.connection.commit()
                    events.append({"status": "partial_payment", "card_name": current["card_name"], "due_date": due_date_text})
                continue

            source_balance = database.account_balance_as_of(
                int(current["source_account_id"]), due_date_text
            )
            if source_balance < amount_minor:
                status = "余额不足，未自动记账"
                if current["last_status"] != status:
                    database.connection.execute(
                        "UPDATE credit_repayment_rules SET last_status=?,updated_at=? WHERE id=?",
                        (status, today_date.isoformat(), schedule_id),
                    )
                database.connection.commit()
                events.append({"status": "insufficient", "card_name": current["card_name"], "due_date": due_date_text})
                continue

            created_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")
            cursor = database.connection.execute(
                """INSERT INTO transactions
                   (occurred_on,kind,amount_minor,currency,account_id,to_account_id,to_amount_minor,
                    category_id,description,balance_effect,needs_review,source,created_at)
                   VALUES (?,'transfer',?,?,?,?,?,NULL,?,'posted',0,'scheduled_card_repayment',?)""",
                (due_date_text, amount_minor, current["currency"],
                 current["source_account_id"], current["card_account_id"], amount_minor,
                 f"{current['card_name']}本期应还（按用户当月填写金额）", created_at),
            )
            transaction_id = int(cursor.lastrowid)
            following_due_date = next_month_due_date(due_date_text, int(current["due_day"]))
            status = f"本期已记入账本 #{transaction_id}；未连接银行"
            database.connection.execute(
                """UPDATE credit_repayment_periods
                   SET status='posted',transaction_id=?,updated_at=? WHERE id=?""",
                (transaction_id, today_date.isoformat(), period["id"]),
            )
            database.connection.execute(
                """UPDATE credit_repayment_rules
                   SET next_due_date=?,last_status=?,updated_at=? WHERE id=?""",
                (following_due_date, status, today_date.isoformat(), schedule_id),
            )
            database._record_credit_recovery_points([transaction_id])
            database.connection.commit()
            events.append({
                "status": "posted", "card_name": current["card_name"],
                "source_name": current["source_name"], "amount_minor": amount_minor,
                "currency": current["currency"], "due_date": due_date_text,
                "next_due_date": following_due_date, "transaction_id": transaction_id,
            })
        except Exception:
            database.connection.rollback()
            raise
    return events


def recent_credit_repayments(database: Database, limit: int = 20) -> list[dict[str, Any]]:
    """List recent account transfers whose destination is a credit card."""
    if not 1 <= limit <= 100:
        raise LedgerError("还款记录显示条数必须在1至100之间")
    rows = database.connection.execute(
        """SELECT t.id,t.occurred_on,t.amount_minor,t.currency,c.minor_digits,t.to_amount_minor,
                  a.name AS source_name,d.name AS card_name,d.currency AS card_currency,
                  t.description
           FROM transactions t
           JOIN accounts a ON a.id=t.account_id
           JOIN accounts d ON d.id=t.to_account_id
           JOIN currencies c ON c.code=t.currency
           WHERE t.kind='transfer' AND d.account_type='credit'
           ORDER BY t.occurred_on DESC,t.id DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def record_credit_card_repayment(
    database: Database,
    *,
    card_name: str,
    source_account_name: str,
    amount: str | int,
    occurred_on: str,
    description: str = "",
) -> int:
    """Record a card repayment as a transfer, never as a second expense."""
    card = database.account(card_name)
    source = database.account(source_account_name)
    if card["account_type"] != "credit":
        raise LedgerError(f"账户“{card_name}”不是信用卡账户")
    if source["account_type"] not in REPAYMENT_SOURCE_TYPES:
        raise LedgerError("还款转出账户必须是银行、钱包、券/预付或交通卡账户")
    if source["currency"] != card["currency"]:
        raise LedgerError("还款账户与信用卡币种不同；此处不支持自动换汇")
    return database.add_transaction(
        occurred_on=occurred_on,
        kind="transfer",
        amount=amount,
        currency=card["currency"],
        account_name=source["name"],
        to_account_name=card["name"],
        description=description.strip() or f"{card_name}信用卡还款",
        source="gui_card_repayment",
    )
