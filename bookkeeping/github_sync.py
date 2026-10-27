from __future__ import annotations

import base64
import json
import os
import shutil
import sqlite3
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterator

from .payment_preferences import PaymentPromptStore
from .backup_scope import (
    BACKUP_SCOPE_KEYS,
    DEFAULT_BACKUP_SCOPE,
    BackupScopeError,
    BackupScopeStore,
    normalize_backup_scope,
)
from .secure_settings import SecureSettingsError, _windows_crypt
from .skill_settings import BookkeepingSkillStore, FoodHealthSkillStore
from .storage import Database, LedgerError
from .user_data import app_data_directory
from .github_app_config import GITHUB_APP_CLIENT_ID


GITHUB_API = "https://api.github.com"
DEVICE_CODE_URL = "https://github.com/login/device/code"
DEVICE_TOKEN_URL = "https://github.com/login/oauth/access_token"
DEVICE_VERIFY_URL = "https://github.com/login/device"
SYNC_FILE_PATH = "household-bookkeeping/sync-bundle.zip"
MAX_SYNC_BUNDLE_BYTES = 60_000_000
MAX_UNPACKED_BUNDLE_BYTES = 512_000_000
_GITHUB_ENTROPY = b"household-bookkeeping-github-token-v1"
DEFAULT_BACKUP_REPOSITORY_NAME = "household-bookkeeping-data"
_EXPECTED_SHA_UNSET = object()


def _app_data_dir() -> Path:
    return app_data_directory()


def _remove_local_settings_from_database(database_path: Path) -> None:
    """Remove device-specific preferences from a portable SQLite snapshot."""
    try:
        connection = sqlite3.connect(database_path)
        try:
            tables = {
                str(row[0])
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            if "settings" not in tables:
                return
            connection.execute(
                "DELETE FROM settings WHERE key IN (?) OR key GLOB ?",
                ("food_review_purchases_count_as_eaten", "cash_management_hidden_default_cash_*"),
            )
            connection.commit()
        finally:
            connection.close()
    except sqlite3.Error as exc:
        raise GitHubSyncError(f"无法从同步快照中排除本机设置：{exc}") from exc


def _local_database_preferences(database_path: Path) -> list[tuple[str, str, str]]:
    if not database_path.is_file():
        return []
    try:
        connection = sqlite3.connect(database_path)
        try:
            tables = {
                str(row[0])
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            if "settings" not in tables:
                return []
            return [
                (str(row[0]), str(row[1]), str(row[2]))
                for row in connection.execute(
                    "SELECT key, value, note FROM settings "
                    "WHERE key IN (?) OR key GLOB ?",
                    ("food_review_purchases_count_as_eaten", "cash_management_hidden_default_cash_*"),
                )
            ]
        finally:
            connection.close()
    except sqlite3.Error as exc:
        raise GitHubSyncError(f"无法读取本机设置以供恢复时保留：{exc}") from exc


def _apply_local_database_preferences(database_path: Path, preferences: list[tuple[str, str, str]]) -> None:
    if not preferences:
        return
    try:
        connection = sqlite3.connect(database_path)
        try:
            tables = {
                str(row[0])
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            if "settings" not in tables:
                return
            connection.executemany(
                "INSERT OR REPLACE INTO settings (key, value, note) VALUES (?, ?, ?)",
                preferences,
            )
            connection.commit()
        finally:
            connection.close()
    except sqlite3.Error as exc:
        raise GitHubSyncError(f"无法在恢复数据中保留本机设置：{exc}") from exc


class GitHubSyncError(RuntimeError):
    """A GitHub sync or archive operation failed with a user-readable message."""


def _apply_backup_scope_to_database(database_path: Path, scope: dict[str, bool]) -> None:
    """Strip unselected rows from a disposable cloud snapshot, keeping FK dependencies."""
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("PRAGMA foreign_keys=OFF")
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }

        def clear(table: str) -> None:
            if table in tables:
                connection.execute(f'DELETE FROM "{table}"')

        if not scope["settings"]:
            clear("settings")

        if not scope["recurring_payments"]:
            clear("recurring_transaction_schedules")
            clear("recurring_transaction_occurrences")

        if not scope["credit_cards"]:
            for table in (
                "credit_repayment_periods",
                "credit_repayment_rules",
                "credit_repayment_schedules",
                "credit_limit_recovery_points",
                "credit_limit_snapshots",
            ):
                clear(table)

        if not scope["assets"]:
            clear("fixed_assets")

        if not scope["bills"]:
            clear("transactions")
            clear("food_purchase_items")
            clear("food_consumption_records")
            if "recurring_transaction_occurrences" in tables:
                connection.execute(
                    "UPDATE recurring_transaction_occurrences SET transaction_id=NULL "
                    "WHERE transaction_id NOT IN (SELECT id FROM transactions)"
                )
            if "credit_repayment_periods" in tables:
                connection.execute(
                    "UPDATE credit_repayment_periods SET transaction_id=NULL "
                    "WHERE transaction_id NOT IN (SELECT id FROM transactions)"
                )
            clear("credit_limit_recovery_points")
            clear("fx_rates")

        if "account_balance_snapshots" in tables and "accounts" in tables:
            if not scope["bank_accounts"]:
                connection.execute(
                    "DELETE FROM account_balance_snapshots WHERE account_id IN "
                    "(SELECT id FROM accounts WHERE account_type!='credit')"
                )
            if not scope["credit_cards"]:
                connection.execute(
                    "DELETE FROM account_balance_snapshots WHERE account_id IN "
                    "(SELECT id FROM accounts WHERE account_type='credit')"
                )

        if "accounts" in tables:
            needed_ids: set[int] = set()
            reference_queries = (
                ("transactions", "SELECT account_id FROM transactions WHERE account_id IS NOT NULL UNION SELECT to_account_id FROM transactions WHERE to_account_id IS NOT NULL"),
                ("recurring_transaction_schedules", "SELECT account_id FROM recurring_transaction_schedules"),
                ("credit_repayment_rules", "SELECT card_account_id FROM credit_repayment_rules UNION SELECT source_account_id FROM credit_repayment_rules"),
                ("credit_repayment_schedules", "SELECT card_account_id FROM credit_repayment_schedules UNION SELECT source_account_id FROM credit_repayment_schedules"),
            )
            for table, query in reference_queries:
                if table in tables:
                    needed_ids.update(int(row[0]) for row in connection.execute(query) if row[0] is not None)

            account_rows = connection.execute("SELECT * FROM accounts ORDER BY id").fetchall()
            account_columns = [row[1] for row in connection.execute("PRAGMA table_info(accounts)")]
            for row in account_rows:
                account = dict(zip(account_columns, row))
                account_id = int(account["id"])
                is_credit = account["account_type"] == "credit"
                full_record = scope["credit_cards"] if is_credit else scope["bank_accounts"]
                if full_record or account_id in needed_ids:
                    if not full_record:
                        placeholder = f"未纳入备份的关联账户 #{account_id}"
                        suffix = 2
                        while connection.execute(
                            "SELECT 1 FROM accounts WHERE name=? AND id<>?",
                            (placeholder, account_id),
                        ).fetchone():
                            placeholder = f"未纳入备份的关联账户 #{account_id} ({suffix})"
                            suffix += 1
                        connection.execute(
                            "UPDATE accounts SET name=?, opening_balance_minor=0, opening_date='1970-01-01', "
                            "balance_completeness='partial', opening_note='账户资料未纳入云备份', "
                            "created_at='1970-01-01 00:00:00' WHERE id=?",
                            (placeholder, account_id),
                        )
                else:
                    connection.execute("DELETE FROM accounts WHERE id=?", (account_id,))

        if "categories" in tables and not scope["settings"]:
            needed_categories: set[int] = set()
            for table in ("transactions", "recurring_transaction_schedules"):
                if table in tables:
                    needed_categories.update(
                        int(row[0])
                        for row in connection.execute(
                            f'SELECT category_id FROM "{table}" WHERE category_id IS NOT NULL'
                        )
                    )
            if needed_categories:
                placeholders = ",".join("?" for _ in needed_categories)
                clear("category_translations")
                connection.execute(
                    f"DELETE FROM categories WHERE id NOT IN ({placeholders})",
                    tuple(sorted(needed_categories)),
                )
                for category_id in sorted(needed_categories):
                    placeholder = f"未纳入备份的类别 #{category_id}"
                    suffix = 2
                    while connection.execute(
                        "SELECT 1 FROM categories WHERE name=? AND id<>?",
                        (placeholder, category_id),
                    ).fetchone():
                        placeholder = f"未纳入备份的类别 #{category_id} ({suffix})"
                        suffix += 1
                    connection.execute(
                        "UPDATE categories SET name=?, is_active=1 WHERE id=?",
                        (placeholder, category_id),
                    )
            else:
                clear("category_translations")
                clear("categories")

        connection.commit()
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise GitHubSyncError("所选云备份内容之间存在关联缺项，未生成备份。")
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if not integrity or integrity[0] != "ok":
            raise GitHubSyncError("所选云备份数据库完整性检查失败。")
    except sqlite3.Error as exc:
        raise GitHubSyncError(f"无法按所选范围整理云备份：{exc}") from exc
    finally:
        connection.close()


class GitHubAutoSyncSettingsError(GitHubSyncError):
    """The local preference controlling automatic GitHub uploads is unavailable."""


class GitHubNotFound(GitHubSyncError):
    pass


class GitHubAuthError(GitHubSyncError):
    pass


class GitHubSyncConflict(GitHubSyncError):
    """A cloud snapshot changed since this device last synchronized."""


@contextmanager
def github_sync_process_lock() -> Iterator[None]:
    """Serialize snapshot creation, restore, and upload across app processes."""
    lock_path = _app_data_dir() / "github_sync.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        if os.name == "nt":
            import msvcrt

            while True:
                try:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.05)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def is_github_app_user_token(token: str) -> bool:
    """GitHub App user access tokens use the ghu_ prefix."""
    return token.startswith("ghu_")


class GitHubSyncSettingsStore:
    """Store per-user repository selection, not the shared app's Client ID."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or _app_data_dir() / "github_sync.json"

    def load(self) -> dict[str, str]:
        if not self.path.exists():
            return {
                "repository_name": DEFAULT_BACKUP_REPOSITORY_NAME,
                "repository": "",
                "last_sync_sha": "",
            }
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(value, dict) or value.get("version") not in {1, 2, 3}:
                raise ValueError("unsupported settings version")
            last_sync_sha = value.get("last_sync_sha", "")
            if not isinstance(last_sync_sha, str):
                raise ValueError("last_sync_sha must be a string")
            return {
                "repository_name": str(value.get("repository_name") or DEFAULT_BACKUP_REPOSITORY_NAME).strip(),
                "repository": str(value.get("repository") or "").strip(),
                "last_sync_sha": last_sync_sha.strip(),
            }
        except (OSError, UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise GitHubSyncError("GitHub 同步设置无法读取；请重新连接 GitHub。") from exc

    def save(
        self,
        *,
        repository_name: str,
        repository: str = "",
        last_sync_sha: str | None = None,
    ) -> None:
        repository_value = repository.strip()
        if last_sync_sha is None:
            try:
                existing = self.load()
            except GitHubSyncError:
                existing = {"repository": "", "last_sync_sha": ""}
            checkpoint = (
                existing.get("last_sync_sha", "")
                if existing.get("repository", "").casefold() == repository_value.casefold()
                else ""
            )
        else:
            checkpoint = last_sync_sha.strip()
        payload = {
            "version": 3,
            "repository_name": repository_name.strip(),
            "repository": repository_value,
            "last_sync_sha": checkpoint,
        }
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
            os.replace(temporary, self.path)
        except OSError as exc:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise GitHubSyncError("无法保存 GitHub 设置，请检查当前用户配置目录权限。") from exc


class GitHubAutoSyncSettingsStore:
    """Persist whether successful ledger entries should trigger a GitHub upload."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or _app_data_dir() / "github_auto_sync_settings.json"

    def load_enabled(self) -> bool:
        if not self.path.exists():
            return True
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(value, dict) or value.get("version") != 1:
                raise ValueError("unsupported settings version")
            enabled = value.get("enabled", True)
            if not isinstance(enabled, bool):
                raise ValueError("enabled must be a boolean")
            return enabled
        except (OSError, UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise GitHubAutoSyncSettingsError("GitHub 自动同步设置无法读取。") from exc

    def save_enabled(self, enabled: bool) -> None:
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(
                json.dumps({"version": 1, "enabled": bool(enabled)}, ensure_ascii=True, indent=2),
                encoding="utf-8",
            )
            os.replace(temporary, self.path)
        except OSError as exc:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise GitHubAutoSyncSettingsError("无法保存 GitHub 自动同步设置。") from exc


class GitHubTokenStore:
    """Keep the GitHub App user token encrypted with Windows DPAPI per user."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or _app_data_dir() / "github_token.json"

    def load(self) -> str:
        return self.load_credentials()["access_token"]

    def load_credentials(self) -> dict[str, str]:
        if not self.path.exists():
            return {"access_token": "", "refresh_token": ""}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            access_field = value.get("access_token_dpapi", value.get("token_dpapi"))
            encrypted = base64.b64decode(access_field, validate=True)
            access_token = _windows_crypt(
                encrypted,
                decrypt=True,
                entropy_value=_GITHUB_ENTROPY,
                description_text="家庭记账 GitHub 访问令牌",
            ).decode("utf-8")
            refresh_token = ""
            if value.get("refresh_token_dpapi"):
                encrypted_refresh = base64.b64decode(value["refresh_token_dpapi"], validate=True)
                refresh_token = _windows_crypt(
                    encrypted_refresh,
                    decrypt=True,
                    entropy_value=_GITHUB_ENTROPY,
                    description_text="家庭记账 GitHub 刷新令牌",
                ).decode("utf-8")
            return {"access_token": access_token, "refresh_token": refresh_token}
        except SecureSettingsError:
            raise
        except (OSError, UnicodeDecodeError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise SecureSettingsError("本地加密的 GitHub 令牌无法读取；请重新授权。") from exc

    def save(self, token: str, refresh_token: str = "") -> None:
        value = token.strip()
        refresh_value = refresh_token.strip()
        if not value:
            raise SecureSettingsError("GitHub 访问令牌为空，无法保存。")
        encrypted = _windows_crypt(
            value.encode("utf-8"),
            decrypt=False,
            entropy_value=_GITHUB_ENTROPY,
            description_text="家庭记账 GitHub 访问令牌",
        )
        saved: dict[str, Any] = {
            "version": 1,
            "access_token_dpapi": base64.b64encode(encrypted).decode("ascii"),
        }
        if refresh_value:
            encrypted_refresh = _windows_crypt(
                refresh_value.encode("utf-8"),
                decrypt=False,
                entropy_value=_GITHUB_ENTROPY,
                description_text="家庭记账 GitHub 刷新令牌",
            )
            saved["refresh_token_dpapi"] = base64.b64encode(encrypted_refresh).decode("ascii")
        payload = json.dumps(saved, ensure_ascii=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(payload, encoding="utf-8")
            os.replace(temporary, self.path)
        except OSError as exc:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise SecureSettingsError("无法保存 GitHub 令牌，请检查当前用户配置目录权限。") from exc


def _http_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    timeout: float = 25,
 ) -> tuple[dict[str, Any], dict[str, str]]:
    request_headers = {"Accept": "application/json", "User-Agent": "HouseholdBookkeeping/1.0"}
    request_headers.update(headers or {})
    request = urllib.request.Request(url, data=body, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            result = json.loads(raw.decode("utf-8")) if raw else {}
            if not isinstance(result, dict):
                raise GitHubSyncError("GitHub 返回了无法识别的响应。")
            return result, {key.lower(): value for key, value in response.headers.items()}
    except urllib.error.HTTPError as exc:
        details = ""
        try:
            parsed = json.loads(exc.read().decode("utf-8", errors="replace"))
            if isinstance(parsed, dict):
                details = str(parsed.get("message") or "")
        except (ValueError, OSError):
            pass
        if exc.code == 404:
            raise GitHubNotFound(details or "GitHub 仓库或同步文件不存在。") from exc
        if method == "PUT" and exc.code in {409, 422}:
            raise GitHubSyncConflict(
                "GitHub 云端同步文件已发生变化，本次上传未覆盖云端数据。请重新同步后再试。"
            ) from exc
        if exc.code == 401:
            raise GitHubAuthError("GitHub 授权已失效；请重新连接 GitHub。") from exc
        if exc.code == 403:
            if details.casefold() == "resource not accessible by integration":
                raise GitHubSyncError(
                    "GitHub App 尚未安装到当前账号，或安装权限尚未生效。请在软件的 GitHub 同步设置中打开 App 安装页，确认使用当前账号安装，并批准 Repository creation 和 Contents 权限，然后重新连接。"
                ) from exc
            raise GitHubSyncError(details or "GitHub 拒绝了请求，请检查授权权限或请求频率。") from exc
        raise GitHubSyncError(details or f"GitHub 请求失败（HTTP {exc.code}）。") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise GitHubSyncError("无法连接 GitHub；请检查网络连接后重试。") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GitHubSyncError("GitHub 返回的数据无法读取。") from exc


def request_device_code(client_id: str) -> dict[str, Any]:
    # GitHub Apps use permissions configured on the app, not OAuth scopes.
    # offline_access only opts the device-flow token into refresh-token rotation.
    data = urllib.parse.urlencode({"client_id": client_id, "scope": "offline_access"}).encode("ascii")
    result, _ = _http_json(
        DEVICE_CODE_URL,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        body=data,
    )
    required = ("device_code", "user_code", "verification_uri", "interval", "expires_in")
    if any(key not in result for key in required):
        raise GitHubSyncError(str(result.get("error_description") or result.get("error") or "无法开始 GitHub 授权。"))
    return result


def poll_device_token(
    client_id: str,
    device_code: str,
    interval: int,
    expires_in: int,
    cancelled: Callable[[], bool],
    status: Callable[[str], None] | None = None,
) -> dict[str, str]:
    deadline = time.monotonic() + int(expires_in)
    delay = max(5, int(interval))
    while time.monotonic() < deadline:
        remaining = min(delay, max(0, deadline - time.monotonic()))
        wait_until = time.monotonic() + remaining
        while time.monotonic() < wait_until:
            if cancelled():
                raise GitHubSyncError("GitHub 授权已取消。")
            time.sleep(min(0.25, wait_until - time.monotonic()))
        if cancelled():
            raise GitHubSyncError("GitHub 授权已取消。")
        body = urllib.parse.urlencode(
            {"client_id": client_id, "device_code": device_code, "grant_type": "urn:ietf:params:oauth:grant-type:device_code"}
        ).encode("ascii")
        result, _ = _http_json(
            DEVICE_TOKEN_URL,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
            body=body,
        )
        token = result.get("access_token")
        if isinstance(token, str) and token:
            return {
                "access_token": token,
                "refresh_token": str(result.get("refresh_token") or ""),
            }
        error = str(result.get("error") or "")
        if error == "authorization_pending":
            if status:
                status("等待在浏览器中完成 GitHub 授权…")
            continue
        if error == "slow_down":
            delay += 5
            continue
        if error == "expired_token":
            raise GitHubSyncError("GitHub 授权码已过期，请重新连接。")
        if error == "access_denied":
            raise GitHubSyncError("你拒绝了 GitHub 授权。")
        if error == "device_flow_disabled":
            raise GitHubSyncError("GitHub App 尚未启用 Device Flow；请由软件开发者检查 App 配置。")
        if error == "incorrect_client_credentials":
            raise GitHubSyncError("GitHub App Client ID 无效；请由软件开发者检查 App 配置。")
        if error == "bad_verification_code":
            raise GitHubSyncError("GitHub 验证码无效或已过期，请重新连接。")
        if error == "unverified_user_email":
            raise GitHubSyncError("请先验证 GitHub 账号的主要邮箱，然后重新连接。")
        raise GitHubSyncError(str(result.get("error_description") or error or "GitHub 授权失败。"))
    raise GitHubSyncError("GitHub 授权等待超时，请重新连接。")


class GitHubClient:
    def __init__(
        self,
        token: str,
        *,
        refresh_token: str = "",
        client_id: str = "",
        token_store: GitHubTokenStore | None = None,
    ) -> None:
        if not token:
            raise GitHubSyncError("请先连接 GitHub。")
        if not is_github_app_user_token(token):
            raise GitHubAuthError("检测到旧版或不支持的 GitHub 授权；请重新连接 GitHub App。")
        self.token = token
        self.refresh_token = refresh_token
        self.client_id = client_id or GITHUB_APP_CLIENT_ID
        self.token_store = token_store

    def _headers(self, accept: str = "application/vnd.github+json") -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": accept,
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def request(
        self,
        path: str,
        *,
        method: str = "GET",
        payload: dict[str, Any] | None = None,
        timeout: float = 25,
    ) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        headers = self._headers()
        if body is not None:
            headers["Content-Type"] = "application/json"
        try:
            result, _ = _http_json(
                GITHUB_API + path, method=method, headers=headers, body=body, timeout=timeout
            )
        except GitHubAuthError:
            self._refresh_access_token()
            headers = self._headers()
            if body is not None:
                headers["Content-Type"] = "application/json"
            result, _ = _http_json(
                GITHUB_API + path, method=method, headers=headers, body=body, timeout=timeout
            )
        return result

    def _refresh_access_token(self) -> None:
        if not self.refresh_token or not self.client_id:
            raise GitHubAuthError("GitHub 授权已失效；请重新连接 GitHub。")
        body = urllib.parse.urlencode(
            {
                "client_id": self.client_id,
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
            }
        ).encode("ascii")
        result, _ = _http_json(
            DEVICE_TOKEN_URL,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
            body=body,
        )
        access = result.get("access_token")
        if not isinstance(access, str) or not access:
            error = str(result.get("error") or "")
            if error == "bad_refresh_token":
                raise GitHubAuthError("GitHub 刷新令牌已过期；请重新连接 GitHub。")
            raise GitHubAuthError(str(result.get("error_description") or "GitHub 授权已失效；请重新连接 GitHub。"))
        self.token = access
        self.refresh_token = str(result.get("refresh_token") or self.refresh_token)
        if self.token_store is not None:
            self.token_store.save(self.token, self.refresh_token)

    def request_raw(self, path: str, *, _retried: bool = False) -> bytes:
        request = urllib.request.Request(
            GITHUB_API + path,
            headers={**self._headers("application/vnd.github.raw+json"), "User-Agent": "HouseholdBookkeeping/1.0"},
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                return response.read(MAX_SYNC_BUNDLE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise GitHubNotFound("GitHub 仓库中还没有账本备份。") from exc
            if exc.code == 401:
                if _retried:
                    raise GitHubAuthError("GitHub 授权已失效；请重新连接 GitHub。") from exc
                self._refresh_access_token()
                return self.request_raw(path, _retried=True)
            raise GitHubSyncError(f"下载 GitHub 账本失败（HTTP {exc.code}）。") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise GitHubSyncError("无法连接 GitHub；请检查网络连接后重试。") from exc

    def current_user(self) -> dict[str, Any]:
        return self.request("/user")

    def ensure_private_repository(self, login: str, name: str) -> tuple[str, bool]:
        owner = urllib.parse.quote(login, safe="")
        repo = urllib.parse.quote(name, safe="")
        path = f"/repos/{owner}/{repo}"
        try:
            existing = self.request(path)
            if existing.get("private") is not True:
                raise GitHubSyncError("同名仓库已经存在且不是私有仓库；请换一个仓库名。")
            return str(existing.get("full_name") or f"{login}/{name}"), False
        except GitHubNotFound:
            created = self.request(
                "/user/repos",
                method="POST",
                payload={
                    "name": name,
                    "description": "Private sync data for Household Bookkeeping",
                    "private": True,
                    "auto_init": True,
                },
            )
            return str(created.get("full_name") or f"{login}/{name}"), True

    def upload_bundle(
        self,
        repository: str,
        bundle: bytes,
        *,
        expected_sha: str | None | object = _EXPECTED_SHA_UNSET,
    ) -> str:
        if len(bundle) > MAX_SYNC_BUNDLE_BYTES:
            raise GitHubSyncError("同步包超过 60 MB；请减少小票图片后重试。")
        path = self._bundle_contents_path(repository)
        current_sha = self.bundle_sha(repository)
        if expected_sha is not _EXPECTED_SHA_UNSET:
            expected = expected_sha or None
            if current_sha != expected:
                raise GitHubSyncConflict(
                    "GitHub 云端同步文件已在其他设备更新，本次上传已取消，云端数据未被覆盖。"
                    "请先从 GitHub 恢复，或确认后手动上传本机数据。"
                )
        payload: dict[str, Any] = {
            "message": "Sync household bookkeeping data",
            "content": base64.b64encode(bundle).decode("ascii"),
        }
        if current_sha:
            payload["sha"] = current_sha
        result = self.request(path, method="PUT", payload=payload, timeout=180)
        content = result.get("content")
        sha = content.get("sha") if isinstance(content, dict) else None
        if not isinstance(sha, str) or not sha:
            sha = self.bundle_sha(repository)
        if not sha:
            raise GitHubSyncError("GitHub 未确认同步文件的版本编号；请重新读取云端版本。")
        return sha

    @staticmethod
    def _bundle_contents_path(repository: str) -> str:
        owner, repo = repository.split("/", 1)
        return "/repos/{}/{}/contents/{}".format(
            urllib.parse.quote(owner, safe=""),
            urllib.parse.quote(repo, safe=""),
            urllib.parse.quote(SYNC_FILE_PATH, safe="/"),
        )

    def bundle_sha(self, repository: str) -> str | None:
        try:
            result = self.request(self._bundle_contents_path(repository))
        except GitHubNotFound:
            return None
        sha = result.get("sha")
        if not isinstance(sha, str) or not sha:
            raise GitHubSyncError("GitHub 未返回同步文件版本编号。")
        return sha

    def sync_bundle_exists(self, repository: str) -> bool:
        return self.bundle_sha(repository) is not None

    def download_bundle(self, repository: str) -> bytes:
        data, _sha = self.download_bundle_with_revision(repository)
        return data

    def download_bundle_with_revision(self, repository: str) -> tuple[bytes, str]:
        """Download one stable cloud version and return its blob SHA checkpoint."""
        path = self._bundle_contents_path(repository)
        for _attempt in range(3):
            before_sha = self.bundle_sha(repository)
            if before_sha is None:
                raise GitHubNotFound("GitHub 仓库中还没有账本备份。")
            data = self.request_raw(path)
            after_sha = self.bundle_sha(repository)
            if before_sha == after_sha:
                if len(data) > MAX_SYNC_BUNDLE_BYTES:
                    raise GitHubSyncError("GitHub 同步包超过 60 MB，无法下载。")
                return data, before_sha
        raise GitHubSyncConflict("下载期间 GitHub 云端同步文件发生变化，请重新恢复。")


def create_sync_bundle(
    database_path: Path,
    destination: Path,
    *,
    payment_store: PaymentPromptStore | None = None,
    bookkeeping_skill_store: BookkeepingSkillStore | None = None,
    food_skill_store: FoodHealthSkillStore | None = None,
    receipt_image_directory: Path | None = None,
    include_scope: dict[str, bool] | None = None,
    max_bundle_bytes: int | None = MAX_SYNC_BUNDLE_BYTES,
    max_bundle_error: str | None = None,
) -> bytes:
    try:
        scope = (
            BackupScopeStore().load()
            if include_scope is None
            else normalize_backup_scope(include_scope)
        )
    except BackupScopeError as exc:
        raise GitHubSyncError(str(exc)) from exc
    if not any(scope.values()):
        raise GitHubSyncError("至少选择一项云备份内容。")
    payment_store = payment_store or PaymentPromptStore()
    bookkeeping_skill_store = bookkeeping_skill_store or BookkeepingSkillStore()
    food_skill_store = food_skill_store or FoodHealthSkillStore()
    image_dir = receipt_image_directory or database_path.parent / "receipt_images"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="household-github-sync-") as temp_name:
        temp = Path(temp_name)
        db_snapshot = temp / "ledger.sqlite3"
        db = Database(database_path)
        try:
            db.backup(db_snapshot)
        except (LedgerError, OSError, sqlite3.Error) as exc:
            raise GitHubSyncError(f"无法制作账本同步快照：{exc}") from exc
        finally:
            db.close()
        _remove_local_settings_from_database(db_snapshot)
        _apply_backup_scope_to_database(db_snapshot, scope)

        skills: dict[str, bytes] = {}
        payment_bytes: bytes | None = None
        if scope["payment_methods"]:
            payment_settings = payment_store.load()
            # Preserve the structured account-order schema for cross-device restore.
            payment_settings.setdefault("version", 2)
            payment_bytes = json.dumps(payment_settings, ensure_ascii=False, indent=2).encode("utf-8")
        if scope["settings"]:
            for archive_name, store in (
                ("bookkeeping.md", bookkeeping_skill_store),
                ("food_health.md", food_skill_store),
            ):
                loaded = store.load()
                if loaded:
                    skills[archive_name] = loaded["content"].encode("utf-8")

        image_files: list[Path] = []
        if scope["bills"] and image_dir.exists():
            image_files = [
                path for path in image_dir.rglob("*")
                if path.is_file() and not path.is_symlink()
            ]
        manifest = {
            "version": 3,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "scope": scope,
            "includes": {
                "ledger": True,
                "payment_rules": scope["payment_methods"],
                "bookkeeping_skill": "bookkeeping.md" in skills,
                "food_health_skill": "food_health.md" in skills,
                "receipt_images": bool(image_files),
            },
            "excludes": [
                "api_credentials",
                "github_authorization",
                "gitee_authorization",
                "interface_language",
                "local_preferences",
                "local_backup_history",
            ],
        }
        try:
            with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
                archive.write(db_snapshot, "ledger.sqlite3")
                if payment_bytes is not None:
                    archive.writestr("payment_prompts.json", payment_bytes)
                archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
                for name, data in skills.items():
                    archive.writestr(f"skills/{name}", data)
                for image in image_files:
                    archive.write(image, f"receipt_images/{image.relative_to(image_dir).as_posix()}")
        except (OSError, zipfile.BadZipFile) as exc:
            raise GitHubSyncError(f"无法打包本机账本数据：{exc}") from exc
        bundle = destination.read_bytes()
        if max_bundle_bytes is not None and len(bundle) > max_bundle_bytes:
            if max_bundle_error:
                raise GitHubSyncError(max_bundle_error)
            if max_bundle_bytes == MAX_SYNC_BUNDLE_BYTES:
                raise GitHubSyncError("同步包超过 60 MB；请减少小票图片后重试。")
            raise GitHubSyncError("恢复前本机备份超过 512 MB，无法安全继续恢复。")
        return bundle


def restore_sync_bundle(
    bundle: bytes,
    database_path: Path,
    *,
    payment_store: PaymentPromptStore | None = None,
    bookkeeping_skill_store: BookkeepingSkillStore | None = None,
    food_skill_store: FoodHealthSkillStore | None = None,
    receipt_image_directory: Path | None = None,
    backup_directory: Path | None = None,
    backup_provider: str = "github",
    skill_restore_directory: Path | None = None,
) -> Path:
    payment_store = payment_store or PaymentPromptStore()
    bookkeeping_skill_store = bookkeeping_skill_store or BookkeepingSkillStore()
    food_skill_store = food_skill_store or FoodHealthSkillStore()
    image_dir = receipt_image_directory or database_path.parent / "receipt_images"
    backup_dir = backup_directory or database_path.parent.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    provider = "gitee" if backup_provider.casefold() == "gitee" else "github"
    local_backup = backup_dir / f"before-{provider}-restore-{stamp}.zip"
    suffix = 1
    while local_backup.exists():
        local_backup = backup_dir / f"before-{provider}-restore-{stamp}-{suffix}.zip"
        suffix += 1

    with tempfile.TemporaryDirectory(prefix="household-github-restore-") as temp_name:
        temp = Path(temp_name)
        incoming = temp / "incoming.zip"
        incoming.write_bytes(bundle)
        extract_dir = temp / "extracted"
        extract_dir.mkdir()
        try:
            with zipfile.ZipFile(incoming) as archive:
                unpacked_size = 0
                for info in archive.infolist():
                    name = PurePosixPath(info.filename)
                    if name.is_absolute() or ".." in name.parts or not name.parts:
                        raise GitHubSyncError("同步包包含无效文件路径，已拒绝恢复。")
                    unpacked_size += info.file_size
                    if unpacked_size > MAX_UNPACKED_BUNDLE_BYTES:
                        raise GitHubSyncError("同步包解压后超过 512 MB，已拒绝恢复。")
                    if info.is_dir():
                        continue
                    allowed = (
                        info.filename in {"manifest.json", "ledger.sqlite3", "payment_prompts.json"}
                        or info.filename in {"skills/bookkeeping.md", "skills/food_health.md"}
                        or info.filename.startswith("receipt_images/")
                    )
                    if not allowed:
                        raise GitHubSyncError("同步包包含不支持的文件，已拒绝恢复。")
                    target = extract_dir.joinpath(*name.parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(info) as source, target.open("wb") as destination:
                        shutil.copyfileobj(source, destination)
        except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
            if isinstance(exc, GitHubSyncError):
                raise
            raise GitHubSyncError("云端同步包损坏或无法解压。") from exc

        manifest_path = extract_dir / "manifest.json"
        ledger_path = extract_dir / "ledger.sqlite3"
        payment_path = extract_dir / "payment_prompts.json"
        if not manifest_path.is_file() or not ledger_path.is_file():
            raise GitHubSyncError("云端同步包缺少账本或清单。")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if (
                not isinstance(manifest, dict)
                or isinstance(manifest.get("version"), bool)
                or manifest.get("version") not in {1, 2, 3}
            ):
                raise ValueError("unsupported sync bundle version")
            if manifest["version"] == 3:
                raw_scope = manifest.get("scope")
                if not isinstance(raw_scope, dict) or any(
                    not isinstance(raw_scope.get(key), bool) for key in BACKUP_SCOPE_KEYS
                ):
                    raise ValueError("invalid scope")
                restore_scope = normalize_backup_scope(raw_scope)
                if not any(restore_scope.values()):
                    raise ValueError("empty scope")
            else:
                # Older bundles always contained all database and payment data.
                restore_scope = dict(DEFAULT_BACKUP_SCOPE)
        except (OSError, UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise GitHubSyncError(
                "云端同步包清单无效或版本不兼容，当前本机账本保持不变。"
            ) from exc

        payment: dict[str, Any] | None = None
        if restore_scope["payment_methods"]:
            if not payment_path.is_file():
                raise GitHubSyncError("云端同步包缺少已勾选的付款方式。")
            try:
                raw_payment = json.loads(payment_path.read_text(encoding="utf-8"))
                # Earlier sync writers serialized PaymentPromptStore.load(), which
                # strips the on-disk version field for both empty and populated
                # settings. Accept that legacy shape, then validate it below.
                if (
                    isinstance(raw_payment, dict)
                    and "version" not in raw_payment
                    and isinstance(raw_payment.get("profiles"), list)
                ):
                    raw_payment["version"] = 1
                payment = PaymentPromptStore._parse_settings(raw_payment)
            except (OSError, UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
                raise GitHubSyncError(
                    "云端同步包付款方式文件无效或版本不兼容，当前本机账本保持不变。"
                ) from exc

        try:
            connection = sqlite3.connect(ledger_path)
            try:
                integrity = connection.execute("PRAGMA integrity_check").fetchone()
                foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
            finally:
                connection.close()
            if not integrity or integrity[0] != "ok" or foreign_keys:
                raise sqlite3.DatabaseError("integrity check failed")
        except sqlite3.Error as exc:
            raise GitHubSyncError(
                "云端同步包账本数据库无法读取或完整性检查失败，当前本机账本保持不变。"
            ) from exc

        # Preserve all current local data before replacing any of it.
        create_sync_bundle(
            database_path,
            local_backup,
            payment_store=payment_store,
            bookkeeping_skill_store=bookkeeping_skill_store,
            food_skill_store=food_skill_store,
            receipt_image_directory=image_dir,
            include_scope=DEFAULT_BACKUP_SCOPE,
            max_bundle_bytes=MAX_UNPACKED_BUNDLE_BYTES,
            max_bundle_error="恢复前本机备份超过 512 MB，无法安全继续恢复。",
        )

        _apply_local_database_preferences(ledger_path, _local_database_preferences(database_path))
        database_path.parent.mkdir(parents=True, exist_ok=True)
        staged_database = database_path.with_name(f"{database_path.name}.{provider}-{uuid.uuid4().hex}.tmp")
        try:
            shutil.copyfile(ledger_path, staged_database)
            with staged_database.open("rb+") as stream:
                os.fsync(stream.fileno())
            os.replace(staged_database, database_path)
        except OSError as exc:
            staged_database.unlink(missing_ok=True)
            raise GitHubSyncError(f"无法替换本机账本；恢复前备份保存在：{local_backup}") from exc

        try:
            if payment is not None:
                payment_store.save_profiles(payment["profiles"])
            if restore_scope["settings"]:
                _restore_skill(extract_dir, "bookkeeping.md", bookkeeping_skill_store, "bookkeeping", provider, skill_restore_directory)
                _restore_skill(extract_dir, "food_health.md", food_skill_store, "food_health", provider, skill_restore_directory)
            if restore_scope["bills"]:
                _restore_receipt_images(extract_dir / "receipt_images", image_dir, provider)
        except (OSError, ValueError, RuntimeError) as exc:
            raise GitHubSyncError(
                f"账本已恢复，但部分支付规则、Skill 或图片未能应用。恢复前备份保存在：{local_backup}。错误：{exc}"
            ) from exc
    return local_backup


def _restore_skill(
    extracted: Path,
    filename: str,
    store: BookkeepingSkillStore,
    kind: str,
    provider: str = "github",
    destination_directory: Path | None = None,
) -> None:
    archived = extracted / "skills" / filename
    if not archived.exists():
        store.clear()
        return
    content = archived.read_text(encoding="utf-8")
    destination = (destination_directory or _app_data_dir() / f"{provider}_synced_skills") / filename
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, destination)
    store.save_path(destination)


def _restore_receipt_images(archived: Path, destination: Path, provider: str = "github") -> None:
    staged = destination.with_name(f"{destination.name}.{provider}-new-{uuid.uuid4().hex}")
    previous = destination.with_name(f"{destination.name}.{provider}-old-{uuid.uuid4().hex}")
    try:
        if archived.exists():
            shutil.copytree(archived, staged)
        else:
            staged.mkdir(parents=True)
        if destination.exists():
            os.replace(destination, previous)
        os.replace(staged, destination)
    except OSError:
        if destination.exists() and previous.exists():
            shutil.rmtree(destination, ignore_errors=True)
            os.replace(previous, destination)
        raise
    finally:
        shutil.rmtree(staged, ignore_errors=True)
        shutil.rmtree(previous, ignore_errors=True)
