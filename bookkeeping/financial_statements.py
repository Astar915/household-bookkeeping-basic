from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from .credit_management import credit_card_overview
from .depreciation import fixed_asset_values as _asset_values
from .storage import Database, billing_cycle, format_account_amount, minor_to_text, parse_date


ACCOUNT_TYPE_LABELS = {
    "bank": "银行存款",
    "wallet": "钱包/账户余额",
    "prepaid": "券/预付",
    "transit": "交通卡",
    "points": "积分",
    "credit": "信用卡",
}


def build_balance_sheet(database: Database, as_of: str | date) -> dict[str, Any]:
    """Build currency-separated assets and liabilities, with points reported separately."""
    as_of_date = parse_date(as_of) if isinstance(as_of, str) else as_of
    monetary_codes = {
        row["code"] for row in database.connection.execute(
            "SELECT code FROM currencies WHERE is_monetary=1 ORDER BY code"
        )
    }
    assets = {code: 0 for code in monetary_codes}
    deposits = {code: 0 for code in monetary_codes}
    known_liabilities = {code: 0 for code in monetary_codes}
    estimated_liabilities = {code: 0 for code in monetary_codes}
    points_total = 0
    unknown_liability_count = 0
    rows: list[dict[str, Any]] = []
    credit_overview = {
        int(row["account_id"]): row
        for row in credit_card_overview(database, as_of=as_of_date.isoformat())
    }

    accounts = database.connection.execute(
        "SELECT a.*,c.minor_digits,c.is_monetary FROM accounts a "
        "JOIN currencies c ON c.code=a.currency "
        "ORDER BY c.is_monetary DESC,a.currency,"
        "CASE a.account_type WHEN 'bank' THEN 0 WHEN 'wallet' THEN 1 "
        "WHEN 'prepaid' THEN 2 WHEN 'transit' THEN 3 WHEN 'points' THEN 4 ELSE 5 END,a.name"
    ).fetchall()

    for account in accounts:
        code = account["currency"]
        digits = int(account["minor_digits"])
        account_type = account["account_type"]
        opening_date = parse_date(account["opening_date"])
        if opening_date > as_of_date:
            rows.append({
                "section": "未生效账户", "name": account["name"], "currency": code,
                "amount_minor": None, "amount_text": "尚未生效",
                "status": f"期初日期为 {opening_date.isoformat()}",
            })
            continue

        balance = database.account_balance_as_of(int(account["id"]), as_of_date)
        completeness = account["balance_completeness"]
        if account_type == "points":
            points_total += max(0, balance)
            if balance >= 0:
                section = "积分（不计入资产）"
                status = "1点=1 JPY"
            else:
                section = "积分负数（待核对）"
                status = "负数积分未计入资产合计；请核对积分使用记录"
            rows.append({
                "section": section,
                "name": account["name"],
                "currency": "PTS（JPY等值）",
                "amount_minor": balance,
                "amount_text": format_account_amount(balance, digits, "JPY", "points"),
                "status": status,
            })
            continue
        if account_type == "credit":
            credit = credit_overview.get(int(account["id"]))
            if credit and credit["debt_estimate_minor"] is not None:
                debt = int(credit["debt_estimate_minor"])
                if debt:
                    estimated_liabilities[code] = estimated_liabilities.get(code, 0) + debt
                rows.append({
                    "section": "信用卡负债估算" if debt else "信用卡",
                    "name": account["name"], "currency": code,
                    "amount_minor": debt,
                    "amount_text": minor_to_text(debt, digits, code),
                    "status": "额度差额·已核对",
                })
            elif completeness == "known":
                if balance > 0:
                    known_liabilities[code] = known_liabilities.get(code, 0) + balance
                    rows.append({
                        "section": "已确认负债", "name": account["name"], "currency": code,
                        "amount_minor": balance, "amount_text": minor_to_text(balance, digits, code),
                        "status": "按完整账本记录；尚无额度快照",
                    })
                elif balance < 0:
                    credit_balance = -balance
                    assets[code] = assets.get(code, 0) + credit_balance
                    rows.append({
                        "section": "资产（信用卡贷余）", "name": account["name"], "currency": code,
                        "amount_minor": credit_balance,
                        "amount_text": minor_to_text(credit_balance, digits, code),
                        "status": "按完整账本记录；尚无额度快照",
                    })
                else:
                    rows.append({
                        "section": "信用卡", "name": account["name"], "currency": code,
                        "amount_minor": 0, "amount_text": minor_to_text(0, digits, code),
                        "status": "无账面欠款记录；尚无额度快照",
                    })
            else:
                unknown_liability_count += 1
                rows.append({
                    "section": "负债（待录入额度）", "name": account["name"], "currency": code,
                    "amount_minor": None, "amount_text": "无法估算",
                    "status": "缺少额度快照",
                })
            continue

        if not bool(account["is_monetary"]):
            rows.append({
                "section": "非货币资产" if balance >= 0 else "非货币负数（待核对）",
                "name": account["name"], "currency": code,
                "amount_minor": balance,
                "amount_text": minor_to_text(balance, digits, code),
                "status": _completeness_label(completeness),
            })
            continue

        if balance >= 0:
            assets[code] = assets.get(code, 0) + balance
            if account_type == "bank":
                deposits[code] = deposits.get(code, 0) + balance
            section = "货币资产"
            status = _completeness_label(completeness)
        else:
            section = "负余额（待核对）"
            status = "负数余额未计入资产合计"
        rows.append({
            "section": section, "name": account["name"], "currency": code,
            "amount_minor": balance,
            "amount_text": minor_to_text(balance, digits, code),
            "status": status,
        })

    report_month = as_of_date.strftime("%Y-%m")
    for asset in database.list_fixed_assets():
        currency = str(asset["currency"])
        if currency not in monetary_codes or str(asset["acquisition_month"]) > report_month:
            continue
        if asset["disposal_month"] and str(asset["disposal_month"]) <= report_month:
            continue
        elapsed, accumulated, book_value = _asset_values(asset, report_month)
        if book_value <= 0:
            continue
        digits = int(database.currency(currency)["minor_digits"])
        included = bool(asset["include_in_balance_sheet"])
        if included:
            assets[currency] = assets.get(currency, 0) + book_value
        rows.append({
            "section": "固定资产",
            "asset_id": int(asset["id"]),
            "include_in_balance_sheet": included,
            "name": str(asset["name"]),
            "currency": currency,
            "amount_minor": book_value,
            "amount_text": minor_to_text(book_value, digits, currency),
            "original_cost_minor": int(asset["cost_minor"]),
            "original_cost_text": minor_to_text(int(asset["cost_minor"]), digits, currency),
            "accumulated_depreciation_minor": accumulated,
            "accumulated_depreciation_text": minor_to_text(accumulated, digits, currency),
            "status": (
                f"原值 {minor_to_text(int(asset['cost_minor']), digits, currency)}；"
                f"累计折旧 {minor_to_text(accumulated, digits, currency)}；"
                f"已使用 {min(elapsed, int(asset['useful_life_months']))}/"
                f"{int(asset['useful_life_months'])} 个月"
            ),
        })

    return {
        "as_of": as_of_date.isoformat(),
        "assets": assets,
        "bank_deposits": deposits,
        "known_liabilities": known_liabilities,
        "estimated_liabilities": estimated_liabilities,
        "net_assets": {
            code: int(assets.get(code, 0))
            - int(known_liabilities.get(code, 0))
            - int(estimated_liabilities.get(code, 0))
            for code in monetary_codes
        },
        "unknown_liability_count": unknown_liability_count,
        "points_total": points_total,
        "rows": rows,
    }


def _completeness_label(value: str) -> str:
    if value == "inferred":
        return "含推算期初；按账本记录"
    if value == "partial":
        return "余额/历史部分记录；待核对"
    return "按账本记录"


def build_profit_statement(database: Database, as_of: str | date) -> dict[str, Any]:
    """Summarize native-currency activity and a transaction-date JPY total."""
    as_of_date = parse_date(as_of) if isinstance(as_of, str) else as_of
    start, end = billing_cycle(as_of_date, database.get_billing_cycle_start_day())
    through = min(end, as_of_date)
    rows = database.report_rows(start.isoformat(), through.isoformat())
    currency_codes = {row["currency"] for row in rows}
    currency_codes.add("JPY")
    summaries: dict[str, dict[str, Any]] = {}
    jpy_income = 0
    jpy_expense = 0
    jpy_posted_expense = 0
    jpy_memo_expense = 0
    jpy_needs_review_expense = 0
    jpy_categories: dict[str, int] = defaultdict(int)
    missing_jpy_conversion_count = 0
    currency_jpy_net: dict[str, int] = defaultdict(int)
    currency_missing_jpy_conversion: dict[str, int] = defaultdict(int)

    for code in sorted(currency_codes):
        currency_rows = [row for row in rows if row["currency"] == code]
        income = sum(int(row["amount_minor"]) for row in currency_rows if row["kind"] == "income")
        expenses = [row for row in currency_rows if row["kind"] == "expense"]
        total_expense = sum(int(row["amount_minor"]) for row in expenses)
        posted_expense = sum(
            int(row["amount_minor"]) for row in expenses if row["balance_effect"] == "posted"
        )
        memo_expense = total_expense - posted_expense
        needs_review = sum(
            int(row["amount_minor"]) for row in expenses if bool(row["needs_review"])
        )
        categories: dict[str, int] = defaultdict(int)
        for row in expenses:
            categories[row["category_name"] or "未分类"] += int(row["amount_minor"])
        currency = database.currency(code)
        summaries[code] = {
            "minor_digits": int(currency["minor_digits"]),
            "income_minor": income,
            "expense_minor": total_expense,
            "posted_expense_minor": posted_expense,
            "memo_expense_minor": memo_expense,
            "needs_review_expense_minor": needs_review,
            "net_minor": income - total_expense,
            "categories": dict(categories),
        }

    for row in rows:
        if row["currency"] == "JPY":
            equivalent = int(row["amount_minor"])
        elif row["jpy_equiv_minor"] is not None:
            equivalent = int(row["jpy_equiv_minor"])
        else:
            missing_jpy_conversion_count += 1
            currency_missing_jpy_conversion[str(row["currency"])] += 1
            continue
        if row["kind"] == "income":
            jpy_income += equivalent
            currency_jpy_net[str(row["currency"])] += equivalent
        elif row["kind"] == "expense":
            jpy_expense += equivalent
            currency_jpy_net[str(row["currency"])] -= equivalent
            jpy_categories[row["category_name"] or "未分类"] += equivalent
            if row["balance_effect"] == "posted":
                jpy_posted_expense += equivalent
            else:
                jpy_memo_expense += equivalent
            if bool(row["needs_review"]):
                jpy_needs_review_expense += equivalent

    for code, summary in summaries.items():
        summary["jpy_equivalent_net_minor"] = currency_jpy_net[code]
        summary["missing_jpy_conversion_count"] = currency_missing_jpy_conversion[code]

    return {
        "as_of": as_of_date.isoformat(),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "through": through.isoformat(),
        "currencies": summaries,
        "jpy_equivalent": {
            "income_minor": jpy_income,
            "expense_minor": jpy_expense,
            "posted_expense_minor": jpy_posted_expense,
            "memo_expense_minor": jpy_memo_expense,
            "needs_review_expense_minor": jpy_needs_review_expense,
            "net_minor": jpy_income - jpy_expense,
            "categories": dict(jpy_categories),
            "missing_conversion_count": missing_jpy_conversion_count,
        },
    }
