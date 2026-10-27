from __future__ import annotations

import re
import sqlite3
import unicodedata
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Sequence

from .food_categories import (
    FOOD_GROUPS,
    FOOD_GROUP_TO_CLASSIFICATION,
    classify_food_name,
    is_confirmed_food_name,
)


class LedgerError(ValueError):
    """用户输入或账本状态不符合账务规则。"""


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS currencies (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    minor_digits INTEGER NOT NULL CHECK (minor_digits BETWEEN 0 AND 4),
    is_monetary INTEGER NOT NULL CHECK (is_monetary IN (0, 1))
);
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    account_type TEXT NOT NULL CHECK (account_type IN ('bank','wallet','prepaid','transit','points','credit')),
    currency TEXT NOT NULL REFERENCES currencies(code),
    opening_balance_minor INTEGER NOT NULL,
    opening_date TEXT NOT NULL,
    balance_completeness TEXT NOT NULL DEFAULT 'known' CHECK (balance_completeness IN ('known','inferred','partial')),
    opening_note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL CHECK (kind IN ('income','expense')),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);
CREATE TABLE IF NOT EXISTS category_translations (
    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    language TEXT NOT NULL CHECK (language IN ('zh-CN','ja-JP','en-US')),
    translated_name TEXT NOT NULL,
    PRIMARY KEY (category_id, language)
);
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY,
    occurred_on TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('income','expense','transfer')),
    amount_minor INTEGER NOT NULL CHECK (amount_minor > 0),
    currency TEXT NOT NULL REFERENCES currencies(code),
    account_id INTEGER REFERENCES accounts(id),
    to_account_id INTEGER REFERENCES accounts(id),
    to_amount_minor INTEGER CHECK (to_amount_minor IS NULL OR to_amount_minor > 0),
    category_id INTEGER REFERENCES categories(id),
    description TEXT NOT NULL,
    balance_effect TEXT NOT NULL CHECK (balance_effect IN ('posted','memo')),
    jpy_equiv_minor INTEGER CHECK (jpy_equiv_minor IS NULL OR jpy_equiv_minor >= 0),
    fx_rate TEXT,
    fx_rate_date TEXT,
    fx_source TEXT,
    account_amount_minor INTEGER CHECK (account_amount_minor IS NULL OR account_amount_minor > 0),
    account_fx_rate TEXT,
    account_fx_rate_date TEXT,
    account_fx_source TEXT,
    needs_review INTEGER NOT NULL DEFAULT 0 CHECK (needs_review IN (0, 1)),
    source TEXT NOT NULL DEFAULT 'user',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK ((kind = 'transfer' AND to_account_id IS NOT NULL AND to_amount_minor IS NOT NULL AND category_id IS NULL AND balance_effect = 'posted')
        OR (kind IN ('income','expense') AND to_account_id IS NULL AND to_amount_minor IS NULL AND category_id IS NOT NULL)),
    CHECK (balance_effect = 'memo' OR account_id IS NOT NULL)
);
CREATE TABLE IF NOT EXISTS account_balance_snapshots (
    id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    snapshot_date TEXT NOT NULL,
    balance_minor INTEGER NOT NULL,
    transaction_id_cutoff INTEGER NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fixed_assets (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    acquisition_month TEXT NOT NULL,
    cost_minor INTEGER NOT NULL CHECK (cost_minor > 0),
    currency TEXT NOT NULL REFERENCES currencies(code),
    useful_life_months INTEGER NOT NULL CHECK (useful_life_months BETWEEN 1 AND 1200),
    include_in_balance_sheet INTEGER NOT NULL DEFAULT 0
        CHECK (include_in_balance_sheet IN (0, 1)),
    disposal_month TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS food_purchase_items (
    id INTEGER PRIMARY KEY,
    transaction_id INTEGER REFERENCES transactions(id) ON DELETE CASCADE,
    purchase_date TEXT NOT NULL,
    item_name TEXT NOT NULL CHECK (length(trim(item_name)) > 0),
    quantity_text TEXT NOT NULL DEFAULT '',
    classification TEXT NOT NULL DEFAULT 'unclassified'
        CHECK (classification IN ('unclassified','ingredient','other')),
    food_group TEXT NOT NULL DEFAULT 'unclassified'
        CHECK (food_group IN ('meat_eggs_dairy','vegetables_fruits','grains_staples','snacks',
            'seafood','beverages','seasonings_dry_goods','beans_tofu','prepared_frozen',
            'other','unclassified')),
    source TEXT NOT NULL DEFAULT 'manual' CHECK (source IN ('receipt','parsed','manual','imported')),
    line_number INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    UNIQUE(transaction_id, line_number)
);
CREATE TABLE IF NOT EXISTS food_consumption_records (
    id INTEGER PRIMARY KEY,
    consumed_on TEXT NOT NULL,
    item_name TEXT NOT NULL CHECK (length(trim(item_name)) > 0),
    quantity_text TEXT NOT NULL DEFAULT '',
    meal TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fx_rates (
    base_currency TEXT NOT NULL REFERENCES currencies(code),
    quote_currency TEXT NOT NULL REFERENCES currencies(code),
    rate_date TEXT NOT NULL,
    rate TEXT NOT NULL,
    source TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    PRIMARY KEY(base_currency, quote_currency, rate_date)
);
CREATE TABLE IF NOT EXISTS credit_limit_snapshots (
    id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    snapshot_date TEXT NOT NULL,
    limit_minor INTEGER NOT NULL CHECK (limit_minor >= 0),
    available_minor INTEGER NOT NULL CHECK (available_minor >= 0),
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(account_id, snapshot_date),
    CHECK (available_minor <= limit_minor)
);
CREATE TABLE IF NOT EXISTS credit_limit_recovery_points (
    id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    transaction_id INTEGER NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    snapshot_date TEXT NOT NULL,
    limit_minor INTEGER CHECK (limit_minor IS NULL OR limit_minor >= 0),
    available_minor INTEGER CHECK (available_minor IS NULL OR available_minor >= 0),
    created_at TEXT NOT NULL,
    UNIQUE(account_id, transaction_id),
    CHECK (available_minor IS NULL OR (limit_minor IS NOT NULL AND available_minor <= limit_minor))
);
CREATE TABLE IF NOT EXISTS credit_repayment_schedules (
    id INTEGER PRIMARY KEY,
    card_account_id INTEGER NOT NULL UNIQUE REFERENCES accounts(id),
    source_account_id INTEGER NOT NULL REFERENCES accounts(id),
    amount_minor INTEGER NOT NULL CHECK (amount_minor > 0),
    currency TEXT NOT NULL REFERENCES currencies(code),
    due_day INTEGER NOT NULL CHECK (due_day BETWEEN 1 AND 31),
    next_due_date TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    last_status TEXT NOT NULL DEFAULT '等待到期',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS credit_repayment_rules (
    id INTEGER PRIMARY KEY,
    card_account_id INTEGER NOT NULL UNIQUE REFERENCES accounts(id),
    source_account_id INTEGER NOT NULL REFERENCES accounts(id),
    currency TEXT NOT NULL REFERENCES currencies(code),
    due_day INTEGER NOT NULL CHECK (due_day BETWEEN 1 AND 31),
    next_due_date TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    last_status TEXT NOT NULL DEFAULT '等待本期金额',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS credit_repayment_periods (
    id INTEGER PRIMARY KEY,
    rule_id INTEGER NOT NULL REFERENCES credit_repayment_rules(id) ON DELETE CASCADE,
    due_date TEXT NOT NULL,
    amount_minor INTEGER NOT NULL CHECK (amount_minor > 0),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','posted','missed','cancelled')),
    transaction_id INTEGER UNIQUE REFERENCES transactions(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(rule_id, due_date)
);
CREATE TABLE IF NOT EXISTS recurring_transaction_schedules (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    kind TEXT NOT NULL CHECK (kind IN ('income','expense')),
    amount_minor INTEGER NOT NULL CHECK (amount_minor > 0),
    currency TEXT NOT NULL REFERENCES currencies(code),
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    category_id INTEGER NOT NULL REFERENCES categories(id),
    frequency TEXT NOT NULL CHECK (frequency IN ('daily','weekly','monthly','yearly')),
    interval_count INTEGER NOT NULL DEFAULT 1 CHECK (interval_count > 0),
    next_due_date TEXT NOT NULL,
    anchor_day INTEGER NOT NULL CHECK (anchor_day BETWEEN 1 AND 31),
    anchor_month INTEGER NOT NULL CHECK (anchor_month BETWEEN 1 AND 12),
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    last_status TEXT NOT NULL DEFAULT '等待到期',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS recurring_transaction_occurrences (
    id INTEGER PRIMARY KEY,
    schedule_id INTEGER NOT NULL REFERENCES recurring_transaction_schedules(id) ON DELETE CASCADE,
    due_date TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('posted','matched')),
    transaction_id INTEGER UNIQUE REFERENCES transactions(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    UNIQUE(schedule_id, due_date)
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(occurred_on);
CREATE INDEX IF NOT EXISTS idx_transactions_kind_date ON transactions(kind, occurred_on);
CREATE INDEX IF NOT EXISTS idx_account_balance_snapshots_lookup ON account_balance_snapshots(account_id, snapshot_date, id);
CREATE INDEX IF NOT EXISTS idx_credit_recovery_lookup ON credit_limit_recovery_points(account_id, snapshot_date, created_at, transaction_id);
CREATE INDEX IF NOT EXISTS idx_fixed_assets_balance_sheet ON fixed_assets(include_in_balance_sheet, acquisition_month, disposal_month);
CREATE INDEX IF NOT EXISTS idx_recurring_schedule_due ON recurring_transaction_schedules(enabled, next_due_date);
CREATE INDEX IF NOT EXISTS idx_food_purchase_date ON food_purchase_items(purchase_date, id);
CREATE INDEX IF NOT EXISTS idx_food_consumption_date ON food_consumption_records(consumed_on, id);
"""


DEFAULT_CURRENCIES = (
    ("JPY", "Japanese yen", 0, 1),
    ("CNY", "Chinese yuan", 2, 1),
    ("PTS", "Legacy points unit (stored as JPY equivalent)", 0, 0),
)

DEFAULT_CATEGORIES = (
    ("工资", "income"),
    ("退款/返现", "income"),
    ("其他收入", "income"),
    ("现金盘盈", "income"),
    ("余额盘盈", "income"),
    ("积分盘盈", "income"),
    ("餐饮", "expense"),
    ("食材", "expense"),
    ("交通", "expense"),
    ("日用品", "expense"),
    ("服装", "expense"),
    ("医疗", "expense"),
    ("娱乐", "expense"),
    ("通信与账单", "expense"),
    ("其他损耗", "expense"),
    ("现金盘亏", "expense"),
    ("余额盘亏", "expense"),
    ("积分盘亏", "expense"),
    ("住房（工资已扣）", "expense"),
    ("其他", "expense"),
)

DEFAULT_CATEGORY_TRANSLATIONS = (
    ("工资", "給与", "Salary"),
    ("退款/返现", "返金・キャッシュバック", "Refund / cashback"),
    ("其他收入", "その他収入", "Other income"),
    ("现金盘盈", "現金過剰", "Cash surplus"),
    ("余额盘盈", "残高過剰", "Balance surplus"),
    ("积分盘盈", "ポイント過剰", "Points surplus"),
    ("餐饮", "外食", "Dining"),
    ("食材", "食材・食品", "Groceries"),
    ("交通", "交通費", "Transportation"),
    ("日用品", "日用品", "Household supplies"),
    ("服装", "衣類", "Clothing"),
    ("医疗", "医療費", "Medical"),
    ("娱乐", "娯楽", "Entertainment"),
    ("通信与账单", "通信費・各種料金", "Communications and bills"),
    ("其他损耗", "その他損失", "Other losses"),
    ("现金盘亏", "現金不足", "Cash shortage"),
    ("余额盘亏", "残高不足", "Balance shortage"),
    ("积分盘亏", "ポイント不足", "Points shortage"),
    ("住房（工资已扣）", "住居費（給与控除済み）", "Housing (deducted from salary)"),
    ("其他", "その他", "Other"),
)


def parse_date(value: str) -> date:
    """Parse common full-date and month-only inputs into a calendar date.

    Month-only inputs resolve to the first day of that month. A month without
    a year uses the current Japan-local year. Compact year/month input is
    deliberately limited to exactly six digits, so values such as ``20268``
    remain invalid rather than being guessed.
    """
    text = value.strip() if isinstance(value, str) else ""
    parsed: tuple[int, int, int] | None = None

    match = re.fullmatch(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", text)
    if match:
        parsed = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    else:
        match = re.fullmatch(r"(\d{4})年(\d{1,2})月(\d{1,2})日?", text)
        if match:
            parsed = (int(match.group(1)), int(match.group(2)), int(match.group(3)))

    if parsed is None and re.fullmatch(r"\d{8}", text):
        parsed = (int(text[:4]), int(text[4:6]), int(text[6:8]))
    if parsed is None:
        match = re.fullmatch(r"(\d{4})[-/.](\d{1,2})", text)
        if match:
            parsed = (int(match.group(1)), int(match.group(2)), 1)
    if parsed is None:
        match = re.fullmatch(r"(\d{4})年(\d{1,2})月", text)
        if match:
            parsed = (int(match.group(1)), int(match.group(2)), 1)
    if parsed is None and re.fullmatch(r"\d{6}", text):
        parsed = (int(text[:4]), int(text[4:6]), 1)
    if parsed is None:
        match = re.fullmatch(r"(\d{1,2})月(?:\s*(\d{1,2})日?)?", text)
        if match:
            parsed = (
                _current_japan_year(),
                int(match.group(1)),
                int(match.group(2) or 1),
            )

    try:
        if parsed is not None:
            return date(*parsed)
    except ValueError as exc:
        raise LedgerError(_DATE_INPUT_ERROR) from exc
    raise LedgerError(_DATE_INPUT_ERROR)


_DATE_INPUT_ERROR = (
    "日期无效或格式不支持。支持 YYYY-MM-DD、YYYY/M/D、YYYYMMDD、YYYYMM 和 M月；"
    "仅写月份时按当前日本年份的1日处理。"
)


def _current_japan_year() -> int:
    return datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=9))).year


def billing_cycle(value: str | date) -> tuple[date, date]:
    day = parse_date(value) if isinstance(value, str) else value
    if day.day >= 15:
        start = date(day.year, day.month, 15)
        if day.month == 12:
            end = date(day.year + 1, 1, 14)
        else:
            end = date(day.year, day.month + 1, 14)
    else:
        if day.month == 1:
            start = date(day.year - 1, 12, 15)
        else:
            start = date(day.year, day.month - 1, 15)
        end = date(day.year, day.month, 14)
    return start, end


def normalize_amount_text(value: str | int | Decimal) -> str:
    """Normalize an amount, accepting correctly grouped thousands separators."""
    amount_text = unicodedata.normalize("NFKC", str(value)).strip()
    if "," in amount_text:
        if not re.fullmatch(r"[+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?", amount_text):
            raise LedgerError(f"无效金额：{value!r}；千位逗号请按 19,950 的格式填写")
        amount_text = amount_text.replace(",", "")
    return amount_text


def to_minor(value: str | int | Decimal, currency: str, digits: int) -> int:
    normalized = normalize_amount_text(value)
    try:
        amount = Decimal(normalized)
    except (InvalidOperation, ValueError) as exc:
        raise LedgerError(f"无效金额：{value!r}") from exc
    if not amount.is_finite() or amount <= 0:
        raise LedgerError("金额必须是大于0的有限数值")
    quantum = Decimal(1).scaleb(-digits)
    quantized = amount.quantize(quantum)
    if quantized != amount:
        raise LedgerError(f"{currency}最多允许{digits}位小数")
    return int(quantized.scaleb(digits))


def to_minor_allow_zero(value: str | int | Decimal, currency: str, digits: int) -> int:
    normalized = normalize_amount_text(value)
    try:
        amount = Decimal(normalized)
    except (InvalidOperation, ValueError) as exc:
        raise LedgerError(f"无效金额：{value!r}") from exc
    if not amount.is_finite() or amount < 0:
        raise LedgerError("金额不能是负数或非有限数值")
    quantum = Decimal(1).scaleb(-digits)
    quantized = amount.quantize(quantum)
    if quantized != amount:
        raise LedgerError(f"{currency}最多允许{digits}位小数")
    return int(quantized.scaleb(digits))


def minor_to_text(value: int, digits: int, currency: str) -> str:
    amount = Decimal(value).scaleb(-digits)
    return f"{amount:,.{digits}f} {currency}"


def account_currency_label(account_type: str, currency: str) -> str:
    """Show points as points while retaining JPY as their internal currency."""
    return "PTS（JPY等值）" if account_type == "points" else currency


def format_account_amount(value: int, digits: int, currency: str, account_type: str) -> str:
    if account_type == "points":
        return f"{value:,}点（{minor_to_text(value, digits, 'JPY')}等值）"
    return minor_to_text(value, digits, currency)


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")

    def close(self) -> None:
        self.connection.close()

    def initialize(self) -> None:
        self._backup_before_variable_repayment_migration()
        self._backup_before_currency_reporting_migration()
        self._backup_before_account_currency_migration()
        self._backup_before_food_tracking_migration()
        self._backup_before_recurring_transactions_migration()
        self._backup_before_balance_snapshot_migration()
        self._backup_before_fixed_assets_migration()
        self.connection.executescript(SCHEMA_SQL)
        self._migrate_category_translation_languages()
        self._migrate_food_purchase_groups()
        transaction_columns = {
            row["name"] for row in self.connection.execute("PRAGMA table_info(transactions)")
        }
        with self.connection:
            for column_name, definition in (
                ("jpy_equiv_minor", "INTEGER CHECK (jpy_equiv_minor IS NULL OR jpy_equiv_minor >= 0)"),
                ("fx_rate", "TEXT"),
                ("fx_rate_date", "TEXT"),
                ("fx_source", "TEXT"),
                ("account_amount_minor", "INTEGER CHECK (account_amount_minor IS NULL OR account_amount_minor > 0)"),
                ("account_fx_rate", "TEXT"),
                ("account_fx_rate_date", "TEXT"),
                ("account_fx_source", "TEXT"),
            ):
                if column_name not in transaction_columns:
                    self.connection.execute(
                        f"ALTER TABLE transactions ADD COLUMN {column_name} {definition}"
                    )
        snapshot_columns = {
            row["name"] for row in self.connection.execute("PRAGMA table_info(credit_limit_snapshots)")
        }
        if "created_at" not in snapshot_columns:
            # Legacy snapshots only stored a date. Use start of that date as a
            # calculation anchor so later recorded card activity is reflected.
            with self.connection:
                self.connection.execute(
                    "ALTER TABLE credit_limit_snapshots ADD COLUMN created_at TEXT NOT NULL DEFAULT ''"
                )
                self.connection.execute(
                    "UPDATE credit_limit_snapshots "
                    "SET created_at = snapshot_date || ' 00:00:00.000000' WHERE created_at = ''"
                )
        with self.connection:
            self.connection.executemany(
                "INSERT OR IGNORE INTO currencies(code,name,minor_digits,is_monetary) VALUES (?,?,?,?)",
                DEFAULT_CURRENCIES,
            )
            self.connection.executemany(
                "INSERT OR IGNORE INTO categories(name,kind) VALUES (?,?)", DEFAULT_CATEGORIES
            )
            for category_name, japanese_name, english_name in DEFAULT_CATEGORY_TRANSLATIONS:
                category = self.connection.execute(
                    "SELECT id FROM categories WHERE name=?", (category_name,)
                ).fetchone()
                if category is None:
                    continue
                self.connection.executemany(
                    "INSERT OR IGNORE INTO category_translations(category_id,language,translated_name) VALUES (?,?,?)",
                    (
                        (int(category["id"]), "ja-JP", japanese_name),
                        (int(category["id"]), "en-US", english_name),
                    ),
                )
            self.connection.execute(
                "INSERT OR IGNORE INTO settings(key,value,note) VALUES (?,?,?)",
                (
                    "food_review_purchases_count_as_eaten",
                    "0",
                    "饮食回顾是否把已分类的采购食品按已吃计入；其他商品和待识别项不纳入",
                ),
            )
        self._migrate_points_to_jpy()
        self._migrate_credit_repayment_schedules()

    def _migrate_category_translation_languages(self) -> None:
        schema = self.connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='category_translations'"
        ).fetchone()
        if schema is None or "zh-CN" in str(schema["sql"]):
            return
        with self.connection:
            self.connection.execute(
                "CREATE TABLE category_translations_new ("
                "category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE, "
                "language TEXT NOT NULL CHECK (language IN ('zh-CN','ja-JP','en-US')), "
                "translated_name TEXT NOT NULL, "
                "PRIMARY KEY (category_id, language))"
            )
            self.connection.execute(
                "INSERT INTO category_translations_new(category_id,language,translated_name) "
                "SELECT category_id,language,translated_name FROM category_translations"
            )
            self.connection.execute("DROP TABLE category_translations")
            self.connection.execute(
                "ALTER TABLE category_translations_new RENAME TO category_translations"
            )

    def _backup_before_fixed_assets_migration(self) -> None:
        """Keep a recoverable copy before adding the fixed-asset register."""
        if not self.path.exists():
            return
        tables = {
            row["name"] for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "transactions" not in tables or "fixed_assets" in tables:
            return
        backup_root = (
            self.path.parent.parent / "backups"
            if self.path.parent.name.lower() == "data"
            else self.path.parent / "backups"
        )
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        target = backup_root / f"{self.path.stem}-before-fixed-assets-{stamp}.sqlite3"
        suffix = 1
        while target.exists():
            target = backup_root / f"{self.path.stem}-before-fixed-assets-{stamp}-{suffix}.sqlite3"
            suffix += 1
        self.backup(target)

    def list_fixed_assets(self) -> list[sqlite3.Row]:
        return self.connection.execute(
            "SELECT * FROM fixed_assets ORDER BY acquisition_month DESC,id DESC"
        ).fetchall()

    def save_fixed_asset(
        self,
        *,
        name: str,
        acquisition_month: str,
        cost_minor: int,
        currency: str,
        useful_life_months: int,
        include_in_balance_sheet: bool,
        disposal_month: str | None = None,
        asset_id: int | None = None,
    ) -> int:
        clean_name = str(name).strip()
        if not clean_name:
            raise LedgerError("固定资产名称不能为空")

        def validate_month(value: str, field: str) -> str:
            try:
                parsed_month = parse_date(str(value).strip())
            except LedgerError as exc:
                raise LedgerError(f"{field}格式无效。支持 YYYY-MM、YYYYMM、M月或完整日期。") from exc
            return parsed_month.strftime("%Y-%m")

        acquisition = validate_month(acquisition_month, "购入月份")
        disposal = validate_month(disposal_month, "报废月份") if disposal_month else None
        if disposal and disposal < acquisition:
            raise LedgerError("报废月份不能早于购入月份")
        if int(cost_minor) <= 0:
            raise LedgerError("购入金额必须大于0")
        if int(cost_minor) > 9_223_372_036_854_775_807:
            raise LedgerError("购入金额超出账本可保存范围")
        if not 1 <= int(useful_life_months) <= 1200:
            raise LedgerError("预计使用月数必须在1到1200之间")
        currency_code = str(currency).upper()
        currency_row = self.currency(currency_code)
        if not bool(currency_row["is_monetary"]):
            raise LedgerError("固定资产币种必须是货币币种")

        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self.connection:
            if asset_id is None:
                cursor = self.connection.execute(
                    "INSERT INTO fixed_assets(name,acquisition_month,cost_minor,currency,"
                    "useful_life_months,include_in_balance_sheet,disposal_month,created_at,updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        clean_name, acquisition, int(cost_minor), currency_code,
                        int(useful_life_months), int(bool(include_in_balance_sheet)),
                        disposal, now, now,
                    ),
                )
                return int(cursor.lastrowid)
            cursor = self.connection.execute(
                "UPDATE fixed_assets SET name=?,acquisition_month=?,cost_minor=?,currency=?,"
                "useful_life_months=?,include_in_balance_sheet=?,disposal_month=?,updated_at=? "
                "WHERE id=?",
                (
                    clean_name, acquisition, int(cost_minor), currency_code,
                    int(useful_life_months), int(bool(include_in_balance_sheet)),
                    disposal, now, int(asset_id),
                ),
            )
            if cursor.rowcount != 1:
                raise LedgerError(f"固定资产记录#{asset_id}不存在")
            return int(asset_id)

    def set_fixed_asset_inclusion(self, asset_id: int, included: bool) -> None:
        with self.connection:
            cursor = self.connection.execute(
                "UPDATE fixed_assets SET include_in_balance_sheet=?,updated_at=? WHERE id=?",
                (
                    int(bool(included)),
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    int(asset_id),
                ),
            )
            if cursor.rowcount != 1:
                raise LedgerError(f"固定资产记录#{asset_id}不存在")

    def delete_fixed_asset(self, asset_id: int) -> None:
        with self.connection:
            cursor = self.connection.execute("DELETE FROM fixed_assets WHERE id=?", (int(asset_id),))
            if cursor.rowcount != 1:
                raise LedgerError(f"固定资产记录#{asset_id}不存在")

    def _backup_before_recurring_transactions_migration(self) -> None:
        """Keep a recoverable copy before adding recurring transaction tables."""
        if not self.path.exists():
            return
        tables = {
            row["name"] for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "transactions" not in tables or "recurring_transaction_schedules" in tables:
            return
        backup_root = (
            self.path.parent.parent / "backups"
            if self.path.parent.name.lower() == "data"
            else self.path.parent / "backups"
        )
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        target = backup_root / f"{self.path.stem}-before-recurring-transactions-{stamp}.sqlite3"
        suffix = 1
        while target.exists():
            target = backup_root / f"{self.path.stem}-before-recurring-transactions-{stamp}-{suffix}.sqlite3"
            suffix += 1
        self.backup(target)

    def _backup_before_balance_snapshot_migration(self) -> None:
        """Keep a recoverable copy before adding non-journal balance snapshots."""
        if not self.path.exists():
            return
        tables = {
            row["name"] for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "transactions" not in tables or "account_balance_snapshots" in tables:
            return
        backup_root = (
            self.path.parent.parent / "backups"
            if self.path.parent.name.lower() == "data"
            else self.path.parent / "backups"
        )
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        target = backup_root / f"{self.path.stem}-before-balance-snapshots-{stamp}.sqlite3"
        suffix = 1
        while target.exists():
            target = backup_root / f"{self.path.stem}-before-balance-snapshots-{stamp}-{suffix}.sqlite3"
            suffix += 1
        self.backup(target)

    def get_setting(self, key: str, default: str = "") -> str:
        row = self.connection.execute(
            "SELECT value FROM settings WHERE key=?", (key,)
        ).fetchone()
        return str(row["value"]) if row is not None else default

    def set_setting(self, key: str, value: str, note: str = "") -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO settings(key,value,note) VALUES (?,?,?)",
            (key, str(value), note),
        )
        self.connection.commit()

    def _backup_before_variable_repayment_migration(self) -> None:
        """Keep a recoverable copy before adding per-month repayment amounts."""
        if not self.path.exists():
            return
        tables = {
            row["name"] for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "credit_repayment_schedules" not in tables or "credit_repayment_rules" in tables:
            return
        backup_root = (
            self.path.parent.parent / "backups"
            if self.path.parent.name.lower() == "data"
            else self.path.parent / "backups"
        )
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        target = backup_root / f"{self.path.stem}-before-variable-repayment-{stamp}.sqlite3"
        suffix = 1
        while target.exists():
            target = backup_root / f"{self.path.stem}-before-variable-repayment-{stamp}-{suffix}.sqlite3"
            suffix += 1
        self.backup(target)

    def _backup_before_currency_reporting_migration(self) -> None:
        """Keep a recoverable copy before adding transaction FX reporting fields."""
        if not self.path.exists():
            return
        tables = {
            row["name"] for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "transactions" not in tables:
            return
        columns = {
            row["name"] for row in self.connection.execute("PRAGMA table_info(transactions)")
        }
        if "jpy_equiv_minor" in columns:
            return
        backup_root = (
            self.path.parent.parent / "backups"
            if self.path.parent.name.lower() == "data"
            else self.path.parent / "backups"
        )
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        target = backup_root / f"{self.path.stem}-before-fx-reporting-{stamp}.sqlite3"
        suffix = 1
        while target.exists():
            target = backup_root / f"{self.path.stem}-before-fx-reporting-{stamp}-{suffix}.sqlite3"
            suffix += 1
        self.backup(target)

    def _backup_before_account_currency_migration(self) -> None:
        """Preserve a recoverable copy before adding account-currency postings."""
        if not self.path.exists():
            return
        tables = {
            row["name"] for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "transactions" not in tables:
            return
        columns = {
            row["name"] for row in self.connection.execute("PRAGMA table_info(transactions)")
        }
        if "account_amount_minor" in columns:
            return
        backup_root = (
            self.path.parent.parent / "backups"
            if self.path.parent.name.lower() == "data"
            else self.path.parent / "backups"
        )
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        target = backup_root / f"{self.path.stem}-before-account-currency-{stamp}.sqlite3"
        suffix = 1
        while target.exists():
            target = backup_root / f"{self.path.stem}-before-account-currency-{stamp}-{suffix}.sqlite3"
            suffix += 1
        self.backup(target)

    def _backup_before_food_tracking_migration(self) -> None:
        """Keep a recoverable copy before food tables or category fields change."""
        if not self.path.exists():
            return
        tables = {
            row["name"] for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "transactions" not in tables:
            return
        needs_backup = not {"food_purchase_items", "food_consumption_records"} <= tables
        if not needs_backup:
            columns = {
                row["name"] for row in self.connection.execute(
                    "PRAGMA table_info(food_purchase_items)"
                )
            }
            needs_backup = "food_group" not in columns
        if not needs_backup:
            return
        backup_root = (
            self.path.parent.parent / "backups"
            if self.path.parent.name.lower() == "data"
            else self.path.parent / "backups"
        )
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        target = backup_root / f"{self.path.stem}-before-food-tracking-{stamp}.sqlite3"
        suffix = 1
        while target.exists():
            target = backup_root / f"{self.path.stem}-before-food-tracking-{stamp}-{suffix}.sqlite3"
            suffix += 1
        self.backup(target)

    def _migrate_food_purchase_groups(self) -> None:
        """Add groups and backfill legacy rows once without overriding later choices."""
        columns = {
            row["name"] for row in self.connection.execute(
                "PRAGMA table_info(food_purchase_items)"
            )
        }
        needs_backfill = "food_group" not in columns
        with self.connection:
            if needs_backfill:
                groups_sql = ",".join(f"'{group}'" for group in FOOD_GROUPS)
                self.connection.execute(
                    "ALTER TABLE food_purchase_items ADD COLUMN food_group TEXT NOT NULL "
                    f"DEFAULT 'unclassified' CHECK (food_group IN ({groups_sql}))"
                )
            if not needs_backfill:
                return
            rows = self.connection.execute(
                "SELECT id,item_name,classification FROM food_purchase_items "
                "WHERE food_group='unclassified'"
            ).fetchall()
            for row in rows:
                classification = str(row["classification"])
                if classification == "other":
                    group = "other"
                else:
                    group = classify_food_name(str(row["item_name"]))
                    if classification == "ingredient" and group == "other":
                        # A prior manual food decision is stronger than a new
                        # non-food keyword hit; leave the subtype for review.
                        group = "unclassified"
                if group == "unclassified":
                    continue
                # Preserve an earlier manual coarse classification. Only rows
                # still awaiting classification receive a derived coarse value.
                new_classification = (
                    FOOD_GROUP_TO_CLASSIFICATION[group]
                    if classification == "unclassified"
                    else classification
                )
                self.connection.execute(
                    "UPDATE food_purchase_items SET food_group=?,classification=? WHERE id=?",
                    (group, new_classification, row["id"]),
                )

    def _migrate_credit_repayment_schedules(self) -> None:
        """Migrate fixed routing only; old recurring amounts must be re-entered per month."""
        old_rows = self.connection.execute(
            "SELECT * FROM credit_repayment_schedules ORDER BY id"
        ).fetchall()
        if not old_rows:
            return
        with self.connection:
            for row in old_rows:
                self.connection.execute(
                    """INSERT OR IGNORE INTO credit_repayment_rules
                       (card_account_id,source_account_id,currency,due_day,next_due_date,
                        enabled,last_status,created_at,updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (row["card_account_id"], row["source_account_id"], row["currency"],
                     row["due_day"], row["next_due_date"], row["enabled"],
                     "旧版计划已迁移；请重新填写本期金额",
                     row["created_at"], row["updated_at"]),
                )

    def _migrate_points_to_jpy(self) -> None:
        """Normalize legacy point accounts and postings to the 1 point = 1 JPY basis."""
        invalid_accounts = self.connection.execute(
            "SELECT name,account_type,currency FROM accounts "
            "WHERE (currency='PTS' AND account_type!='points') "
            "OR (account_type='points' AND currency NOT IN ('PTS','JPY'))"
        ).fetchall()
        if invalid_accounts:
            names = ", ".join(
                f"{row['name']} ({row['account_type']}/{row['currency']})" for row in invalid_accounts
            )
            raise LedgerError(f"积分币种迁移遇到无法安全转换的账户：{names}")

        invalid_transactions = self.connection.execute(
            "SELECT t.id,t.account_id,a.name AS account_name,a.account_type "
            "FROM transactions t LEFT JOIN accounts a ON a.id=t.account_id "
            "WHERE t.currency='PTS' AND t.account_id IS NOT NULL AND a.account_type!='points'"
        ).fetchall()
        if invalid_transactions:
            ids = ", ".join(f"#{row['id']}（{row['account_name']}）" for row in invalid_transactions)
            raise LedgerError(f"积分币种迁移遇到非积分账户上的PTS流水，未修改：{ids}")

        has_legacy_points = self.connection.execute(
            "SELECT EXISTS(SELECT 1 FROM accounts WHERE account_type='points' AND currency='PTS') "
            "OR EXISTS(SELECT 1 FROM transactions WHERE currency='PTS')"
        ).fetchone()[0]
        if has_legacy_points:
            backup_root = (
                self.path.parent.parent / "backups"
                if self.path.parent.name.lower() == "data"
                else self.path.parent / "backups"
            )
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            target = backup_root / f"{self.path.stem}-before-points-jpy-{stamp}.sqlite3"
            suffix = 1
            while target.exists():
                target = backup_root / f"{self.path.stem}-before-points-jpy-{stamp}-{suffix}.sqlite3"
                suffix += 1
            self.backup(target)

        with self.connection:
            self.connection.execute(
                "UPDATE accounts SET currency='JPY', "
                "opening_note=replace(opening_note,'积分数量快照；不是现金或JPY余额。',"
                "'积分数量快照；账内按1积分=1 JPY等值核算，界面标记为积分。') "
                "WHERE account_type='points' AND currency='PTS'"
            )
            self.connection.execute("UPDATE transactions SET currency='JPY' WHERE currency='PTS'")
            self.connection.execute(
                "UPDATE currencies SET name='Legacy points unit (stored as JPY equivalent)',"
                "minor_digits=0,is_monetary=0 WHERE code='PTS'"
            )

    def currency(self, code: str) -> sqlite3.Row:
        row = self.connection.execute("SELECT * FROM currencies WHERE code = ?", (code.upper(),)).fetchone()
        if row is None:
            raise LedgerError(f"不支持的币种/单位：{code}")
        return row

    def account(self, name: str) -> sqlite3.Row:
        row = self.connection.execute("SELECT * FROM accounts WHERE name = ?", (name,)).fetchone()
        if row is None:
            raise LedgerError(f"找不到账户：{name}")
        return row

    def selectable_account_rows(self) -> list[sqlite3.Row]:
        """Return accounts offered as ordinary choices, excluding point accounts.

        Cash-management accounts and credit cards are both valid ordinary
        account choices. Point accounts remain available to explicit point
        transactions and configured payment allocation, but are not shown as
        generic choices.
        """
        return self.connection.execute(
            "SELECT name,account_type,currency FROM accounts "
            "WHERE account_type IN ('bank','wallet','prepaid','transit','credit') "
            "ORDER BY name"
        ).fetchall()

    def delete_managed_account(self, account_name: str) -> Path:
        """Delete an unused cash-management account after creating a backup.

        Ledger transactions and active plans are never removed implicitly.
        Account-only balance snapshots are removed with the account.
        """
        account = self.account(account_name)
        account_id = int(account["id"])
        if account["account_type"] not in {"bank", "wallet", "prepaid", "transit", "points"}:
            raise LedgerError("此账户不属于现金管理；请在对应管理页面处理。")
        protected_references = self._account_deletion_blockers(account_id)
        if protected_references:
            labels = "、".join(dict.fromkeys(protected_references))
            raise LedgerError(
                f"无法删除账户“{account_name}”：仍有关联的{labels}。"
                "请先处理关联计划；已有账本流水不会随账户删除。"
            )

        backup_root = (
            self.path.parent.parent / "backups"
            if self.path.parent.name.lower() == "data"
            else self.path.parent / "backups"
        )
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        target = backup_root / f"{self.path.stem}-before-account-delete-{stamp}.sqlite3"
        suffix = 1
        while target.exists():
            target = backup_root / f"{self.path.stem}-before-account-delete-{stamp}-{suffix}.sqlite3"
            suffix += 1
        self.backup(target)

        self.connection.execute("BEGIN IMMEDIATE")
        try:
            # Recheck under the write lock so a concurrent transaction cannot
            # attach ledger history between the backup and the deletion.
            account = self.connection.execute(
                "SELECT id FROM accounts WHERE id=?", (account_id,)
            ).fetchone()
            if account is None:
                raise LedgerError(f"账户“{account_name}”已不存在。")
            protected_references = self._account_deletion_blockers(account_id)
            if protected_references:
                labels = "、".join(dict.fromkeys(protected_references))
                raise LedgerError(
                    f"无法删除账户“{account_name}”：仍有关联的{labels}。"
                    "请先处理关联计划；已有账本流水不会随账户删除。"
                )
            self.connection.execute(
                "DELETE FROM account_balance_snapshots WHERE account_id=?", (account_id,)
            )
            self.connection.execute("DELETE FROM accounts WHERE id=?", (account_id,))
            hidden_cash_currencies = {
                "现金（日元）": "JPY",
                "现金（人民币）": "CNY",
            }
            cash_currency = hidden_cash_currencies.get(account_name)
            if cash_currency is not None:
                self.connection.execute(
                    "INSERT OR REPLACE INTO settings(key,value,note) VALUES (?,?,?)",
                    (
                        f"cash_management_hidden_default_cash_{cash_currency}",
                        "1",
                        "用户已从现金管理中删除此默认现金账户，不再自动显示首次盘点行。",
                    ),
                )
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
        return target

    def _account_deletion_blockers(self, account_id: int) -> list[str]:
        table_labels = {
            "transactions": "账本流水",
            "recurring_transaction_schedules": "定期收支计划",
            "credit_repayment_schedules": "每月应还计划",
            "credit_repayment_rules": "信用卡还款规则",
            "credit_limit_snapshots": "信用卡额度快照",
        }
        blockers: list[str] = []
        table_names = [
            str(row["name"])
            for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        ]
        for table_name in table_names:
            quoted_table = '"' + table_name.replace('"', '""') + '"'
            foreign_keys = self.connection.execute(
                f"PRAGMA foreign_key_list({quoted_table})"
            ).fetchall()
            for foreign_key in foreign_keys:
                if foreign_key["table"] != "accounts":
                    continue
                column_name = str(foreign_key["from"])
                quoted_column = '"' + column_name.replace('"', '""') + '"'
                count = int(self.connection.execute(
                    f"SELECT COUNT(*) FROM {quoted_table} WHERE {quoted_column}=?",
                    (account_id,),
                ).fetchone()[0])
                if count and table_name != "account_balance_snapshots":
                    blockers.append(table_labels.get(table_name, "其他账本记录"))
        return blockers

    def category(self, name: str, kind: str) -> sqlite3.Row:
        row = self.connection.execute(
            "SELECT * FROM categories WHERE name = ? AND kind = ? AND is_active = 1", (name, kind)
        ).fetchone()
        if row is None:
            raise LedgerError(f"找不到{kind}类别：{name}")
        return row

    def category_translations(self) -> dict[int, dict[str, str]]:
        rows = self.connection.execute(
            "SELECT category_id,language,translated_name FROM category_translations"
        ).fetchall()
        translations: dict[int, dict[str, str]] = {}
        for row in rows:
            translations.setdefault(int(row["category_id"]), {})[str(row["language"])] = str(
                row["translated_name"]
            )
        return translations

    def set_category_translation(self, category_id: int, language: str, translated_name: str) -> None:
        if language not in {"zh-CN", "ja-JP", "en-US"}:
            raise LedgerError("类别名称语言必须是中文、日语或英语")
        category = self.connection.execute(
            "SELECT id FROM categories WHERE id=? AND is_active=1", (int(category_id),)
        ).fetchone()
        if category is None:
            raise LedgerError("找不到要翻译的有效记账类别")
        name = translated_name.strip()
        if len(name) > 80:
            raise LedgerError("类别名称不能超过80个字符")
        if any(ord(character) < 32 or ord(character) == 127 for character in name):
            raise LedgerError("类别名称不能包含换行或控制字符")
        with self.connection:
            if not name:
                self.connection.execute(
                    "DELETE FROM category_translations WHERE category_id=? AND language=?",
                    (int(category_id), language),
                )
            else:
                self.connection.execute(
                    "INSERT INTO category_translations(category_id,language,translated_name) VALUES (?,?,?) "
                    "ON CONFLICT(category_id,language) DO UPDATE SET translated_name=excluded.translated_name",
                    (int(category_id), language, name),
                )

    def add_category(self, name: str, kind: str) -> int:
        category_name = name.strip()
        if not category_name:
            raise LedgerError("类别名称不能为空")
        if len(category_name) > 40:
            raise LedgerError("类别名称不能超过40个字符")
        if any(ord(character) < 32 or ord(character) == 127 for character in category_name):
            raise LedgerError("类别名称不能包含换行或控制字符")
        if kind not in {"income", "expense"}:
            raise LedgerError("类别类型必须是收入或支出")

        existing = self.connection.execute(
            "SELECT id,kind,is_active FROM categories WHERE name=? COLLATE NOCASE",
            (category_name,),
        ).fetchone()
        if existing is not None:
            if existing["kind"] != kind:
                raise LedgerError(f"类别“{category_name}”已存在，且类型为另一种收支类别")
            if existing["is_active"]:
                raise LedgerError(f"类别“{category_name}”已经存在")
            with self.connection:
                self.connection.execute(
                    "UPDATE categories SET is_active=1 WHERE id=?", (existing["id"],)
                )
            return int(existing["id"])

        with self.connection:
            cursor = self.connection.execute(
                "INSERT INTO categories(name,kind,is_active) VALUES (?,?,1)",
                (category_name, kind),
            )
        return int(cursor.lastrowid)

    def add_account(
        self,
        *,
        name: str,
        account_type: str,
        currency: str,
        opening_balance: str | int | Decimal,
        opening_date: str,
        completeness: str = "known",
        note: str = "",
    ) -> int:
        if account_type not in {"bank", "wallet", "prepaid", "transit", "points", "credit"}:
            raise LedgerError(f"不支持的账户类型：{account_type}")
        currency_code = currency.upper()
        if account_type == "points":
            if currency_code not in {"JPY", "PTS"}:
                raise LedgerError("积分账户按1积分=1 JPY等值核算，币种请选择JPY。")
            currency_code = "JPY"
        elif currency_code == "PTS":
            raise LedgerError("PTS仅为旧数据兼容单位；新账户请使用实际币种，积分账户内部使用JPY。")
        currency_row = self.currency(currency_code)
        if completeness not in {"known", "inferred", "partial"}:
            raise LedgerError(f"不支持的余额完整度：{completeness}")
        date_text = parse_date(opening_date).isoformat()
        if not name.strip():
            raise LedgerError("账户名称不能为空")
        amount_minor = to_minor_allow_zero(opening_balance, currency_code, currency_row["minor_digits"])
        if account_type == "points":
            points_note = "积分按1积分=1 JPY等值核算，界面标记为积分。"
            note = note.strip()
            if points_note not in note:
                note = f"{note}；{points_note}" if note else points_note
        try:
            cursor = self.connection.execute(
                "INSERT INTO accounts(name,account_type,currency,opening_balance_minor,opening_date,balance_completeness,opening_note) VALUES (?,?,?,?,?,?,?)",
                (name.strip(), account_type, currency_code, amount_minor, date_text, completeness, note),
            )
            self.connection.commit()
        except sqlite3.IntegrityError as exc:
            self.connection.rollback()
            raise LedgerError(f"无法新增账户：{exc}") from exc
        return int(cursor.lastrowid)

    def add_transaction(
        self,
        *,
        occurred_on: str,
        kind: str,
        amount: str | int | Decimal,
        currency: str,
        description: str,
        category_name: str | None = None,
        account_name: str | None = None,
        to_account_name: str | None = None,
        to_amount: str | int | Decimal | None = None,
        memo_only: bool = False,
        needs_review: bool = False,
        source: str = "user",
        account_amount_minor: int | None = None,
        account_fx_rate: str | Decimal | None = None,
        account_fx_rate_date: str | None = None,
        account_fx_source: str | None = None,
        purchase_items: Sequence[str] = (),
        purchase_item_source: str = "parsed",
    ) -> int:
        date_text = parse_date(occurred_on).isoformat()
        account_row = self.account(account_name) if account_name else None
        destination_row = self.account(to_account_name) if to_account_name else None
        currency_code = currency.upper()
        if currency_code == "PTS":
            if account_row is not None and account_row["account_type"] != "points":
                raise LedgerError("PTS不再作为交易币种；请选择积分账户，积分交易将按JPY等值记录。")
            currency_code = "JPY"
        currency_row = self.currency(currency_code)
        amount_minor = to_minor(amount, currency_row["code"], currency_row["minor_digits"])
        if kind not in {"income", "expense", "transfer"}:
            raise LedgerError(f"不支持的交易类型：{kind}")
        item_names = self._clean_food_item_names(purchase_items)
        if item_names and kind != "expense":
            raise LedgerError("只有购买消费可以关联采购商品行")
        if purchase_item_source not in {"receipt", "parsed", "manual", "imported"}:
            raise LedgerError("采购商品来源无效")
        if not description.strip():
            raise LedgerError("交易说明不能为空")
        category_row = self.category(category_name, kind) if category_name and kind != "transfer" else None
        jpy_equiv_minor: int | None = None
        fx_rate: str | None = None
        fx_rate_date: str | None = None
        fx_source: str | None = None
        account_fx_rate_text: str | None = None
        if account_amount_minor is not None:
            if isinstance(account_amount_minor, bool) or not isinstance(account_amount_minor, int) or account_amount_minor <= 0:
                raise LedgerError("账户扣款金额必须是正的最小货币单位整数")
            if account_row is None or memo_only:
                raise LedgerError("账户扣款金额只能用于绑定资金账户的已过账收支")
            if account_fx_rate is None or account_fx_rate_date is None or not account_fx_source:
                raise LedgerError("跨币种账户扣款必须保存汇率、有效日期和来源")
            try:
                account_rate = Decimal(str(account_fx_rate))
            except InvalidOperation as exc:
                raise LedgerError("账户换算汇率格式无效") from exc
            if not account_rate.is_finite() or account_rate <= 0:
                raise LedgerError("账户换算汇率必须为正数")
            account_fx_rate_text = format(account_rate, "f")
        elif any(value is not None for value in (account_fx_rate, account_fx_rate_date, account_fx_source)):
            raise LedgerError("账户换算信息缺少扣款金额")

        if kind in {"income", "expense"}:
            if category_row is None:
                raise LedgerError(f"{kind}必须指定类别")
            if destination_row is not None:
                raise LedgerError("收入或消费不能指定转入账户")
            if memo_only:
                if account_row is not None:
                    raise LedgerError("备查交易不得绑定账户；省略--account")
            elif account_row is None:
                raise LedgerError("入账交易必须指定账户；无账户的备查支出请使用--memo-only")
            if account_row is not None:
                if date_text < account_row["opening_date"]:
                    raise LedgerError(f"交易日期早于账户期初日期：{account_row['opening_date']}")
                account_currency = str(account_row["currency"])
                if account_currency != currency_row["code"]:
                    if account_amount_minor is None:
                        raise LedgerError("跨币种收支必须提供按交易日汇率换算的账户扣款金额")
                    from .fx_rates import convert_minor_at_rate

                    account_rate_date = parse_date(str(account_fx_rate_date))
                    if account_rate_date.isoformat() > date_text:
                        raise LedgerError("账户换算汇率有效日期不能晚于交易日期")
                    expected_account_amount = convert_minor_at_rate(
                        amount_minor,
                        int(currency_row["minor_digits"]),
                        int(self.currency(account_currency)["minor_digits"]),
                        Decimal(str(account_fx_rate)),
                    )
                    if expected_account_amount != account_amount_minor:
                        raise LedgerError("账户扣款金额与账单金额及保存的汇率不一致")
                elif account_amount_minor is not None:
                    raise LedgerError("同币种收支不应额外指定账户换算金额")
            account_id = account_row["id"] if account_row else None
            to_account_id = None
            to_amount_minor = None
            category_id = category_row["id"]
            effect = "memo" if memo_only else "posted"
            if currency_row["code"] == "CNY":
                from .fx_rates import convert_minor_to_jpy_minor, resolve_jpy_rate

                try:
                    applied_rate = resolve_jpy_rate(self, "CNY", date_text)
                except (ValueError, RuntimeError) as exc:
                    raise LedgerError(str(exc)) from exc
                jpy_equiv_minor = convert_minor_to_jpy_minor(
                    amount_minor, int(currency_row["minor_digits"]), applied_rate.rate
                )
                fx_rate = format(applied_rate.rate, "f")
                fx_rate_date = applied_rate.rate_date
                fx_source = applied_rate.source
        else:
            if account_amount_minor is not None:
                raise LedgerError("转账金额请使用转出金额和转入金额字段")
            if memo_only:
                raise LedgerError("转账不能作为备查交易")
            if account_row is None or destination_row is None:
                raise LedgerError("转账必须同时指定转出和转入账户")
            if category_name:
                raise LedgerError("转账不使用消费/收入类别")
            if account_row["currency"] != currency_row["code"]:
                raise LedgerError("转出金额币种必须与转出账户一致")
            if date_text < account_row["opening_date"] or date_text < destination_row["opening_date"]:
                raise LedgerError("转账日期不能早于任一账户期初日期")
            destination_currency = self.currency(destination_row["currency"])
            if to_amount is None:
                if destination_row["currency"] != currency_row["code"]:
                    raise LedgerError("跨币种转账必须明确提供--to-amount")
                to_amount_minor = amount_minor
            else:
                to_amount_minor = to_minor(to_amount, destination_currency["code"], destination_currency["minor_digits"])
            account_id = account_row["id"]
            to_account_id = destination_row["id"]
            category_id = None
            effect = "posted"

        try:
            cursor = self.connection.execute(
                """INSERT INTO transactions
                (occurred_on,kind,amount_minor,currency,account_id,to_account_id,to_amount_minor,category_id,
                 description,balance_effect,jpy_equiv_minor,fx_rate,fx_rate_date,fx_source,
                 account_amount_minor,account_fx_rate,account_fx_rate_date,account_fx_source,
                 needs_review,source,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    date_text, kind, amount_minor, currency_row["code"], account_id, to_account_id,
                    to_amount_minor, category_id, description.strip(), effect, jpy_equiv_minor,
                    fx_rate, fx_rate_date, fx_source, account_amount_minor, account_fx_rate_text,
                    account_fx_rate_date, account_fx_source, int(needs_review), source,
                    datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f"),
                ),
            )
            if item_names and not memo_only:
                self._insert_food_purchase_items(
                    int(cursor.lastrowid), date_text, item_names,
                    purchase_item_source, "unclassified",
                )
            if effect == "posted":
                self._record_credit_recovery_points([int(cursor.lastrowid)])
            self.connection.commit()
        except sqlite3.IntegrityError as exc:
            self.connection.rollback()
            raise LedgerError(f"无法保存交易：{exc}") from exc
        return int(cursor.lastrowid)

    def add_split_expense(
        self,
        *,
        occurred_on: str,
        amount: str | int | Decimal,
        currency: str,
        allocations: Sequence[tuple[str, int]],
        category_name: str,
        descriptions: Sequence[str],
        source: str = "user",
        needs_review: bool = False,
        purchase_items: Sequence[str] = (),
        purchase_item_source: str = "parsed",
    ) -> list[int]:
        """Atomically post one expense across ordered accounts in one currency."""
        date_text = parse_date(occurred_on).isoformat()
        currency_code = "JPY" if currency.upper() == "PTS" else currency.upper()
        currency_row = self.currency(currency_code)
        total_minor = to_minor(amount, currency_row["code"], currency_row["minor_digits"])
        jpy_total_minor: int | None = None
        fx_rate: str | None = None
        fx_rate_date: str | None = None
        fx_source: str | None = None
        if currency_row["code"] == "CNY":
            from .fx_rates import convert_minor_to_jpy_minor, resolve_jpy_rate

            try:
                applied_rate = resolve_jpy_rate(self, "CNY", date_text)
            except (ValueError, RuntimeError) as exc:
                raise LedgerError(str(exc)) from exc
            jpy_total_minor = convert_minor_to_jpy_minor(
                total_minor, int(currency_row["minor_digits"]), applied_rate.rate
            )
            fx_rate = format(applied_rate.rate, "f")
            fx_rate_date = applied_rate.rate_date
            fx_source = applied_rate.source
        category_row = self.category(category_name, "expense")
        if not allocations or len(allocations) != len(descriptions):
            raise LedgerError("分摊账户与说明必须一一对应，且至少有一项")
        if not all(isinstance(description, str) and description.strip() for description in descriptions):
            raise LedgerError("每项分摊都必须有交易说明")
        item_names = self._clean_food_item_names(purchase_items)
        if purchase_item_source not in {"receipt", "parsed", "manual", "imported"}:
            raise LedgerError("采购商品来源无效")

        validated: list[tuple[int, int, str]] = []
        for (account_name, amount_minor), description in zip(allocations, descriptions):
            if isinstance(amount_minor, bool) or not isinstance(amount_minor, int) or amount_minor <= 0:
                raise LedgerError("分摊金额必须是正的最小货币单位整数")
            account = self.account(account_name)
            if account["currency"] != currency_row["code"]:
                raise LedgerError("自动分摊只支持同一内部币种；JPY与CNY不可自动换算")
            if date_text < account["opening_date"]:
                raise LedgerError(f"交易日期早于账户期初日期：{account['opening_date']}")
            validated.append((int(account["id"]), amount_minor, description.strip()))
        if sum(amount_minor for _, amount_minor, _ in validated) != total_minor:
            raise LedgerError("分摊金额合计与消费总额不一致")
        if self.connection.in_transaction:
            raise LedgerError("账本正在执行其他写入，无法安全保存分摊交易")

        if jpy_total_minor is None:
            jpy_allocations: list[int | None] = [None] * len(validated)
        else:
            jpy_allocations = [
                jpy_total_minor * amount_minor // total_minor
                for _, amount_minor, _ in validated
            ]
            remainder = jpy_total_minor - sum(int(value or 0) for value in jpy_allocations)
            for index in range(remainder):
                target_index = index % len(jpy_allocations)
                jpy_allocations[target_index] = int(jpy_allocations[target_index] or 0) + 1

        created_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")
        ids: list[int] = []
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            totals_by_account: dict[int, int] = {}
            for account_id, amount_minor, _ in validated:
                totals_by_account[account_id] = totals_by_account.get(account_id, 0) + amount_minor
            account_rows = {
                int(row["id"]): row
                for row in self.connection.execute(
                    f"SELECT id,account_type FROM accounts WHERE id IN ({','.join('?' for _ in totals_by_account)})",
                    tuple(totals_by_account),
                )
            }
            if any(row["account_type"] == "credit" for row in account_rows.values()):
                from .credit_management import credit_card_overview

                credit_available = {
                    int(item["account_id"]): item["available_minor"]
                    for item in credit_card_overview(self)
                }
            else:
                credit_available = {}
            for account_id, amount_minor in totals_by_account.items():
                account_type = account_rows[account_id]["account_type"]
                if account_type == "credit":
                    available = credit_available.get(account_id)
                    if available is not None and amount_minor > int(available):
                        raise LedgerError("信用卡当前可用额度已变化，分摊消费未写入；请重新记账")
                elif amount_minor > max(0, self.account_balance_minor(account_id)):
                    raise LedgerError("账户当前余额已变化，分摊消费未写入；请重新记账")
            for (account_id, amount_minor, description), jpy_minor in zip(validated, jpy_allocations):
                cursor = self.connection.execute(
                    """INSERT INTO transactions
                    (occurred_on,kind,amount_minor,currency,account_id,to_account_id,to_amount_minor,category_id,
                     description,balance_effect,jpy_equiv_minor,fx_rate,fx_rate_date,fx_source,
                     needs_review,source,created_at)
                    VALUES (?,'expense',?,?,?,NULL,NULL,?,?,'posted',?,?,?,?,?,?,?)""",
                    (
                        date_text, amount_minor, currency_row["code"], account_id, int(category_row["id"]),
                        description, jpy_minor, fx_rate, fx_rate_date, fx_source,
                        int(needs_review), source, created_at,
                    ),
                )
                ids.append(int(cursor.lastrowid))
            if item_names:
                self._insert_food_purchase_items(
                    ids[0], date_text, item_names, purchase_item_source, "unclassified"
                )
            self._record_credit_recovery_points(ids)
            self.connection.commit()
        except sqlite3.IntegrityError as exc:
            self.connection.rollback()
            raise LedgerError(f"无法保存分摊消费：{exc}") from exc
        except Exception:
            self.connection.rollback()
            raise
        return ids

    @staticmethod
    def _clean_food_item_names(items: Sequence[str]) -> list[str]:
        if isinstance(items, (str, bytes)) or not isinstance(items, (list, tuple)):
            raise LedgerError("采购商品行格式无效")
        if len(items) > 100:
            raise LedgerError("一次最多保存100个采购商品行")
        cleaned: list[str] = []
        for item in items:
            if not isinstance(item, str):
                raise LedgerError("采购商品名称必须是文字")
            name = item.strip()[:200]
            if name:
                cleaned.append(name)
        return cleaned

    def _insert_food_purchase_items(
        self,
        transaction_id: int | None,
        purchase_date: str,
        items: Sequence[str],
        source: str,
        classification: str,
        quantities: Sequence[str] | None = None,
    ) -> list[int]:
        if classification not in {"unclassified", "ingredient", "other"}:
            raise LedgerError("商品分类无效")
        if quantities is None:
            # A receipt item line represents one purchased unit when the receipt
            # parser does not provide a separate quantity.
            default_quantity = "1" if source in {"receipt", "parsed", "imported"} else ""
            quantities = [default_quantity] * len(items)
        if len(items) != len(quantities):
            raise LedgerError("采购商品与数量信息必须一一对应")
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")
        created_ids: list[int] = []
        item_rows = list(zip(items, quantities))
        if source in {"receipt", "parsed", "imported"}:
            # The food log stores food items, not every line from a mixed receipt.
            # Keep only positive food matches; non-food and ambiguous OCR rows remain
            # in the financial receipt description and are not promoted to food.
            item_rows = [row for row in item_rows if is_confirmed_food_name(row[0])]
        for line_number, (name, quantity) in enumerate(item_rows, start=1):
            food_group = classify_food_name(name)
            row_classification = classification
            if classification == "other":
                food_group = "other"
            elif classification == "unclassified":
                row_classification = FOOD_GROUP_TO_CLASSIFICATION[food_group]
            elif classification == "ingredient":
                if food_group == "other":
                    row_classification = "other"
                else:
                    row_classification = "ingredient"
            cursor = self.connection.execute(
                """INSERT INTO food_purchase_items
                   (transaction_id,purchase_date,item_name,quantity_text,classification,food_group,
                    source,line_number,created_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (transaction_id, purchase_date, name, str(quantity).strip()[:80],
                 row_classification, food_group, source, line_number, now),
            )
            created_ids.append(int(cursor.lastrowid))
        return created_ids

    def add_food_purchases(
        self,
        purchase_date: str,
        items: Sequence[tuple[str, str]],
    ) -> list[int]:
        """Save a manually confirmed food purchase without creating a financial transaction."""
        date_text = parse_date(purchase_date).isoformat()
        if not isinstance(items, (list, tuple)) or not items:
            raise LedgerError("请至少填写一种食材")
        names: list[str] = []
        quantities: list[str] = []
        for item in items:
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                raise LedgerError("采购食材格式无效")
            name, quantity = item
            if not isinstance(name, str) or not name.strip():
                raise LedgerError("食材名称不能为空")
            names.append(name.strip()[:200])
            quantities.append(str(quantity or "").strip()[:80])
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            ids = self._insert_food_purchase_items(
                None, date_text, names, "manual", "ingredient", quantities
            )
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
        return ids

    def add_food_consumptions(
        self,
        consumed_on: str,
        items: Sequence[tuple[str, str]],
        *,
        meal: str = "",
        note: str = "",
    ) -> list[int]:
        """Save explicitly reported foods eaten; this does not infer inventory balances."""
        date_text = parse_date(consumed_on).isoformat()
        if not isinstance(items, (list, tuple)) or not items:
            raise LedgerError("请至少填写一种食物")
        normalized: list[tuple[str, str]] = []
        for item in items:
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                raise LedgerError("食用记录格式无效")
            name, quantity = item
            if not isinstance(name, str) or not name.strip():
                raise LedgerError("食物名称不能为空")
            normalized.append((name.strip()[:200], str(quantity or "").strip()[:80]))
        created_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            ids: list[int] = []
            for name, quantity in normalized:
                cursor = self.connection.execute(
                    """INSERT INTO food_consumption_records
                       (consumed_on,item_name,quantity_text,meal,note,created_at)
                       VALUES (?,?,?,?,?,?)""",
                    (date_text, name, quantity, str(meal).strip()[:40],
                     str(note).strip()[:500], created_at),
                )
                ids.append(int(cursor.lastrowid))
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
        return ids

    def classify_food_purchase(self, item_id: int, classification: str) -> None:
        if classification in FOOD_GROUP_TO_CLASSIFICATION:
            self.set_food_purchase_group(item_id, classification)
            return
        if classification not in {"ingredient", "other", "unclassified"}:
            raise LedgerError("商品分类无效")
        if classification == "other":
            self.set_food_purchase_group(item_id, "other")
            return
        if classification == "unclassified":
            self.set_food_purchase_group(item_id, "unclassified")
            return
        row = self.connection.execute(
            "SELECT item_name FROM food_purchase_items WHERE id=?", (item_id,)
        ).fetchone()
        if row is None:
            raise LedgerError("找不到这条采购商品")
        group = classify_food_name(str(row["item_name"]))
        if group == "other":
            group = "unclassified"
        self.connection.execute(
            "UPDATE food_purchase_items SET classification='ingredient',food_group=? WHERE id=?",
            (group, item_id),
        )
        self.connection.commit()

    def set_food_purchase_group(self, item_id: int, food_group: str) -> None:
        if food_group not in FOOD_GROUP_TO_CLASSIFICATION:
            raise LedgerError("商品分类无效")
        cursor = self.connection.execute(
            "UPDATE food_purchase_items SET food_group=?,classification=? WHERE id=?",
            (food_group, FOOD_GROUP_TO_CLASSIFICATION[food_group], item_id),
        )
        if cursor.rowcount != 1:
            raise LedgerError("找不到这条采购商品")
        self.connection.commit()

    def auto_classify_food_purchase(self, item_id: int) -> str:
        row = self.connection.execute(
            "SELECT item_name FROM food_purchase_items WHERE id=?", (item_id,)
        ).fetchone()
        if row is None:
            raise LedgerError("找不到这条采购商品")
        group = classify_food_name(str(row["item_name"]))
        self.connection.execute(
            "UPDATE food_purchase_items SET food_group=?,classification=? WHERE id=?",
            (group, FOOD_GROUP_TO_CLASSIFICATION[group], item_id),
        )
        self.connection.commit()
        return group

    def update_food_purchase_item(
        self,
        item_id: int,
        item_name: str,
        quantity_text: str = "",
        food_group: str | None = None,
    ) -> None:
        if not isinstance(item_name, str) or not item_name.strip():
            raise LedgerError("商品名称不能为空")
        clean_name = item_name.strip()[:200]
        clean_quantity = str(quantity_text or "").strip()[:80]
        if food_group is None:
            cursor = self.connection.execute(
                "UPDATE food_purchase_items SET item_name=?,quantity_text=? WHERE id=?",
                (clean_name, clean_quantity, item_id),
            )
        else:
            if food_group not in FOOD_GROUP_TO_CLASSIFICATION:
                raise LedgerError("商品分类无效")
            cursor = self.connection.execute(
                """UPDATE food_purchase_items
                   SET item_name=?,quantity_text=?,food_group=?,classification=? WHERE id=?""",
                (clean_name, clean_quantity, food_group,
                 FOOD_GROUP_TO_CLASSIFICATION[food_group], item_id),
            )
        if cursor.rowcount != 1:
            raise LedgerError("找不到这条采购商品")
        self.connection.commit()

    def delete_food_purchase_item(self, item_id: int) -> None:
        cursor = self.connection.execute("DELETE FROM food_purchase_items WHERE id=?", (item_id,))
        if cursor.rowcount != 1:
            raise LedgerError("找不到这条采购商品")
        self.connection.commit()

    def delete_food_consumption(self, record_id: int) -> None:
        cursor = self.connection.execute(
            "DELETE FROM food_consumption_records WHERE id=?", (record_id,)
        )
        if cursor.rowcount != 1:
            raise LedgerError("找不到这条食用记录")
        self.connection.commit()

    def import_receipt_purchase_items(self, transaction_ids: Sequence[int]) -> int:
        """Import visible product names from existing receipt expense descriptions once."""
        import re

        ids = list(dict.fromkeys(int(value) for value in transaction_ids))
        if not ids:
            return 0
        placeholders = ",".join("?" for _ in ids)
        rows = self.connection.execute(
            f"SELECT id,occurred_on,kind,description FROM transactions WHERE id IN ({placeholders})",
            tuple(ids),
        ).fetchall()
        inserted = 0
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            for row in rows:
                description = str(row["description"] or "")
                match = re.match(r"^收据商品[:：]\s*(.+)$", description)
                if row["kind"] != "expense" or not match:
                    continue
                already_imported = self.connection.execute(
                    "SELECT 1 FROM food_purchase_items WHERE transaction_id=? LIMIT 1",
                    (row["id"],),
                ).fetchone()
                if already_imported:
                    continue
                names = [
                    value.strip()[:200]
                    for value in re.split(r"[、,，;；\n]+", match.group(1))
                    if value.strip()
                ][:100]
                if not names:
                    continue
                inserted += len(self._insert_food_purchase_items(
                    int(row["id"]), row["occurred_on"], names, "imported", "unclassified"
                ))
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
        return inserted

    def add_credit_limit_snapshot(
        self, account_name: str, snapshot_date: str, limit: str | int, available: str | int, note: str = ""
    ) -> int:
        account = self.account(account_name)
        if account["account_type"] != "credit":
            raise LedgerError("额度快照只能绑定信用卡账户")
        currency = self.currency(account["currency"])
        limit_minor = to_minor_allow_zero(limit, currency["code"], currency["minor_digits"])
        available_minor = to_minor_allow_zero(available, currency["code"], currency["minor_digits"])
        if available_minor > limit_minor:
            raise LedgerError("可用额度不能高于总额度")
        date_text = parse_date(snapshot_date).isoformat()
        try:
            cursor = self.connection.execute(
                "INSERT INTO credit_limit_snapshots(account_id,snapshot_date,limit_minor,available_minor,note,created_at) VALUES (?,?,?,?,?,?)",
                (
                    account["id"], date_text, limit_minor, available_minor, note,
                    datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f"),
                ),
            )
            self.connection.commit()
        except sqlite3.IntegrityError as exc:
            self.connection.rollback()
            raise LedgerError(f"无法保存额度快照：{exc}") from exc
        return int(cursor.lastrowid)

    def _record_credit_recovery_points(self, transaction_ids: Sequence[int]) -> int:
        """Save an automatic post-transaction limit snapshot for each affected card."""
        ids = tuple(sorted({int(value) for value in transaction_ids}))
        if not ids:
            return 0
        placeholders = ",".join("?" for _ in ids)
        card_rows = self.connection.execute(
            f"""SELECT DISTINCT a.id
                FROM transactions t JOIN accounts a ON a.id=t.account_id
                WHERE t.id IN ({placeholders}) AND a.account_type='credit'
                UNION
                SELECT DISTINCT a.id
                FROM transactions t JOIN accounts a ON a.id=t.to_account_id
                WHERE t.id IN ({placeholders}) AND a.account_type='credit'""",
            ids + ids,
        ).fetchall()
        if not card_rows:
            return 0

        from .credit_management import credit_card_overview

        overview = {
            int(item["account_id"]): item for item in credit_card_overview(self)
        }
        inserted = 0
        for card_row in card_rows:
            account_id = int(card_row["id"])
            state = overview.get(account_id)
            if not state:
                continue
            event = self.connection.execute(
                f"""SELECT occurred_on,created_at,id FROM transactions
                    WHERE id IN ({placeholders})
                      AND (account_id=? OR to_account_id=?)
                    ORDER BY created_at DESC,id DESC LIMIT 1""",
                ids + (account_id, account_id),
            ).fetchone()
            if event is None:
                continue
            event_date = str(event["occurred_on"])
            event_created_at = str(event["created_at"])
            anchor_date = state["snapshot_date"]
            anchor_created_at = state["snapshot_created_at"]
            if anchor_date and (
                event_date < str(anchor_date)
                or (event_date == str(anchor_date) and event_created_at <= str(anchor_created_at))
            ):
                # A later manual snapshot is already the authoritative balance.
                continue
            self.connection.execute(
                """INSERT OR REPLACE INTO credit_limit_recovery_points
                   (account_id,transaction_id,snapshot_date,limit_minor,available_minor,created_at)
                   VALUES (?,?,?,?,?,?)""",
                (
                    account_id, int(event["id"]), event_date,
                    int(state["limit_minor"]) if state["limit_minor"] is not None else None,
                    int(state["available_minor"]) if state["available_minor"] is not None else None,
                    event_created_at,
                ),
            )
            inserted += 1
        return inserted

    def credit_snapshot_history(self, account_id: int, limit: int = 100) -> list[dict[str, Any]]:
        if not 1 <= limit <= 500:
            raise LedgerError("额度快照历史显示条数必须在1至500之间")
        account = self.connection.execute(
            "SELECT account_type FROM accounts WHERE id=?", (account_id,)
        ).fetchone()
        if account is None or account["account_type"] != "credit":
            raise LedgerError("找不到对应的信用卡账户")
        rows = self.connection.execute(
            """SELECT * FROM (
                   SELECT s.id,s.account_id,s.snapshot_date,s.limit_minor,s.available_minor,
                          s.note,s.created_at,NULL AS transaction_id,NULL AS description,
                          'manual' AS snapshot_type
                   FROM credit_limit_snapshots s WHERE s.account_id=?
                   UNION ALL
                   SELECT p.id,p.account_id,p.snapshot_date,p.limit_minor,p.available_minor,
                          '流水后自动快照' AS note,p.created_at,p.transaction_id,t.description,
                          'automatic' AS snapshot_type
                   FROM credit_limit_recovery_points p
                   JOIN transactions t ON t.id=p.transaction_id
                   WHERE p.account_id=?
               ) ORDER BY snapshot_date DESC,created_at DESC,
                        COALESCE(transaction_id,0) DESC,id DESC LIMIT ?""",
            (account_id, account_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def credit_transaction_history(self, account_id: int, limit: int = 100) -> list[dict[str, Any]]:
        if not 1 <= limit <= 500:
            raise LedgerError("信用卡流水历史显示条数必须在1至500之间")
        account = self.connection.execute(
            "SELECT account_type FROM accounts WHERE id=?", (account_id,)
        ).fetchone()
        if account is None or account["account_type"] != "credit":
            raise LedgerError("找不到对应的信用卡账户")
        rows = self.connection.execute(
            """SELECT t.id,t.occurred_on,t.kind,t.description,t.created_at,
                      CASE WHEN t.account_id=? THEN COALESCE(t.account_amount_minor,t.amount_minor)
                           ELSE t.to_amount_minor END AS card_amount_minor,
                      CASE WHEN t.account_id=? THEN 'out' ELSE 'in' END AS direction
               FROM transactions t
               WHERE t.balance_effect='posted' AND (t.account_id=? OR t.to_account_id=?)
               ORDER BY t.occurred_on DESC,t.created_at DESC,t.id DESC LIMIT ?""",
            (account_id, account_id, account_id, account_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def _backup_before_credit_recovery(self, action: str) -> Path:
        backup_root = (
            self.path.parent.parent / "backups"
            if self.path.parent.name.lower() == "data"
            else self.path.parent / "backups"
        )
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        target = backup_root / f"{self.path.stem}-before-credit-{action}-{stamp}.sqlite3"
        suffix = 1
        while target.exists():
            target = backup_root / f"{self.path.stem}-before-credit-{action}-{stamp}-{suffix}.sqlite3"
            suffix += 1
        return self.backup(target)

    def restore_credit_snapshot_history(
        self, account_id: int, snapshot_type: str, snapshot_id: int
    ) -> tuple[Path, int, int]:
        """Keep the selected snapshot and remove later snapshot anchors, preserving ledger rows."""
        if self.connection.in_transaction:
            raise LedgerError("账本正在执行其他写入，暂时无法恢复额度快照")
        if snapshot_type not in {"manual", "automatic"}:
            raise LedgerError("额度快照类型无效")
        table = "credit_limit_snapshots" if snapshot_type == "manual" else "credit_limit_recovery_points"
        selected = self.connection.execute(
            f"SELECT * FROM {table} WHERE account_id=? AND id=?",
            (account_id, snapshot_id),
        ).fetchone()
        if selected is None:
            raise LedgerError("所选额度快照已不存在，请刷新历史后重试")
        if snapshot_type == "automatic" and selected["available_minor"] is None:
            raise LedgerError("这笔流水发生时还没有额度基准，无法作为恢复快照；可以在流水列表中撤销这笔记录")
        snapshot_date = str(selected["snapshot_date"])
        created_at = str(selected["created_at"])
        transaction_id = (
            int(selected["transaction_id"]) if snapshot_type == "automatic" else 0
        )
        manual_count = int(self.connection.execute(
            """SELECT COUNT(*) FROM credit_limit_snapshots
               WHERE account_id=? AND (snapshot_date>? OR (snapshot_date=? AND created_at>?))""",
            (account_id, snapshot_date, snapshot_date, created_at),
        ).fetchone()[0])
        recovery_count = int(self.connection.execute(
            """SELECT COUNT(*) FROM credit_limit_recovery_points
               WHERE account_id=? AND (
                   snapshot_date>? OR
                   (snapshot_date=? AND (created_at>? OR (created_at=? AND transaction_id>?)))
               )""",
            (account_id, snapshot_date, snapshot_date, created_at, created_at, transaction_id),
        ).fetchone()[0])
        if manual_count + recovery_count == 0:
            raise LedgerError("所选快照已经是最新快照，无需恢复")

        backup_path = self._backup_before_credit_recovery("snapshot-restore")
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            self.connection.execute(
                """DELETE FROM credit_limit_snapshots
                   WHERE account_id=? AND (snapshot_date>? OR (snapshot_date=? AND created_at>?))""",
                (account_id, snapshot_date, snapshot_date, created_at),
            )
            self.connection.execute(
                """DELETE FROM credit_limit_recovery_points
                   WHERE account_id=? AND (
                       snapshot_date>? OR
                       (snapshot_date=? AND (created_at>? OR (created_at=? AND transaction_id>?)))
                   )""",
                (account_id, snapshot_date, snapshot_date, created_at, created_at, transaction_id),
            )
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
        return backup_path, manual_count, recovery_count

    def latest_credit_snapshot(self, account_id: int) -> sqlite3.Row | None:
        return self.connection.execute(
            "SELECT * FROM credit_limit_snapshots WHERE account_id=? ORDER BY snapshot_date DESC,id DESC LIMIT 1",
            (account_id,),
        ).fetchone()

    def account_balance_minor(self, account_id: int) -> int:
        return self.account_balance_as_of(account_id, None)

    def account_balance_as_of(self, account_id: int, as_of: str | date | None) -> int:
        """Return the ledger balance as of a date, excluding later-dated entries."""
        account = self.connection.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
        if account is None:
            raise LedgerError(f"找不到账户ID：{account_id}")
        as_of_text = parse_date(as_of).isoformat() if isinstance(as_of, str) else (as_of.isoformat() if as_of else None)
        if as_of_text and as_of_text < account["opening_date"]:
            return 0
        if as_of_text:
            snapshot = self.connection.execute(
                """SELECT * FROM account_balance_snapshots
                   WHERE account_id=? AND snapshot_date<=?
                   ORDER BY snapshot_date DESC,id DESC LIMIT 1""",
                (account_id, as_of_text),
            ).fetchone()
        else:
            snapshot = self.connection.execute(
                """SELECT * FROM account_balance_snapshots WHERE account_id=?
                   ORDER BY snapshot_date DESC,id DESC LIMIT 1""",
                (account_id,),
            ).fetchone()
        if snapshot is None:
            balance = int(account["opening_balance_minor"])
            query = "SELECT * FROM transactions WHERE balance_effect='posted' AND occurred_on>=?"
            params: list[Any] = [account["opening_date"]]
        else:
            balance = int(snapshot["balance_minor"])
            snapshot_date = str(snapshot["snapshot_date"])
            query = (
                "SELECT * FROM transactions WHERE balance_effect='posted' "
                "AND (occurred_on>? OR (occurred_on=? AND id>?))"
            )
            params = [snapshot_date, snapshot_date, int(snapshot["transaction_id_cutoff"])]
        if as_of_text:
            query += " AND occurred_on<=?"
            params.append(as_of_text)
        query += " ORDER BY occurred_on,id"
        rows = self.connection.execute(query, params).fetchall()
        for row in rows:
            account_amount = (
                int(row["account_amount_minor"])
                if row["account_amount_minor"] is not None
                else int(row["amount_minor"])
            )
            if row["kind"] == "income" and row["account_id"] == account_id:
                balance += -account_amount if account["account_type"] == "credit" else account_amount
            elif row["kind"] == "expense" and row["account_id"] == account_id:
                balance += account_amount if account["account_type"] == "credit" else -account_amount
            elif row["kind"] == "transfer":
                if row["account_id"] == account_id:
                    balance += row["amount_minor"] if account["account_type"] == "credit" else -row["amount_minor"]
                if row["to_account_id"] == account_id:
                    balance += -row["to_amount_minor"] if account["account_type"] == "credit" else row["to_amount_minor"]
        return balance

    def report_rows(self, start: str, end: str, currency_code: str | None = None) -> list[sqlite3.Row]:
        parse_date(start)
        parse_date(end)
        if start > end:
            raise LedgerError("报表开始日期不能晚于结束日期")
        query = """SELECT t.*, c.name AS category_name FROM transactions t
                   LEFT JOIN categories c ON c.id=t.category_id
                   WHERE t.occurred_on BETWEEN ? AND ? AND t.kind IN ('income','expense')"""
        params: list[Any] = [start, end]
        if currency_code:
            self.currency(currency_code)
            query += " AND t.currency=?"
            params.append(currency_code.upper())
        query += " ORDER BY t.occurred_on,t.id"
        return self.connection.execute(query, params).fetchall()

    def transactions_between(self, start: str, end: str) -> list[sqlite3.Row]:
        """Return all ledger entries in a date range, newest first."""
        start_date = parse_date(start).isoformat()
        end_date = parse_date(end).isoformat()
        if start_date > end_date:
            raise LedgerError("开始日期不能晚于结束日期")
        return self.connection.execute(
            """SELECT t.*,
                      c.name AS category_name,
                      source_account.name AS account_name,
                      source_account.account_type AS account_type,
                      source_account.currency AS account_currency,
                      source_currency.minor_digits AS account_minor_digits,
                      destination_account.name AS to_account_name,
                      destination_account.currency AS to_currency,
                      destination_account.account_type AS to_account_type,
                      destination_currency.minor_digits AS to_minor_digits,
                      transaction_currency.minor_digits AS currency_minor_digits
               FROM transactions t
               LEFT JOIN categories c ON c.id=t.category_id
               LEFT JOIN accounts source_account ON source_account.id=t.account_id
               LEFT JOIN currencies source_currency ON source_currency.code=source_account.currency
               LEFT JOIN accounts destination_account ON destination_account.id=t.to_account_id
               LEFT JOIN currencies destination_currency ON destination_currency.code=destination_account.currency
               JOIN currencies transaction_currency ON transaction_currency.code=t.currency
               WHERE t.occurred_on BETWEEN ? AND ?
               ORDER BY t.occurred_on DESC,t.id DESC""",
            (start_date, end_date),
        ).fetchall()

    def confirm_transaction_review(
        self,
        transaction_id: int,
        *,
        account_name: str | None = None,
    ) -> bool:
        """Mark a reviewed entry as confirmed, posting memo-only entries when assigned an account.

        Returns True when a memo-only entry was converted to a posted transaction.
        """
        row = self.connection.execute(
            "SELECT id,occurred_on,kind,amount_minor,currency,account_id,balance_effect,needs_review "
            "FROM transactions WHERE id=?",
            (transaction_id,),
        ).fetchone()
        if row is None:
            raise LedgerError("找不到所选账务记录。")
        if not row["needs_review"]:
            raise LedgerError("所选流水已不需要核对。")

        if row["balance_effect"] == "posted":
            with self.connection:
                cursor = self.connection.execute(
                    "UPDATE transactions SET needs_review=0 WHERE id=? AND needs_review=1",
                    (transaction_id,),
                )
                if cursor.rowcount != 1:
                    raise LedgerError("流水状态已改变，请刷新后重试。")
            return False

        if row["kind"] not in {"income", "expense"}:
            raise LedgerError("只有收入或支出备查流水可以在核对时转为已入账。")
        if not account_name:
            raise LedgerError("备查流水转为已入账前必须选择实际账户。")
        account = self.account(account_name)
        if account["account_type"] == "points":
            raise LedgerError("请选择银行、钱包、券/预付、交通卡或信用卡账户。")
        occurred_on = parse_date(str(row["occurred_on"])).isoformat()
        if occurred_on < account["opening_date"]:
            raise LedgerError(f"交易日期早于账户期初日期：{account['opening_date']}")

        transaction_currency = str(row["currency"])
        account_currency = str(account["currency"])
        account_amount_minor: int | None = None
        account_fx_rate: str | None = None
        account_fx_rate_date: str | None = None
        account_fx_source: str | None = None
        if account_currency != transaction_currency:
            from .fx_rates import convert_minor_at_rate, resolve_exchange_rate

            try:
                exchange = resolve_exchange_rate(
                    self, transaction_currency, account_currency, occurred_on
                )
            except (ValueError, RuntimeError) as exc:
                raise LedgerError(str(exc)) from exc
            if exchange.rate_date > occurred_on:
                raise LedgerError("账户换算汇率有效日期不能晚于交易日期")
            account_amount_minor = convert_minor_at_rate(
                int(row["amount_minor"]),
                int(self.currency(transaction_currency)["minor_digits"]),
                int(self.currency(account_currency)["minor_digits"]),
                exchange.rate,
            )
            if account_amount_minor <= 0:
                raise LedgerError("按交易日参考汇率换算后的账户扣款金额小于最小货币单位。")
            account_fx_rate = format(exchange.rate, "f")
            account_fx_rate_date = exchange.rate_date
            account_fx_source = exchange.source

        with self.connection:
            cursor = self.connection.execute(
                """UPDATE transactions
                   SET account_id=?,balance_effect='posted',needs_review=0,
                       account_amount_minor=?,account_fx_rate=?,account_fx_rate_date=?,account_fx_source=?
                   WHERE id=? AND balance_effect='memo' AND needs_review=1""",
                (
                    int(account["id"]), account_amount_minor, account_fx_rate,
                    account_fx_rate_date, account_fx_source, transaction_id,
                ),
            )
            if cursor.rowcount != 1:
                raise LedgerError("流水状态已改变，请刷新后重试。")
            self._record_credit_recovery_points([transaction_id])
        return True

    def update_transaction_with_backup(
        self,
        transaction_id: int,
        *,
        occurred_on: str,
        kind: str,
        amount: str | int | Decimal,
        currency: str,
        description: str,
        category_name: str | None = None,
        account_name: str | None = None,
        to_account_name: str | None = None,
        to_amount: str | int | Decimal | None = None,
        memo_only: bool = False,
        needs_review: bool = False,
    ) -> Path:
        """Validate, back up, then update an existing ledger entry in place."""
        if isinstance(transaction_id, bool) or not isinstance(transaction_id, int) or transaction_id <= 0:
            raise LedgerError("流水编号无效")
        if self.connection.in_transaction:
            raise LedgerError("账本正在执行其他写入，暂时无法编辑流水")
        old = self.connection.execute(
            "SELECT * FROM transactions WHERE id=?", (transaction_id,)
        ).fetchone()
        if old is None:
            raise LedgerError("所选流水已不存在，请刷新账单记录后重试。")
        if self.connection.execute(
            "SELECT 1 FROM credit_repayment_periods WHERE transaction_id=?", (transaction_id,)
        ).fetchone() is not None:
            raise LedgerError("这条流水关联着信用卡自动还款计划，请在还款管理中调整，避免计划金额与账目不一致。")
        linked_food_items = self.connection.execute(
            "SELECT 1 FROM food_purchase_items WHERE transaction_id=? LIMIT 1",
            (transaction_id,),
        ).fetchone() is not None

        date_text = parse_date(occurred_on).isoformat()
        currency_code = str(currency).upper()
        currency_row = self.currency(currency_code)
        if not bool(currency_row["is_monetary"]):
            raise LedgerError("账务记录必须使用货币币种")
        amount_minor = to_minor(amount, currency_code, int(currency_row["minor_digits"]))
        clean_description = str(description).strip()
        if not clean_description:
            raise LedgerError("交易说明不能为空")
        if kind not in {"income", "expense", "transfer"}:
            raise LedgerError("请选择有效的账务类型。")
        if linked_food_items and kind != "expense":
            raise LedgerError("这笔支出关联着采购商品记录，请先在食材与饮食记录中处理关联商品，再修改账务类型。")

        account = self.account(account_name) if account_name else None
        destination = self.account(to_account_name) if to_account_name else None
        category_row = None
        to_amount_minor: int | None = None
        account_amount_minor: int | None = None
        account_fx_rate: str | None = None
        account_fx_rate_date: str | None = None
        account_fx_source: str | None = None
        jpy_equiv_minor: int | None = None
        fx_rate: str | None = None
        fx_rate_date: str | None = None
        fx_source: str | None = None

        if kind in {"income", "expense"}:
            if not category_name:
                raise LedgerError("请选择有效类别。")
            category_row = self.connection.execute(
                "SELECT * FROM categories WHERE name=? AND kind=?",
                (category_name, kind),
            ).fetchone()
            if category_row is None:
                raise LedgerError("所选类别与交易类型不匹配。")
            if not category_row["is_active"] and int(category_row["id"]) != int(old["category_id"] or 0):
                raise LedgerError("已停用类别不能用于这笔账务记录。")
            if destination is not None or to_amount is not None:
                raise LedgerError("收入或消费不能指定转入账户或转入金额")
            if memo_only:
                if account is not None:
                    raise LedgerError("备查交易不得绑定账户")
            elif account is None:
                raise LedgerError("入账交易必须指定账户；无账户的备查记录请选择“备查”")
            if account is not None:
                if date_text < account["opening_date"]:
                    raise LedgerError(f"交易日期早于账户期初日期：{account['opening_date']}")
                account_currency = str(account["currency"])
                if account_currency != currency_code:
                    same_conversion = (
                        old["balance_effect"] == "posted"
                        and old["occurred_on"] == date_text
                        and old["currency"] == currency_code
                        and int(old["amount_minor"]) == amount_minor
                        and old["account_id"] == account["id"]
                        and old["account_amount_minor"] is not None
                    )
                    if same_conversion:
                        account_amount_minor = int(old["account_amount_minor"])
                        account_fx_rate = old["account_fx_rate"]
                        account_fx_rate_date = old["account_fx_rate_date"]
                        account_fx_source = old["account_fx_source"]
                    else:
                        from .fx_rates import convert_minor_at_rate, resolve_exchange_rate

                        try:
                            exchange = resolve_exchange_rate(
                                self, currency_code, account_currency, date_text
                            )
                        except (ValueError, RuntimeError) as exc:
                            raise LedgerError(str(exc)) from exc
                        if exchange.rate_date > date_text:
                            raise LedgerError("账户换算汇率有效日期不能晚于交易日期")
                        account_amount_minor = convert_minor_at_rate(
                            amount_minor,
                            int(currency_row["minor_digits"]),
                            int(self.currency(account_currency)["minor_digits"]),
                            exchange.rate,
                        )
                        if account_amount_minor <= 0:
                            raise LedgerError("按交易日参考汇率换算后的账户扣款金额小于最小货币单位。")
                        account_fx_rate = format(exchange.rate, "f")
                        account_fx_rate_date = exchange.rate_date
                        account_fx_source = exchange.source
            elif memo_only:
                account = None
                account_amount_minor = None

            if currency_code == "CNY":
                if (
                    old["kind"] in {"income", "expense"}
                    and old["currency"] == currency_code
                    and old["occurred_on"] == date_text
                    and int(old["amount_minor"]) == amount_minor
                    and old["jpy_equiv_minor"] is not None
                ):
                    jpy_equiv_minor = int(old["jpy_equiv_minor"])
                    fx_rate = old["fx_rate"]
                    fx_rate_date = old["fx_rate_date"]
                    fx_source = old["fx_source"]
                else:
                    from .fx_rates import convert_minor_to_jpy_minor, resolve_jpy_rate

                    try:
                        applied_rate = resolve_jpy_rate(self, "CNY", date_text)
                    except (ValueError, RuntimeError) as exc:
                        raise LedgerError(str(exc)) from exc
                    jpy_equiv_minor = convert_minor_to_jpy_minor(
                        amount_minor, int(currency_row["minor_digits"]), applied_rate.rate
                    )
                    fx_rate = format(applied_rate.rate, "f")
                    fx_rate_date = applied_rate.rate_date
                    fx_source = applied_rate.source
            effect = "memo" if memo_only else "posted"
            account_id = int(account["id"]) if account is not None else None
            to_account_id = None
            category_id = int(category_row["id"])
        else:
            if memo_only:
                raise LedgerError("转账不能作为备查交易")
            if account is None or destination is None:
                raise LedgerError("转账必须同时指定转出和转入账户")
            if int(account["id"]) == int(destination["id"]):
                raise LedgerError("转出账户和转入账户不能相同")
            if account["currency"] != currency_code:
                raise LedgerError("转出金额币种必须与转出账户一致")
            if date_text < account["opening_date"] or date_text < destination["opening_date"]:
                raise LedgerError("转账日期不能早于任一账户期初日期")
            destination_currency = self.currency(str(destination["currency"]))
            if to_amount is None or not str(to_amount).strip():
                if destination["currency"] != currency_code:
                    raise LedgerError("跨币种转账必须填写转入金额")
                to_amount_minor = amount_minor
            else:
                to_amount_minor = to_minor(
                    to_amount,
                    str(destination_currency["code"]),
                    int(destination_currency["minor_digits"]),
                )
            effect = "posted"
            account_id = int(account["id"])
            to_account_id = int(destination["id"])
            category_id = None

        backup_root = (
            self.path.parent.parent / "backups"
            if self.path.parent.name.lower() == "data"
            else self.path.parent / "backups"
        )
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        target = backup_root / f"{self.path.stem}-before-transaction-edit-{stamp}.sqlite3"
        suffix = 1
        while target.exists():
            target = backup_root / f"{self.path.stem}-before-transaction-edit-{stamp}-{suffix}.sqlite3"
            suffix += 1
        self.backup(target)

        affected_card_ids = {
            int(value) for value in (
                old["account_id"], old["to_account_id"], account_id, to_account_id
            ) if value is not None
        }
        affected_card_ids = {
            account_id_value for account_id_value in affected_card_ids
            if self.connection.execute(
                "SELECT 1 FROM accounts WHERE id=? AND account_type='credit'",
                (account_id_value,),
            ).fetchone() is not None
        }
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            fresh = self.connection.execute(
                "SELECT * FROM transactions WHERE id=?", (transaction_id,)
            ).fetchone()
            if fresh is None or tuple(fresh) != tuple(old):
                raise LedgerError("流水已在其他窗口中改变，请刷新账单记录后重试。")
            cursor = self.connection.execute(
                """UPDATE transactions
                   SET occurred_on=?,kind=?,amount_minor=?,currency=?,account_id=?,to_account_id=?,
                       to_amount_minor=?,category_id=?,description=?,balance_effect=?,jpy_equiv_minor=?,
                       fx_rate=?,fx_rate_date=?,fx_source=?,account_amount_minor=?,account_fx_rate=?,
                       account_fx_rate_date=?,account_fx_source=?,needs_review=?
                   WHERE id=?""",
                (
                    date_text, kind, amount_minor, currency_code, account_id, to_account_id,
                    to_amount_minor, category_id, clean_description, effect, jpy_equiv_minor,
                    fx_rate, fx_rate_date, fx_source, account_amount_minor, account_fx_rate,
                    account_fx_rate_date, account_fx_source, int(bool(needs_review)), transaction_id,
                ),
            )
            if cursor.rowcount != 1:
                raise LedgerError("流水状态已改变，请刷新后重试。")
            if kind == "expense":
                self.connection.execute(
                    "UPDATE food_purchase_items SET purchase_date=? WHERE transaction_id=?",
                    (date_text, transaction_id),
                )
            else:
                self.connection.execute(
                    "DELETE FROM food_purchase_items WHERE transaction_id=?", (transaction_id,)
                )
            self._rebuild_credit_recovery_points(affected_card_ids)
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
        return target

    def _rebuild_credit_recovery_points(self, account_ids: Sequence[int]) -> None:
        """Recreate automatic card availability points after transaction edits."""
        for account_id in sorted({int(value) for value in account_ids}):
            card = self.connection.execute(
                "SELECT account_type FROM accounts WHERE id=?", (account_id,)
            ).fetchone()
            if card is None or card["account_type"] != "credit":
                continue
            self.connection.execute(
                "DELETE FROM credit_limit_recovery_points WHERE account_id=?", (account_id,)
            )
            snapshot = self.connection.execute(
                """SELECT * FROM credit_limit_snapshots WHERE account_id=?
                   ORDER BY snapshot_date DESC,created_at DESC,id DESC LIMIT 1""",
                (account_id,),
            ).fetchone()
            if snapshot is None:
                continue
            limit_minor = int(snapshot["limit_minor"])
            available_minor = int(snapshot["available_minor"])
            movements = self.connection.execute(
                """SELECT id,occurred_on,created_at,kind,amount_minor,currency,account_amount_minor,
                          to_amount_minor,account_id,to_account_id
                   FROM transactions
                   WHERE balance_effect='posted'
                     AND (occurred_on>? OR (occurred_on=? AND (
                          created_at>? OR (created_at=? AND id>0))))
                     AND (account_id=? OR to_account_id=?)
                   ORDER BY occurred_on,created_at,id""",
                (
                    snapshot["snapshot_date"], snapshot["snapshot_date"],
                    snapshot["created_at"], snapshot["created_at"], account_id, account_id,
                ),
            ).fetchall()
            for movement in movements:
                delta = 0
                if movement["kind"] == "expense" and movement["account_id"] == account_id:
                    delta -= int(
                        movement["account_amount_minor"]
                        if movement["account_amount_minor"] is not None
                        else movement["amount_minor"]
                    )
                elif movement["kind"] == "income" and movement["account_id"] == account_id:
                    delta += int(
                        movement["account_amount_minor"]
                        if movement["account_amount_minor"] is not None
                        else movement["amount_minor"]
                    )
                elif movement["kind"] == "transfer":
                    if movement["account_id"] == account_id:
                        delta -= int(movement["amount_minor"])
                    if movement["to_account_id"] == account_id:
                        delta += int(movement["to_amount_minor"])
                if not delta:
                    continue
                available_minor = min(limit_minor, max(0, available_minor + delta))
                self.connection.execute(
                    """INSERT INTO credit_limit_recovery_points
                       (account_id,transaction_id,snapshot_date,limit_minor,available_minor,created_at)
                       VALUES (?,?,?,?,?,?)""",
                    (
                        account_id, int(movement["id"]), movement["occurred_on"],
                        limit_minor, available_minor, movement["created_at"],
                    ),
                )

    def delete_transaction_with_backup(self, transaction_id: int) -> Path:
        """Back up the ledger, then remove one transaction and its linked records.

        A repayment period linked to the transaction is canceled before removal,
        so a manually deleted scheduled repayment cannot be silently reposted.
        Food purchase rows cascade with the transaction; recurring occurrence
        rows retain their history with a NULL transaction reference.
        """
        if isinstance(transaction_id, bool) or not isinstance(transaction_id, int) or transaction_id <= 0:
            raise LedgerError("流水编号无效")
        if self.connection.in_transaction:
            raise LedgerError("账本正在执行其他写入，暂时无法删除流水")
        if self.connection.execute(
            "SELECT 1 FROM transactions WHERE id=?", (transaction_id,)
        ).fetchone() is None:
            raise LedgerError(f"找不到流水 #{transaction_id}；请刷新账单记录后重试")
        transaction = self.connection.execute(
            """SELECT id,occurred_on,created_at,account_id,to_account_id
               FROM transactions WHERE id=?""",
            (transaction_id,),
        ).fetchone()

        backup_root = (
            self.path.parent.parent / "backups"
            if self.path.parent.name.lower() == "data"
            else self.path.parent / "backups"
        )
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        target = backup_root / f"{self.path.stem}-before-transaction-delete-{stamp}.sqlite3"
        suffix = 1
        while target.exists():
            target = backup_root / f"{self.path.stem}-before-transaction-delete-{stamp}-{suffix}.sqlite3"
            suffix += 1
        self.backup(target)

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            if self.connection.execute(
                "SELECT 1 FROM transactions WHERE id=?", (transaction_id,)
            ).fetchone() is None:
                raise LedgerError(f"流水 #{transaction_id} 已不存在；未执行删除")

            repayment_periods = self.connection.execute(
                "SELECT id,rule_id FROM credit_repayment_periods WHERE transaction_id=?",
                (transaction_id,),
            ).fetchall()
            if repayment_periods:
                self.connection.execute(
                    """UPDATE credit_repayment_periods
                       SET status='cancelled',transaction_id=NULL,updated_at=?
                       WHERE transaction_id=?""",
                    (now, transaction_id),
                )
                rule_ids = sorted({int(row["rule_id"]) for row in repayment_periods})
                placeholders = ",".join("?" for _ in rule_ids)
                self.connection.execute(
                    f"UPDATE credit_repayment_rules SET last_status=?,updated_at=? WHERE id IN ({placeholders})",
                    ("本期流水已手工删除；自动还款关联已取消", now, *rule_ids),
                )

            for account_id in (transaction["account_id"], transaction["to_account_id"]):
                if account_id is None:
                    continue
                is_credit = self.connection.execute(
                    "SELECT 1 FROM accounts WHERE id=? AND account_type='credit'",
                    (account_id,),
                ).fetchone()
                if is_credit:
                    self.connection.execute(
                        """DELETE FROM credit_limit_recovery_points
                           WHERE account_id=? AND (
                               snapshot_date>? OR
                               (snapshot_date=? AND (
                                   created_at>? OR (created_at=? AND transaction_id>=?)
                               ))
                           )""",
                        (
                            int(account_id), transaction["occurred_on"], transaction["occurred_on"],
                            transaction["created_at"], transaction["created_at"], transaction_id,
                        ),
                    )

            cursor = self.connection.execute(
                "DELETE FROM transactions WHERE id=?", (transaction_id,)
            )
            if cursor.rowcount != 1:
                raise LedgerError(f"流水 #{transaction_id} 已不存在；未执行删除")
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
        return target

    def validate(self) -> tuple[list[str], list[str]]:
        errors: list[str] = []
        warnings: list[str] = []
        integrity = self.connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            errors.append(f"SQLite完整性检查失败：{integrity}")
        fk_rows = self.connection.execute("PRAGMA foreign_key_check").fetchall()
        if fk_rows:
            errors.append(f"发现{len(fk_rows)}条外键错误")
        for row in self.connection.execute(
            "SELECT name,account_type,currency FROM accounts "
            "WHERE (account_type='points' AND currency!='JPY') OR currency='PTS'"
        ):
            errors.append(f"账户“{row['name']}”未按积分JPY等值规则保存（{row['account_type']}/{row['currency']}）")
        legacy_points_transactions = self.connection.execute(
            "SELECT COUNT(*) FROM transactions WHERE currency='PTS'"
        ).fetchone()[0]
        if legacy_points_transactions:
            errors.append(f"仍有{legacy_points_transactions}笔流水使用旧PTS币种，需运行数据库迁移")
        for row in self.connection.execute("SELECT * FROM transactions ORDER BY id"):
            account_currency: str | None = None
            if row["account_id"] is not None:
                account_row = self.connection.execute(
                    "SELECT currency FROM accounts WHERE id=?", (row["account_id"],)
                ).fetchone()
                account_currency = str(account_row["currency"]) if account_row is not None else None
            if row["kind"] in {"income", "expense"}:
                category = self.connection.execute("SELECT kind FROM categories WHERE id=?", (row["category_id"],)).fetchone()
                if category is None or category["kind"] != row["kind"]:
                    errors.append(f"交易#{row['id']}的类别类型不匹配")
                if row["balance_effect"] == "posted" and row["account_id"] is None:
                    errors.append(f"入账交易#{row['id']}没有账户")
                if row["balance_effect"] == "memo" and row["account_id"] is not None:
                    errors.append(f"备查交易#{row['id']}不应影响账户余额")
                if (
                    row["balance_effect"] == "posted"
                    and account_currency is not None
                    and account_currency != row["currency"]
                    and row["account_amount_minor"] is None
                ):
                    errors.append(f"交易#{row['id']}的账单币种与扣款账户币种不同，但缺少账户扣款金额")
                if row["account_amount_minor"] is not None:
                    if row["balance_effect"] != "posted" or account_currency is None:
                        errors.append(f"交易#{row['id']}不应包含账户扣款金额")
                    elif not row["account_fx_rate"] or not row["account_fx_rate_date"] or not row["account_fx_source"]:
                        errors.append(f"交易#{row['id']}的账户换算信息不完整")
                    else:
                        try:
                            rate_date = parse_date(str(row["account_fx_rate_date"]))
                            account_rate = Decimal(str(row["account_fx_rate"]))
                            if not account_rate.is_finite() or account_rate <= 0 or rate_date.isoformat() > row["occurred_on"]:
                                errors.append(f"交易#{row['id']}的账户换算汇率或有效日期无效")
                            else:
                                from .fx_rates import convert_minor_at_rate

                                expected_account_amount = convert_minor_at_rate(
                                    int(row["amount_minor"]),
                                    int(self.currency(str(row["currency"]))["minor_digits"]),
                                    int(self.currency(account_currency)["minor_digits"]),
                                    account_rate,
                                )
                                if expected_account_amount != int(row["account_amount_minor"]):
                                    errors.append(f"交易#{row['id']}的账户扣款金额与汇率不一致")
                        except (LedgerError, InvalidOperation, TypeError, ValueError):
                            errors.append(f"交易#{row['id']}的账户换算汇率格式无效")
            elif row["kind"] == "transfer":
                if row["account_id"] is None or row["to_account_id"] is None or row["to_amount_minor"] is None:
                    errors.append(f"转账#{row['id']}缺少一端账户或金额")
            if row["needs_review"]:
                warnings.append(f"交易#{row['id']}待核对：{row['description']}")
            if row["currency"] == "CNY" and row["kind"] in {"income", "expense"}:
                if row["jpy_equiv_minor"] is None or not row["fx_rate"] or not row["fx_rate_date"]:
                    warnings.append(f"人民币交易#{row['id']}尚无交易日JPY折算；利润表日元合计不含该笔")
                else:
                    try:
                        parse_date(row["fx_rate_date"])
                        if Decimal(str(row["fx_rate"])) <= 0 or int(row["jpy_equiv_minor"]) < 0:
                            errors.append(f"人民币交易#{row['id']}的交易日汇率或JPY折算金额无效")
                    except (LedgerError, InvalidOperation, TypeError, ValueError):
                        errors.append(f"人民币交易#{row['id']}的交易日汇率格式无效")
        for row in self.connection.execute(
            "SELECT s.*,a.name FROM credit_limit_snapshots s JOIN accounts a ON a.id=s.account_id"
        ):
            if row["available_minor"] > row["limit_minor"]:
                errors.append(f"{row['name']}的可用额度高于总额度")
        for row in self.connection.execute(
            """SELECT r.*,card.name AS card_name,card.account_type AS card_type,
                      card.currency AS card_currency,source.name AS source_name,
                      source.account_type AS source_type,source.currency AS source_currency
               FROM credit_repayment_rules r
               JOIN accounts card ON card.id=r.card_account_id
               JOIN accounts source ON source.id=r.source_account_id"""
        ):
            if row["card_type"] != "credit":
                errors.append(f"每月还款计划“{row['card_name']}”目标账户不是信用卡")
            if row["source_type"] not in {"bank", "wallet", "prepaid", "transit"}:
                errors.append(f"每月还款计划“{row['card_name']}”转出账户类型不支持")
            if row["card_currency"] != row["source_currency"] or row["currency"] != row["card_currency"]:
                errors.append(f"每月还款计划“{row['card_name']}”币种不一致")
            try:
                parse_date(row["next_due_date"])
            except LedgerError:
                errors.append(f"每月还款计划“{row['card_name']}”日期无效")
        for row in self.connection.execute(
            """SELECT p.*,r.card_account_id,card.name AS card_name,t.kind AS transaction_kind,
                      t.to_account_id AS transaction_card_id,t.occurred_on AS transaction_date
               FROM credit_repayment_periods p
               JOIN credit_repayment_rules r ON r.id=p.rule_id
               JOIN accounts card ON card.id=r.card_account_id
               LEFT JOIN transactions t ON t.id=p.transaction_id"""
        ):
            try:
                parse_date(row["due_date"])
            except LedgerError:
                errors.append(f"信用卡“{row['card_name']}”本期还款日期无效")
            if row["transaction_id"] is not None and (
                row["transaction_kind"] != "transfer"
                or row["transaction_card_id"] != row["card_account_id"]
                or row["transaction_date"] != row["due_date"]
            ):
                errors.append(f"信用卡“{row['card_name']}”本期还款关联的流水不匹配")
        for row in self.connection.execute("SELECT * FROM accounts"):
            balance = self.account_balance_minor(row["id"])
            if row["account_type"] == "credit" and row["balance_completeness"] == "partial":
                warnings.append(f"{row['name']}历史流水不完整；当前欠款按额度差额估算，需与当月账单核对")
            elif balance < 0:
                warnings.append(f"{row['name']}余额为负数，请核对")
        for row in self.connection.execute("SELECT id,purchase_date,item_name FROM food_purchase_items"):
            try:
                parse_date(row["purchase_date"])
            except LedgerError:
                errors.append(f"采购商品记录#{row['id']}的日期无效")
            if not str(row["item_name"]).strip():
                errors.append(f"采购商品记录#{row['id']}的商品名称为空")
        for row in self.connection.execute("SELECT id,consumed_on,item_name FROM food_consumption_records"):
            try:
                parse_date(row["consumed_on"])
            except LedgerError:
                errors.append(f"食用记录#{row['id']}的日期无效")
            if not str(row["item_name"]).strip():
                errors.append(f"食用记录#{row['id']}的食物名称为空")
        return errors, warnings

    def backup(self, destination: str | Path, overwrite: bool = False) -> Path:
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.resolve() == self.path.resolve():
            raise LedgerError("备份目标不能与当前数据库相同")
        if target.exists() and not overwrite:
            raise LedgerError(f"备份文件已存在：{target}（如确需覆盖，使用--overwrite）")
        target_connection = sqlite3.connect(target)
        try:
            self.connection.backup(target_connection)
        finally:
            target_connection.close()
        return target


def seed_demo_data(database: Database) -> None:
    """Populate an empty database with clearly synthetic example data."""
    if database.connection.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] or database.connection.execute(
        "SELECT COUNT(*) FROM transactions"
    ).fetchone()[0]:
        raise LedgerError("演示数据只能写入空账本；没有修改现有数据")

    rows = (
        ("瑞穗银行", "bank", "JPY", 100000, "2026-10-14", "known", "Synthetic demo opening balance."),
        ("PayPay钱包", "wallet", "JPY", 2000, "2026-10-15", "known", "Synthetic demo opening balance."),
        ("Rakuten Pay", "wallet", "JPY", 1000, "2026-10-15", "known", "Synthetic demo wallet; separate from the card account."),
        ("Suica", "transit", "JPY", 800, "2026-10-15", "known", "Synthetic demo opening balance."),
        ("PASMO", "transit", "JPY", 5000, "2026-10-15", "known", "Synthetic demo opening balance."),
        ("PayPay券", "prepaid", "JPY", 1300, "2026-10-14", "known", "Synthetic demo opening balance."),
        ("Rakuten积分", "points", "JPY", 300, "2026-10-15", "known", "Synthetic demo points balance."),
        ("Mercari积分", "points", "JPY", 600, "2026-10-15", "known", "Synthetic demo points balance."),
        ("d积分", "points", "JPY", 1000, "2026-10-15", "known", "Synthetic demo points balance."),
        ("Moppy积分", "points", "JPY", 500, "2026-10-15", "known", "Synthetic demo points balance."),
        ("Rakuten Card", "credit", "JPY", 0, "2026-10-15", "partial", "Synthetic demo credit card."),
        ("PayPay Card", "credit", "JPY", 0, "2026-10-15", "partial", "Synthetic demo credit card."),
        ("Mercari Card", "credit", "JPY", 0, "2026-10-15", "partial", "Synthetic demo credit card."),
    )
    for name, account_type, currency, opening, opened, completeness, note in rows:
        database.add_account(
            name=name, account_type=account_type, currency=currency,
            opening_balance=opening, opening_date=opened,
            completeness=completeness, note=note,
        )

    database.add_transaction(
        occurred_on="2026-10-15", kind="income", amount=100000, currency="JPY",
        account_name="瑞穗银行", category_name="工资", description="Example monthly income", source="demo_data",
    )
    database.add_transaction(
        occurred_on="2026-10-15", kind="expense", amount=500, currency="JPY",
        account_name="PayPay券", category_name="餐饮", description="Example meal", source="demo_data",
    )
    database.add_transaction(
        occurred_on="2026-10-15", kind="expense", amount=200, currency="JPY",
        category_name="其他损耗", description="Example memo-only expense",
        memo_only=True, needs_review=True, source="demo_data",
    )

    limits = (
        ("Rakuten Card", 100000, 50000),
        ("PayPay Card", 50000, 25000),
        ("Mercari Card", 100000, 40000),
    )
    for name, limit, available in limits:
        database.add_credit_limit_snapshot(
            name, "2026-10-15", limit, available,
            "Synthetic demo credit limit and available balance.",
        )

    with database.connection:
        database.connection.execute(
            "INSERT OR REPLACE INTO settings(key,value,note) VALUES (?,?,?)",
            ("snapshot_date", "2026-10-15", "Synthetic demo data date."),
        )
