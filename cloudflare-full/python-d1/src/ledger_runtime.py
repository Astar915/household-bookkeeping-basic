"""Ephemeral SQLite workspace backed by durable D1 snapshots.

The existing ledger domain model remains the source of accounting rules. Each
request restores one user's files to the Worker memory filesystem, opens the
same SQLite schema, then commits a checksummed snapshot to D1 before returning.
No process-local file is treated as durable state.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import uuid
import zipfile
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from d1_snapshot_store import D1SnapshotStore, SnapshotConflict, SnapshotError
from ledger_row_deltas import apply_changes, clear_change_log, read_pending_changes
from secret_crypto import decrypt_text, encrypt_text
from bookkeeping.web_features import MobileWorkspace


WEB_SYNC_SCHEMA = """
CREATE TABLE IF NOT EXISTS web_sync_operations (
    operation_id TEXT PRIMARY KEY,
    payload_hash TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL
)
"""

MAX_LEDGER_DELTA_ROWS = 2000
MAX_LEDGER_DELTA_BYTES = 2 * 1024 * 1024


def _ledger_schema_hash(connection: sqlite3.Connection) -> str:
    """Hash the initialized schema, including migrations outside SCHEMA_SQL."""
    schema = connection.execute(
        "SELECT type,name,tbl_name,sql FROM main.sqlite_master "
        "WHERE type IN ('table','index','trigger','view') AND name NOT LIKE 'sqlite_%' "
        "ORDER BY type,name"
    ).fetchall()
    encoded = json.dumps(
        [tuple(row) for row in schema], ensure_ascii=False, separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _enable_worker_row_tracking() -> None:
    """Instrument only the isolated Worker copy of Database at runtime."""
    from bookkeeping.storage import Database
    if getattr(Database, "_d1_row_tracking", False):
        return
    original_constructor = Database.__init__
    original_initialize = Database.initialize
    original_close = Database.close

    def construct(instance, *args, **kwargs):
        result = original_constructor(instance, *args, **kwargs)
        from ledger_row_deltas import install_change_tracking
        install_change_tracking(instance.connection)
        return result

    def initialize(instance, *args, **kwargs):
        result = original_initialize(instance, *args, **kwargs)
        from ledger_row_deltas import install_change_tracking
        install_change_tracking(instance.connection)
        return result

    def close(instance):
        try:
            from ledger_row_deltas import capture_changes, write_pending_changes
            write_pending_changes(instance.path, capture_changes(instance.connection))
        finally:
            original_close(instance)

    Database.__init__ = construct
    Database.initialize = initialize
    Database.close = close
    Database._d1_row_tracking = True


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rows(result: Any) -> list[Any]:
    if isinstance(result, dict):
        return list(result.get("results", []) or [])
    return list(getattr(result, "results", []) or [])


def _field(row: Any, name: str) -> Any:
    return row[name] if isinstance(row, dict) else getattr(row, name)


def _default_config() -> dict[str, Any]:
    from bookkeeping.backup_scope import DEFAULT_BACKUP_SCOPE
    return {
        "profiles": [],
        "agents": {"bookkeeping": "", "food_health": ""},
        "visionAgents": {"bookkeeping": "", "food_health": ""},
        "scope": dict(DEFAULT_BACKUP_SCOPE),
        "billingCycleStartDay": 15,
        # Existing accounts predate the required first-run setup. New OAuth
        # accounts explicitly seed this as False during account creation.
        "onboardingCompleted": True,
        "onboardingStage": "complete",
        # GitHub/Gitee are optional export backups. D1 is the live cloud
        # ledger; external-provider uploads require an explicit opt-in.
        "autoSync": False,
        "saveImages": False,
        "cloud": {},
    }


async def load_mobile_config(database: Any, env: Any, user_id: str) -> dict[str, Any]:
    cfg = _default_config()
    row = await database.prepare(
        "SELECT encrypted_value FROM user_secrets WHERE user_id=? AND secret_name='mobile-config'"
    ).bind(user_id).first()
    if row is not None:
        saved = await decrypt_text(
            str(_field(row, "encrypted_value")), str(env.TOKEN_ENCRYPTION_KEY),
            "user:" + user_id + ":mobile-config",
        )
        decoded = json.loads(saved)
        if isinstance(decoded, dict):
            cfg.update(decoded)
            if int(cfg.get("autoSyncConsentVersion", 0) or 0) < 1:
                # Earlier releases treated the default as consent. Migrate
                # those accounts to the safe, opt-in behavior once.
                cfg["autoSync"] = False
                cfg["autoSyncConsentVersion"] = 1
    cfg.setdefault("profiles", [])
    cfg.setdefault("agents", {"bookkeeping": "", "food_health": ""})
    cfg.setdefault("visionAgents", dict(cfg["agents"]))
    cfg.setdefault("cloud", {})
    if not bool(cfg.get("onboardingCompleted", True)) and not cfg.get("onboardingStage"):
        cfg["onboardingStage"] = "base"
    try:
        cycle_start_day = int(cfg.get("billingCycleStartDay", 15))
    except (TypeError, ValueError):
        cycle_start_day = 15
    cfg["billingCycleStartDay"] = cycle_start_day if 1 <= cycle_start_day <= 31 else 15
    cfg["saveImages"] = False

    # GitHub sign-in grants the same account's private-repository sync token.
    # Keep it encrypted at rest and merge it into the existing mobile setting
    # shape expected by the full UI.
    sync_row = await database.prepare(
        "SELECT encrypted_value FROM user_secrets WHERE user_id=? AND secret_name='github-sync'"
    ).bind(user_id).first()
    if sync_row is not None:
        raw = await decrypt_text(
            str(_field(sync_row, "encrypted_value")), str(env.TOKEN_ENCRYPTION_KEY),
            "user:" + user_id + ":github-sync",
        )
        github = json.loads(raw)
        if isinstance(github, dict) and github.get("token"):
            current = cfg["cloud"].get("github", {})
            merged = {**github, **current}
            # The dedicated secret is updated by sign-in and token rotation.
            # Keep repository/checkpoint preferences, but never let stale
            # credentials embedded in mobile-config undo reauthorization.
            merged["token"] = github["token"]
            merged["refresh_token"] = str(github.get("refresh_token") or "")
            for field in ("client_id", "auth_flow"):
                if github.get(field):
                    merged[field] = github[field]
            cfg["cloud"]["github"] = merged
    return cfg


async def first_run_setup_required(database: Any, env: Any, user_id: str) -> bool:
    """Return whether this account must finish the required first-run setup."""
    config = await load_mobile_config(database, env, user_id)
    return not bool(config.get("onboardingCompleted", True))


class WorkerPaymentPromptStore:
    """File-compatible payment-rule store without OS locks or fcntl."""

    def __init__(self, path: Path):
        from bookkeeping.payment_preferences import PaymentPromptStore
        self.path = path
        self.backup_path = path.with_suffix(path.suffix + ".bak")
        self._store_type = PaymentPromptStore

    @staticmethod
    def _digest(payload: bytes | None) -> str:
        return hashlib.sha256(payload if payload is not None else b"<missing-payment-settings>").hexdigest()

    def load_snapshot(self):
        choices = []
        errors = []
        for path in (self.path, self.backup_path):
            if not path.is_file():
                continue
            try:
                payload = path.read_bytes()
                value = self._store_type._parse_settings(json.loads(payload.decode("utf-8")))
                saved = json.loads(payload.decode("utf-8"))
                revision = saved.get("revision")
                choices.append((int(revision or 0), path, value, payload))
            except Exception as exc:
                errors.append(exc)
        if not choices:
            if errors:
                raise ValueError("支付规则和备份都无法读取，请重新保存支付规则。") from errors[-1]
            return {"profiles": [], "default_index": None}, self._digest(None)
        _revision, source, value, payload = max(choices, key=lambda item: item[0])
        if source != self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_bytes(payload)
        return value, self._digest(payload)

    def load(self):
        return self.load_snapshot()[0]

    def save_profiles(self, profiles, *, expected_revision=None):
        current, revision = self.load_snapshot()
        if expected_revision is not None and expected_revision != revision:
            raise ValueError("支付规则已在其他设备修改，请刷新后再保存。")
        cleaned = []
        for profile in profiles:
            row = {"payment_method": str(profile.get("payment_method", "")).strip(),
                   "purpose": str(profile.get("purpose", "")).strip()}
            if "currency" in profile:
                currency = str(profile.get("currency") or "").strip().upper()
                row["currency"] = "" if currency in {"不限", "ANY", "ALL"} else currency
            if "account_order" in profile:
                row["account_order"] = list(profile["account_order"])
            if not row["payment_method"]:
                raise ValueError("每种支付方式都要填写名称。")
            cleaned.append(row)
        previous_revision = 0
        for candidate in (self.path, self.backup_path):
            try:
                previous_revision = max(previous_revision, int(json.loads(candidate.read_text("utf-8")).get("revision", 0)))
            except Exception:
                pass
        body = json.dumps({"version": 2, "revision": previous_revision + 1,
                           "profiles": cleaned, "default_index": current.get("default_index")},
                          ensure_ascii=False, indent=2).encode("utf-8")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.is_file():
            shutil.copyfile(self.path, self.backup_path)
        self._store_type._write_bytes_atomically(self.path, body)
        return self._digest(body)


class WorkerMobileWorkspace(MobileWorkspace):
    """Runtime facade over the existing mobile feature and ledger modules."""

    def __init__(self, root: Path, user_id: str, config: dict[str, Any], conversations: dict[str, dict[str, Any]]):
        self.server = type("WorkerServer", (), {})()
        self.server.data_dir = root
        self.server.ledger_dir = root / "ledgers"
        self.server.ledger_dir.mkdir(parents=True, exist_ok=True)
        self.root = root / "mobile"
        self.root.mkdir(parents=True, exist_ok=True)
        self._config = copy.deepcopy(config)
        self._config_dirty = False
        self._uid = user_id
        self.jobs = {}
        self.guard = None
        self.locks = {}
        self.conversations = {(user_id, agent): copy.deepcopy(value) for agent, value in conversations.items()}
        self.generations = {user_id: 0}
        self.auto_status = {}
        self.pending_ledger_changes: list[dict[str, Any]] = []
        self.ledger_replaced = False
        self._default_skill_root = Path(__file__).resolve().parent / "bookkeeping" / "web_defaults"
        self._mobile_base = self.root / user_id
        self._mobile_base.mkdir(parents=True, exist_ok=True)

    def lock(self, _uid):
        return nullcontext()

    def folder(self, uid):
        if uid != self._uid:
            raise ValueError("账号隔离校验失败。")
        path = self.root / uid
        path.mkdir(parents=True, exist_ok=True)
        return path

    def db_path(self, uid):
        if uid != self._uid:
            raise ValueError("账号隔离校验失败。")
        return self.server.ledger_dir / f"{uid}.sqlite3"

    @staticmethod
    def receipt_image_archive_enabled():
        return False

    def config(self, uid):
        if uid != self._uid:
            raise ValueError("账号隔离校验失败。")
        return copy.deepcopy(self._config)

    def save_config(self, uid, value):
        if uid != self._uid:
            raise ValueError("账号隔离校验失败。")
        self._config = copy.deepcopy(value)
        self._config["saveImages"] = False
        self._config_dirty = True

    def stores(self, uid):
        from bookkeeping.skill_settings import BookkeepingSkillStore
        folder = self.folder(uid)
        defaults = self._default_skill_root
        return {
            "payment_store": WorkerPaymentPromptStore(folder / "payment_prompts.json"),
            "bookkeeping_skill_store": BookkeepingSkillStore(
                folder / "bookkeeping_skill.json", default_path=defaults / "bookkeeping.md",
                managed_paths=(folder / "restored_skills" / "bookkeeping.md", folder / "bookkeeping.md")),
            "food_skill_store": BookkeepingSkillStore(
                folder / "food_skill.json", default_path=defaults / "food-health.md",
                managed_paths=(folder / "restored_skills" / "food_health.md", folder / "food_health.md")),
            "receipt_image_directory": folder / "receipt_images",
        }

    def after_write(self, uid):
        self.generations[uid] = self.generations.get(uid, 0) + 1
        self.pending_ledger_changes.extend(read_pending_changes(Path(str(self.db_path(uid)))))
        try:
            folder = self.folder(uid) / "backups"
            from bookkeeping.web_features import today
            day_stamp = today().replace("-", "")
            if not any(folder.glob(f"automatic-{day_stamp}-*.zip")):
                self.backup(uid, "automatic", full=True)
            for old in sorted(folder.glob("automatic-*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)[50:]:
                old.unlink(missing_ok=True)
        except Exception:
            self.auto_status[uid] = "记账已保存，但自动备份失败，请手动备份。"

    def public_settings(self, uid):
        value = super().public_settings(uid)
        value["autoStatus"] = str(self.config(uid).get("autoStatus", ""))
        value["onboardingRequired"] = not bool(self.config(uid).get("onboardingCompleted", True))
        value.pop("onboardingCompleted", None)
        return value

    def _check_endpoint(self, endpoint):
        from urllib.parse import urlsplit
        import ipaddress
        parts = urlsplit(str(endpoint).strip())
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.fragment:
            raise ValueError("模型接口必须是有效的 HTTPS 地址。")
        host = parts.hostname.rstrip(".").casefold()
        if host in {"localhost", "metadata.google.internal", "instance-data"}:
            raise ValueError("模型接口不能指向本机或云平台内部地址。")
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address is not None and not address.is_global:
            raise ValueError("模型接口不能指向内网或系统元数据地址。")

    def _agent(self, uid, data, _job=None):
        """Run the existing Agent logic in a disposable SQLite candidate.

        The synchronous domain session is replayed from its original snapshot
        whenever it reaches a model call. ReplayOpener supplies prior durable
        responses and raises ModelRequestRequired for the next async fetch.
        Nothing reaches the D1 snapshot until the full turn succeeds.
        """
        import base64
        from bookkeeping.natural_language import load_image_attachment
        from bookkeeping.request_worker import run_isolated_request_result, merge_isolated_database
        from bookkeeping.storage import LedgerError
        from model_jobs import ReplayOpener

        agent = str(data.get("agent", "bookkeeping"))
        if agent not in {"bookkeeping", "food_health"}:
            raise LedgerError("Agent 无效。")
        key = (uid, agent)
        config = self.config(uid)
        state = self.conversations.get(key, {})
        incoming = data.get("images", [])
        if not isinstance(incoming, list) or len(incoming) > 5:
            raise LedgerError("最多上传5张图片。")
        use_vision = bool(incoming)
        profile_id = state.get("profileId") if state.get("pending") else (
            config["visionAgents" if use_vision else "agents"].get(agent)
        )
        profile = next((item for item in config["profiles"] if item["id"] == profile_id), None)
        if not profile:
            raise LedgerError("请先在设置中配置并分配 Agent 的 API 服务。")
        self._check_endpoint(profile.get("api_url", ""))

        stores = self.stores(uid)
        skill_store = stores["bookkeeping_skill_store" if agent == "bookkeeping" else "food_skill_store"]
        loaded = skill_store.load()
        hints = stores["payment_store"].load().get("profiles", [])
        expected_revision = getattr(self, "_provider_expected_revision", None)
        if not expected_revision:
            raise LedgerError("云端请求缺少账本版本校验；本次操作未写入。")
        replay = getattr(self, "_provider_replies", [])

        with tempfile.TemporaryDirectory(prefix="ledger-worker-agent-") as temp:
            directory = Path(temp)
            prepared_images = []
            for index, item in enumerate(incoming):
                if not isinstance(item, dict):
                    raise LedgerError("图片附件格式无效，请重新选择图片。")
                try:
                    raw = base64.b64decode(str(item.get("data", "")), validate=True)
                except (ValueError, TypeError):
                    raise LedgerError("图片附件格式无效，请重新选择图片。") from None
                if not raw or len(raw) > 10 * 1024 * 1024:
                    raise LedgerError("单张图片为空或超过10MB。")
                media_type = str(item.get("type", "")).lower()
                suffix = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}.get(media_type)
                if suffix is None:
                    raise LedgerError("请使用 JPEG、PNG 或 WebP 图片。")
                path = directory / f"image-{index}{suffix}"
                path.write_bytes(raw)
                prepared_images.append(load_image_attachment(path, cloud_fast_path=True))

            baseline = directory / "baseline.sqlite3"
            candidate = directory / "candidate.sqlite3"
            client_config = {
                **profile,
                "timeout": 300,
                "thinking_enabled": profile.get("thinking_enabled", False),
                "reasoning_effort": profile.get("reasoning_effort", "low"),
                # This migration target is exercised with the local inline
                # Workflow switch. Show only sanitized file/line diagnostics
                # in that local mode so failures can be fixed without exposing
                # internal source locations in a later deployed Worker.
                "show_diagnostic_locations": str(
                    getattr(getattr(self, "_env", None), "WORKFLOW_LOCAL_INLINE", "")
                ) == "1",
            }
            opener = ReplayOpener(replay, expected_revision)
            status, answer, history, pending, usage = run_isolated_request_result(
                str(self.db_path(uid)), str(baseline), str(candidate), client_config,
                str(data.get("text", ""))[:24000], state.get("history", []),
                state.get("pending"), hints, loaded["content"] if loaded else "",
                prepared_images, agent, data.get("language", "zh-CN"), opener=opener,
                request_now=(_job or {}).get("request_now"),
            )
            if status != "ok":
                raise LedgerError(answer)

            # Verify the D1 snapshot has not changed while the external model
            # was responding. The caller performs this check before each replay;
            # the snapshot commit repeats it atomically as the final guard.
            from ledger_row_deltas import capture_changes, install_change_tracking, write_pending_changes

            live_path = self.db_path(uid)

            def persist_agent_row_changes(connection):
                try:
                    write_pending_changes(Path(str(live_path)), capture_changes(connection))
                except Exception:
                    # The caller detects a changed SQLite file without row
                    # deltas and safely falls back to a new base snapshot.
                    pass

            changed = merge_isolated_database(
                live_path, baseline, candidate,
                prepare_live_connection=install_change_tracking,
                after_live_commit=persist_agent_row_changes,
            )
            # ImageAttachment objects are request-scoped and intentionally not
            # archived in the cloud. Keep only text in durable chat history so
            # serializing the conversation to D1 never receives image objects.
            response_language = str(data.get("language", "zh-CN"))
            image_history_note = {
                "ja-JP": "（画像の内容はクラウドに保存していません）",
                "en-US": "(Image content was not saved in the cloud)",
            }.get(response_language, "（附图内容未保存在云端）")
            persisted_history = []
            for message in history:
                if not isinstance(message, dict):
                    continue
                saved_message = {
                    name: value for name, value in message.items() if name != "images"
                }
                if message.get("images"):
                    prior_text = str(saved_message.get("content") or "").strip()
                    saved_message["content"] = "\n".join(
                        part for part in (prior_text, image_history_note) if part
                    )
                persisted_history.append(saved_message)
            self.conversations[key] = {
                "history": persisted_history,
                "pending": pending,
                "profileId": profile_id,
                # Cloud mode intentionally does not archive receipt images.
                "receiptImages": [],
            }
            if changed and not ((_job or {}).get("defer_write")):
                self.after_write(uid)
            return {
                "answer": answer,
                "pending": pending is not None,
                "transactionIds": changed,
                "usage": usage,
                "agent": agent,
            }

    def _cloud_remote(self, uid, action, data):
        """Replay the existing private GitHub/Gitee backup behavior via fetch."""
        import re
        from model_jobs import ModelRequestRequired
        from bookkeeping.cloud_pull import CloudPullConflict, PullState, automatic_pull, local_revision
        from bookkeeping.github_sync import (
            GITHUB_APP_CLIENT_ID, GitHubClient, GitHubSyncConflict,
            sync_bundle_created_at,
        )
        from bookkeeping.gitee_sync import (
            GiteeClient, GiteeSyncConflict, MAX_GITEE_SYNC_BUNDLE_BYTES,
        )
        from bookkeeping.storage import LedgerError

        provider = "github" if action == "github_auth" else str(data.get("provider", "github")).lower()
        if provider not in {"github", "gitee"}:
            raise LedgerError("备份服务无效。")
        config = self.config(uid)
        saved = config.get("cloud", {}).get(provider, {})
        opener = getattr(self, "_provider_opener", None)

        if action == "cloud_auto_sync":
            outcomes = []
            for selected_provider, cloud in list(config.get("cloud", {}).items()):
                if selected_provider not in {"github", "gitee"} or not cloud.get("token"):
                    continue
                try:
                    outcome = self._cloud_remote(
                        uid, "cloud_upload", {"provider": selected_provider, "automatic": True},
                    )
                    outcomes.append((selected_provider, True, outcome.get("message", "上传完成。")))
                except ModelRequestRequired:
                    raise
                except Exception:
                    outcomes.append((selected_provider, False, "自动备份未完成，请检查网络、授权或云端版本。账目已保存。"))
            updated = self.config(uid)
            successful = sum(1 for _provider, ok, _message in outcomes if ok)
            failed = sum(1 for _provider, ok, _message in outcomes if not ok)
            if not outcomes:
                status = "未连接云端备份服务。"
            elif failed and successful:
                status = "部分云端自动备份未完成，请检查连接状态。账目已保存。"
            elif failed:
                status = "云端自动备份未完成，请检查网络、授权或云端版本。账目已保存。"
            else:
                status = "云端自动备份完成。"
            updated["autoStatus"] = status
            self.save_config(uid, updated)
            return {"message": status, "providers": outcomes}

        def make_client(selected_provider, cloud, supplied_token=""):
            token = str(supplied_token or cloud.get("token", ""))
            if selected_provider == "github":
                return GitHubClient(
                    token,
                    refresh_token=str(cloud.get("refresh_token", "")),
                    client_id=str(cloud.get("client_id") or GITHUB_APP_CLIENT_ID),
                    opener=opener,
                )
            return GiteeClient(token, opener=opener)

        if action in {"github_auth", "cloud_connect"}:
            token = data.get("token", "") if provider == "gitee" else ""
            client = make_client(provider, saved, token)
            identity = client.current_user()
            name = str(data.get("repositoryName") or saved.get("repositoryName") or "household-bookkeeping-data")
            if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", name):
                raise LedgerError("仓库名无效。")
            repository, _created = client.ensure_private_repository(str(identity.get("login", "")), name)
            sha = client.bundle_sha(repository)
            config.setdefault("cloud", {})[provider] = {
                "token": client.token,
                "refresh_token": getattr(client, "refresh_token", ""),
                "repositoryName": name,
                "repository": repository,
                "lastSha": None,
                "cloudSha": sha,
            }
            self.save_config(uid, config)
            if action == "github_auth":
                PullState(self.folder(uid) / "cloud_pull_state.json").pause_downloads(choice_pending=True)
            return {
                "message": "已连接。请选择上传或恢复现有备份。" if sha else "已连接，可以上传备份。",
                "repository": repository,
                "hasBackup": bool(sha),
            }

        if action == "startup_pull":
            if data.get("pendingOutbox"):
                raise LedgerError("手机有离线待同步记录，已暂停自动下载；请先完成同步。")
            current_config = self.config(uid)
            candidates = []
            clients = {}
            for selected_provider, cloud in current_config.get("cloud", {}).items():
                if selected_provider not in {"github", "gitee"} or not cloud.get("token") or not cloud.get("repository"):
                    continue
                client = make_client(selected_provider, cloud)
                clients[selected_provider] = (cloud.get("repository"), client)

                def persist_remote(sha, selected_provider=selected_provider,
                                   repository=cloud.get("repository"), selected_client=client):
                    updated = self.config(uid)
                    selected = updated.get("cloud", {}).get(selected_provider, {})
                    if selected.get("repository") != repository:
                        raise LedgerError("下载期间云端连接已改变，请重试。")
                    selected.update(lastSha=sha, token=selected_client.token,
                                    refresh_token=getattr(selected_client, "refresh_token", ""))
                    self.save_config(uid, updated)

                candidates.append((selected_provider, cloud["repository"], client, persist_remote))
            try:
                result = automatic_pull(
                    self.db_path(uid), candidates,
                    PullState(self.folder(uid) / "cloud_pull_state.json"),
                    lambda body, source: self.restore(uid, body, source)["backup"],
                    stores=self.stores(uid), lock=self.lock(uid), cancelled=lambda: False,
                )
            except CloudPullConflict:
                # This is a source-selection decision, not a network failure.
                # Persist the pause so another sign-in cannot restore before
                # the user chooses to keep this ledger or restore GitHub.
                PullState(self.folder(uid) / "cloud_pull_state.json").pause_downloads(
                    choice_pending=True, reason="conflict",
                )
                result = {"status": "conflict", "reason": "conflict", "restored": False}
            finally:
                # Device-flow refresh tokens rotate. Persist them even when the
                # automatic pull sees an unchanged remote or safely pauses due
                # to a local edit/conflict.
                updated = self.config(uid)
                token_changed = False
                for selected_provider, (repository, client) in clients.items():
                    selected = updated.get("cloud", {}).get(selected_provider, {})
                    if selected.get("repository") != repository:
                        continue
                    token = str(client.token)
                    refresh_token = str(getattr(client, "refresh_token", ""))
                    if (selected.get("token") != token
                            or selected.get("refresh_token", "") != refresh_token):
                        selected.update(token=token, refresh_token=refresh_token)
                        token_changed = True
                if token_changed:
                    self.save_config(uid, updated)
            if result.get("restored"):
                self.auto_status[uid] = "已自动下载最新云端账本，恢复前已备份本机数据。"
            elif result.get("status") == "current":
                self.auto_status[uid] = "当前已是最新云端账本。"
            return result

        repository = str(saved.get("repository", ""))
        if not repository:
            raise LedgerError("请先连接备份服务。")
        client = make_client(provider, saved, data.get("token", "") if provider == "gitee" else "")
        if action == "cloud_restore":
            self._confirmed(data)
            body, sha = client.download_bundle_with_revision(repository)
            result = self.restore(uid, body, provider)
            sync_revision = local_revision(self.db_path(uid), **self.stores(uid))
            PullState(self.folder(uid) / "cloud_pull_state.json").resume_downloads()
        elif action == "cloud_upload":
            if not data.get("automatic"):
                self._confirmed(data)
            sync_revision = local_revision(self.db_path(uid), **self.stores(uid))
            name, body = self.backup(uid, "upload")
            if provider == "gitee" and len(body) > MAX_GITEE_SYNC_BUNDLE_BYTES:
                raise LedgerError("备份包超过 Gitee 容量限制。")
            if data.get("automatic"):
                # D1 is the live ledger. On return/write, the user asked for
                # this current web snapshot to be uploaded, so a stale
                # lastSha must not turn an ordinary background backup into a
                # restore/download prompt. The provider updates the existing
                # file as a new commit, retaining its previous versions in
                # repository history. Read the current file revision inside
                # upload_bundle and retry brief concurrent writes safely.
                conflict_types = (GitHubSyncConflict, GiteeSyncConflict)
                for attempt in range(3):
                    try:
                        sha = client.upload_bundle(repository, body)
                        break
                    except conflict_types as exc:
                        if attempt == 2:
                            raise LedgerError(
                                "云端文件正在被其他设备连续更新，本次自动备份稍后重试；网页版账本未被更改。"
                            ) from exc
            else:
                sha = client.upload_bundle(
                    repository, body, expected_sha=client.bundle_sha(repository),
                )
            result = {"message": "上传完成。", "backup": name}
        else:
            raise LedgerError("备份操作无效。")

        updated = self.config(uid)
        selected = updated.get("cloud", {}).get(provider, {})
        if selected.get("repository") != repository:
            raise LedgerError("操作期间云端连接已改变；本次设置没有覆盖新连接。")
        selected.update(lastSha=sha, token=client.token,
                        refresh_token=getattr(client, "refresh_token", ""))
        self.save_config(uid, updated)
        PullState(self.folder(uid) / "cloud_pull_state.json").synced(
            provider, repository, sha, sync_revision, sync_bundle_created_at(body),
        )
        return result

    def restore(self, uid, body: bytes, provider="github"):
        result = super().restore(uid, body, provider)
        # An imported SQLite image can lack the web-only schema. Normalize it
        # before calculating the pull checkpoint and mark it as a replacement,
        # so old D1 row deltas cannot be applied over the restored ledger.
        from bookkeeping.storage import Database
        db = Database(self.db_path(uid))
        try:
            db.initialize()
            db.connection.executescript(WEB_SYNC_SCHEMA)
            clear_change_log(db.connection)
        finally:
            db.close()
        read_pending_changes(self.db_path(uid))
        self.pending_ledger_changes.clear()
        self.ledger_replaced = True
        # Cloud archives deliberately do not retain receipt images.
        shutil.rmtree(self.folder(uid) / "receipt_images", ignore_errors=True)
        cfg = self.config(uid)
        cfg["saveImages"] = False
        self.save_config(uid, cfg)
        return result


class LedgerWorkspace:
    """One request's restored user state, with explicit D1 commit semantics."""

    def __init__(self, database: Any, user_id: str, root: Path, revision: str, files: dict[str, bytes],
                 store: D1SnapshotStore, current_schema_hash: str):
        self.database = database
        self.user_id = user_id
        self.root = root
        self.revision = revision
        self.files = files
        self.store = store
        self.ledger_rows_enabled = store.ledger_rows_enabled
        self.ledger_schema_hash = store.ledger_schema_hash
        self.ledger_row_deltas = store.ledger_row_deltas
        self.current_schema_hash = current_schema_hash
        self.ledger_rebase_needed = (
            self.ledger_rows_enabled and self.ledger_schema_hash != self.current_schema_hash
        )
        self.legacy_base_changed = False

    @classmethod
    async def open(cls, database: Any, user_id: str):
        store = D1SnapshotStore(database)
        revision, files = await store.load(user_id)
        root = Path(tempfile.mkdtemp(prefix="household-ledger-worker-"))
        for relative, body in files.items():
            target = root.joinpath(*relative.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
        ledger_dir = root / "ledgers"
        ledger_dir.mkdir(parents=True, exist_ok=True)
        ledger_path = ledger_dir / f"{user_id}.sqlite3"
        old_ledger_body = files.get(f"ledgers/{user_id}.sqlite3")
        _enable_worker_row_tracking()
        from bookkeeping.storage import Database
        db = Database(ledger_path)
        initialization_data_changes = False
        try:
            if store.ledger_rows_enabled and store.ledger_schema_hash != _ledger_schema_hash(db.connection):
                raise SnapshotError("云端账本基础文件与增量索引结构不匹配；本次操作已停止。")
            if store.ledger_rows_enabled and store.ledger_row_deltas:
                try:
                    apply_changes(db.connection, store.ledger_row_deltas)
                except Exception as exc:
                    raise SnapshotError("云端账本增量无法应用到当前 SQLite 结构；本次操作已停止。") from exc
            before_initialize_changes = db.connection.total_changes
            db.initialize()
            initialization_data_changes = db.connection.total_changes > before_initialize_changes
            db.connection.executescript(WEB_SYNC_SCHEMA)
            db.connection.commit()
            from ledger_row_deltas import install_change_tracking
            install_change_tracking(db.connection)
            clear_change_log(db.connection)
            current_schema_hash = _ledger_schema_hash(db.connection)
        finally:
            db.close()
        read_pending_changes(ledger_path)
        state = cls(database, user_id, root, revision, files, store, current_schema_hash)
        if store.ledger_rows_enabled and initialization_data_changes:
            # A data migration can change rows without changing sqlite_master.
            # Rebase those changes so they are not lost when this request ends.
            state.ledger_rebase_needed = True
        if not store.ledger_rows_enabled:
            current_ledger_body = ledger_path.read_bytes() if ledger_path.is_file() else None
            state.legacy_base_changed = old_ledger_body != current_ledger_body
        return state

    async def load_config(self, env):
        return await load_mobile_config(self.database, env, self.user_id)

    async def load_conversations(self):
        result = await self.database.prepare(
            "SELECT agent,conversation_json FROM agent_conversations WHERE user_id=?"
        ).bind(self.user_id).run()
        values = {}
        for row in _rows(result):
            agent = str(_field(row, "agent"))
            try:
                value = json.loads(str(_field(row, "conversation_json")))
            except (TypeError, ValueError):
                raise SnapshotError("Agent 对话状态损坏；本次请求已停止。")
            if agent in {"bookkeeping", "food_health"} and isinstance(value, dict):
                values[agent] = value
        return values

    def workspace(self, config, conversations):
        # WorkerMobileWorkspace deliberately skips MobileWorkspace.__init__,
        # which would start an unsupported thread and create a local key file.
        return WorkerMobileWorkspace(self.root, self.user_id, config, conversations)

    def files_after(self) -> dict[str, bytes]:
        collected: dict[str, bytes] = {}
        for path in self.root.rglob("*"):
            if path.is_symlink() or not path.is_file():
                continue
            relative = path.relative_to(self.root).as_posix()
            if relative.endswith(("-wal", "-shm", ".tmp")):
                continue
            if relative.endswith(".d1delta.json"):
                continue
            if any(part.casefold() in {"receipt_images", "receipts"} for part in relative.split("/")):
                continue
            collected[relative] = path.read_bytes()
        return collected

    def conversation_statements(self, workspace, new_revision: str):
        statements = []
        current = {agent: value for (uid, agent), value in workspace.conversations.items() if uid == self.user_id}
        for agent in ("bookkeeping", "food_health"):
            value = current.get(agent)
            if value is None:
                statements.append(self.database.prepare(
                    "DELETE FROM agent_conversations WHERE user_id=? AND agent=? AND EXISTS "
                    "(SELECT 1 FROM user_state_roots WHERE user_id=? AND revision=?)"
                ).bind(self.user_id, agent, self.user_id, new_revision))
            else:
                encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
                statements.append(self.database.prepare(
                    "INSERT INTO agent_conversations(user_id,agent,conversation_json,updated_at) "
                    "SELECT ?,?,?,? WHERE EXISTS (SELECT 1 FROM user_state_roots WHERE user_id=? AND revision=?) "
                    "ON CONFLICT(user_id,agent) DO UPDATE SET conversation_json=excluded.conversation_json,updated_at=excluded.updated_at"
                ).bind(self.user_id, agent, encoded, _now(), self.user_id, new_revision))
        return statements

    async def commit(self, workspace, *, job_id=None, result=None, persist_conversations=False):
        ledger_path = f"ledgers/{self.user_id}.sqlite3"
        pending_changes = list(workspace.pending_ledger_changes)
        pending_changes.extend(read_pending_changes(self.root / ledger_path))
        if workspace.ledger_replaced:
            pending_changes = []
        has_ledger_write = bool(workspace.generations.get(self.user_id, 0) or pending_changes)
        schema_hash = self.current_schema_hash
        if workspace.ledger_replaced:
            connection = sqlite3.connect(self.root / ledger_path)
            try:
                schema_hash = _ledger_schema_hash(connection)
            finally:
                connection.close()
        enable_row_storage = self.ledger_rows_enabled or has_ledger_write or workspace.ledger_replaced
        rebase_rows = bool(enable_row_storage and (
            not self.ledger_rows_enabled or self.ledger_rebase_needed or workspace.ledger_replaced
        ))
        if enable_row_storage and self.ledger_rows_enabled and not rebase_rows and has_ledger_write:
            projected_count = len(self.ledger_row_deltas) + len(pending_changes)
            projected_bytes = sum(len(str(item.get("row_json") or "").encode("utf-8"))
                                  for item in self.ledger_row_deltas)
            projected_bytes += sum(len(str(item.get("row_json") or "").encode("utf-8"))
                                  for item in pending_changes)
            rebase_rows = projected_count > MAX_LEDGER_DELTA_ROWS or projected_bytes > MAX_LEDGER_DELTA_BYTES
        new_files = self.files_after()
        if (enable_row_storage and self.ledger_rows_enabled and not rebase_rows and has_ledger_write
                and ledger_path in self.files and new_files.get(ledger_path) != self.files[ledger_path]
                and not pending_changes):
            # A bulk import/restore or an uninstrumented schema operation must
            # become a new base snapshot rather than being silently discarded.
            rebase_rows = True
        if enable_row_storage and not rebase_rows and ledger_path in self.files:
            # Keep the last full SQLite image as a base. The operation's changed
            # rows are layered over it from D1 and aren't written back to this file.
            new_files[ledger_path] = self.files[ledger_path]
        old_files = self.files
        encrypted = None
        github_ciphertext = None
        if workspace._config_dirty:
            encrypted = await encrypt_text(
                json.dumps(workspace.config(self.user_id), ensure_ascii=False, separators=(",", ":")),
                str(workspace._env.TOKEN_ENCRYPTION_KEY), "user:" + self.user_id + ":mobile-config",
            )
            github = workspace.config(self.user_id).get("cloud", {}).get("github")
            if github and github.get("token"):
                github_ciphertext = await encrypt_text(
                    json.dumps(github, ensure_ascii=False, separators=(",", ":")),
                    str(workspace._env.TOKEN_ENCRYPTION_KEY), "user:" + self.user_id + ":github-sync",
                )

        def build_final_statements(new_revision):
            statements = []
            if persist_conversations:
                statements.extend(self.conversation_statements(workspace, new_revision))
            if workspace._config_dirty:
                statements.append(self.database.prepare(
                    "INSERT INTO user_secrets(user_id,secret_name,encrypted_value,updated_at) "
                    "SELECT ?,'mobile-config',?,? WHERE EXISTS "
                    "(SELECT 1 FROM user_state_roots WHERE user_id=? AND revision=?) "
                    "ON CONFLICT(user_id,secret_name) DO UPDATE SET encrypted_value=excluded.encrypted_value,updated_at=excluded.updated_at"
                ).bind(self.user_id, encrypted, _now(), self.user_id, new_revision))
                if github_ciphertext:
                    statements.append(self.database.prepare(
                        "INSERT INTO user_secrets(user_id,secret_name,encrypted_value,updated_at) "
                        "SELECT ?,'github-sync',?,? WHERE EXISTS "
                        "(SELECT 1 FROM user_state_roots WHERE user_id=? AND revision=?) "
                        "ON CONFLICT(user_id,secret_name) DO UPDATE SET encrypted_value=excluded.encrypted_value,updated_at=excluded.updated_at"
                    ).bind(self.user_id, github_ciphertext, _now(), self.user_id, new_revision))
                else:
                    statements.append(self.database.prepare(
                        "DELETE FROM user_secrets WHERE user_id=? AND secret_name='github-sync' AND EXISTS "
                        "(SELECT 1 FROM user_state_roots WHERE user_id=? AND revision=?)"
                    ).bind(self.user_id, self.user_id, new_revision))
            return statements

        encoded_result = json.dumps(result or {"ok": True}, ensure_ascii=False, separators=(",", ":"))
        job_action = ""
        if job_id:
            action_row = await self.database.prepare(
                "SELECT action FROM app_jobs WHERE user_id=? AND operation_id=?"
            ).bind(self.user_id, job_id).first()
            if action_row is not None:
                job_action = str(_field(action_row, "action"))
        no_auto_sync_actions = {
            "cloud_upload", "cloud_auto_sync", "cloud_restore", "cloud_connect",
            "github_auth", "startup_pull", "cloud_disconnect", "keep_local_cloud",
            "onboarding_save",
            "settings",
        }
        committed = await self.store.commit(
            self.user_id, self.revision, old_files, new_files,
            final_statements=build_final_statements if (workspace._config_dirty or persist_conversations) else [],
            force_revision=bool(job_id or workspace._config_dirty or persist_conversations),
            job_id=job_id, job_result_json=encoded_result,
            queue_auto_sync=(
                bool(workspace.config(self.user_id).get("autoSync", False))
                and not (job_id and job_action in no_auto_sync_actions)
            ),
            auto_sync_complete_operation_id=job_id if job_action == "cloud_auto_sync" else None,
            ledger_row_changes=pending_changes if enable_row_storage and not rebase_rows else [],
            ledger_storage_meta={"schemaHash": schema_hash} if enable_row_storage and rebase_rows else None,
            clear_ledger_row_deltas=rebase_rows,
        )
        self.revision = committed
        self.files = new_files
        self.ledger_rows_enabled = enable_row_storage
        self.ledger_schema_hash = schema_hash if enable_row_storage else self.ledger_schema_hash
        self.ledger_rebase_needed = False
        return committed

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)


def _bootstrap_payload(db, user, language, transaction_ids=None):
    from bookkeeping.web_features import today
    account_rows = db.connection.execute(
        "SELECT a.id,a.name,a.account_type,a.currency,a.opening_date,c.minor_digits "
        "FROM accounts a JOIN currencies c ON c.code=a.currency ORDER BY a.name COLLATE NOCASE"
    ).fetchall()
    accounts = [{"id": int(row["id"]), "name": str(row["name"]),
                 "type": str(row["account_type"]), "currency": str(row["currency"]),
                 "minorDigits": int(row["minor_digits"]), "openingDate": str(row["opening_date"]),
                 "balanceMinor": str(db.account_balance_minor(int(row["id"])))} for row in account_rows]
    categories = db.connection.execute(
        "SELECT c.id,c.name,c.kind,COALESCE(t.translated_name,c.name) AS display_name "
        "FROM categories c LEFT JOIN category_translations t "
        "ON t.category_id=c.id AND t.language=? WHERE c.is_active=1 ORDER BY c.kind,c.name", (language,)
    ).fetchall()
    transaction_select = """SELECT t.id,t.occurred_on,t.kind,t.amount_minor,t.currency,t.description,
                  t.balance_effect,t.needs_review,t.account_amount_minor,
                  COALESCE(ct.translated_name,c.name) AS category_name,
                  a.name AS account_name,a.account_type AS account_type,
                  x.name AS to_account_name,x.currency AS to_currency,x.account_type AS to_account_type,t.to_amount_minor,
                  to_cur.minor_digits AS to_minor_digits,cur.minor_digits
           FROM transactions t LEFT JOIN categories c ON c.id=t.category_id
           LEFT JOIN category_translations ct ON ct.category_id=c.id AND ct.language=?
           LEFT JOIN accounts a ON a.id=t.account_id LEFT JOIN accounts x ON x.id=t.to_account_id
           LEFT JOIN currencies to_cur ON to_cur.code=x.currency JOIN currencies cur ON cur.code=t.currency """
    if transaction_ids is None:
        transactions = db.connection.execute(
            transaction_select + " ORDER BY t.occurred_on DESC,t.id DESC LIMIT 100", (language,)
        ).fetchall()
    else:
        ids = [int(value) for value in transaction_ids]
        transactions = []
        for offset in range(0, len(ids), 500):
            batch = ids[offset:offset + 500]
            if not batch:
                continue
            placeholders = ",".join("?" for _ in batch)
            transactions.extend(db.connection.execute(
                transaction_select + f" WHERE t.id IN ({placeholders}) ORDER BY t.occurred_on DESC,t.id DESC",
                (language, *batch),
            ).fetchall())
    payload = {
        "user": user, "accounts": accounts, "categories": [dict(row) for row in categories],
        "transactions": [{**dict(row), "amount_minor": str(row["amount_minor"]),
                          "to_amount_minor": str(row["to_amount_minor"]) if row["to_amount_minor"] is not None else None,
                          "account_amount_minor": str(row["account_amount_minor"]) if row["account_amount_minor"] is not None else None}
                         for row in transactions],
        "serverDate": today(),
    }
    return payload


async def bootstrap(database: Any, user: dict[str, str], language: str, env: Any):
    from bookkeeping.storage import Database
    from bookkeeping.web_features import serial, today
    from bookkeeping.localization import translate
    user_id = user["id"]
    state = await LedgerWorkspace.open(database, user_id)
    try:
        config = await state.load_config(env)
        workspace = state.workspace(config, await state.load_conversations())
        db = Database(state.root / "ledgers" / f"{user_id}.sqlite3")
        try:
            payload = _bootstrap_payload(db, user, language)
        finally:
            db.close()
        payload["user"] = user
        if state.ledger_rebase_needed or state.legacy_base_changed:
            await state.commit(workspace)
        return serial(payload)
    finally:
        state.cleanup()


async def workspace_snapshot(database: Any, user_id: str, language="zh-CN", report_date=None, env=None, *, bootstrap_user=None):
    from bookkeeping.storage import Database
    from bookkeeping.web_features import serial
    from bookkeeping.localization import translate
    from bookkeeping.web_features import today
    state = await LedgerWorkspace.open(database, user_id)
    try:
        cfg = await state.load_config(env)
        mobile = state.workspace(cfg, await state.load_conversations())
        snapshot = mobile.snapshot(user_id, language, report_date)
        if bootstrap_user is not None:
            if bootstrap_user["id"] != user_id:
                raise ValueError("账号隔离校验失败。")
            # One restored revision supplies every view; avoid downloading and
            # decrypting the same D1 snapshot for a parallel bootstrap request.
            db = Database(state.root / "ledgers" / f"{user_id}.sqlite3")
            try:
                snapshot["bootstrap"] = _bootstrap_payload(db, bootstrap_user, language)
            finally:
                db.close()
        for report in (snapshot, snapshot.get("reports", {})):
            balance_sheet = report.get("balanceSheet")
            if balance_sheet:
                for row in balance_sheet.get("rows", []):
                    for key in ("section", "status", "account_type_label"):
                        if key in row:
                            row[key] = translate(row[key], language)
        if state.ledger_rebase_needed or state.legacy_base_changed:
            await state.commit(mobile)
        snapshot["revision"] = state.revision
        return serial(snapshot)
    finally:
        state.cleanup()


def _save_web_account(db, data):
    from bookkeeping.storage import LedgerError, parse_date, to_minor_allow_zero
    name = str(data.get("name", "")).strip()
    account_type = str(data.get("type", ""))
    currency = str(data.get("currency", "")).upper()
    opening_balance = str(data.get("openingBalance", "0")).strip()
    opening_date = str(data.get("openingDate", datetime.now(timezone.utc).date().isoformat()))
    existing = db.connection.execute("SELECT * FROM accounts WHERE name=?", (name,)).fetchone()
    if existing is not None:
        curr = db.currency(currency)
        expected = to_minor_allow_zero(opening_balance, currency, int(curr["minor_digits"]))
        if (str(existing["account_type"]) == account_type and str(existing["currency"]) == currency
                and int(existing["opening_balance_minor"]) == expected
                and str(existing["opening_date"]) == parse_date(opening_date).isoformat()):
            return {"accountId": int(existing["id"]), "alreadyExists": True}
        raise LedgerError(f"账户名称“{name}”已存在，请使用不同名称。")
    account_id = db.add_account(
        name=name, account_type=account_type, currency=currency, opening_balance=opening_balance,
        opening_date=opening_date, completeness=str(data.get("completeness", "known")),
        note=str(data.get("note", "")),
    )
    return {"accountId": account_id}


def _save_web_transaction(db, op_id: str, payload_hash: str, data: dict[str, Any]):
    from bookkeeping.storage import LedgerError
    source_marker = f"websync:{op_id}:{payload_hash}"
    existing = db.connection.execute("SELECT id FROM transactions WHERE source=?", (source_marker,)).fetchone()
    if existing:
        return {"transactionId": int(existing["id"]), "recoveredAfterRetry": True}
    kind = str(data.get("kind", ""))
    currency = str(data.get("currency", "")).upper()
    description = str(data.get("description", "")).strip()
    account_name = str(data.get("accountName", "")).strip()
    if kind not in {"income", "expense", "transfer"}:
        raise LedgerError("请选择收入、支出或转账。")
    if not description or len(description) > 240:
        raise LedgerError("说明不能为空，且最多240个字符。")
    if kind in {"income", "expense"}:
        category_name = str(data.get("categoryName", "")).strip()
        db.currency(currency)
        account = db.account(account_name)
        if str(account["currency"]) != currency:
            raise LedgerError("此Web版本的收支必须使用与账户相同的币种；跨币种账单后续版本再支持。")
        transaction_id = db.add_transaction(
            occurred_on=str(data.get("date", "")), kind=kind, amount=str(data.get("amount", "")),
            currency=currency, description=description, category_name=category_name,
            account_name=account_name, source=source_marker,
        )
    else:
        to_account_name = str(data.get("toAccountName", "")).strip()
        source_account = db.account(account_name)
        destination_account = db.account(to_account_name)
        if account_name == to_account_name:
            raise LedgerError("转出账户和转入账户不能相同。")
        if str(source_account["currency"]) != currency:
            raise LedgerError("转出金额币种必须与转出账户一致。")
        to_amount = data.get("toAmount")
        if not to_amount and str(destination_account["currency"]) != currency:
            raise LedgerError("跨币种转账必须填写实际转入金额。")
        transaction_id = db.add_transaction(
            occurred_on=str(data.get("date", "")), kind="transfer", amount=str(data.get("amount", "")),
            currency=currency, description=description, account_name=account_name,
            to_account_name=to_account_name, to_amount=str(to_amount) if to_amount else None,
            source=source_marker,
        )
    return {"transactionId": transaction_id}


def _apply_sync_operation(db, user_id: str, operation: Any, *, prepared_agent=None):
    import hmac
    from bookkeeping.storage import LedgerError
    if not isinstance(operation, dict):
        raise ValueError("同步项目格式无效。")
    if operation.get("ownerId") and operation["ownerId"] != user_id:
        raise ValueError("待同步记录属于另一个账号，已停止写入。")
    op_id = str(operation.get("opId", ""))
    operation_type = str(operation.get("type", ""))
    data = operation.get("data")
    import re
    if not re.fullmatch(r"[A-Za-z0-9_-]{12,80}", op_id) or not isinstance(data, dict):
        raise ValueError("同步项目缺少有效编号或数据。")
    if operation_type not in {"transaction", "account", "category", "prepared_agent"}:
        raise ValueError("不支持此同步项目类型。")
    canonical = json.dumps({"type": operation_type, "data": data}, sort_keys=True,
                           ensure_ascii=False, separators=(",", ":"))
    payload_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    previous = db.connection.execute(
        "SELECT payload_hash,result_json FROM web_sync_operations WHERE operation_id=?", (op_id,)
    ).fetchone()
    if previous:
        if not hmac.compare_digest(str(previous["payload_hash"]), payload_hash):
            raise ValueError("此同步编号对应的数据不同，已停止以保护账本。")
        return json.loads(previous["result_json"]), False
    if operation_type == "prepared_agent":
        if not isinstance(prepared_agent, dict):
            raise ValueError("待同步的 Agent 操作不存在或已过期。")
        if str(data.get("prepareJobId", "")) != op_id:
            raise ValueError("Agent 同步编号与准备任务不匹配。")
        changes = prepared_agent.get("changes")
        if not isinstance(changes, list) or not changes:
            raise ValueError("Agent 准备结果没有可提交的账本变更。")
        apply_changes(db.connection, changes, validate_foreign_keys=True)
        clear_change_log(db.connection)
        result = {
            "transactionIds": prepared_agent.get("transactionIds", []),
            "agent": prepared_agent.get("agent", "bookkeeping"),
        }
    elif operation_type == "transaction":
        result = _save_web_transaction(db, op_id, payload_hash, data)
    elif operation_type == "account":
        result = _save_web_account(db, data)
    else:
        name = str(data.get("name", "")).strip()
        kind = str(data.get("kind", ""))
        if not name or len(name) > 80 or kind not in {"income", "expense"}:
            raise ValueError("类别名称或类型无效。")
        exists = db.connection.execute("SELECT kind FROM categories WHERE name=?", (name,)).fetchone()
        if exists is None:
            db.connection.execute("INSERT INTO categories(name,kind,is_active) VALUES(?,?,1)", (name, kind))
        elif str(exists["kind"]) != kind:
            raise ValueError("同名类别已存在，但类别类型不同。")
        result = {"categoryName": name}
    result.update({"opId": op_id, "ok": True, "type": operation_type})
    db.connection.execute(
        "INSERT INTO web_sync_operations(operation_id,payload_hash,resource_type,result_json,created_at) VALUES(?,?,?,?,?)",
        (op_id, payload_hash, operation_type, json.dumps(result, ensure_ascii=False, separators=(",", ":")), _now()),
    )
    return result, True


async def apply_sync(
    database: Any,
    env: Any,
    user: dict[str, str],
    operations: list[dict[str, Any]],
    *,
    provider_opener=None,
    expected_revision: str | None = None,
    job_id: str | None = None,
):
    from bookkeeping.storage import Database
    from model_jobs import cleanup_prepared_agent_payload, load_job_payload
    if any(isinstance(item, dict) and item.get("type") == "prepared_agent" for item in operations) and len(operations) != 1:
        raise ValueError("Agent 准备结果必须单独同步，请稍后重试。")
    state = await LedgerWorkspace.open(database, user["id"])
    try:
        if expected_revision is not None and state.revision != expected_revision:
            raise SnapshotConflict("等待外部服务期间云端账本已更新；为避免覆盖新数据，本次操作没有写入。请刷新后重试。")
        config = await state.load_config(env)
        mobile = state.workspace(config, await state.load_conversations())
        mobile._provider_opener = provider_opener
        db = Database(state.root / "ledgers" / f"{user['id']}.sqlite3")
        # CNY transaction creation needs a daily reference rate. In a Worker,
        # route that HTTP request through the replayable asynchronous fetch
        # boundary instead of urllib's synchronous socket implementation.
        db.external_opener = provider_opener
        modified = False
        persist_conversations = False
        prepared_keys_to_cleanup = []
        results = []
        try:
            for operation in operations:
                try:
                    prepared_agent = None
                    is_prepared_agent = isinstance(operation, dict) and operation.get("type") == "prepared_agent"
                    if is_prepared_agent:
                        operation_id = str(operation.get("opId", ""))
                        data = operation.get("data")
                        if not isinstance(data, dict) or str(data.get("prepareJobId", "")) != operation_id:
                            raise ValueError("Agent 同步编号与准备任务不匹配。")
                        # A retry after a lost acknowledgement is resolved from
                        # the ledger's idempotency table before the encrypted
                        # preparation payload is read or removed.
                        prior = db.connection.execute(
                            "SELECT payload_hash,result_json FROM web_sync_operations WHERE operation_id=?",
                            (operation_id,),
                        ).fetchone()
                        if prior is None:
                            prepared_job = await database.prepare(
                                "SELECT action,state,result_json FROM app_jobs WHERE user_id=? AND operation_id=?"
                            ).bind(user["id"], operation_id).first()
                            if (prepared_job is None
                                    or str(_field(prepared_job, "action")) != "agent_prepare"
                                    or str(_field(prepared_job, "state")) != "done"):
                                raise ValueError("Agent 准备任务不存在或尚未完成。")
                            try:
                                prepared_status = json.loads(str(_field(prepared_job, "result_json") or "{}"))
                            except (TypeError, ValueError):
                                prepared_status = {}
                            if not prepared_status.get("prepared"):
                                raise ValueError("Agent 准备任务没有可同步的账本变更。")
                            payload_key = "prepared_" + operation_id
                            payload_row = await database.prepare(
                                "SELECT payload_hash FROM app_job_payloads WHERE user_id=? AND operation_id=? AND action='prepared_agent'"
                            ).bind(user["id"], payload_key).first()
                            if payload_row is None:
                                raise ValueError("Agent 本机待同步数据已过期，请刷新账本后重新记账。")
                            _payload_action, prepared_agent = await load_job_payload(
                                database, env, user["id"], payload_key,
                                str(_field(payload_row, "payload_hash")), "prepared_agent",
                            )
                            base_revision = str(prepared_agent.get("baseRevision", ""))
                            if base_revision != state.revision:
                                raise SnapshotConflict(
                                    "Agent 处理期间云端账本已更新；本次没有覆盖新数据。请先刷新并核对待同步记录。"
                                )
                            agent = str(prepared_agent.get("agent", ""))
                            conversation = prepared_agent.get("conversation")
                            if agent not in {"bookkeeping", "food_health"} or not isinstance(conversation, dict):
                                raise ValueError("Agent 对话准备数据无效；本次没有写入。")
                        else:
                            prepared_agent = None
                    result, was_new = _apply_sync_operation(
                        db, user["id"], operation, prepared_agent=prepared_agent,
                    )
                    # Existing ledger methods such as add_account/add_transaction
                    # commit internally. A SAVEPOINT around them is therefore
                    # released by that commit, making RELEASE/ROLLBACK fail and
                    # returning an error after the transaction was already
                    # inserted. Commit each queue item independently instead:
                    # previous successes remain durable in this snapshot while
                    # a failed current item can still be rolled back.
                    db.connection.commit()
                    results.append(result)
                    modified = modified or was_new
                    if is_prepared_agent and was_new and prepared_agent:
                        mobile.conversations[(user["id"], str(prepared_agent["agent"]))] = prepared_agent["conversation"]
                        mobile.pending_ledger_changes.extend(prepared_agent["changes"])
                        persist_conversations = True
                    if is_prepared_agent:
                        prepared_keys_to_cleanup.append("prepared_" + str(operation.get("opId", "")))
                except Exception as exc:
                    try:
                        db.connection.rollback()
                    except sqlite3.Error:
                        pass
                    if provider_opener is not None and exc.__class__.__name__ == "ModelRequestRequired":
                        # No D1 snapshot has been committed yet. Discard this
                        # candidate and let the durable Workflow fetch the rate,
                        # then replay the whole idempotent batch.
                        raise
                    results.append({"opId": operation.get("opId") if isinstance(operation, dict) else None,
                                    "ok": False, "error": str(exc) or "无法同步此条记录。"})
            if modified:
                mobile.after_write(user["id"])
        finally:
            db.close()
        result = {"results": results}
        await state.commit(
            mobile, job_id=job_id, result=result if job_id else None,
            persist_conversations=persist_conversations,
        )
        for prepared_key in prepared_keys_to_cleanup:
            await cleanup_prepared_agent_payload(database, user["id"], prepared_key)
        result["revision"] = state.revision
        if job_id:
            await database.prepare(
                "UPDATE app_jobs SET result_json=?,updated_at=? WHERE user_id=? AND operation_id=? AND state='done'"
            ).bind(
                json.dumps(result, ensure_ascii=False, separators=(",", ":")),
                _now(), user["id"], job_id,
            ).run()
        return result
    finally:
        state.cleanup()


async def create_account(database: Any, env: Any, user: dict[str, str], data: dict[str, Any]):
    from bookkeeping.storage import Database
    state = await LedgerWorkspace.open(database, user["id"])
    try:
        config = await state.load_config(env)
        mobile = state.workspace(config, await state.load_conversations())
        db = Database(state.root / "ledgers" / f"{user['id']}.sqlite3")
        try:
            result = _save_web_account(db, data)
            db.connection.commit()
            if not result.get("alreadyExists"):
                mobile.after_write(user["id"])
        finally:
            db.close()
        await state.commit(mobile)
        return {"ok": True, **result}
    finally:
        state.cleanup()


async def create_category(database: Any, env: Any, user: dict[str, str], data: dict[str, Any]):
    from bookkeeping.storage import Database, LedgerError
    state = await LedgerWorkspace.open(database, user["id"])
    try:
        db = Database(state.root / "ledgers" / f"{user['id']}.sqlite3")
        try:
            name = str(data.get("name", "")).strip()
            kind = str(data.get("kind", ""))
            if not name or len(name) > 80 or kind not in {"income", "expense"}:
                raise LedgerError("类别名称或类型无效。")
            db.connection.execute("INSERT INTO categories(name,kind,is_active) VALUES(?,?,1)", (name, kind))
            db.connection.commit()
        except sqlite3.IntegrityError as exc:
            raise LedgerError("该类别名称已存在。") from exc
        finally:
            db.close()
        config = await state.load_config(env)
        mobile = state.workspace(config, await state.load_conversations())
        mobile.after_write(user["id"])
        await state.commit(mobile)
        return {"ok": True}
    finally:
        state.cleanup()


async def list_transactions(database: Any, env: Any, user_id: str, start: str, end: str):
    from bookkeeping.storage import Database, parse_date
    start_date = parse_date(start).isoformat()
    end_date = parse_date(end).isoformat()
    if end_date < start_date:
        raise ValueError("结束日期不能早于开始日期。")
    state = await LedgerWorkspace.open(database, user_id)
    try:
        db = Database(state.root / "ledgers" / f"{user_id}.sqlite3")
        try:
            rows = db.transactions_between(start_date, end_date)
        finally:
            db.close()
        mobile = state.workspace(await state.load_config(env), await state.load_conversations())
        if state.ledger_rebase_needed or state.legacy_base_changed:
            await state.commit(mobile)
        from bookkeeping.web_features import serial
        return serial(rows)
    finally:
        state.cleanup()


async def create_manual_backup(database: Any, env: Any, user_id: str):
    state = await LedgerWorkspace.open(database, user_id)
    try:
        mobile = state.workspace(await state.load_config(env), await state.load_conversations())
        name, body = mobile.backup(user_id)
        await state.commit(mobile)
        return name, body
    finally:
        state.cleanup()


async def read_backup(database: Any, env: Any, user_id: str, name: str) -> bytes:
    import re
    if not re.fullmatch(r"[\w.-]+\.zip", name):
        raise ValueError("备份文件名无效。")
    state = await LedgerWorkspace.open(database, user_id)
    try:
        mobile = state.workspace(await state.load_config(env), await state.load_conversations())
        path = mobile.folder(user_id) / "backups" / name
        if path.is_symlink() or not path.is_file():
            raise FileNotFoundError("找不到此备份。")
        return path.read_bytes()
    finally:
        state.cleanup()


async def export_ledger(database: Any, user_id: str):
    from bookkeeping.storage import Database
    state = await LedgerWorkspace.open(database, user_id)
    target = state.root / f"household-ledger-{uuid.uuid4().hex}.sqlite3"
    try:
        db = Database(state.root / "ledgers" / f"{user_id}.sqlite3")
        try:
            db.backup(target)
        finally:
            db.close()
        return target.read_bytes()
    finally:
        state.cleanup()


async def restore_bundle(database: Any, env: Any, user: dict[str, str], body: bytes):
    state = await LedgerWorkspace.open(database, user["id"])
    try:
        mobile = state.workspace(await state.load_config(env), await state.load_conversations())
        mobile._env = env
        result = mobile.restore(user["id"], body, provider="local")
        await state.commit(mobile, result=result, persist_conversations=True)
        return result
    finally:
        state.cleanup()


async def import_ledger(database: Any, env: Any, user: dict[str, str], body: bytes):
    """Import a validated desktop SQLite ledger into a still-empty cloud ledger."""
    import sqlite3
    from bookkeeping.storage import DEFAULT_CATEGORIES, Database

    if not body.startswith(b"SQLite format 3\x00"):
        raise ValueError("所选文件不是有效的SQLite账本。")
    state = await LedgerWorkspace.open(database, user["id"])
    upload = state.root / f"import-{uuid.uuid4().hex}.sqlite3"
    try:
        live = Database(state.root / "ledgers" / f"{user['id']}.sqlite3")
        try:
            custom_names = tuple(name for name, _kind in DEFAULT_CATEGORIES)
            placeholders = ",".join("?" for _ in custom_names)
            existing_counts = (
                int(live.connection.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]),
                int(live.connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]),
                int(live.connection.execute("SELECT COUNT(*) FROM web_sync_operations").fetchone()[0]),
                int(live.connection.execute(
                    f"SELECT COUNT(*) FROM categories WHERE name NOT IN ({placeholders})", custom_names,
                ).fetchone()[0]),
            )
        finally:
            live.close()
        if any(existing_counts):
            raise ValueError("只有尚未建立账户、流水或自定义内容的空云账本可以导入，以免覆盖数据。")

        upload.write_bytes(body)
        check = sqlite3.connect(upload)
        try:
            integrity = check.execute("PRAGMA integrity_check").fetchone()
            tables = {str(row[0]) for row in check.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if (not integrity or integrity[0] != "ok"
                    or not {"accounts", "transactions", "categories", "currencies"}.issubset(tables)):
                raise ValueError("账本完整性检查失败，文件未导入。")
            foreign_key_errors = check.execute("PRAGMA foreign_key_check").fetchone()
            if foreign_key_errors:
                raise ValueError("账本关联检查失败，文件未导入。")
        finally:
            check.close()

        imported = Database(upload)
        try:
            imported.initialize()
            account_count = int(imported.connection.execute("SELECT COUNT(*) FROM accounts").fetchone()[0])
            transaction_count = int(imported.connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0])
            imported.connection.executescript(WEB_SYNC_SCHEMA)
            imported.connection.commit()
            try:
                if str(imported.connection.execute("PRAGMA journal_mode").fetchone()[0]).lower() == "wal":
                    imported.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                    imported.connection.execute("PRAGMA journal_mode=DELETE")
            except sqlite3.Error:
                pass
        finally:
            imported.close()

        mobile = state.workspace(await state.load_config(env), await state.load_conversations())
        mobile.backup(user["id"], "before-import", full=True)
        live_path = state.root / "ledgers" / f"{user['id']}.sqlite3"
        Path(f"{live_path}-wal").unlink(missing_ok=True)
        Path(f"{live_path}-shm").unlink(missing_ok=True)
        os.replace(upload, live_path)
        mobile.ledger_replaced = True
        mobile.after_write(user["id"])
        result = {"ok": True, "accounts": account_count, "transactions": transaction_count}
        await state.commit(mobile, result=result)
        return result
    finally:
        state.cleanup()


async def process_scheduled_entries(
    database: Any,
    env: Any,
    user_id: str,
    *,
    provider_opener=None,
    expected_revision: str | None = None,
    job_id: str | None = None,
):
    """Run due credit repayments and recurring entries against one D1 snapshot."""
    from bookkeeping.credit_management import process_due_credit_repayments
    from bookkeeping.recurring_transactions import process_due_recurring_transactions
    from bookkeeping.storage import Database
    from bookkeeping.web_features import serial, today

    state = await LedgerWorkspace.open(database, user_id)
    try:
        if expected_revision is not None and state.revision != expected_revision:
            raise SnapshotConflict("等待外部服务期间云端账本已更新；自动计划未执行，请稍后重试。")
        mobile = state.workspace(await state.load_config(env), await state.load_conversations())
        if provider_opener is None:
            # Cron first attempts a replayable, cache-only pass. If the ledger
            # needs a fresh FX observation, this opener yields to a Workflow.
            from model_jobs import ReplayOpener
            provider_opener = ReplayOpener([], expected_revision or state.revision)
        mobile._provider_opener = provider_opener
        db = Database(state.root / "ledgers" / f"{user_id}.sqlite3")
        db.external_opener = provider_opener
        try:
            db.initialize()
            credit = process_due_credit_repayments(db, today())
            recurring = process_due_recurring_transactions(db, today())
        finally:
            db.close()
        if any(item.get("transaction_id") for item in credit + recurring):
            mobile.after_write(user_id)
        result = {"credit": serial(credit), "recurring": serial(recurring)}
        await state.commit(mobile, job_id=job_id, result=result)
        return {"credit": credit, "recurring": recurring}
    finally:
        state.cleanup()


async def execute_action(
    database: Any,
    env: Any,
    user_id: str,
    action: str,
    data: dict[str, Any],
    job_id: str,
    *,
    provider_replies: list[dict[str, Any]] | None = None,
    expected_revision: str | None = None,
    request_now: datetime | None = None,
):
    from model_jobs import ReplayOpener
    from bookkeeping.storage import Database

    if action == "process_scheduled":
        return await process_scheduled_entries(
            database, env, user_id,
            provider_opener=ReplayOpener(
                list(provider_replies or []), expected_revision or "",
            ),
            expected_revision=expected_revision,
            job_id=job_id,
        )

    if action == "sync":
        operations = data.get("operations")
        if not isinstance(operations, list) or len(operations) > 100:
            raise ValueError("同步队列格式无效或超过100项。")
        revision = expected_revision or ""
        return await apply_sync(
            database, env, {"id": user_id}, operations,
            provider_opener=ReplayOpener(list(provider_replies or []), revision),
            expected_revision=expected_revision,
            job_id=job_id,
        )

    state = await LedgerWorkspace.open(database, user_id)
    try:
        if expected_revision is not None and state.revision != expected_revision:
            raise SnapshotConflict("等待模型回复期间云端账本已更新；为避免覆盖新数据，本次操作没有写入。请刷新后重试。")
        config = await state.load_config(env)
        mobile = state.workspace(config, await state.load_conversations())
        mobile._env = env
        mobile._backup_created_at = request_now
        mobile._deterministic_backup = request_now is not None
        if action == "delete_transaction":
            base_revision = data.get("baseRevision")
            if not base_revision:
                raise SnapshotConflict(
                    "删除请求缺少账本版本；请刷新网页后重新操作，本次没有删除账目。"
                )
            if str(base_revision) != state.revision:
                raise SnapshotConflict(
                    "云端账本已在其他设备更新；为避免删除新版本中的账目，本次删除已取消。请刷新后核对。"
                )
        if action in {"agent", "agent_prepare"}:
            # The synchronous domain logic runs on a disposable SQLite copy.
            # Its opener replays prior replies and yields control to Workflow
            # for each new asynchronous provider request.
            mobile._provider_replies = list(provider_replies or [])
            mobile._provider_expected_revision = expected_revision or state.revision
            result = mobile._agent(
                user_id, data,
                _job={
                    "request_now": request_now,
                    "defer_write": action == "agent_prepare",
                },
            )
        elif action in {"cloud_upload", "cloud_auto_sync", "cloud_restore", "cloud_connect", "github_auth", "startup_pull"}:
            mobile._provider_opener = ReplayOpener(
                list(provider_replies or []), expected_revision or state.revision,
            )
            result = mobile._cloud_remote(user_id, action, data)
        else:
            # Other existing feature actions can also need FX data (for
            # reconciliation, recurring entries, or editing a CNY transaction).
            # Give them the same replayable Workers-fetch boundary.
            mobile._provider_opener = ReplayOpener(
                list(provider_replies or []), expected_revision or state.revision,
            )
            result = mobile._action(user_id, action, data)
        from bookkeeping.web_features import serial
        result = serial(result or {"ok": True})
        if action == "agent_prepare":
            from ledger_row_deltas import read_pending_changes, write_pending_changes
            changes = read_pending_changes(state.root / "ledgers" / f"{user_id}.sqlite3")
            change_bytes = sum(len(str(item.get("row_json") or "").encode("utf-8")) for item in changes)
            if changes and len(changes) <= MAX_LEDGER_DELTA_ROWS and change_bytes <= 1536 * 1024:
                from model_jobs import (
                    canonical_payload, cleanup_prepared_agent_payload,
                    store_prepared_agent_payload,
                )

                language = str(data.get("language", "zh-CN"))
                snapshot = mobile.snapshot(user_id, language, data.get("reportDate"))
                changed_ids = {str(value) for value in result.get("transactionIds", [])}
                preview_transactions = [
                    row for row in snapshot.get("transactions", [])
                    if str(row.get("id", "")) in changed_ids
                ]
                db_for_preview = Database(state.root / "ledgers" / f"{user_id}.sqlite3")
                try:
                    bootstrap_preview = _bootstrap_payload(
                        db_for_preview, {"id": user_id}, language, result.get("transactionIds", []),
                    )
                finally:
                    db_for_preview.close()
                workspace_fields = (
                    "date", "cash", "cards", "creditHistory", "repaymentPlans",
                    "recurring", "assets", "balanceSheet", "profit", "reports",
                    "settings", "food", "eaten", "foodGroups", "foodReview", "validation",
                )
                preview = {key: snapshot[key] for key in workspace_fields if key in snapshot}
                preview["transactions"] = bootstrap_preview.get("transactions", []) or preview_transactions
                preview["accounts"] = bootstrap_preview.get("accounts", [])

                prepared_data = {
                    "baseRevision": state.revision,
                    "changes": changes,
                    "conversation": mobile.conversations.get((user_id, result.get("agent", "bookkeeping")), {}),
                    "agent": result.get("agent", "bookkeeping"),
                    "transactionIds": result.get("transactionIds", []),
                }
                payload = canonical_payload("prepared_agent", prepared_data)
                payload_hash = hashlib.sha256(payload).hexdigest()
                prepared_key = "prepared_" + job_id
                try:
                    await store_prepared_agent_payload(
                        database, env, user_id, job_id, prepared_data, payload_hash,
                    )
                except Exception as exc:
                    # Preserve the validated ledger change if the durable D1
                    # preparation path is rejected. Normal requests remain
                    # local-first; this is only a last-resort commit path.
                    if type(exc).__name__ != "JsException":
                        raise
                    await cleanup_prepared_agent_payload(database, user_id, prepared_key)
                    write_pending_changes(
                        state.root / "ledgers" / f"{user_id}.sqlite3", changes,
                    )
                    mobile.after_write(user_id)
                    result["cloudCommitted"] = True
                    await state.commit(
                        mobile, job_id=job_id, result=result,
                        persist_conversations=True,
                    )
                    print(
                        "Prepared Agent payload could not be saved; "
                        "committed the validated ledger delta through D1."
                    )
                    return result
                public_result = {
                    **result,
                    "prepared": True,
                    "prepareJobId": job_id,
                    "baseRevision": state.revision,
                    "preview": preview,
                }
                await database.prepare(
                    "UPDATE app_jobs SET state='done',message='Agent 结果已准备，等待同步',result_json=?,updated_at=? "
                    "WHERE user_id=? AND operation_id=? AND state='running' AND cancel_requested=0 "
                    "AND EXISTS (SELECT 1 FROM user_state_roots WHERE user_id=? AND revision=?)"
                ).bind(
                    json.dumps(public_result, ensure_ascii=False, separators=(",", ":")),
                    _now(), user_id, job_id, user_id, state.revision,
                ).run()
                saved = await database.prepare(
                    "SELECT state FROM app_jobs WHERE user_id=? AND operation_id=?"
                ).bind(user_id, job_id).first()
                if saved is None or str(_field(saved, "state")) != "done":
                    await cleanup_prepared_agent_payload(database, user_id, prepared_key)
                    raise SnapshotConflict(
                        "Agent 处理期间云端账本已更新或任务已取消；本次没有写入，请刷新账本后重试。"
                    )
                return public_result

            # A missing/oversized row delta cannot safely enter the local queue.
            # Restore the captured changes to the normal commit path instead.
            if changes:
                write_pending_changes(state.root / "ledgers" / f"{user_id}.sqlite3", changes)
            if changes or result.get("transactionIds"):
                mobile.after_write(user_id)
                result["cloudCommitted"] = True
        await state.commit(
            mobile, job_id=job_id, result=result,
            persist_conversations=action in {"agent", "agent_prepare", "agent_reset", "settings", "onboarding_save", "cloud_restore", "startup_pull"},
        )
        return result
    finally:
        state.cleanup()
