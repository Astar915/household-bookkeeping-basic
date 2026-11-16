"""Read-only natural-language queries and ledger-grounded advice."""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from bookkeeping.natural_language import OpenAICompatibleClient
from bookkeeping.region_time import DEFAULT_TIME_ZONE, region_timezone
from bookkeeping.storage import (
    Database,
    LedgerError,
    billing_cycle,
    format_account_amount,
    minor_to_text,
    parse_date,
)


_QUERY_CUES = re.compile(
    r"查一下|查下|查查|查询|统计|列出|显示|找一下|多少|几笔|总额|合计|余额|欠款|明细|哪些|"
    r"how much|how many|what did i spend|what have i spent|list|show|balance|transactions?|total|"
    r"いくら|何件|一覧|残高|合計|明細|支出|収入",
    re.IGNORECASE,
)
_FOLLOW_UP_CUES = re.compile(
    r"那(今天|昨天|本月|上个月|这周|本周|上周|最近|今年|去年)|"
    r"(今天|昨天|本月|上个月|这周|本周|上周|最近|今年|去年)(呢|的话)?$|"
    r"what about|and (yesterday|last month|this month|this week|last week)|"
    r"では|それと|先月|今月|昨日|今日",
    re.IGNORECASE,
)
_EXPLICIT_QUERY_CUES = re.compile(
    r"查一下|查下|查查|查询|统计|列出|显示|找一下|多少|几笔|总额|合计|余额|欠款|明细|哪些|"
    r"how much|how many|what did i spend|what have i spent|list|show|balance|transactions?|total|"
    r"いくら|何件|一覧|残高|合計|明細|吗|？|\?",
    re.IGNORECASE,
)
_WRITE_CUES = re.compile(
    r"帮我记|记一笔|记账|记一下|记录一下|新增一笔|添加一笔|删除|修改|改成|转账|"
    r"买了|支付了|花了|收到了|入账|记入|(?:i )?(?:spent|paid)|bought|record|log an? (expense|income)|add an? (expense|income)|"
    r"記帳|記録して|追加して|削除|変更|振込",
    re.IGNORECASE,
)

_SCHEMA = {
    "type": "object",
    "properties": {
        "is_query": {"type": "boolean"},
        "advice": {"type": "boolean"},
        "query_type": {"type": "string", "enum": ["summary", "transactions", "balances"]},
        "kind": {"type": "string", "enum": ["expense", "income", "transfer", "all", "net"]},
        "period": {
            "type": "string",
            "enum": ["current_cycle", "this_month", "last_month", "today", "yesterday",
                     "this_week", "last_week", "this_year", "last_year",
                     "last_7_days", "last_30_days", "custom", "all_time"],
        },
        "start_date": {"type": ["string", "null"]},
        "end_date": {"type": ["string", "null"]},
        "category": {"type": ["string", "null"]},
        "account": {"type": ["string", "null"]},
        "keyword": {"type": ["string", "null"]},
        "currency": {"type": ["string", "null"]},
        "group_by": {"type": "string", "enum": ["none", "category", "account", "day"]},
        "limit": {"type": "integer"},
        "clarification": {"type": "string"},
    },
    "required": ["is_query", "advice", "query_type", "kind", "period", "start_date", "end_date",
                 "category", "account", "keyword", "currency", "group_by", "limit", "clarification"],
    "additionalProperties": False,
}


def is_ledger_query_candidate(text: str, conversation: dict[str, Any] | None = None) -> bool:
    """Use a cheap lexical gate so ordinary bookkeeping does not incur a second model call."""
    value = str(text or "").strip()
    if not value:
        return False
    if conversation and conversation.get("lastMode") == "ledger_query" and _FOLLOW_UP_CUES.search(value):
        return True
    explicit_query = bool(_EXPLICIT_QUERY_CUES.search(value))
    if _WRITE_CUES.search(value) and not explicit_query:
        return False
    if re.search(r"\d", value) and not explicit_query:
        return False
    if _QUERY_CUES.search(value):
        return True
    has_period = bool(re.search(r"本月|上个月|这个月|这周|本周|上周|最近\d+天|今年|去年|this month|last month|this week|last week", value, re.I))
    has_finance_term = bool(re.search(r"支出|收入|花费|花销|消费|流水|账目|余额|spend|income|expense|balance", value, re.I))
    return has_period and has_finance_term


def _language(language: str) -> str:
    return language if language in {"zh-CN", "ja-JP", "en-US"} else "zh-CN"


def _regional_date(request_now: datetime | None, time_zone: str = DEFAULT_TIME_ZONE) -> date:
    if request_now is None:
        request_now = datetime.now(timezone.utc)
    return request_now.astimezone(region_timezone(time_zone)).date()


def _decode_intent(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    decoder = json.JSONDecoder()
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, _end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise LedgerError("我没能看懂你要查的范围。请换成“查本月支出”或“列出昨天的流水”。")


def _model_intent(
    client: OpenAICompatibleClient,
    text: str,
    language: str,
    today: date,
    cycle_start_day: int,
    previous: dict[str, Any] | None,
    history: list[dict[str, Any]] | None = None,
    time_zone: str = DEFAULT_TIME_ZONE,
) -> dict[str, Any]:
    lang_name = {"zh-CN": "简体中文", "ja-JP": "日本語", "en-US": "English"}[language]
    system = (
        "你是记账软件的查询条件提取器。把用户查询已有账目/余额，或要求根据账本给建议的请求整理成JSON，"
        "绝不计算金额、编造账目、生成SQL或执行操作。可从问题中提取商品或商户关键词来匹配流水说明。"
        "若用户要求记账/修改/删除，或查询和写入混在一起，"
        "is_query=false。若用户要省钱计划、预算建议、消费分析等依赖账本的建议，is_query=true、advice=true、"
        "query_type=summary、kind=expense、group_by=category，并按用户说的期间取数；未指定期间时用current_cycle。"
        "普通查询advice=false。默认日期范围为 current_cycle；账期起始日由应用提供。"
        "省略的条件在追问时继承上一条查询条件；用户明确更换的条件才替换。"
        "recent_messages只用于理解上下文、省略和追问；不可把其中助手说过的数字当成事实，账本数据随后由程序查询。"
        "自定义日期用YYYY-MM-DD；无法判断且会影响查询范围时写入clarification。"
        f"输出语言：{lang_name}。当前日期（用户所在地区 {time_zone}）：{today.isoformat()}；账期每月从{cycle_start_day}日开始。"
        "只返回符合给定JSON Schema的JSON。"
    )
    user_payload = {
        "request": str(text or "")[:2000],
        "previous_query": previous,
        "recent_messages": [
            {"role": item.get("role"), "text": str(item.get("text", ""))[:1000]}
            for item in (history or [])[-8:]
            if isinstance(item, dict) and item.get("role") in {"user", "assistant"}
        ],
        "output_schema": _SCHEMA,
        "allowed_values": {
            "query_type": ["summary", "transactions", "balances"],
            "kind": ["expense", "income", "transfer", "all", "net"],
            "period": ["current_cycle", "this_month", "last_month", "today", "yesterday",
                       "this_week", "last_week", "this_year", "last_year",
                       "last_7_days", "last_30_days", "custom", "all_time"],
            "group_by": ["none", "category", "account", "day"],
        },
    }
    raw = client.complete(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
        response_schema=_SCHEMA,
        max_tokens=700,
        structured_output=True,
    )
    value = _decode_intent(raw)
    if not isinstance(value.get("is_query"), bool):
        raise LedgerError("没能确认这是查询请求。请使用“查一下”“多少”或“列出”等说法重试。")
    if not value["is_query"]:
        return {"is_query": False}
    value.setdefault("query_type", "summary")
    value.setdefault("advice", False)
    value.setdefault("kind", "all")
    value.setdefault("period", "current_cycle")
    value.setdefault("start_date", None)
    value.setdefault("end_date", None)
    value.setdefault("category", None)
    value.setdefault("account", None)
    value.setdefault("keyword", None)
    value.setdefault("currency", None)
    value.setdefault("group_by", "none")
    value.setdefault("limit", 10)
    value.setdefault("clarification", "")
    allowed = {
        "query_type": {"summary", "transactions", "balances"},
        "kind": {"expense", "income", "transfer", "all", "net"},
        "period": {"current_cycle", "this_month", "last_month", "today", "yesterday",
                   "this_week", "last_week", "this_year", "last_year",
                   "last_7_days", "last_30_days", "custom", "all_time"},
        "group_by": {"none", "category", "account", "day"},
    }
    for key, options in allowed.items():
        if value.get(key) not in options:
            raise LedgerError("查询条件格式不正确，请换一种说法重试。")
    for key in ("category", "account", "keyword", "currency", "start_date", "end_date"):
        item = value.get(key)
        if item is not None and (not isinstance(item, str) or len(item) > 100):
            raise LedgerError("查询条件太长或格式不正确，请换一种说法重试。")
    if not isinstance(value.get("limit"), int) or isinstance(value.get("limit"), bool):
        value["limit"] = 10
    value["limit"] = min(30, max(1, value["limit"]))
    value["clarification"] = str(value.get("clarification") or "")[:240]
    return value


def _period_range(
    intent: dict[str, Any], today: date, cycle_start_day: int,
    time_zone: str = DEFAULT_TIME_ZONE,
) -> tuple[date, date]:
    period = intent["period"]
    if period == "current_cycle":
        start, end = billing_cycle(today, cycle_start_day)
        return start, min(end, today)
    if period == "this_month":
        return today.replace(day=1), today
    if period == "last_month":
        first_this_month = today.replace(day=1)
        last_previous = first_this_month - timedelta(days=1)
        return last_previous.replace(day=1), last_previous
    if period == "today":
        return today, today
    if period == "yesterday":
        yesterday = today - timedelta(days=1)
        return yesterday, yesterday
    if period == "this_week":
        start = today - timedelta(days=today.weekday())
        return start, today
    if period == "last_week":
        this_week = today - timedelta(days=today.weekday())
        end = this_week - timedelta(days=1)
        return end - timedelta(days=6), end
    if period == "this_year":
        return today.replace(month=1, day=1), today
    if period == "last_year":
        end = today.replace(month=1, day=1) - timedelta(days=1)
        return end.replace(month=1, day=1), end
    if period == "last_7_days":
        return today - timedelta(days=6), today
    if period == "last_30_days":
        return today - timedelta(days=29), today
    if period == "all_time":
        return date(1, 1, 1), today
    if period == "custom":
        if not intent.get("start_date") or not intent.get("end_date"):
            raise LedgerError("请补充要查询的开始日期和结束日期，例如“2026-10-01到2026-10-31”。")
        start = parse_date(intent["start_date"], time_zone)
        end = parse_date(intent["end_date"], time_zone)
        if start > end:
            raise LedgerError("查询开始日期不能晚于结束日期。")
        return start, end
    raise LedgerError("不支持这个日期范围，请换一种说法重试。")


def _resolve_category(database: Database, phrase: str | None, language: str) -> tuple[int | None, str | None]:
    if not phrase:
        return None, None
    normalized = phrase.strip().casefold()
    rows = database.connection.execute(
        "SELECT id,name FROM categories WHERE is_active=1 ORDER BY name"
    ).fetchall()
    translation_rows = database.connection.execute(
            "SELECT category_id,translated_name FROM category_translations",
    ).fetchall()
    names: dict[int, set[str]] = {int(row["id"]): {str(row["name"])} for row in rows}
    for row in translation_rows:
        if int(row["category_id"]) in names:
            names[int(row["category_id"])].add(str(row["translated_name"]))
    exact = [int(row["id"]) for row in rows if any(name.casefold() == normalized for name in names[int(row["id"])])]
    matches = exact or [int(row["id"]) for row in rows if any(
        normalized in name.casefold() or name.casefold() in normalized
        for name in names[int(row["id"]) ]
    )]
    matches = list(dict.fromkeys(matches))
    if len(matches) != 1:
        if not matches:
            raise LedgerError(f"账本里没有找到类别“{phrase}”。请使用设置里的类别名称再查一次。")
        raise LedgerError(f"“{phrase}”可能对应多个类别，请使用完整类别名称再查一次。")
    category_id = matches[0]
    canonical = next(str(row["name"]) for row in rows if int(row["id"]) == category_id)
    return category_id, canonical


def _resolve_account(database: Database, phrase: str | None) -> tuple[int | None, str | None]:
    if not phrase:
        return None, None
    canonical = database.canonical_account_name(phrase.strip())
    if canonical is None:
        raise LedgerError(f"账本里没有找到账户“{phrase}”。请核对账户名称后再查一次。")
    row = database.account(canonical)
    return int(row["id"]), str(row["name"])


def _unit(row: Any) -> tuple[str, int]:
    if str(row["source_account_type"] or "") == "points":
        return "POINTS", 0
    return str(row["currency"]), int(row["minor_digits"])


def _amount(value: int, currency: str, digits: int, language: str) -> str:
    if currency == "POINTS":
        if language == "ja-JP":
            return f"{value:,}ポイント"
        if language == "en-US":
            return f"{value:,} points"
        return f"{value:,}点"
    return minor_to_text(value, digits, currency)


def _localized_category(database: Database, category_id: int | None, fallback: str, language: str) -> str:
    if category_id is None:
        return fallback
    row = database.connection.execute(
        "SELECT translated_name FROM category_translations WHERE category_id=? AND language=?",
        (category_id, language),
    ).fetchone()
    return str(row["translated_name"]) if row else fallback


def _query_rows(
    database: Database,
    start: date,
    end: date,
    intent: dict[str, Any],
    category_id: int | None,
    account_id: int | None,
) -> list[sqlite3.Row]:
    clauses = ["t.occurred_on BETWEEN ? AND ?"]
    params: list[Any] = [start.isoformat(), end.isoformat()]
    kind = intent["kind"]
    if kind in {"expense", "income", "transfer"}:
        clauses.append("t.kind=?")
        params.append(kind)
    if category_id is not None:
        clauses.append("t.category_id=?")
        params.append(category_id)
    if account_id is not None:
        clauses.append("(t.account_id=? OR t.to_account_id=?)")
        params.extend((account_id, account_id))
    currency = intent.get("currency")
    keyword = intent.get("keyword")
    if keyword:
        escaped_keyword = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        clauses.append("t.description LIKE ? ESCAPE '\\'")
        params.append(f"%{escaped_keyword}%")
    if currency:
        try:
            database.currency(currency)
        except LedgerError:
            raise LedgerError(f"账本不支持币种“{currency}”。") from None
        clauses.append("t.currency=?")
        params.append(currency.upper())
    where = " AND ".join(clauses)
    if intent["query_type"] == "summary":
        group_cols = ["t.kind", "t.currency", "cur.minor_digits", "t.balance_effect", "source_account.account_type"]
        selected = [
            "t.kind", "t.currency", "cur.minor_digits", "t.balance_effect",
            "source_account.account_type AS source_account_type",
            "SUM(t.amount_minor) AS total_minor", "COUNT(*) AS entry_count",
        ]
        group_by = intent["group_by"]
        if group_by == "category":
            group_cols.append("c.id")
            selected.extend(["c.id AS category_id", "c.name AS category_name"])
        elif group_by == "account":
            group_cols.extend(["source_account.id", "source_account.name"])
            selected.extend(["source_account.name AS account_name", "source_account.id AS account_id"])
        elif group_by == "day":
            group_cols.append("t.occurred_on")
            selected.append("t.occurred_on")
        return database.connection.execute(
            "SELECT " + ",".join(selected) +
            " FROM transactions t JOIN currencies cur ON cur.code=t.currency "
            "LEFT JOIN categories c ON c.id=t.category_id "
            "LEFT JOIN accounts source_account ON source_account.id=t.account_id "
            "WHERE " + where + " GROUP BY " + ",".join(group_cols) +
            " ORDER BY t.currency,t.kind,t.balance_effect," +
            ("c.name" if group_by == "category" else "source_account.name" if group_by == "account" else "t.occurred_on" if group_by == "day" else "t.kind"),
            params,
        ).fetchall()
    limit = int(intent["limit"])
    return database.connection.execute(
        "SELECT t.id,t.occurred_on,t.kind,t.amount_minor,t.currency,cur.minor_digits,"
        "t.balance_effect,t.description,t.account_id,t.to_account_id,t.to_amount_minor,"
        "t.category_id,c.name AS category_name,a.name AS account_name,a.account_type AS source_account_type,"
        "a.currency AS account_currency,ta.name AS to_account_name,ta.currency AS to_currency,"
        "ta.account_type AS to_account_type,tocur.minor_digits AS to_minor_digits,"
        "t.needs_review "
        "FROM transactions t JOIN currencies cur ON cur.code=t.currency "
        "LEFT JOIN categories c ON c.id=t.category_id "
        "LEFT JOIN accounts a ON a.id=t.account_id "
        "LEFT JOIN accounts ta ON ta.id=t.to_account_id "
        "LEFT JOIN currencies tocur ON tocur.code=ta.currency "
        "WHERE " + where + " ORDER BY t.occurred_on DESC,t.id DESC LIMIT ?",
        [*params, limit],
    ).fetchall()


def _period_label(start: date, end: date, language: str) -> str:
    if language == "ja-JP":
        return f"{start:%Y/%m/%d}〜{end:%Y/%m/%d}"
    if language == "en-US":
        return f"{start:%b %d, %Y}–{end:%b %d, %Y}"
    return f"{start.isoformat()} 至 {end.isoformat()}"


def _kind_label(kind: str, language: str) -> str:
    labels = {
        "expense": {"zh-CN": "支出", "ja-JP": "支出", "en-US": "Expense"},
        "income": {"zh-CN": "收入", "ja-JP": "収入", "en-US": "Income"},
        "transfer": {"zh-CN": "转账", "ja-JP": "振替", "en-US": "Transfer"},
        "memo": {"zh-CN": "备查（不影响余额）", "ja-JP": "参考記録（残高に反映しません）", "en-US": "Memo only (does not affect balance)"},
    }
    return labels.get(kind, {}).get(language, kind)


def _summary_answer(database: Database, rows: list[sqlite3.Row], intent: dict[str, Any], start: date,
                    end: date, language: str) -> str:
    if not rows:
        return {
            "zh-CN": f"{_period_label(start, end, language)}没有找到符合条件的记录。",
            "ja-JP": f"{_period_label(start, end, language)}に該当する記録はありません。",
            "en-US": f"No matching records were found for {_period_label(start, end, language)}.",
        }[language]
    title = {"zh-CN": "查询结果", "ja-JP": "検索結果", "en-US": "Results"}[language]
    lines = [f"{title}（{_period_label(start, end, language)}）"]
    kind = intent["kind"]
    group_by = intent["group_by"]
    if kind == "net":
        net: dict[tuple[str, int], int] = {}
        memo: dict[tuple[str, int], int] = {}
        for row in rows:
            unit, digits = _unit(row)
            key = (unit, digits)
            if row["balance_effect"] == "memo":
                memo[key] = memo.get(key, 0) + (int(row["total_minor"]) if row["kind"] == "income" else -int(row["total_minor"]))
            elif row["kind"] == "income":
                net[key] = net.get(key, 0) + int(row["total_minor"])
            elif row["kind"] == "expense":
                net[key] = net.get(key, 0) - int(row["total_minor"])
        for (unit, digits), value in sorted(net.items()):
            label = {"zh-CN": "收入减支出", "ja-JP": "収入−支出", "en-US": "Income minus expense"}[language]
            lines.append(f"{label}：{_amount(value, unit, digits, language)}")
        for (unit, digits), value in sorted(memo.items()):
            lines.append(f"{_kind_label('memo', language)}：{_amount(value, unit, digits, language)}")
        return "\n".join(lines)
    display_rows = rows[:15]
    for row in display_rows:
        row_kind = str(row["kind"])
        unit, digits = _unit(row)
        label = _kind_label(row_kind, language)
        if row["balance_effect"] == "memo":
            label = _kind_label("memo", language) + " · " + label
        extra = ""
        if group_by == "category":
            extra = " / " + _localized_category(database, row["category_id"], str(row["category_name"] or "未分类"), language)
        elif group_by == "account":
            extra = " / " + str(row["account_name"] or "未指定账户")
        elif group_by == "day":
            extra = " / " + str(row["occurred_on"])
        if language == "en-US":
            lines.append(f"{label}{extra} — {_amount(int(row['total_minor']), unit, digits, language)} ({int(row['entry_count'])} entries)")
        else:
            lines.append(f"{label}{extra}：{_amount(int(row['total_minor']), unit, digits, language)}（{int(row['entry_count'])}笔）")
    if len(rows) > len(display_rows):
        lines.append({"zh-CN": f"另有 {len(rows)-len(display_rows)} 个分组未显示。", "ja-JP": f"ほかに{len(rows)-len(display_rows)}件の分類があります。", "en-US": f"{len(rows)-len(display_rows)} more groups are omitted."}[language])
    if language == "zh-CN":
        lines.append("不同币种和积分分开显示；备查记录单独列出，不与余额类流水混算。")
    elif language == "ja-JP":
        lines.append("通貨とポイントは別々に表示しています。参考記録は残高に反映されません。")
    else:
        lines.append("Currencies and points are shown separately. Memo-only entries do not affect balances.")
    return "\n".join(lines)


def _transactions_answer(database: Database, rows: list[sqlite3.Row], start: date, end: date,
                         language: str) -> str:
    if not rows:
        return {"zh-CN": "这段时间没有找到符合条件的流水。", "ja-JP": "該当する取引はありません。", "en-US": "No matching transactions were found."}[language]
    heading = {"zh-CN": "流水", "ja-JP": "取引", "en-US": "Transactions"}[language]
    lines = [f"{heading}（{_period_label(start, end, language)}）"]
    for row in rows:
        unit, digits = _unit(row)
        amount = _amount(int(row["amount_minor"]), unit, digits, language)
        kind = _kind_label(str(row["kind"]), language)
        description = str(row["description"] or "")[:120]
        account = str(row["account_name"] or "")
        if row["kind"] == "transfer":
            account = f"{account} → {row['to_account_name'] or ''}"
        category = _localized_category(database, row["category_id"], str(row["category_name"] or ""), language)
        if row["kind"] == "transfer" and row["to_amount_minor"] is not None:
            target_unit = "POINTS" if row["to_account_type"] == "points" else str(row["to_currency"] or "")
            target_digits = 0 if target_unit == "POINTS" else int(row["to_minor_digits"] or 0)
            amount += " → " + _amount(int(row["to_amount_minor"]), target_unit, target_digits, language)
        details = " · ".join(part for part in (kind, category, account) if part)
        if row["balance_effect"] == "memo":
            details = " · ".join(part for part in (details, _kind_label("memo", language)) if part)
        lines.append(f"{row['occurred_on']}  {amount}  {description}" + (f"（{details}）" if details else ""))
    return "\n".join(lines)


def _balances_answer(database: Database, account_id: int | None, end: date, currency: str | None,
                     language: str) -> str:
    sql = (
        "SELECT a.id,a.name,a.account_type,a.currency,a.balance_completeness,c.minor_digits "
        "FROM accounts a JOIN currencies c ON c.code=a.currency"
    )
    params: list[Any] = []
    conditions = []
    if account_id is not None:
        conditions.append("a.id=?")
        params.append(account_id)
    if currency:
        try:
            database.currency(currency)
        except LedgerError:
            raise LedgerError(f"账本不支持币种“{currency}”。") from None
        conditions.append("a.currency=?")
        params.append(currency.upper())
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    rows = database.connection.execute(sql + " ORDER BY a.currency,a.name", params).fetchall()
    if not rows:
        return {"zh-CN": "没有找到符合条件的账户。", "ja-JP": "該当する口座はありません。", "en-US": "No matching accounts were found."}[language]
    heading = {"zh-CN": f"截至 {end.isoformat()} 的账面余额", "ja-JP": f"{end:%Y/%m/%d}時点の台帳残高", "en-US": f"Ledger balances as of {end.isoformat()}"}[language]
    lines = [heading]
    for row in rows[:30]:
        balance = database.account_balance_as_of(int(row["id"]), end)
        amount = format_account_amount(balance, int(row["minor_digits"]), str(row["currency"]), str(row["account_type"]))
        name = str(row["name"])
        if row["account_type"] == "credit":
            name += {"zh-CN": "（信用卡欠款）", "ja-JP": "（カード利用残高）", "en-US": " (credit card balance)"}[language]
        lines.append(f"{name}：{amount}" if language != "en-US" else f"{name}: {amount}")
    note = {"zh-CN": "按账本已入账流水计算，未包含未入账备查记录；与账户实际余额有差异时请核对余额。", "ja-JP": "台帳の記帳済み取引から計算しています。実際の残高と異なる場合は口座残高を確認してください。", "en-US": "Calculated from posted ledger entries; check the account if its real balance differs."}[language]
    lines.append(note)
    return "\n".join(lines)


def run_ledger_query(
    database_path: str,
    client_config: dict[str, Any],
    text: str,
    language: str,
    *,
    opener: Any,
    request_now: datetime | None,
    cycle_start_day: int = 15,
    conversation: dict[str, Any] | None = None,
    history: list[dict[str, Any]] | None = None,
    time_zone: str = DEFAULT_TIME_ZONE,
) -> dict[str, Any]:
    """Interpret the question with the selected API, then query SQLite read-only."""
    language = _language(language)
    path = Path(database_path).resolve()
    database = Database.__new__(Database)
    database.path = path
    database.connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=15)
    database.connection.row_factory = sqlite3.Row
    database.connection.execute("PRAGMA query_only=ON")
    database.time_zone = time_zone
    try:
        today = _regional_date(request_now, time_zone)
        try:
            cycle_start_day = int(cycle_start_day)
        except (TypeError, ValueError):
            cycle_start_day = 15
        if not 1 <= cycle_start_day <= 31:
            cycle_start_day = 15
        client = OpenAICompatibleClient(
            str(client_config.get("api_key", "")),
            api_url=str(client_config["api_url"]),
            model=str(client_config["model"]),
            thinking_enabled=client_config.get("thinking_enabled", False),
            reasoning_effort=str(client_config.get("reasoning_effort", "low")),
            timeout=float(client_config.get("timeout", 90)),
            opener=opener,
        )
        intent = _model_intent(
            client, text, language, today, cycle_start_day,
            (conversation or {}).get("queryContext"), history, time_zone,
        )
        if not intent.get("is_query"):
            lang_name = {"zh-CN": "简体中文", "ja-JP": "日本語", "en-US": "English"}[language]
            messages = [{
                "role": "system",
                "content": (
                    "你是家庭记账软件里的自然语言助手。请直接回答用户，不要说你只能查账。"
                    "如果用户实际想查账或记账，请简短说明可以直接自然地描述需求。"
                    f"使用{lang_name}。"
                ),
            }]
            messages.extend(
                {"role": item["role"], "content": str(item.get("text", ""))[:1000]}
                for item in (history or [])[-6:]
                if isinstance(item, dict) and item.get("role") in {"user", "assistant"}
            )
            messages.append({"role": "user", "content": str(text or "")[:4000]})
            answer = client.complete(messages, max_tokens=1000, structured_output=False)
            return {"answer": answer, "usage": client.usage_snapshot(), "context": None}
        clarification = intent.get("clarification", "").strip()
        if clarification:
            return {"answer": clarification, "usage": client.usage_snapshot(), "context": None}

        if intent.get("period") is None:
            intent["period"] = "current_cycle"
        previous = (conversation or {}).get("queryContext") or {}
        is_follow_up = bool(previous and _FOLLOW_UP_CUES.search(str(text or "")))
        if is_follow_up:
            explicit_period = re.search(
                r"今天|昨日|昨天|本月|这个月|上个月|最近\d+天|这周|本周|上周|今年|去年|"
                r"today|yesterday|this month|last month|this week|last \d+ days|last week|"
                r"今日|昨日|今月|先月|今週|先週",
                str(text or ""), re.IGNORECASE,
            )
            if not explicit_period and intent["period"] == "current_cycle":
                intent["period"] = previous.get("period", "current_cycle")
            for key in ("kind", "query_type", "category", "account", "keyword", "currency", "group_by", "limit"):
                if intent.get(key) in (None, "", "all", "none") and previous.get(key) not in (None, "", "all", "none"):
                    intent[key] = previous[key]
        start, end = _period_range(intent, today, cycle_start_day, time_zone)
        category_id, canonical_category = _resolve_category(database, intent.get("category"), language)
        account_id, canonical_account = _resolve_account(database, intent.get("account"))
        intent["category"] = canonical_category
        intent["account"] = canonical_account
        if intent["query_type"] == "balances":
            answer = _balances_answer(database, account_id, end, intent.get("currency"), language)
        else:
            rows = _query_rows(database, start, end, intent, category_id, account_id)
            if intent["query_type"] == "summary":
                answer = _summary_answer(database, rows, intent, start, end, language)
            else:
                answer = _transactions_answer(database, rows, start, end, language)
        if intent.get("advice"):
            lang_name = {"zh-CN": "简体中文", "ja-JP": "日本語", "en-US": "English"}[language]
            answer = client.complete(
                [
                    {
                        "role": "system",
                        "content": (
                            "你是家庭账本助手。根据提供的账本汇总，给出简短、可执行的省钱或预算建议。"
                            "账本汇总中的金额和期间是唯一事实来源；不要虚构记录、余额或预算。"
                            "明确区分账本事实和建议；若没有可用支出数据，坦诚说明并给出需要补充什么。"
                            "不要把建议说成保证节省的金额，也不要要求用户删除或隐瞒账目。"
                            f"使用{lang_name}，优先用项目符号列出最多3条建议。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {"request": str(text or "")[:2000], "ledger_summary": answer},
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                    },
                ],
                max_tokens=900,
                structured_output=False,
            )
        context = {key: intent.get(key) for key in (
            "advice", "query_type", "kind", "period", "start_date", "end_date", "category", "account", "keyword",
            "currency", "group_by", "limit",
        )}
        return {"answer": answer, "usage": client.usage_snapshot(), "context": context}
    finally:
        database.close()
