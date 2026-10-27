from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import re
from typing import Any
import unicodedata

from .cash_management import CASH_ACCOUNTS
from .credit_management import credit_card_overview
from .storage import Database, LedgerError, format_account_amount, parse_date, to_minor_allow_zero
from .localization import translate


def is_balance_count_request(text: str) -> bool:
    """Recognize an instruction to count a remaining balance, not a question."""
    normalized = unicodedata.normalize("NFKC", text)
    if re.search(r"怎么|如何|怎样|为什么|如果|假如|假设|打算|计划|不要|别盘点|不盘点|"
                 r"how\s+(?:to|do)|what\s+if|should\s+i|どう|方法", normalized, re.IGNORECASE):
        return False
    if re.search(r"[?？]", normalized) and not re.search(r"请|請|帮我|幫我|麻烦|麻煩|能不能|可以帮|可以幫|please", normalized, re.IGNORECASE):
        return False
    count = re.search(r"盘点|盤點|清点|清點|盘查|盤查|核对|核對|校准|校準|校正|调整|調整|修正|更正|棚卸|reconcil(?:e|ing|iation)|adjust|count", normalized, re.IGNORECASE)
    balance = re.search(r"余额|餘額|余額|额度|額度|残高|利用可能額|balance|available\s+credit|points?|积分|積分|现金|現金", normalized, re.IGNORECASE)
    return bool(count and balance)


def count_amount(text: str, *, bare_answer: bool = False) -> tuple[str | None, str | None]:
    """Read the actual remaining balance, without treating a difference as the count."""
    normalized = unicodedata.normalize("NFKC", text).strip()
    if re.search(r"差额|差額|盘亏了|盘盈了|减少了?|增加了?|少了|多了|差了|"
                 r"decrease(?:d)?\s+by|increase(?:d)?\s+by", normalized, re.IGNORECASE):
        return None, None
    number = r"(?P<amount>[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)"
    unit = r"(?P<unit>人民币元|人民币|CNY|RMB|日元|JPY|円|元|块(?:钱)?|积分|積分|点|ポイント|points?)?"
    prefix = (r"(?:仅剩|僅剩|只剩|还剩|還剩|剩余|剩餘|剩下|剩|只有|实盘(?:余额)?|實盤(?:餘額)?|"
              r"实际(?:余额|额度)?|実際(?:の残高)?|盘点后(?:的)?(?:余额|额度)?|盤點後(?:的)?(?:餘額|額度)?|"
              r"盘点(?:余额|额度)|盤點(?:餘額|額度)|余额(?:盘点后)?|餘額(?:盤點後)?|"
              r"残高|利用可能額|available\s+credit|balance|调整到|調整到|调整成|調整成|校准到|校準到|校正为|校正為|改成|改为|改為)"
              r"\s*(?:仅剩|僅剩|只剩|还剩|還剩|剩余|剩餘|剩下|剩|调整到|調整到|调整成|調整成|改成|改为|改為|为|為|是|:|=|is|of)?\s*")
    matches = list(re.finditer(prefix + number + r"\s*" + unit, normalized, re.IGNORECASE))
    if not matches and bare_answer:
        bare = re.fullmatch(r"\s*(?:为|為|是|改为|改成|is)?\s*" + number + r"\s*" + unit + r"[。.!！]?\s*", normalized, re.IGNORECASE)
        matches = [bare] if bare else []
    if len(matches) != 1:
        return None, None
    match = matches[0]
    amount = match.group("amount").replace(",", "")
    if amount.startswith("-"):
        return None, None
    unit_text = (match.group("unit") or "").casefold()
    currency = "CNY" if unit_text in {"人民币元", "人民币", "cny", "rmb"} else (
        "JPY" if unit_text in {"日元", "jpy", "円", "积分", "積分", "点", "ポイント", "point", "points"} else None
    )
    return amount, currency


def reconcile_named_balance(
    database: Database,
    account_name: str,
    counted_amount: str | int | Decimal,
    occurred_on: str,
    *,
    stated_currency: str | None = None,
) -> dict[str, Any]:
    """Post the difference between an explicit count and this account's ledger balance.

    A credit card's counted remaining balance means its available limit, whose
    baseline comes from the saved limit snapshot. All reads and the posting
    are made under one write lock; the caller's isolated worker can then merge
    the result only if the live ledger is unchanged.
    """
    date_text = parse_date(occurred_on).isoformat()
    account = database.account(account_name)
    currency = database.currency(str(account["currency"]))
    code = str(currency["code"])
    digits = int(currency["minor_digits"])
    if stated_currency and stated_currency != code:
        raise LedgerError("盘点金额的币种与所选账户不一致，请核对。")
    if date_text < str(account["opening_date"]):
        raise LedgerError("盘点日期早于账户的期初日期，请核对。")
    counted_minor = to_minor_allow_zero(counted_amount, code, digits)
    is_credit = account["account_type"] == "credit"
    account_id = int(account["id"])

    def current_balance() -> tuple[int, int | None]:
        if not is_credit:
            return database.account_balance_as_of(account_id, date_text), None
        state = next(
            (row for row in credit_card_overview(database, date_text)
             if row["account_id"] == account_id), None
        )
        if not state or state["available_minor"] is None or state["limit_minor"] is None:
            raise LedgerError("这张信用卡没有可用额度快照，请先在信用卡管理中设置总额度和可用额度。")
        limit = int(state["limit_minor"])
        if counted_minor > limit:
            raise LedgerError("盘点后的可用额度不能超过该卡总额度，请核对。")
        # Existing later automatic snapshots would otherwise retain a value
        # calculated before this newly backdated adjustment.
        later = database.connection.execute(
            """SELECT 1 FROM transactions WHERE occurred_on>? AND balance_effect='posted'
               AND (account_id=? OR to_account_id=?)
               UNION ALL SELECT 1 FROM credit_limit_snapshots WHERE account_id=? AND snapshot_date>?
               UNION ALL SELECT 1 FROM credit_limit_recovery_points WHERE account_id=? AND snapshot_date>?
               LIMIT 1""",
            (date_text, account_id, account_id, account_id, date_text, account_id, date_text),
        ).fetchone()
        if later:
            raise LedgerError("这张信用卡在盘点日期之后已有流水或额度快照，请先核对后续记录，再调整该日期的余额。")
        return int(state["available_minor"]), limit

    connection = database.connection
    if connection.in_transaction:
        raise LedgerError("账本正在执行其他写入，请稍后再盘点。")
    rate = None
    try:
        connection.execute("BEGIN IMMEDIATE")
        before_minor, _limit = current_balance()
        difference = counted_minor - before_minor
        if difference and code == "CNY":
            # Network/cache access must not occur while holding a write lock.
            connection.rollback()
            from .fx_rates import resolve_jpy_rate

            try:
                rate = resolve_jpy_rate(database, "CNY", date_text)
            except (ValueError, RuntimeError) as exc:
                raise LedgerError(str(exc)) from exc
            if connection.in_transaction:
                connection.commit()
            connection.execute("BEGIN IMMEDIATE")
            before_minor, _limit = current_balance()
            difference = counted_minor - before_minor

        transaction_id = None
        category_name = None
        if difference:
            group = "积分" if account["account_type"] == "points" else (
                "现金" if account_name in CASH_ACCOUNTS.values() else "余额"
            )
            kind = "income" if difference > 0 else "expense"
            category_name = f"{group}盘{'盈' if difference > 0 else '亏'}"
            category = database.category(category_name, kind)
            before_text = format_account_amount(before_minor, digits, code, account["account_type"])
            counted_text = format_account_amount(counted_minor, digits, code, account["account_type"])
            subject = "可用额度" if is_credit else "余额"
            fx_values: tuple[Any, ...] = (None, None, None, None)
            if code == "CNY":
                if rate is None:
                    raise LedgerError("人民币余额调整缺少交易日JPY汇率，未修改余额。")
                from .fx_rates import convert_minor_to_jpy_minor
                fx_values = (convert_minor_to_jpy_minor(abs(difference), digits, rate.rate),
                             format(rate.rate, "f"), rate.rate_date, rate.source)
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")
            cursor = connection.execute(
                """INSERT INTO transactions
                   (occurred_on,kind,amount_minor,currency,account_id,category_id,description,
                    balance_effect,jpy_equiv_minor,fx_rate,fx_rate_date,fx_source,needs_review,source,created_at)
                   VALUES (?,?,?,?,?,?,?,'posted',?,?,?,?,0,?,?)""",
                (date_text, kind, abs(difference), code, account_id, category["id"],
                 f"{group}盘点调整：账面{subject}{before_text}，实盘{counted_text}",
                 *fx_values, "cash_reconciliation" if group == "现金" else "balance_reconciliation", now),
            )
            transaction_id = int(cursor.lastrowid)
            if is_credit:
                database._record_credit_recovery_points([transaction_id])
        connection.commit()
    except Exception:
        if connection.in_transaction:
            connection.rollback()
        raise
    return {"account_name": account_name, "account_type": account["account_type"],
            "currency": code, "minor_digits": digits, "before_minor": before_minor,
            "counted_minor": counted_minor, "difference_minor": difference,
            "category_name": category_name, "transaction_id": transaction_id}


def handle_balance_count(session: Any, text: str) -> str:
    """Complete a balance count locally, retaining account and amount across turns."""
    from .natural_language import _date_reference, _now_japan, _normalize_account_label

    tr = lambda source: translate(source, session.response_language)
    previous = session.pending_state or {}
    state = dict(previous) if previous.get("workflow") == "balance_count" else {
        "workflow": "balance_count", "account": None, "amount": None,
        "currency": None, "date": _now_japan().date().isoformat(), "original_text": "",
    }
    if previous and session._looks_like_new_transaction(text):
        answer = tr("上一笔余额盘点还没有完成，请先回答上一个问题，或说‘取消这笔’。")
        session.history.append({"role": "user", "content": text})
        session._remember(answer)
        return answer

    state["original_text"] = "\n".join(part for part in (state.get("original_text", ""), text) if part)
    session.history.append({"role": "user", "content": text})

    def ask(message: str, slot: str) -> str:
        state["question"] = message
        state["awaiting_slot"] = slot
        session.pending_state = state
        session._remember(message)
        return message

    amount, currency = count_amount(text, bare_answer=state.get("awaiting_slot") == "amount")
    if amount is not None:
        state["amount"] = amount
        state["currency"] = currency

    has_date, date_text = _date_reference(text, now=_now_japan())
    if has_date:
        try:
            date_text = parse_date(str(date_text)).isoformat() if date_text else None
        except LedgerError:
            date_text = None
        state["date"] = date_text
    if state.get("date") and state["date"] > _now_japan().date().isoformat():
        state["date"] = None

    matches = session._mentioned_accounts(text)
    if not matches and not state.get("account"):
        # A brand can refer to several products. The generic word “余额” is
        # not evidence that the user meant the wallet instead of the card.
        context = _normalize_account_label(text)
        rows = session.database.connection.execute(
            "SELECT name,account_type,currency FROM accounts ORDER BY name"
        ).fetchall()
        matches = [dict(row) for row in rows if any(
            _normalize_account_label(term) in context
            for term in session._account_context_terms(str(row["name"]))
        ) and not session._account_is_negated_in_text(str(row["name"]), text)]
    if len(matches) > 1:
        state["account"] = None
        return ask(tr("有多个账户符合这个名称：{accounts}。请说完整账户名称。").format(
            accounts="、".join(str(row["name"]) for row in matches)), "account")
    if len(matches) == 1:
        state["account"] = str(matches[0]["name"])

    if not state.get("account"):
        return ask(tr("请告诉我盘点的是哪个账户。"), "account")
    if state.get("amount") is None:
        return ask(tr("已识别账户 {account}。请告诉我盘点后实际剩余多少；不是填写差额。").format(
            account=state["account"]), "amount")
    if not state.get("date"):
        return ask(tr("请告诉我实际盘点日期，不能使用未来日期。"), "date")

    try:
        result = reconcile_named_balance(
            session.database, str(state["account"]), str(state["amount"]), str(state["date"]),
            stated_currency=state.get("currency"),
        )
    except LedgerError as exc:
        message = tr("余额盘点未记账：{error}").format(error=tr(str(exc)))
        if "没有可用额度快照" in str(exc) or "已有流水或额度快照" in str(exc):
            session.pending_state = None
            session.history.clear()
            return message
        if "币种" in str(exc) or "金额" in str(exc) or "额度不能超过" in str(exc):
            state["amount"] = None
            state["currency"] = None
            message += "\n" + tr("请重新填写盘点后的实际余额。")
            return ask(message, "amount")
        return ask(message, "date")

    subject = tr("可用额度") if result["account_type"] == "credit" else tr("余额")
    def format_value(value: int) -> str:
        return format_account_amount(value, result["minor_digits"], result["currency"], result["account_type"])
    before = format_value(result["before_minor"])
    counted = format_value(result["counted_minor"])
    if result["difference_minor"]:
        category = tr(str(result["category_name"]))
        amount_text = format_value(abs(result["difference_minor"]))
        answer = tr("已完成 {account} 的{subject}盘点：账面 {before}，实际 {counted}；已记录{category} {difference}。{date}").format(
            account=result["account_name"], subject=subject, before=before, counted=counted,
            category=category, difference=amount_text, date=result_date(state["date"]),
        )
    else:
        answer = tr("已核对 {account} 的{subject}：账面与实际均为 {counted}，没有差额，无需新增流水。{date}").format(
            account=result["account_name"], subject=subject, counted=counted, date=result_date(state["date"]),
        )
    session.pending_state = None
    session._remember(answer)
    return answer


def result_date(value: Any) -> str:
    return str(value)
