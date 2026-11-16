from __future__ import annotations

import base64
import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

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


def _snapshot_api():
    from .sync_snapshot import SNAPSHOT_ROOT
    return SNAPSHOT_ROOT


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

    def __init__(self, token: str, *, opener: Callable[..., Any] | None = None) -> None:
        if not token.strip():
            raise GiteeAuthError("请先连接 Gitee。")
        self.token = token.strip()
        self.opener = opener

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
        allow_array: bool = False,
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
            with (self.opener or urllib.request.urlopen)(request, timeout=timeout) as response:
                raw = response.read(MAX_GITEE_SYNC_BUNDLE_BYTES * 2 + 1)
            result = json.loads(raw.decode("utf-8")) if raw else {}
            # Gitee's contents endpoint can represent a not-yet-created file
            # as an empty JSON array instead of an HTTP 404. Callers probing
            # for the sync bundle treat that shape as "no snapshot yet".
            if empty_array_is_missing and result == []:
                return {}
            if not isinstance(result, dict) and not (allow_array and isinstance(result, list)):
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

    def _request_json_payload(self, path: str, *, method: str, payload: dict[str, Any], timeout: float = 180):
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(
            self._url(path), data=body,
            headers={"Accept": "application/json", "Content-Type": "application/json",
                     "User-Agent": "HouseholdBookkeeping/1.0"},
            method=method,
        )
        try:
            with (self.opener or urllib.request.urlopen)(request, timeout=timeout) as response:
                raw = response.read(MAX_GITEE_SYNC_BUNDLE_BYTES * 4 + 1)
            result = json.loads(raw.decode("utf-8")) if raw else {}
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
                raise GiteeNotFound(details or "Gitee 仓库或文件不存在。") from exc
            if exc.code in {401, 403}:
                raise GiteeAuthError("Gitee 令牌无效或权限不足；请检查仓库读写权限。") from exc
            if exc.code in {409, 422}:
                raise GiteeSyncConflict("Gitee 云端目录已被其他设备更新；本次提交未覆盖云端数据。") from exc
            if exc.code == 413:
                raise GiteeSyncError("Gitee 拒绝了过大的分区提交；请减少小票图片后重试。") from exc
            raise GiteeSyncError(details or f"Gitee 请求失败（HTTP {exc.code}）。") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise GiteeSyncError("无法连接 Gitee；请检查网络连接后重试。") from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GiteeSyncError("Gitee 返回的数据无法读取。") from exc

    def _request_raw(self, path: str, *, timeout: float = 90, limit: int = MAX_GITEE_SYNC_BUNDLE_BYTES) -> bytes:
        request = urllib.request.Request(
            self._url(path),
            headers={
                "Accept": "application/octet-stream",
                "User-Agent": "HouseholdBookkeeping/1.0",
            },
        )
        try:
            with (self.opener or urllib.request.urlopen)(request, timeout=timeout) as response:
                data = response.read(limit + 1)
            if len(data) > limit:
                raise GiteeSyncError("Gitee 云端文件超过安全大小限制，无法下载。")
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
    def _contents_path_for(repository: str, file_path: str) -> str:
        owner, repo = repository.split("/", 1)
        return "/repos/{}/{}/contents/{}".format(
            urllib.parse.quote(owner, safe=""), urllib.parse.quote(repo, safe=""),
            urllib.parse.quote(file_path, safe="/"),
        )

    @staticmethod
    def _raw_path(repository: str) -> str:
        owner, repo = repository.split("/", 1)
        return "/repos/{}/{}/raw/{}".format(
            urllib.parse.quote(owner, safe=""),
            urllib.parse.quote(repo, safe=""),
            urllib.parse.quote(GITEE_SYNC_FILE_PATH, safe="/"),
        )

    @staticmethod
    def _raw_path_for(repository: str, file_path: str) -> str:
        owner, repo = repository.split("/", 1)
        return "/repos/{}/{}/raw/{}".format(
            urllib.parse.quote(owner, safe=""), urllib.parse.quote(repo, safe=""),
            urllib.parse.quote(file_path, safe="/"),
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

    def _snapshot_content(self, repository: str):
        from .sync_snapshot import SnapshotFormatError, parse_manifest
        path = self._contents_path_for(repository, _snapshot_api() + "/manifest.json")
        try:
            result = self._request_json(path, empty_array_is_missing=True)
        except GiteeNotFound:
            return None, None, None
        if not result:
            return None, None, None
        sha = result.get("sha")
        encoded = result.get("content")
        if not isinstance(sha, str) or not sha:
            raise GiteeSyncError("Gitee 未返回分区备份版本编号。")
        if not isinstance(encoded, str) or not encoded:
            raise GiteeSyncError("Gitee 分区备份清单缺少内容。")
        try:
            payload = base64.b64decode(encoded)
            manifest = parse_manifest(payload)
        except (ValueError, SnapshotFormatError) as exc:
            raise GiteeSyncError("Gitee 分区备份清单无效。") from exc
        actual_sha = hashlib.sha1(f"blob {len(payload)}\0".encode("ascii") + payload).hexdigest()
        if actual_sha != sha:
            raise GiteeSyncError("Gitee 分区备份清单校验失败。")
        return manifest, sha, str(result.get("last_commit_id") or "")

    def read_snapshot_manifest(self, repository: str, etag: str | None = None):
        manifest, sha, _last_commit_id = self._snapshot_content(repository)
        if manifest is not None and sha:
            self._snapshot_manifest_cache = (sha, manifest)
        return manifest, sha, None, False

    def cloud_revision(self, repository: str) -> str | None:
        _manifest, sha, _last_commit_id = self._snapshot_content(repository)
        return sha or self.bundle_sha(repository)

    def bundle_snapshot_with_etag(self, repository: str, etag: str | None = None):
        manifest, sha, _last_commit_id = self._snapshot_content(repository)
        if manifest is not None:
            self._snapshot_manifest_cache = (sha, manifest)
            return sha, None, False, None
        # Gitee does not expose an ETag through the contents endpoint; SHA is
        # still a stable no-download revision check for the legacy bundle.
        return self.bundle_sha(repository), None, False, None

    def upload_snapshot(self, repository: str, plan, *, expected_sha: str | None = None) -> str:
        """Submit the changed files and new manifest as one Gitee commit."""
        from .sync_snapshot import SNAPSHOT_ROOT, SnapshotFormatError, snapshot_manifest_bytes

        manifest_body = snapshot_manifest_bytes(plan.manifest)
        if sum(len(body) for body in plan.changed.values()) + len(manifest_body) > MAX_GITEE_SYNC_BUNDLE_BYTES:
            raise GiteeSyncError("本次 Gitee 分区提交超过 45 MiB；请减少小票图片后重试。")
        current_revision = self.cloud_revision(repository)
        if expected_sha != current_revision:
            raise GiteeSyncConflict("Gitee 云端备份在本机准备期间发生变化，本次没有覆盖云端数据；请刷新后重试。")
        if plan.unchanged:
            return current_revision or hashlib.sha1(f"blob {len(manifest_body)}\0".encode("ascii") + manifest_body).hexdigest()

        owner, repo = repository.split("/", 1)
        repo_path = f"/repos/{urllib.parse.quote(owner, safe='')}/{urllib.parse.quote(repo, safe='')}"
        repo_info = self._request_json(repo_path)
        branch = str(repo_info.get("default_branch") or "master")
        if self.cloud_revision(repository) != expected_sha:
            raise GiteeSyncConflict("Gitee 云端备份已被其他设备更新；本次上传已取消。")

        actions = []
        new_items = dict(plan.changed)
        old_files = set()
        old_manifest, _old_sha, _old_commit = self._snapshot_content(repository)
        if old_manifest:
            old_files = set(old_manifest["files"])
        changes = sorted(set(plan.changed) | set(plan.deleted))
        # Existing file updates/deletes carry last_commit_id so Gitee refuses a
        # stale writer. New files are created. The manifest is included in the
        # same multi-action commit and acts as the atomic revision pointer.
        existing_metadata = {}
        for relative in changes:
            if relative not in old_files:
                continue
            actual = f"{SNAPSHOT_ROOT}/{relative}"
            try:
                self._request_json(
                    self._contents_path_for(repository, actual),
                )
            except GiteeNotFound as exc:
                raise GiteeSyncConflict("Gitee 分区文件缺失或已被手动更改；本次上传已取消。") from exc
            history = self._request_json(
                f"{repo_path}/commits", params={"path": actual, "per_page": 1}, allow_array=True,
            )
            if not isinstance(history, list) or not history or not isinstance(history[0], dict):
                raise GiteeSyncError("Gitee 未返回分区文件的冲突校验版本。")
            commit_id = history[0].get("sha")
            if not isinstance(commit_id, str) or not commit_id:
                raise GiteeSyncError("Gitee 未返回分区文件的冲突校验版本。")
            existing_metadata[relative] = {"last_commit_id": commit_id}
        for relative, body in sorted(new_items.items()):
            actual = f"{SNAPSHOT_ROOT}/{relative}" if relative != "manifest.json" else f"{SNAPSHOT_ROOT}/manifest.json"
            old = existing_metadata.get(relative)
            action = {"action": "update" if old else "create", "path": actual,
                      "content": base64.b64encode(body).decode("ascii"), "encoding": "base64"}
            if old:
                commit_id = old.get("last_commit_id")
                if not isinstance(commit_id, str) or not commit_id:
                    raise GiteeSyncError("Gitee 未返回分区文件的冲突校验版本。")
                action["last_commit_id"] = commit_id
            actions.append(action)
        for relative in plan.deleted:
            old = existing_metadata.get(relative)
            if not old:
                continue
            commit_id = old.get("last_commit_id")
            if not isinstance(commit_id, str) or not commit_id:
                raise GiteeSyncError("Gitee 未返回待删除分区文件的冲突校验版本。")
            actions.append({"action": "delete", "path": f"{SNAPSHOT_ROOT}/{relative}",
                            "last_commit_id": commit_id})
        # The manifest must be the final action so clients never observe a
        # revision that points to files from an incomplete commit.
        manifest_info = None
        if old_manifest:
            history = self._request_json(
                f"{repo_path}/commits",
                params={"path": f"{SNAPSHOT_ROOT}/manifest.json", "per_page": 1},
                allow_array=True,
            )
            if not isinstance(history, list) or not history or not isinstance(history[0], dict):
                raise GiteeSyncError("Gitee 未返回清单的冲突校验版本。")
            manifest_info = {"last_commit_id": history[0].get("sha")}
        manifest_action = {"action": "update" if manifest_info else "create",
                           "path": f"{SNAPSHOT_ROOT}/manifest.json",
                           "content": base64.b64encode(manifest_body).decode("ascii"), "encoding": "base64"}
        if manifest_info:
            commit_id = manifest_info.get("last_commit_id")
            if not isinstance(commit_id, str) or not commit_id:
                raise GiteeSyncError("Gitee 未返回清单的冲突校验版本。")
            manifest_action["last_commit_id"] = commit_id
        actions.append(manifest_action)
        if self.cloud_revision(repository) != expected_sha:
            raise GiteeSyncConflict("Gitee 云端目录已被其他设备更新；本次上传已取消。")
        payload = {"branch": branch, "message": "Update household bookkeeping snapshot", "actions": actions}
        encoded_payload = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(encoded_payload) > MAX_GITEE_SYNC_BUNDLE_BYTES * 2:
            raise GiteeSyncError("本次 Gitee 提交请求超过安全大小限制；请减少同步内容后重试。")
        self._request_json_payload(f"{repo_path}/commits", method="POST", payload=payload, timeout=240)
        expected_manifest_sha = hashlib.sha1(f"blob {len(manifest_body)}\0".encode("ascii") + manifest_body).hexdigest()
        _verified_manifest, verified_sha, _commit_id = self._snapshot_content(repository)
        if verified_sha != expected_manifest_sha:
            raise GiteeSyncError("Gitee 未确认完整分区提交；请重新检查云端版本。")
        return expected_manifest_sha

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

    def download_bundle_with_revision(self, repository: str, *, initial_sha: str | None = None,
                                      initial_etag: str | None = None, initial_data: bytes | None = None) -> tuple[bytes, str]:
        from .sync_snapshot import (
            MAX_ARCHIVE_BYTES, SnapshotFormatError, materialize_snapshot_bundle,
            snapshot_from_repository_archive,
        )
        manifest, manifest_sha, _last_commit_id = self._snapshot_content(repository)
        if manifest is not None:
            if initial_sha and initial_sha != manifest_sha:
                raise GiteeSyncConflict("Gitee 分区备份已变化，请重新恢复。")
            owner, repo = repository.split("/", 1)
            path = f"/repos/{urllib.parse.quote(owner, safe='')}/{urllib.parse.quote(repo, safe='')}/zipball"
            archive_body = self._request_raw(path, timeout=180, limit=MAX_ARCHIVE_BYTES)
            try:
                parsed_manifest, blobs = snapshot_from_repository_archive(archive_body, manifest_sha or "")
                bundle = materialize_snapshot_bundle(parsed_manifest, blobs)
            except SnapshotFormatError as exc:
                raise GiteeSyncError(str(exc)) from exc
            if self.cloud_revision(repository) != manifest_sha:
                raise GiteeSyncConflict("下载期间 Gitee 云端目录发生变化，请重新恢复。")
            return bundle, str(manifest_sha)
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

    def download_snapshot_delta_with_revision(
        self, repository: str, local_files: dict[str, bytes], *, expected_sha: str,
        manifest: dict[str, Any] | None = None,
    ) -> tuple[bytes, str]:
        """Restore a folder snapshot while downloading only changed file objects."""
        from .sync_snapshot import (
            SNAPSHOT_ROOT, SnapshotFormatError, materialize_snapshot_delta, snapshot_manifest_bytes,
        )

        revision = None
        if manifest is None:
            manifest, revision, _last_commit_id = self._snapshot_content(repository)
        else:
            payload = snapshot_manifest_bytes(manifest)
            revision = hashlib.sha1(f"blob {len(payload)}\0".encode("ascii") + payload).hexdigest()
        if manifest is None or revision != expected_sha:
            raise GiteeSyncConflict("Gitee 分区备份已变化，请重新检查后再恢复。")

        def fetch_file(relative: str, descriptor: dict[str, Any]) -> bytes:
            try:
                size = int(descriptor["size"])
            except (KeyError, TypeError, ValueError) as exc:
                raise GiteeSyncError("Gitee 分区文件大小无效。") from exc
            if size > MAX_GITEE_SYNC_BUNDLE_BYTES:
                raise GiteeSyncError("Gitee 分区文件超过安全大小限制。")
            return self._request_raw(
                self._raw_path_for(repository, f"{SNAPSHOT_ROOT}/{relative}"),
                timeout=90, limit=size,
            )

        try:
            bundle = materialize_snapshot_delta(manifest, local_files, fetch_file)
        except SnapshotFormatError as exc:
            raise GiteeSyncError(str(exc)) from exc
        if self.cloud_revision(repository) != revision:
            raise GiteeSyncConflict("下载期间 Gitee 云端目录发生变化，请重新恢复。")
        return bundle, str(revision)

    def download_bundle(self, repository: str) -> bytes:
        data, _revision = self.download_bundle_with_revision(repository)
        return data
