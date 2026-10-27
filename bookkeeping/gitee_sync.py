from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .secure_settings import SecureSettingsError, _windows_crypt
from .user_data import app_data_directory


GITEE_API = "https://gitee.com/api/v5"
GITEE_TOKEN_SETTINGS_URL = "https://gitee.com/profile/personal_access_tokens"
GITEE_SYNC_FILE_PATH = "household-bookkeeping/sync-bundle.zip"
# Gitee's free plan limits an individual repository file to 50 MB. Keep headroom
# below that limit for the API's base64/form encoding overhead and server variance.
MAX_GITEE_SYNC_BUNDLE_BYTES = 45 * 1024 * 1024
DEFAULT_GITEE_BACKUP_REPOSITORY_NAME = "household-bookkeeping-data"
_GITEE_ENTROPY = b"household-bookkeeping-gitee-token-v1"
_EXPECTED_SHA_UNSET = object()


def _app_data_dir() -> Path:
    return app_data_directory()


class GiteeSyncError(RuntimeError):
    """A Gitee sync or archive operation failed with a user-readable message."""


class GiteeNotFound(GiteeSyncError):
    pass


class GiteeAuthError(GiteeSyncError):
    pass


class GiteeSyncConflict(GiteeSyncError):
    """A Gitee snapshot changed since this device last synchronized."""


class GiteeAutoSyncSettingsError(GiteeSyncError):
    pass


class GiteeSyncSettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or _app_data_dir() / "gitee_sync.json"

    def load(self) -> dict[str, str]:
        if not self.path.exists():
            return {
                "repository_name": DEFAULT_GITEE_BACKUP_REPOSITORY_NAME,
                "repository": "",
                "last_sync_sha": "",
            }
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(value, dict) or value.get("version") != 1:
                raise ValueError("unsupported settings version")
            revision = value.get("last_sync_sha", "")
            if not isinstance(revision, str):
                raise ValueError("last_sync_sha must be a string")
            return {
                "repository_name": str(
                    value.get("repository_name") or DEFAULT_GITEE_BACKUP_REPOSITORY_NAME
                ).strip(),
                "repository": str(value.get("repository") or "").strip(),
                "last_sync_sha": revision.strip(),
            }
        except (OSError, UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise GiteeSyncError("Gitee 同步设置无法读取；请重新连接 Gitee。") from exc

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
            except GiteeSyncError:
                existing = {"repository": "", "last_sync_sha": ""}
            checkpoint = (
                existing.get("last_sync_sha", "")
                if existing.get("repository", "").casefold() == repository_value.casefold()
                else ""
            )
        else:
            checkpoint = last_sync_sha.strip()
        payload = {
            "version": 1,
            "repository_name": repository_name.strip(),
            "repository": repository_value,
            "last_sync_sha": checkpoint,
        }
        _atomic_write_json(self.path, payload, "无法保存 Gitee 设置，请检查当前用户配置目录权限。")


class GiteeAutoSyncSettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or _app_data_dir() / "gitee_auto_sync_settings.json"

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
            raise GiteeAutoSyncSettingsError("Gitee 自动同步设置无法读取。") from exc

    def save_enabled(self, enabled: bool) -> None:
        try:
            _atomic_write_json(
                self.path,
                {"version": 1, "enabled": bool(enabled)},
                "无法保存 Gitee 自动同步设置。",
            )
        except GiteeSyncError as exc:
            raise GiteeAutoSyncSettingsError(str(exc)) from exc


def _atomic_write_json(path: Path, value: dict[str, Any], error_message: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(json.dumps(value, ensure_ascii=True, indent=2), encoding="utf-8")
        os.replace(temporary, path)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise GiteeSyncError(error_message) from exc


class GiteeTokenStore:
    """Store the user's Gitee personal access token encrypted with Windows DPAPI."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or _app_data_dir() / "gitee_token.json"

    def load(self) -> str:
        if not self.path.exists():
            return ""
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            encrypted = base64.b64decode(value["token_dpapi"], validate=True)
            return _windows_crypt(
                encrypted,
                decrypt=True,
                entropy_value=_GITEE_ENTROPY,
                description_text="家庭记账 Gitee 访问令牌",
            ).decode("utf-8")
        except SecureSettingsError:
            raise
        except (OSError, UnicodeDecodeError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise SecureSettingsError("本地加密的 Gitee 令牌无法读取；请重新连接。") from exc

    def save(self, token: str) -> None:
        value = token.strip()
        if not value:
            raise SecureSettingsError("Gitee 访问令牌为空，无法保存。")
        encrypted = _windows_crypt(
            value.encode("utf-8"),
            decrypt=False,
            entropy_value=_GITEE_ENTROPY,
            description_text="家庭记账 Gitee 访问令牌",
        )
        payload = {
            "version": 1,
            "token_dpapi": base64.b64encode(encrypted).decode("ascii"),
        }
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
            os.replace(temporary, self.path)
        except OSError as exc:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise SecureSettingsError("无法保存 Gitee 令牌，请检查当前用户配置目录权限。") from exc


class GiteeClient:
    """Minimal Gitee v5 API client for one private backup repository."""

    def __init__(self, token: str) -> None:
        if not token.strip():
            raise GiteeAuthError("请先连接 Gitee。")
        self.token = token.strip()

    def _url(self, path: str, params: dict[str, Any] | None = None) -> str:
        query = {"access_token": self.token}
        query.update({key: value for key, value in (params or {}).items() if value is not None})
        return f"{GITEE_API}{path}?{urllib.parse.urlencode(query)}"

    def _request_json(
        self,
        path: str,
        *,
        method: str = "GET",
        params: dict[str, Any] | None = None,
        form: dict[str, Any] | None = None,
        empty_array_is_missing: bool = False,
        timeout: float = 45,
    ) -> dict[str, Any]:
        headers = {
            "Accept": "application/json",
            "User-Agent": "HouseholdBookkeeping/1.0",
        }
        body = None
        if method == "GET" or method == "DELETE":
            url = self._url(path, params)
        else:
            url = self._url(path, params)
            fields = {"access_token": self.token}
            fields.update({key: value for key, value in (form or {}).items() if value is not None})
            body = urllib.parse.urlencode(fields).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read(MAX_GITEE_SYNC_BUNDLE_BYTES * 2 + 1)
            result = json.loads(raw.decode("utf-8")) if raw else {}
            # Gitee's contents endpoint can represent a not-yet-created file
            # as an empty JSON array instead of an HTTP 404. Callers probing
            # for the sync bundle treat that shape as "no snapshot yet".
            if empty_array_is_missing and result == []:
                return {}
            if not isinstance(result, dict):
                raise GiteeSyncError("Gitee 返回了无法识别的响应。")
            return result
        except urllib.error.HTTPError as exc:
            details = ""
            try:
                parsed = json.loads(exc.read().decode("utf-8", errors="replace"))
                if isinstance(parsed, dict):
                    details = str(parsed.get("message") or parsed.get("error_description") or parsed.get("error") or "")
            except (ValueError, OSError):
                pass
            if exc.code == 404:
                raise GiteeNotFound(details or "Gitee 仓库或同步文件不存在。") from exc
            if exc.code in {401, 403}:
                raise GiteeAuthError(
                    "Gitee 令牌无效或权限不足；请重新生成令牌并勾选 user_info 与 projects 权限。"
                ) from exc
            if exc.code in {409, 422} and method in {"POST", "PUT"}:
                raise GiteeSyncConflict(
                    "Gitee 云端同步文件已发生变化，本次上传未覆盖云端数据。请先恢复云端数据或再次手动上传。"
                ) from exc
            if exc.code == 413:
                raise GiteeSyncError("Gitee 拒绝了过大的同步文件；请减少小票图片后重试。") from exc
            raise GiteeSyncError(details or f"Gitee 请求失败（HTTP {exc.code}）。") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise GiteeSyncError("无法连接 Gitee；请检查网络连接后重试。") from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GiteeSyncError("Gitee 返回的数据无法读取。") from exc

    def _request_raw(self, path: str, *, timeout: float = 90) -> bytes:
        request = urllib.request.Request(
            self._url(path),
            headers={
                "Accept": "application/octet-stream",
                "User-Agent": "HouseholdBookkeeping/1.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data = response.read(MAX_GITEE_SYNC_BUNDLE_BYTES + 1)
            if len(data) > MAX_GITEE_SYNC_BUNDLE_BYTES:
                raise GiteeSyncError("Gitee 同步包超过 45 MiB，无法下载。")
            return data
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise GiteeNotFound("Gitee 仓库中还没有账本备份。") from exc
            if exc.code in {401, 403}:
                raise GiteeAuthError("Gitee 令牌无效或没有读取私有仓库的权限。") from exc
            raise GiteeSyncError(f"下载 Gitee 账本失败（HTTP {exc.code}）。") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise GiteeSyncError("无法连接 Gitee；请检查网络连接后重试。") from exc

    def current_user(self) -> dict[str, Any]:
        return self._request_json("/user")

    def ensure_private_repository(self, login: str, name: str) -> tuple[str, bool]:
        owner = urllib.parse.quote(login, safe="")
        repo = urllib.parse.quote(name, safe="")
        path = f"/repos/{owner}/{repo}"
        try:
            existing = self._request_json(path)
            is_private = existing.get("private") is True or existing.get("public") == 0
            if not is_private:
                raise GiteeSyncError("同名 Gitee 仓库已存在且不是私有仓库；请先改名或设为私有。")
            return str(existing.get("full_name") or f"{login}/{name}"), False
        except GiteeNotFound:
            created = self._request_json(
                "/user/repos",
                method="POST",
                form={
                    "name": name,
                    "description": "Private sync data for Household Bookkeeping",
                    "private": "true",
                    "auto_init": "true",
                    "has_issues": "false",
                    "has_wiki": "false",
                },
                timeout=90,
            )
            return str(created.get("full_name") or f"{login}/{name}"), True

    @staticmethod
    def _contents_path(repository: str) -> str:
        owner, repo = repository.split("/", 1)
        return "/repos/{}/{}/contents/{}".format(
            urllib.parse.quote(owner, safe=""),
            urllib.parse.quote(repo, safe=""),
            urllib.parse.quote(GITEE_SYNC_FILE_PATH, safe="/"),
        )

    @staticmethod
    def _raw_path(repository: str) -> str:
        owner, repo = repository.split("/", 1)
        return "/repos/{}/{}/raw/{}".format(
            urllib.parse.quote(owner, safe=""),
            urllib.parse.quote(repo, safe=""),
            urllib.parse.quote(GITEE_SYNC_FILE_PATH, safe="/"),
        )

    def bundle_sha(self, repository: str) -> str | None:
        try:
            result = self._request_json(
                self._contents_path(repository),
                empty_array_is_missing=True,
            )
        except GiteeNotFound:
            return None
        if not result:
            return None
        sha = result.get("sha")
        if not isinstance(sha, str) or not sha:
            raise GiteeSyncError("Gitee 未返回同步文件版本编号。")
        return sha

    def sync_bundle_exists(self, repository: str) -> bool:
        return self.bundle_sha(repository) is not None

    def upload_bundle(
        self,
        repository: str,
        bundle: bytes,
        *,
        expected_sha: str | None | object = _EXPECTED_SHA_UNSET,
    ) -> str:
        if len(bundle) > MAX_GITEE_SYNC_BUNDLE_BYTES:
            raise GiteeSyncError("Gitee 同步包超过 45 MiB；请减少小票图片后重试。")
        path = self._contents_path(repository)
        current_sha = self.bundle_sha(repository)
        if expected_sha is not _EXPECTED_SHA_UNSET and current_sha != (expected_sha or None):
            raise GiteeSyncConflict(
                "Gitee 云端同步文件已在其他设备更新，本次上传已取消，云端数据未被覆盖。"
                "请先从 Gitee 恢复，或确认后手动上传本机数据。"
            )
        form: dict[str, Any] = {
            "message": "Sync household bookkeeping data",
            "content": base64.b64encode(bundle).decode("ascii"),
        }
        method = "POST"
        if current_sha:
            method = "PUT"
            form["sha"] = current_sha
        result = self._request_json(path, method=method, form=form, timeout=240)
        content = result.get("content")
        sha = content.get("sha") if isinstance(content, dict) else None
        if not isinstance(sha, str) or not sha:
            sha = self.bundle_sha(repository)
        if not sha:
            raise GiteeSyncError("Gitee 未确认同步文件的版本编号；请重新读取云端版本。")
        return sha

    def download_bundle_with_revision(self, repository: str) -> tuple[bytes, str]:
        path = self._raw_path(repository)
        for _attempt in range(3):
            before_sha = self.bundle_sha(repository)
            if before_sha is None:
                raise GiteeNotFound("Gitee 仓库中还没有账本备份。")
            data = self._request_raw(path)
            after_sha = self.bundle_sha(repository)
            if before_sha == after_sha:
                return data, before_sha
        raise GiteeSyncConflict("下载期间 Gitee 云端同步文件发生变化，请重新恢复。")

    def download_bundle(self, repository: str) -> bytes:
        data, _revision = self.download_bundle_with_revision(repository)
        return data
