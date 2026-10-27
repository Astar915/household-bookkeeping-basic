from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from .storage import (
    Database,
    LedgerError,
    billing_cycle,
    format_account_amount,
    minor_to_text,
    parse_date,
    seed_demo_data,
)
from .credit_management import credit_card_overview
from .natural_language import NaturalLanguageError, NaturalLanguageSession, OpenAICompatibleClient
from .payment_preferences import PaymentPromptSettingsError, PaymentPromptStore
from .skill_settings import BookkeepingSkillError, BookkeepingSkillStore


DEFAULT_DB = Path(__file__).resolve().parents[1] / "data" / "household_bookkeeping.sqlite3"


def _add_global_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="household-bookkeeping", description="离线家庭记账CLI")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite数据库路径")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="初始化数据库")
    init.add_argument("--seed-demo", action="store_true", help="向空数据库写入虚构演示数据")

    sub.add_parser("summary", help="按币种查看账户余额和额度快照")
    sub.add_parser("accounts", help="列出账户")
    sub.add_parser("chat", help="通过配置的Chat Completions API用自然语言记账")

    add = sub.add_parser("account-add", help="新增一个独立账户")
    add.add_argument("--name", required=True)
    add.add_argument("--type", dest="account_type", required=True, choices=("bank", "wallet", "prepaid", "transit", "points", "credit"))
    add.add_argument("--currency", required=True)
    add.add_argument("--opening-balance", required=True)
    add.add_argument("--opening-date", required=True)
    add.add_argument("--completeness", choices=("known", "inferred", "partial"), default="known")
    add.add_argument("--note", default="")

    for kind in ("income", "expense"):
        record = sub.add_parser(kind, help=f"记录{kind}")
        record.add_argument("--date", required=True)
        record.add_argument("--amount", required=True)
        record.add_argument("--currency", required=True)
        record.add_argument("--account")
        record.add_argument("--category", required=True)
        record.add_argument("--description", required=True)
        record.add_argument("--memo-only", action="store_true", help="只作备查，不改变账户余额")
        record.add_argument("--needs-review", action="store_true")

    transfer = sub.add_parser("transfer", help="记录转账/信用卡还款，不计入消费")
    transfer.add_argument("--date", required=True)
    transfer.add_argument("--from-account", required=True)
    transfer.add_argument("--to-account", required=True)
    transfer.add_argument("--amount", required=True, help="转出金额")
    transfer.add_argument("--to-amount", help="转入金额；跨币种时必填")
    transfer.add_argument("--description", required=True)

    snapshot = sub.add_parser("card-limit-snapshot", help="保存信用卡额度快照并计算当前欠款估算")
    snapshot.add_argument("--account", required=True)
    snapshot.add_argument("--date", required=True)
    snapshot.add_argument("--limit", required=True)
    snapshot.add_argument("--available", required=True)
    snapshot.add_argument("--note", default="")

    report = sub.add_parser("report", help="按日期和币种查看收支分类报表")
    report.add_argument("--from", dest="start", required=True)
    report.add_argument("--to", dest="end", required=True)
    report.add_argument("--currency")

    cycle = sub.add_parser("billing-cycle", help="查询某日所属15日至14日账期")
    cycle.add_argument("date")

    transactions = sub.add_parser("transactions", help="列出收支和转账记录")
    transactions.add_argument("--from", dest="start")
    transactions.add_argument("--to", dest="end")

    sub.add_parser("validate", help="校验数据库和交易结构")
    backup = sub.add_parser("backup", help="创建SQLite一致性备份")
    backup.add_argument("--destination", type=Path)
    backup.add_argument("--overwrite", action="store_true")
    return parser


def _format_account(db: Database, row: sqlite3.Row) -> str:
    currency = db.currency(row["currency"])
    if row["account_type"] == "credit":
        overview = next(
            item for item in credit_card_overview(db)
            if int(item["account_id"]) == int(row["id"])
        )
        if overview["debt_estimate_minor"] is None:
            return f"- {row['name']} [credit] 当前欠款估算: 无法估算（尚无额度快照）"
        completeness = "历史流水不完整；" if row["balance_completeness"] != "known" else ""
        return (
            f"- {row['name']} [credit] 当前欠款估算: "
            f"{minor_to_text(overview['debt_estimate_minor'], currency['minor_digits'], currency['code'])} "
            f"（总额度 {minor_to_text(overview['limit_minor'], currency['minor_digits'], currency['code'])} − "
            f"可用额度 {minor_to_text(overview['available_minor'], currency['minor_digits'], currency['code'])}；"
            f"{completeness}非当月应还账单）"
        )
    balance = db.account_balance_minor(row["id"])
    label = "余额"
    suffix = ""
    if row["balance_completeness"] == "inferred":
        suffix = "（快照已还原；过渡期初推算）"
    elif row["balance_completeness"] == "partial":
        suffix = "（历史记录部分缺失）" if row["account_type"] == "credit" else "（部分记录）"
    amount_text = format_account_amount(
        balance, currency["minor_digits"], currency["code"], row["account_type"]
    )
    return f"- {row['name']} [{row['account_type']}] {label}: {amount_text}{suffix}"


def _summary(db: Database) -> None:
    print("账户余额（按币种分别显示）")
    accounts = db.connection.execute("SELECT * FROM accounts ORDER BY currency,account_type,name").fetchall()
    current_currency = None
    for row in accounts:
        if row["currency"] != current_currency:
            current_currency = row["currency"]
            print(f"\n{current_currency}")
        print(_format_account(db, row))
    print("\n注：信用卡欠款估算按总额度减当前可用额度计算；当月应还金额和实际扣款仍需单独确认。")


def _report(db: Database, start: str, end: str, currency_filter: str | None) -> None:
    rows = db.report_rows(start, end, currency_filter)
    all_rows = rows if currency_filter else db.report_rows(start, end)
    currencies = [currency_filter.upper()] if currency_filter else sorted({row["currency"] for row in rows})
    if not currencies:
        currencies = [currency_filter.upper()] if currency_filter else ["JPY"]
    print(f"收支报表：{start} 至 {end}（转账/还款不计作支出）")
    for code in currencies:
        currency = db.currency(code)
        digits = currency["minor_digits"]
        cur_rows = [row for row in rows if row["currency"] == code]
        income_total = sum(row["amount_minor"] for row in cur_rows if row["kind"] == "income")
        expense_total = sum(row["amount_minor"] for row in cur_rows if row["kind"] == "expense")
        print(f"\n{code}")
        print(f"  收入：{minor_to_text(income_total, digits, code)}")
        print(f"  支出：{minor_to_text(expense_total, digits, code)}")
        print(f"  净收支：{minor_to_text(income_total - expense_total, digits, code)}")
        expense_categories: dict[str, int] = {}
        for row in cur_rows:
            if row["kind"] == "expense":
                name = row["category_name"] or "未分类"
                expense_categories[name] = expense_categories.get(name, 0) + row["amount_minor"]
        if expense_categories:
            print("  支出分类：")
            for name, amount in sorted(expense_categories.items(), key=lambda item: (-item[1], item[0])):
                print(f"    {name}: {minor_to_text(amount, digits, code)}")
        memo_total = sum(
            row["amount_minor"] for row in cur_rows if row["kind"] == "expense" and row["balance_effect"] == "memo"
        )
        if memo_total:
            print(f"  其中备查（不影响余额）：{minor_to_text(memo_total, digits, code)}")
        if code == "JPY":
            budget_value = db.get_setting("monthly_jpy_budget_minor", "")
            if budget_value:
                budget = int(budget_value)
                print(f"  JPY账期预算参考：{minor_to_text(budget, digits, code)}；区间剩余：{minor_to_text(budget-expense_total, digits, code)}")

    if currency_filter:
        print("\nJPY合并口径请在不指定--currency时查看。")
        print("\n积分按1点=1 JPY等值保存并计入JPY收支；账户明细仍标记为积分。")
        return

    jpy_income = 0
    jpy_expense = 0
    jpy_categories: dict[str, int] = {}
    missing_fx_count = 0
    for row in all_rows:
        if row["currency"] == "JPY":
            equivalent = int(row["amount_minor"])
        elif row["currency"] == "CNY" and row["jpy_equiv_minor"] is not None:
            equivalent = int(row["jpy_equiv_minor"])
        elif row["currency"] == "CNY":
            missing_fx_count += 1
            continue
        else:
            continue
        if row["kind"] == "income":
            jpy_income += equivalent
        elif row["kind"] == "expense":
            jpy_expense += equivalent
            category_name = row["category_name"] or "未分类"
            jpy_categories[category_name] = jpy_categories.get(category_name, 0) + equivalent

    print("\nJPY合并口径（JPY原币 + CNY按交易日汇率折算）")
    print(f"  收入：{minor_to_text(jpy_income, 0, 'JPY')}")
    print(f"  费用：{minor_to_text(-jpy_expense, 0, 'JPY')}")
    print(f"  合计：{minor_to_text(jpy_income-jpy_expense, 0, 'JPY')}")
    if jpy_categories:
        print("  费用分类：")
        for name, amount in sorted(jpy_categories.items(), key=lambda item: (-item[1], item[0])):
            print(f"    {name}: {minor_to_text(-amount, 0, 'JPY')}")
    if missing_fx_count:
        print(f"  待补汇率：{missing_fx_count}笔人民币流水未计入JPY合并口径。")
    print("\n积分按1点=1 JPY等值保存并计入JPY收支；账户明细仍标记为积分。转账按实际两边金额，不使用报表汇率自动换算。")


def run(args: argparse.Namespace) -> int:
    if args.command == "billing-cycle":
        start, end = billing_cycle(args.date)
        print(f"{start.isoformat()} 至 {end.isoformat()}")
        return 0

    db = Database(args.db)
    try:
        db.initialize()
        if args.command == "init":
            if args.seed_demo:
                seed_demo_data(db)
                print(f"已初始化并录入虚构演示数据：{args.db}")
            else:
                print(f"数据库已初始化：{args.db}")
            return 0
        if args.command == "chat":
            client = OpenAICompatibleClient.from_environment_or_prompt()
            try:
                payment_hints = PaymentPromptStore().all_profiles()
            except PaymentPromptSettingsError as exc:
                print(f"支付提示设置无法读取：{exc}", file=sys.stderr)
                return 1
            try:
                loaded_skill = BookkeepingSkillStore().load()
            except BookkeepingSkillError as exc:
                print(f"记账 Skill 无法读取：{exc}", file=sys.stderr)
                return 1
            session = NaturalLanguageSession(
                db,
                client,
                payment_hints=payment_hints,
                loaded_skill=loaded_skill["content"] if loaded_skill else "",
            )
            print("自然语言记账已启动。输入一笔收入、消费、转账或还款；输入“退出”结束。")
            print("记账文字、账户/类别名称、支付场景规则和已加载 Skill 正文会发送到你配置的API服务供解析；不要输入密码或完整银行卡号。")
            if payment_hints:
                print(f"已加载支付场景规则：{len(payment_hints)} 项。")
            if loaded_skill:
                print(f"已加载记账 Skill：{loaded_skill['name']}。")
            print(f"使用模型：{client.model}\n")
            while True:
                try:
                    user_text = input("你> ").strip()
                except (EOFError, KeyboardInterrupt):
                    print("\n已退出自然语言记账。")
                    break
                if user_text.lower() in {"退出", "exit", "quit", "q"}:
                    print("已退出自然语言记账。")
                    break
                try:
                    print(f"记账助手> {session.handle(user_text)}")
                except NaturalLanguageError as exc:
                    print(f"记账助手> {exc}", file=sys.stderr)
        elif args.command == "summary":
            _summary(db)
        elif args.command == "accounts":
            for row in db.connection.execute("SELECT * FROM accounts ORDER BY currency,name"):
                print(_format_account(db, row))
        elif args.command == "account-add":
            account_id = db.add_account(
                name=args.name, account_type=args.account_type, currency=args.currency,
                opening_balance=args.opening_balance, opening_date=args.opening_date,
                completeness=args.completeness, note=args.note,
            )
            print(f"已新增账户 #{account_id}: {args.name}")
        elif args.command in {"income", "expense"}:
            transaction_id = db.add_transaction(
                occurred_on=args.date, kind=args.command, amount=args.amount, currency=args.currency,
                account_name=args.account, category_name=args.category, description=args.description,
                memo_only=args.memo_only, needs_review=args.needs_review,
            )
            suffix = "（备查，不影响余额）" if args.memo_only else ""
            print(f"已记录{args.command} #{transaction_id}{suffix}")
        elif args.command == "transfer":
            transaction_id = db.add_transaction(
                occurred_on=args.date, kind="transfer", amount=args.amount, currency=db.account(args.from_account)["currency"],
                account_name=args.from_account, to_account_name=args.to_account, to_amount=args.to_amount,
                description=args.description,
            )
            print(f"已记录转账/还款 #{transaction_id}；不会计入消费报表")
        elif args.command == "card-limit-snapshot":
            snapshot_id = db.add_credit_limit_snapshot(
                args.account, args.date, args.limit, args.available, args.note,
            )
            print(f"已保存额度快照 #{snapshot_id}；当前欠款估算已按总额度减可用额度更新")
        elif args.command == "report":
            _report(db, args.start, args.end, args.currency)
        elif args.command == "transactions":
            query = "SELECT t.*,c.name AS category_name,a.name AS account_name,d.name AS destination_name FROM transactions t LEFT JOIN categories c ON c.id=t.category_id LEFT JOIN accounts a ON a.id=t.account_id LEFT JOIN accounts d ON d.id=t.to_account_id WHERE 1=1"
            params: list[str] = []
            if args.start:
                parse_date(args.start)
                query += " AND t.occurred_on>=?"
                params.append(args.start)
            if args.end:
                parse_date(args.end)
                query += " AND t.occurred_on<=?"
                params.append(args.end)
            query += " ORDER BY t.occurred_on,t.id"
            for row in db.connection.execute(query, params):
                currency = db.currency(row["currency"])
                source_account = db.account(row["account_name"]) if row["account_name"] else None
                amount = format_account_amount(
                    row["amount_minor"], currency["minor_digits"], currency["code"],
                    source_account["account_type"] if source_account else "",
                )
                if row["kind"] == "transfer":
                    dest = db.account(row["destination_name"])
                    target_cur = db.currency(dest["currency"])
                    target_amount = format_account_amount(
                        row["to_amount_minor"], target_cur["minor_digits"], target_cur["code"], dest["account_type"]
                    )
                    detail = f"{row['account_name']} → {row['destination_name']} {amount} → {target_amount}"
                else:
                    detail = f"{row['kind']} / {row['category_name']} / {row['account_name'] or '备查'} / {amount}"
                print(f"#{row['id']} {row['occurred_on']} {detail} — {row['description']}")
        elif args.command == "validate":
            errors, warnings = db.validate()
            if errors:
                print("校验失败：")
                for item in errors:
                    print(f"  ERROR: {item}")
                for item in warnings:
                    print(f"  REVIEW: {item}")
                return 1
            print(f"校验通过：0个错误，{len(warnings)}项提示。")
            for item in warnings:
                print(f"  REVIEW: {item}")
        elif args.command == "backup":
            destination = args.destination
            if destination is None:
                stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                destination = args.db.parent.parent / "backups" / f"household-bookkeeping-{stamp}.sqlite3"
            target = db.backup(destination, overwrite=args.overwrite)
            print(f"备份已创建：{target}")
        return 0
    except (LedgerError, NaturalLanguageError, sqlite3.Error, OSError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = _add_global_parser()
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
