from __future__ import annotations

import base64
import ctypes
import json
import os
from ctypes import wintypes
from pathlib import Path

from .user_data import app_data_directory


class SecureSettingsError(RuntimeError):
    """The per-user encrypted API key could not be read or written."""


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]


_ENTROPY = b"household-bookkeeping-api-key-v1"


def _make_blob(value: bytes) -> tuple[_DataBlob, ctypes.Array[ctypes.c_byte]]:
    buffer = (ctypes.c_byte * len(value)).from_buffer_copy(value)
    return _DataBlob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer


def _windows_crypt(
    value: bytes,
    *,
    decrypt: bool,
    entropy_value: bytes = _ENTROPY,
    description_text: str = "家庭记账 API Key",
) -> bytes:
    if os.name != "nt":
        raise SecureSettingsError("API Key 的安全保存目前仅支持 Windows DPAPI。")

    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    crypt = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    crypt.argtypes = (
        ctypes.POINTER(_DataBlob),
        ctypes.POINTER(wintypes.LPWSTR) if decrypt else wintypes.LPCWSTR,
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_DataBlob),
    )
    crypt.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = (ctypes.c_void_p,)
    kernel32.LocalFree.restype = ctypes.c_void_p

    source, source_buffer = _make_blob(value)
    entropy, entropy_buffer = _make_blob(entropy_value)
    destination = _DataBlob()
    description = wintypes.LPWSTR()
    try:
        if decrypt:
            succeeded = crypt(
                ctypes.byref(source),
                ctypes.byref(description),
                ctypes.byref(entropy),
                None,
                None,
                0x1,
                ctypes.byref(destination),
            )
        else:
            succeeded = crypt(
                ctypes.byref(source),
                description_text,
                ctypes.byref(entropy),
                None,
                None,
                0x1,
                ctypes.byref(destination),
            )
        if not succeeded:
            code = ctypes.get_last_error()
            raise SecureSettingsError(f"Windows 无法处理加密密钥（错误码 {code}）。")
        return ctypes.string_at(destination.pbData, destination.cbData)
    finally:
        if destination.pbData:
            kernel32.LocalFree(ctypes.cast(destination.pbData, ctypes.c_void_p))
        if description:
            kernel32.LocalFree(ctypes.cast(description, ctypes.c_void_p))
        # Keep source and entropy buffers alive until the Windows call returns.
        _ = (source_buffer, entropy_buffer)


class ApiKeyStore:
    """Store one API key as DPAPI ciphertext in the current user's app data."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or app_data_directory() / "settings.json"

    def load(self) -> str:
        if not self.path.exists():
            return ""
        try:
            saved = json.loads(self.path.read_text(encoding="utf-8"))
            encrypted = base64.b64decode(saved["api_key_dpapi"], validate=True)
            return _windows_crypt(encrypted, decrypt=True).decode("utf-8")
        except SecureSettingsError:
            raise
        except (OSError, UnicodeDecodeError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise SecureSettingsError("本地加密 API Key 无法读取；可在设置中重新保存。") from exc

    def save(self, api_key: str) -> None:
        value = api_key.strip()
        if not value:
            raise SecureSettingsError("API Key 不能为空。")
        encrypted = _windows_crypt(value.encode("utf-8"), decrypt=False)
        payload = json.dumps(
            {"version": 1, "api_key_dpapi": base64.b64encode(encrypted).decode("ascii")},
            ensure_ascii=True,
        )
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
            raise SecureSettingsError("无法写入本地安全设置，请检查用户配置目录权限。") from exc

    def delete(self) -> None:
        try:
            self.path.unlink(missing_ok=True)
        except OSError as exc:
            raise SecureSettingsError("无法删除已保存的 API Key，请检查用户配置目录权限。") from exc


class ApiProfileStore:
    """Persist API endpoint profiles, encrypting each non-empty key with DPAPI."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or app_data_directory() / "api_profiles.json"

    def load(self) -> dict[str, object]:
        if not self.path.exists():
            return {
                "active_profile_id": "",
                "profiles": [],
                "agent_profile_ids": {},
                "agent_vision_profile_ids": {},
            }
        try:
            saved = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(saved, dict):
                raise SecureSettingsError("API服务配置格式无法识别。")
            if saved.get("version") != 1 or not isinstance(saved.get("profiles"), list):
                raise SecureSettingsError("API服务配置格式无法识别。")
            profiles: list[dict[str, object]] = []
            for item in saved["profiles"]:
                if not isinstance(item, dict):
                    raise SecureSettingsError("API服务配置格式无法识别。")
                key_blob = item.get("api_key_dpapi", "")
                if not isinstance(key_blob, str):
                    raise SecureSettingsError("API服务密钥格式无法识别。")
                key = (
                    _windows_crypt(base64.b64decode(key_blob, validate=True), decrypt=True).decode("utf-8")
                    if key_blob
                    else ""
                )
                profile = {
                    "id": item.get("id", ""),
                    "name": item.get("name", ""),
                    "api_url": item.get("api_url", ""),
                    "model": item.get("model", ""),
                    "api_key": key,
                    # Profiles created before these settings existed default to
                    # the lower-token, non-thinking request mode.
                    "thinking_enabled": item.get("thinking_enabled", False),
                    "reasoning_effort": item.get("reasoning_effort", "low"),
                }
                if not all(
                    isinstance(profile[field], str)
                    for field in ("id", "name", "api_url", "model", "api_key")
                ):
                    raise SecureSettingsError("API服务配置格式无法识别。")
                if not isinstance(profile["thinking_enabled"], bool):
                    raise SecureSettingsError("API服务思考模式配置格式无法识别。")
                if not isinstance(profile["reasoning_effort"], str) or profile["reasoning_effort"] not in {
                    "low", "high", "max"
                }:
                    profile["reasoning_effort"] = "low"
                profiles.append(profile)
            active_profile_id = saved.get("active_profile_id", "")
            if not isinstance(active_profile_id, str):
                raise SecureSettingsError("当前API服务配置格式无法识别。")
            raw_agent_profile_ids = saved.get("agent_profile_ids", {})
            if not isinstance(raw_agent_profile_ids, dict):
                raw_agent_profile_ids = {}
            agent_profile_ids = {
                mode: profile_id
                for mode, profile_id in raw_agent_profile_ids.items()
                if isinstance(mode, str) and isinstance(profile_id, str)
            }
            raw_vision_profile_ids = saved.get("agent_vision_profile_ids", {})
            if not isinstance(raw_vision_profile_ids, dict):
                raw_vision_profile_ids = {}
            agent_vision_profile_ids = {
                mode: profile_id
                for mode, profile_id in raw_vision_profile_ids.items()
                if isinstance(mode, str) and isinstance(profile_id, str)
            }
            return {
                "active_profile_id": active_profile_id,
                "profiles": profiles,
                "agent_profile_ids": agent_profile_ids,
                "agent_vision_profile_ids": agent_vision_profile_ids,
            }
        except SecureSettingsError:
            raise
        except (OSError, UnicodeDecodeError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise SecureSettingsError("本机 API 服务配置无法读取；请打开设置重新保存。") from exc

    def save(
        self,
        profiles: list[dict[str, object]],
        active_profile_id: str,
        agent_profile_ids: dict[str, str] | None = None,
        agent_vision_profile_ids: dict[str, str] | None = None,
    ) -> None:
        saved_profiles: list[dict[str, object]] = []
        for profile in profiles:
            key = str(profile.get("api_key", "")).strip()
            encrypted = _windows_crypt(key.encode("utf-8"), decrypt=False) if key else b""
            thinking_enabled = profile.get("thinking_enabled", False)
            if not isinstance(thinking_enabled, bool):
                thinking_enabled = False
            reasoning_effort = profile.get("reasoning_effort", "low")
            if not isinstance(reasoning_effort, str) or reasoning_effort not in {"low", "high", "max"}:
                reasoning_effort = "low"
            saved_profiles.append(
                {
                    "id": str(profile["id"]),
                    "name": str(profile["name"]),
                    "api_url": str(profile["api_url"]),
                    "model": str(profile["model"]),
                    "api_key_dpapi": base64.b64encode(encrypted).decode("ascii"),
                    "thinking_enabled": thinking_enabled,
                    "reasoning_effort": reasoning_effort,
                }
            )
        settings: dict[str, object] = {
            "version": 1,
            "active_profile_id": active_profile_id,
            "profiles": saved_profiles,
        }
        if agent_profile_ids is not None:
            settings["agent_profile_ids"] = dict(agent_profile_ids)
        if agent_vision_profile_ids is not None:
            settings["agent_vision_profile_ids"] = dict(agent_vision_profile_ids)
        payload = json.dumps(settings, ensure_ascii=True)
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
            raise SecureSettingsError("无法写入 API 服务配置，请检查用户配置目录权限。") from exc
