"""Account-isolated mobile services built on the desktop ledger rules."""
from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import multiprocessing
import os
import re
import secrets
import socket
import sqlite3
import tempfile
import threading
import time
import uuid
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlsplit

from cryptography.fernet import Fernet
from .cloud_pull import PullState, automatic_pull, local_revision

from .backup_scope import DEFAULT_BACKUP_SCOPE, normalize_backup_scope
from .cash_management import managed_balances, reconcile_account_balances
from .credit_management import (
    credit_card_overview, credit_repayment_schedules, record_credit_card_repayment,
    save_credit_repayment_schedule, set_credit_repayment_schedule_enabled,
    process_due_credit_repayments,
)
from .financial_statements import build_balance_sheet, build_profit_statement
from .food_categories import FOOD_GROUP_LABELS
from .localization import translate
from .food_review import build_food_review_answer
from .github_sync import (
    GITHUB_APP_CLIENT_ID, GitHubClient, GitHubSyncError,
    create_sync_bundle, restore_sync_bundle, request_device_code, poll_device_token,
)
from .github_app_config import GITHUB_APP_INSTALL_URL
from .gitee_sync import GiteeClient, GiteeSyncError, MAX_GITEE_SYNC_BUNDLE_BYTES
from .natural_language import load_image_attachment
from .payment_preferences import PaymentPromptStore
from .recurring_transactions import (
    list_recurring_schedules, save_recurring_schedule, delete_recurring_schedule,
    set_recurring_schedule_enabled, process_due_recurring_transactions,
)
from .request_worker import run_isolated_request, merge_isolated_database
from .skill_settings import BookkeepingSkillStore, FoodHealthSkillStore, BookkeepingSkillError
from .storage import Database, LedgerError, to_minor_allow_zero, parse_date, billing_cycle

WEB_DEFAULTS = Path(__file__).with_name("web_defaults")
JST = timezone(timedelta(hours=9))


def today() -> str:
    return datetime.now(JST).date().isoformat()


def serial(value):
    if isinstance(value, sqlite3.Row):
        value = dict(value)
    if isinstance(value, dict):
        return {k: serial(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [serial(v) for v in value]
    # Money remains integers throughout Python. JS receives decimal strings.
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return value


def atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            os.chmod(temporary, 0o600)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    os.replace(temporary, path)


class MobileWorkspace:
    def __init__(self, server):
        self.server = server
        self.root = server.data_dir / "mobile"
        self.root.mkdir(parents=True, exist_ok=True)
        key_path = self.root / ".credential-key"
        if not key_path.exists():
            # Exclusive creation avoids two startups choosing different keys.
            try:
                with key_path.open("xb") as stream:
                    os.chmod(key_path, 0o600)
                    stream.write(Fernet.generate_key())
            except FileExistsError:
                pass
        self.cipher = Fernet(key_path.read_bytes())
        self.jobs = {}
        self.guard = threading.RLock()
        self.locks = {}
        self.conversations = {}
        self.auto_pending = set()
        self.auto_running = set()
        self.auto_status = {}
        self.generations = {}
        self.pulling = set()
        self.stop_event = threading.Event()
        threading.Thread(target=self._scheduled_entries, daemon=True).start()

    def lock(self, uid):
        # Same lock as basic web writes, imports and exports.
        from .web import _get_user_lock
        return _get_user_lock(uid)

    def folder(self, uid):
        if not re.fullmatch(r"[a-f0-9-]{32,36}", uid):
            raise LedgerError("账号标识无效。")
        path = self.root / uid
        path.mkdir(parents=True, exist_ok=True)
        return path

    def db_path(self, uid):
        return self.server.ledger_dir / f"{uid}.sqlite3"

    def config(self, uid):
        path = self.folder(uid) / "settings.enc"
        if path.exists():
            value = json.loads(self.cipher.decrypt(path.read_bytes()))
        else:
            value = {}
        value.setdefault("profiles", [])
        value.setdefault("agents", {"bookkeeping": "", "food_health": ""})
        value.setdefault("visionAgents", dict(value["agents"]))
        value.setdefault("scope", dict(DEFAULT_BACKUP_SCOPE))
        value.setdefault("autoSync", True)
        value.setdefault("saveImages", True)
        value.setdefault("cloud", {})
        return value

    def save_config(self, uid, value):
        atomic(self.folder(uid) / "settings.enc",
               self.cipher.encrypt(json.dumps(value, ensure_ascii=False).encode()))

    def stores(self, uid):
        folder = self.folder(uid)
        return {
            "payment_store": PaymentPromptStore(folder / "payment_prompts.json"),
            "bookkeeping_skill_store": BookkeepingSkillStore(
                folder / "bookkeeping_skill.json", default_path=WEB_DEFAULTS / "bookkeeping.md",
                managed_paths=(folder / "restored_skills" / "bookkeeping.md", folder / "bookkeeping.md")),
            "food_skill_store": BookkeepingSkillStore(
                folder / "food_skill.json", default_path=WEB_DEFAULTS / "food-health.md",
                managed_paths=(folder / "restored_skills" / "food_health.md", folder / "food_health.md")),
            "receipt_image_directory": folder / "receipt_images",
        }

    def public_settings(self, uid):
        cfg = deepcopy(self.config(uid))
        for profile in cfg["profiles"]:
            profile["keyPresent"] = bool(profile.pop("api_key", ""))
        for cloud in cfg["cloud"].values():
            cloud["connected"] = bool(cloud.pop("token", ""))
            cloud.pop("refresh_token", None)
        cfg["githubInstallUrl"] = GITHUB_APP_INSTALL_URL
        stores = self.stores(uid)
        payment, revision = stores["payment_store"].load_snapshot()
        cfg["paymentRules"] = payment.get("profiles", [])
        cfg["paymentRevision"] = revision
        cfg["skillErrors"] = {}
        for agent, key in (("bookkeeping", "bookkeeping_skill_store"), ("food_health", "food_skill_store")):
            try:
                loaded = stores[key].load()
            except BookkeepingSkillError:
                # A broken optional Agent configuration must not hide the
                # ledger, reports, or the settings page needed to repair it.
                loaded = None
                cfg["skillErrors"][agent] = True
            cfg.setdefault("skills", {})[agent] = loaded["content"] if loaded else ""
        cfg["autoStatus"] = self.auto_status.get(uid, "")
        return cfg

    def snapshot(self, uid, language="zh-CN", report_date=None):
        report_date = parse_date(report_date).isoformat() if report_date else today()
        with self.lock(uid):
            db = Database(self.db_path(uid))
            try:
                db.initialize()
                setting_rows = db.connection.execute(
                    "SELECT key,value FROM settings WHERE key NOT LIKE 'web_%'"
                ).fetchall()
                bills = db.transactions_between("1900-01-01", "2199-12-31")
                food = db.connection.execute(
                    "SELECT * FROM food_purchase_items ORDER BY purchase_date DESC,id DESC LIMIT 500"
                ).fetchall()
                eaten = db.connection.execute(
                    "SELECT * FROM food_consumption_records ORDER BY consumed_on DESC,id DESC LIMIT 500"
                ).fetchall()
                cards = credit_card_overview(db, today())
                history = {
                    str(card["account_id"]): {
                        "snapshots": db.credit_snapshot_history(card["account_id"]),
                        "transactions": db.credit_transaction_history(card["account_id"]),
                    } for card in cards
                }
                errors, reviews = db.validate()
                value = {
                    "date": today(), "cash": managed_balances(db),
                    "cards": cards, "creditHistory": history,
                    "repaymentPlans": credit_repayment_schedules(db),
                    "recurring": list_recurring_schedules(db),
                    "assets": db.list_fixed_assets(),
                    "balanceSheet": build_balance_sheet(db, today()),
                    "profit": build_profit_statement(db, today()),
                    "reports": {"date": report_date,
                        "balanceSheet": build_balance_sheet(db, report_date),
                        "profit": build_profit_statement(db, report_date)},
                    "settings": {row["key"]: row["value"] for row in setting_rows},
                    "food": food, "eaten": eaten, "foodGroups": FOOD_GROUP_LABELS,
                    "foodReview": build_food_review_answer(db, "最近20天吃了什么", datetime.now(JST).date()),
                    "transactions": bills[:2000],
                    "validation": {"errors": errors, "reviews": reviews},
                }
            finally:
                db.close()
            for report in (value, value["reports"]):
                for row in report["balanceSheet"]["rows"]:
                    for key in ("section", "status", "account_type_label"):
                        if key in row:
                            row[key] = translate(row[key], language)
            value["foodGroups"] = {key: translate(label, language) for key, label in FOOD_GROUP_LABELS.items()}
            value["foodReview"] = translate(value["foodReview"], language)
            value["preferences"] = self.public_settings(uid)
            value["backups"] = self.backups(uid)
            image_dir = self.folder(uid) / "receipt_images"
            value["receipts"] = sorted([p.name for p in image_dir.iterdir() if p.is_file() and not p.is_symlink()])[-200:] if image_dir.exists() else []
            return serial(value)

    def backups(self, uid):
        folder = self.folder(uid) / "backups"
        if not folder.exists():
            return []
        return [
            {"name": p.name, "size": str(p.stat().st_size),
             "date": datetime.fromtimestamp(p.stat().st_mtime, JST).isoformat()}
            for p in sorted(folder.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)[:100]
        ]

    def backup(self, uid, prefix="manual", full=False):
        folder = self.folder(uid) / "backups"
        name = f"{prefix}-{datetime.now(JST):%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}.zip"
        with self.lock(uid):
            cfg = self.config(uid)
            body = create_sync_bundle(
                self.db_path(uid), folder / name, **self.stores(uid),
                include_scope=DEFAULT_BACKUP_SCOPE if full else cfg["scope"],
                max_bundle_bytes=512 * 1024 * 1024 if full else 60 * 1024 * 1024,
            )
        return name, body

    def backup_file(self, uid, name):
        if not re.fullmatch(r"[\w.-]+\.zip", name):
            raise LedgerError("备份文件名无效。")
        file = self.folder(uid) / "backups" / name
        if not file.is_file() or file.is_symlink():
            raise LedgerError("找不到此备份。")
        return file

    def restore(self, uid, body, provider="github"):
        with self.lock(uid):
            stores = self.stores(uid)
            before = restore_sync_bundle(
                body, self.db_path(uid), **stores,
                backup_directory=self.folder(uid) / "backups", backup_provider=provider,
                skill_restore_directory=self.folder(uid) / "restored_skills",
            )
            self.conversations.pop((uid, "bookkeeping"), None)
            self.conversations.pop((uid, "food_health"), None)
            self.generations[uid] = self.generations.get(uid, 0) + 1
            return {"message": "恢复完成，恢复前的数据已另外备份。", "backup": before.name}

    def _journal(self, uid):
        db = sqlite3.connect(self.folder(uid) / "actions.sqlite3", timeout=20)
        db.execute("CREATE TABLE IF NOT EXISTS actions(id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, state TEXT NOT NULL, result TEXT NOT NULL)")
        return db

    def start(self, uid, action, data, opid):
        if not isinstance(data, dict) or not re.fullmatch(r"[a-zA-Z0-9_-]{12,80}", opid):
            raise LedgerError("操作编号或数据无效，请重新打开页面。")
        fingerprint = hashlib.sha256(json.dumps([action, data], sort_keys=True).encode()).hexdigest()
        key = uid + ":" + opid
        with self.guard:
            if key in self.jobs:
                job = self.jobs[key]
                if job["fingerprint"] != fingerprint:
                    raise LedgerError("同一操作编号的数据发生变化，请刷新页面。")
                return self.job(uid, opid)
            journal = self._journal(uid)
            try:
                row = journal.execute("SELECT fingerprint,state,result FROM actions WHERE id=?", (opid,)).fetchone()
                if row:
                    if row[0] != fingerprint:
                        raise LedgerError("操作编号冲突。")
                    if row[1] == "running":
                        raise LedgerError("此操作在服务重启前已开始，请先核对账本结果，避免重复执行。")
                    return {"id": opid, "state": row[1], "result": json.loads(row[2])}
                if sum(j["state"] == "running" and j["uid"] == uid for j in self.jobs.values()) >= 2:
                    raise LedgerError("已有操作正在执行，请等待完成。")
                journal.execute("INSERT INTO actions VALUES(?,?,?,?)", (opid, fingerprint, "running", "{}"))
                journal.commit()
            finally:
                journal.close()
            self.jobs[key] = {"id": opid, "uid": uid, "state": "running",
                              "fingerprint": fingerprint, "cancel": threading.Event(),
                              "message": "正在处理…", "result": {}, "started": time.time()}
            thread = threading.Thread(target=self._work, args=(uid, action, data, opid), daemon=True)
            thread.start()
        return self.job(uid, opid)

    def job(self, uid, opid):
        with self.guard:
            item = self.jobs.get(uid + ":" + opid)
            if not item:
                journal = self._journal(uid)
                try:
                    row = journal.execute("SELECT state,result FROM actions WHERE id=?", (opid,)).fetchone()
                finally:
                    journal.close()
                if not row:
                    raise LedgerError("找不到此操作。")
                return {"id": opid, "state": "failed" if row[0] == "running" else row[0],
                        "result": json.loads(row[1]), "message": "服务已重启，请核对操作结果。"}
            result = {k: serial(item[k]) for k in ("id", "state", "message", "result")}
            if item.get("persisting"):
                result["state"] = "running"
            return result

    def cancel(self, uid, opid):
        item = self.jobs.get(uid + ":" + opid)
        if item and item["state"] == "running":
            item["cancel"].set()
        return {"ok": True}

    def _work(self, uid, action, data, opid):
        job = self.jobs[uid + ":" + opid]
        job["persisting"] = True
        try:
            if action in {"agent", "cloud_upload", "cloud_restore", "cloud_connect", "github_auth", "startup_pull"}:
                result = self._remote(uid, action, data, job)
            else:
                with self.lock(uid):
                    result = self._action(uid, action, data)
            job.update(state="done", message="已完成", result=result or {"ok": True})
        except Exception as exc:
            message = str(exc) if isinstance(exc, (ValueError, RuntimeError)) else "操作未完成，请核对输入或服务连接后重试。"
            cfg = self.config(uid)
            for profile in cfg["profiles"]:
                if profile.get("api_key"):
                    message = message.replace(profile["api_key"], "••••")
            for cloud in cfg["cloud"].values():
                for key in ("token", "refresh_token"):
                    if cloud.get(key):
                        message = message.replace(cloud[key], "••••")
            job.update(state="failed", message=message, result={"error": message})
        finally:
            journal = self._journal(uid)
            try:
                journal.execute("UPDATE actions SET state=?,result=? WHERE id=?",
                                (job["state"], json.dumps(serial(job["result"]), ensure_ascii=False), opid))
                journal.commit()
            finally:
                journal.close()
                job["persisting"] = False
            # Completed job payloads expire in memory; durable receipts remain.
            with self.guard:
                for key, item in list(self.jobs.items()):
                    if item["state"] != "running" and time.time() - item["started"] > 86400:
                        self.jobs.pop(key, None)

    def _action(self, uid, action, data):
        if action == 'keep_local_cloud':
            PullState(self.folder(uid) / 'cloud_pull_state.json').pause_downloads()
            return {'status': 'local_kept', 'restored': False}
        if action == "backup":
            name, _ = self.backup(uid)
            return {"message": "备份已创建。", "name": name}
        if action == "restore_local":
            self._confirmed(data)
            return self.restore(uid, self.backup_file(uid, str(data["name"])).read_bytes())
        if action == "settings":
            result = self._save_settings(uid, data)
            self.after_write(uid)
            return result
        if action == "payment_rules":
            if any(key[0] == uid for key in self.locks):
                raise LedgerError("请先等待当前 Agent 请求完成。")
            rules = data.get("profiles", [])
            db = Database(self.db_path(uid))
            try:
                for rule in rules:
                    parent = db.account(rule["payment_method"])
                    if parent["account_type"] == "points":
                        raise LedgerError("普通支付账户不能选择积分。")
                    order = rule.get("account_order", [rule["payment_method"]])
                    currencies = {db.account(name)["currency"] for name in order}
                    if len(currencies) != 1:
                        raise LedgerError("一个扣款顺序必须使用同一币种。")
                    if rule.get("currency") and rule["currency"] not in currencies:
                        raise LedgerError("规则币种必须与扣款账户一致。")
                self.stores(uid)["payment_store"].save_profiles(rules, expected_revision=data.get("revision"))
            finally:
                db.close()
            self.after_write(uid)
            return {"message": "付款规则已保存。"}
        if action == "agent_reset":
            self.conversations.pop((uid, data.get("agent", "bookkeeping")), None)
            return {"ok": True}
        if action == "cloud_disconnect":
            self._confirmed(data)
            cfg = self.config(uid)
            cfg["cloud"].pop(data["provider"], None)
            self.save_config(uid, cfg)
            return {"message": "已断开连接。"}
        db = Database(self.db_path(uid))
        try:
            db.initialize()
            result = {"message": "已保存。"}
            if action in {"delete_transaction", "delete_account", "delete_asset", "delete_recurring",
                          "delete_food", "restore_credit", "delete_category"}:
                self._confirmed(data)
                self.backup(uid, "before-change", full=True)
            if action == "reconcile":
                result["adjustments"] = serial(reconcile_account_balances(
                    db, data["amounts"], data.get("date") or today(),
                    post_differences=bool(data.get("postDifferences", True))))
            elif action == "credit_snapshot":
                db.add_credit_limit_snapshot(data["account"], data.get("date") or today(),
                                             str(data["limit"]), str(data["available"]), data.get("note", ""))
            elif action == "credit_repay":
                record_credit_card_repayment(db, card_name=data["card"], source_account_name=data["source"],
                                             amount=str(data["amount"]), occurred_on=data.get("date") or today(),
                                             description=data.get("description", "信用卡还款"))
            elif action == "credit_plan":
                save_credit_repayment_schedule(db, card_name=data["card"], source_account_name=data["source"],
                                               first_due_date=data["date"], amount=data.get("amount") or None)
            elif action == "credit_plan_toggle":
                set_credit_repayment_schedule_enabled(db, card_name=data["card"], enabled=bool(data["enabled"]))
            elif action == "restore_credit":
                db.restore_credit_snapshot_history(int(data["accountId"]), data["snapshotType"], int(data["snapshotId"]))
            elif action == "recurring":
                save_recurring_schedule(
                    db, name=data["name"], kind=data["kind"], amount=str(data["amount"]),
                    account_name=data["account"], category_name=data["category"],
                    frequency=data["frequency"], interval_count=int(data.get("interval", 1)),
                    first_date=data["date"], currency_code=data.get("currency") or None,
                    schedule_id=int(data["id"]) if data.get("id") else None)
            elif action == "recurring_toggle":
                set_recurring_schedule_enabled(db, int(data["id"]), bool(data["enabled"]))
            elif action == "delete_recurring":
                delete_recurring_schedule(db, int(data["id"]))
            elif action == "run_due":
                result["credit"] = serial(process_due_credit_repayments(db, today()))
                result["recurring"] = serial(process_due_recurring_transactions(db, today()))
            elif action == "asset":
                code = data["currency"]
                digits = db.currency(code)["minor_digits"]
                db.save_fixed_asset(
                    name=data["name"], acquisition_month=data["month"],
                    cost_minor=to_minor_allow_zero(str(data["cost"]), code, digits), currency=code,
                    useful_life_months=int(data["months"]),
                    include_in_balance_sheet=bool(data.get("included", True)),
                    disposal_month=data.get("disposal") or None,
                    asset_id=int(data["id"]) if data.get("id") else None)
            elif action == "delete_asset":
                db.delete_fixed_asset(int(data["id"]))
            elif action == "asset_toggle":
                db.set_fixed_asset_inclusion(int(data["id"]), bool(data["included"]))
            elif action == "food_purchase":
                db.add_food_purchases(data.get("date") or today(), data["items"])
            elif action == "food_eaten":
                db.add_food_consumptions(data.get("date") or today(), data["items"],
                                         meal=data.get("meal", ""), note=data.get("note", ""))
            elif action == "food_group":
                db.set_food_purchase_group(int(data["id"]), data["group"])
            elif action == "delete_food":
                if data["kind"] == "eaten":
                    db.delete_food_consumption(int(data["id"]))
                else:
                    db.delete_food_purchase_item(int(data["id"]))
            elif action == "delete_transaction":
                db.delete_transaction_with_backup(int(data["id"]))
            elif action == "review_transaction":
                db.confirm_transaction_review(int(data["id"]), account_name=data.get("account") or None)
            elif action == "delete_account":
                db.delete_managed_account(data["name"])
            elif action == "category":
                category_id = db.add_category(data["name"], data["kind"])
                for language in ("zh-CN", "ja-JP", "en-US"):
                    if data.get(language):
                        db.set_category_translation(category_id, language, data[language])
            elif action == "category_translation":
                db.set_category_translation(int(data["id"]), data["language"], data["name"])
            elif action == "delete_category":
                row = db.connection.execute("SELECT * FROM categories WHERE id=?", (int(data["id"]),)).fetchone()
                if not row:
                    raise LedgerError("类别不存在。")
                db.connection.execute("UPDATE categories SET is_active=0 WHERE id=?", (int(data["id"]),))
                db.connection.commit()
            elif action == "budget":
                amount = to_minor_allow_zero(str(data["total"]), "JPY", 0)
                db.set_setting("monthly_jpy_budget_minor", str(amount), "Web budget")
                items = {name: to_minor_allow_zero(str(value), "JPY", 0) for name, value in data.get("items", {}).items()}
                start, _ = billing_cycle(datetime.now(JST).date())
                for key in (f"savings_plan:{start.isoformat()}", "savings_plan:monthly_template"):
                    db.set_setting(key, json.dumps({"items": items}, ensure_ascii=False))
                if data.get("goal") is not None:
                    db.set_setting("savings_goal_jpy", str(to_minor_allow_zero(str(data["goal"]), "JPY", 0)))
            elif action == "food_preference":
                db.set_setting("food_review_purchases_count_as_eaten", "1" if data["enabled"] else "0")
            else:
                raise LedgerError("不支持此操作。")
        finally:
            db.close()
        self.after_write(uid)
        return result

    @staticmethod
    def _confirmed(data):
        if data.get("confirmed") is not True:
            raise LedgerError("请确认此操作后重试。")

    def _save_settings(self, uid, data):
        if any(key[0] == uid for key in self.locks):
            raise LedgerError("请先等待当前 Agent 请求完成。")
        cfg = self.config(uid)
        current = {p["id"]: p for p in cfg["profiles"]}
        profiles = data.get("profiles", [])
        if not isinstance(profiles, list) or len(profiles) > 20:
            raise LedgerError("API 服务数量无效。")
        clean = []
        for profile in profiles:
            profile = dict(profile)
            profile["id"] = str(profile.get("id") or uuid.uuid4().hex)
            endpoint = str(profile.get("api_url", "")).strip()
            self._check_endpoint(endpoint)
            if not str(profile.get("name", "")).strip() or not str(profile.get("model", "")).strip():
                raise LedgerError("API 服务名称和模型不能为空。")
            if not profile.get("api_key") and not profile.get("clearKey"):
                profile["api_key"] = current.get(profile["id"], {}).get("api_key", "")
            profile.pop("keyPresent", None)
            profile.pop("clearKey", None)
            clean.append(profile)
        ids = {p["id"] for p in clean}
        for group in ("agents", "visionAgents"):
            mapping = data.get(group, cfg[group])
            if any(value and value not in ids for value in mapping.values()):
                raise LedgerError("Agent 所选服务已不存在。")
            cfg[group] = mapping
        cfg["profiles"] = clean
        cfg["scope"] = normalize_backup_scope(data.get("scope", cfg["scope"]))
        if not any(cfg["scope"].values()):
            raise LedgerError("至少选择一项备份内容。")
        cfg["autoSync"] = bool(data.get("autoSync", cfg["autoSync"]))
        cfg["saveImages"] = bool(data.get("saveImages", cfg["saveImages"]))
        for agent in ("bookkeeping", "food_health"):
            if self.conversations.get((uid, agent), {}).get("pending"):
                raise LedgerError("请先完成或取消当前记账，再更改设置。")
        skills = data.get("skills", {})
        if not isinstance(skills, dict) or any(not isinstance(content, str) or len(content.encode()) > 256 * 1024 for content in skills.values()):
            raise LedgerError("Skill 文本无效或超过256KB。")
        for agent, store_key in (("bookkeeping", "bookkeeping_skill_store"), ("food_health", "food_skill_store")):
            if agent in skills:
                content = str(skills[agent])
                if len(content.encode()) > 256 * 1024:
                    raise LedgerError("Skill 超过256KB。")
                store = self.stores(uid)[store_key]
                if content.strip():
                    target = self.folder(uid) / f"{agent}.md"
                    atomic(target, content.encode())
                    store.save_path(target)
                else:
                    store.clear()
        self.save_config(uid, cfg)
        self.conversations.pop((uid, "bookkeeping"), None)
        self.conversations.pop((uid, "food_health"), None)
        return {"message": "设置已应用。"}

    def _check_endpoint(self, endpoint):
        parts = urlsplit(endpoint)
        if parts.username or parts.password or not parts.hostname or parts.fragment:
            raise LedgerError("模型接口地址无效。")
        allow_local = os.environ.get("HOUSEHOLD_WEB_ALLOW_LOCAL_API") == "1"
        if parts.scheme != "https" and not (
            allow_local and parts.scheme == "http" and parts.hostname in {"localhost", "127.0.0.1", "::1"}
        ):
            raise LedgerError("模型接口必须使用 HTTPS；本机模型需管理员开启本机接口。")
        try:
            addresses = socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80))
        except OSError as exc:
            raise LedgerError("无法解析模型接口地址。") from exc
        for address in addresses:
            ip = ipaddress.ip_address(address[4][0])
            if not ip.is_global and not (allow_local and ip.is_loopback):
                raise LedgerError("模型接口不能指向内网或系统元数据地址。")

    def _remote(self, uid, action, data, job):
        if action == 'startup_pull':
            if data.get('pendingOutbox'):
                raise LedgerError('手机有离线待同步记录，已暂停自动下载；请先完成同步。')
            return self._startup_pull(uid, cancelled=job.get('cancel'))
        if action == "agent":
            return self._agent(uid, data, job)
        provider = data.get("provider", "github")
        if provider not in {"github", "gitee"}:
            raise LedgerError("备份服务无效。")
        if action == "github_auth":
            with self.lock(uid):
                PullState(self.folder(uid) / 'cloud_pull_state.json').pause_downloads(choice_pending=True)
            challenge = request_device_code(GITHUB_APP_CLIENT_ID)
            job["result"] = {"userCode": challenge["user_code"], "verificationUri": challenge["verification_uri"],
                             "installUrl": GITHUB_APP_INSTALL_URL}
            job["message"] = "请在 GitHub 输入授权码并确认，再返回此页面。"
            tokens = poll_device_token(GITHUB_APP_CLIENT_ID, challenge["device_code"],
                                       challenge["interval"], challenge["expires_in"], job["cancel"].is_set)
            token, refresh = tokens["access_token"], tokens.get("refresh_token", "")
            client = GitHubClient(token, refresh_token=refresh, client_id=GITHUB_APP_CLIENT_ID)
        else:
            with self.lock(uid):
                cfg = self.config(uid)
                cloud = cfg["cloud"].get(provider, {})
            token = str(data.get("token") or cloud.get("token", ""))
            refresh = cloud.get("refresh_token", "")
            client = GitHubClient(token, refresh_token=refresh) if provider == "github" else GiteeClient(token)
        with self.lock(uid):
            cfg = self.config(uid)
            cloud = cfg["cloud"].get(provider, {})
        if action in {"github_auth", "cloud_connect"}:
            identity = client.current_user()
            name = str(data.get("repositoryName") or cloud.get("repositoryName") or "household-bookkeeping-data")
            if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", name):
                raise LedgerError("仓库名无效。")
            repository, created = client.ensure_private_repository(identity["login"], name)
            # Connecting never uploads over an existing snapshot.
            sha = client.bundle_sha(repository)
            with self.lock(uid):
                cfg = self.config(uid)
                cfg["cloud"][provider] = {"token": client.token, "refresh_token": getattr(client, "refresh_token", ""),
                    "repositoryName": name, "repository": repository, "lastSha": None, "cloudSha": sha}
                self.save_config(uid, cfg)
            return {"message": "已连接。请选择上传或恢复现有备份。" if sha else "已连接，可以上传备份。",
                    "repository": repository, "hasBackup": bool(sha)}
        repository = cloud.get("repository")
        if not repository:
            raise LedgerError("请先连接备份服务。")
        if action == "cloud_restore":
            self._confirmed(data)
            with self.lock(uid):
                version = self.generations.get(uid, 0)
            body, sha = client.download_bundle_with_revision(repository)
            with self.lock(uid):
                if self.generations.get(uid, 0) != version:
                    raise LedgerError("下载期间本地数据已更新，请重新恢复，避免覆盖刚保存的记录。")
                result = self.restore(uid, body, provider)
                sync_revision = local_revision(self.db_path(uid), **self.stores(uid))
                PullState(self.folder(uid) / 'cloud_pull_state.json').resume_downloads()
        else:
            if not data.get("automatic"):
                self._confirmed(data)
            with self.lock(uid):
                sync_revision = local_revision(self.db_path(uid), **self.stores(uid))
                name, body = self.backup(uid, "upload")
            if provider == "gitee" and len(body) > MAX_GITEE_SYNC_BUNDLE_BYTES:
                raise LedgerError("备份包超过 Gitee 容量限制。")
            expected = cloud.get("lastSha") if data.get("automatic") else client.bundle_sha(repository)
            sha = client.upload_bundle(repository, body, expected_sha=expected)
            result = {"message": "上传完成。", "backup": name}
        with self.lock(uid):
            cfg = self.config(uid)
            if cfg["cloud"].get(provider, {}).get("repository") == repository:
                cfg["cloud"][provider].update(lastSha=sha, token=client.token,
                                               refresh_token=getattr(client, "refresh_token", ""))
                self.save_config(uid, cfg)
                PullState(self.folder(uid) / 'cloud_pull_state.json').synced(provider, repository, sha, sync_revision)
        return result

    def _startup_pull(self, uid, cancelled=None):
        with self.guard:
            if uid in self.pulling:
                raise LedgerError('此账号正在下载最新云端账本，请稍后再试。')
            if any(key[0] == uid for key in self.locks):
                raise LedgerError('Agent 正在处理请求，已暂停自动下载，请稍后重试。')
            self.pulling.add(uid)
        candidates = []
        try:
            with self.lock(uid):
                cfg = self.config(uid)
            for provider, cloud in cfg['cloud'].items():
                if provider not in {'github', 'gitee'} or not cloud.get('token') or not cloud.get('repository'):
                    continue
                repository = cloud['repository']
                client = (GitHubClient(cloud['token'], refresh_token=cloud.get('refresh_token', ''), client_id=GITHUB_APP_CLIENT_ID)
                          if provider == 'github' else GiteeClient(cloud['token']))
                def save(sha, provider=provider, repository=repository, client=client):
                    current = self.config(uid)
                    selected = current['cloud'].get(provider, {})
                    if selected.get('repository') != repository:
                        raise LedgerError('下载期间云端连接已改变，请重试。')
                    selected.update(lastSha=sha, token=client.token, refresh_token=getattr(client, 'refresh_token', ''))
                    self.save_config(uid, current)
                candidates.append((provider, repository, client, save))
            result = automatic_pull(self.db_path(uid), candidates,
                PullState(self.folder(uid) / 'cloud_pull_state.json'),
                lambda body, provider: self.restore(uid, body, provider)['backup'],
                stores=self.stores(uid), lock=self.lock(uid),
                cancelled=lambda: self.stop_event.is_set() or (cancelled is not None and cancelled.is_set()))
            self.auto_status[uid] = ('已自动下载最新云端账本，恢复前已备份本机数据。' if result['restored'] else
                                     '当前已是最新云端账本。' if result['status'] == 'current' else '')
            return result
        finally:
            # A GitHub refresh token may rotate during a read, even when the
            # later restore is paused by a local conflict. Keep it encrypted.
            try:
                with self.lock(uid):
                    current = self.config(uid)
                    for provider, repository, client, _ in candidates:
                        selected = current['cloud'].get(provider, {})
                        if selected.get('repository') == repository:
                            selected.update(token=client.token, refresh_token=getattr(client, 'refresh_token', ''))
                    if candidates:
                        self.save_config(uid, current)
            finally:
                with self.guard:
                    self.pulling.discard(uid)

    def _agent(self, uid, data, job):
        agent = data.get("agent", "bookkeeping")
        if agent not in {"bookkeeping", "food_health"}:
            raise LedgerError("Agent 无效。")
        key = (uid, agent)
        with self.guard:
            if key in self.locks:
                raise LedgerError("此 Agent 正在处理上一条请求。")
            self.locks[key] = True
        process = None
        receive = send = None
        try:
            cfg = self.config(uid)
            state = self.conversations.get(key, {})
            generation = self.generations.get(uid, 0)
            use_vision = bool(data.get("images"))
            profile_id = state.get("profileId") if state.get("pending") else (
                cfg["visionAgents" if use_vision else "agents"].get(agent)
            )
            profile = next((p for p in cfg["profiles"] if p["id"] == profile_id), None)
            if not profile:
                raise LedgerError("请先在设置中配置并分配 Agent 的 API 服务。")
            self._check_endpoint(profile["api_url"])
            stores = self.stores(uid)
            loaded = stores["bookkeeping_skill_store" if agent == "bookkeeping" else "food_skill_store"].load()
            hints = stores["payment_store"].load().get("profiles", [])
            with tempfile.TemporaryDirectory(prefix="ledger-mobile-agent-") as temp:
                directory = Path(temp)
                images = []
                incoming = data.get("images", [])
                if not isinstance(incoming, list) or len(incoming) > 5:
                    raise LedgerError("最多上传5张图片。")
                for index, image in enumerate(incoming):
                    raw = base64.b64decode(image["data"], validate=True)
                    if len(raw) > 10 * 1024 * 1024:
                        raise LedgerError("单张图片超过10MB。")
                    suffix = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}.get(image.get("type"))
                    if not suffix:
                        raise LedgerError("请使用 JPEG、PNG 或 WebP 图片。")
                    file = directory / f"image-{index}{suffix}"
                    file.write_bytes(raw)
                    images.append(load_image_attachment(file))
                context = multiprocessing.get_context("spawn")
                receive, send = context.Pipe(duplex=False)
                config = {**profile, "timeout": 600 if "127.0.0.1" in profile["api_url"] else 300}
                process = context.Process(target=run_isolated_request, args=(
                    str(self.db_path(uid)), str(directory / "baseline.sqlite3"), str(directory / "candidate.sqlite3"),
                    config, str(data.get("text", ""))[:24000], state.get("history", []),
                    state.get("pending"), hints, loaded["content"] if loaded else "", images, agent,
                    data.get("language", "zh-CN"), send), daemon=True)
                process.start()
                send.close()
                deadline = time.monotonic() + config["timeout"] + 60
                while not receive.poll(0.15):
                    if job["cancel"].is_set() or time.monotonic() > deadline:
                        process.terminate()
                        process.join(5)
                        if process.is_alive():
                            process.kill()
                            process.join()
                        raise LedgerError("请求已中断，本次结果未写入账本。")
                    if not process.is_alive():
                        raise LedgerError("处理进程已退出，本次结果未写入账本。")
                message = receive.recv()
                process.join(5)
                if job["cancel"].is_set():
                    raise LedgerError("请求已中断，本次结果未写入账本。")
                status, answer, history, pending, usage = message
                if status != "ok":
                    raise LedgerError(answer)
                with self.lock(uid):
                    if self.generations.get(uid, 0) != generation:
                        raise LedgerError("请求期间账本已更新，本次 Agent 结果没有写入。")
                    changed = merge_isolated_database(
                        self.db_path(uid), directory / "baseline.sqlite3", directory / "candidate.sqlite3")
                    receipt_images = images or state.get("receiptImages", [])
                    self.conversations[key] = {"history": history, "pending": pending,
                                               "profileId": profile_id,
                                               "receiptImages": receipt_images if pending else []}
                    if changed and agent == "bookkeeping" and cfg["saveImages"]:
                        from .receipt_images import archive_receipt_image
                        for attachment in receipt_images:
                            archive_receipt_image(attachment, stores["receipt_image_directory"])
                if changed:
                    self.after_write(uid)
                return {"answer": answer, "pending": pending is not None, "transactionIds": changed,
                        "usage": usage, "agent": agent}
        finally:
            if process is not None and process.is_alive():
                process.terminate()
                process.join(5)
            if receive:
                receive.close()
            if send:
                send.close()
            with self.guard:
                self.locks.pop(key, None)

    def after_write(self, uid):
        self.generations[uid] = self.generations.get(uid, 0) + 1
        try:
            self.backup(uid, "automatic", full=True)
            folder = self.folder(uid) / "backups"
            for old in sorted(folder.glob("automatic-*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)[50:]:
                old.unlink()
        except Exception:
            self.auto_status[uid] = "记账已保存，但自动本地备份失败，请手动备份。"
        cfg = self.config(uid)
        if not cfg["autoSync"] or not cfg["cloud"]:
            return
        with self.guard:
            self.auto_pending.add(uid)
            if uid in self.auto_running:
                return
            self.auto_running.add(uid)
        threading.Thread(target=self._auto_upload, args=(uid,), daemon=True).start()

    def _auto_upload(self, uid):
        try:
            while True:
                with self.guard:
                    if uid not in self.auto_pending:
                        break
                    self.auto_pending.discard(uid)
                cfg = self.config(uid)
                for provider, cloud in cfg["cloud"].items():
                    if not cloud.get("token"):
                        continue
                    try:
                        self._remote(uid, "cloud_upload", {"provider": provider, "automatic": True}, {})
                        self.auto_status[uid] = f"{provider.title()} 自动备份完成。"
                    except Exception:
                        self.auto_status[uid] = f"{provider.title()} 自动备份未完成，请检查网络、授权或云端版本。账目已保存。"
        finally:
            with self.guard:
                self.auto_running.discard(uid)

    def _scheduled_entries(self):
        while not self.stop_event.wait(60):
            for file in self.server.ledger_dir.glob("*.sqlite3"):
                uid = file.stem
                if not re.fullmatch(r"[a-f0-9-]{32,36}", uid):
                    continue
                try:
                    with self.lock(uid):
                        if uid in self.pulling or any(key[0] == uid for key in self.locks):
                            continue
                        db = Database(file)
                        try:
                            db.initialize()
                            credit = process_due_credit_repayments(db, today())
                            recurring = process_due_recurring_transactions(db, today())
                        finally:
                            db.close()
                    if any(row.get("transaction_id") for row in credit + recurring):
                        self.after_write(uid)
                except Exception:
                    self.auto_status[uid] = "到期项目未能自动记账，请在定期付款中检查。"
