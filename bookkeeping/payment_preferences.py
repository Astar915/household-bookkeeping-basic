from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .user_data import app_data_directory


class PaymentPromptSettingsError(RuntimeError):
    """The user's saved payment prompt preferences could not be read or written."""


class PaymentPromptSettingsConflict(PaymentPromptSettingsError):
    """Another app window changed payment preferences while this editor was open."""


def _settings_path() -> Path:
    return app_data_directory() / "payment_prompts.json"


class PaymentPromptStore:
    """Store payment rules atomically and protect them from stale app windows."""

    _LOCK_TIMEOUT_SECONDS = 15.0

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or _settings_path()

    @property
    def backup_path(self) -> Path:
        return self.path.with_suffix(self.path.suffix + ".bak")

    @property
    def lock_path(self) -> Path:
        return self.path.with_suffix(self.path.suffix + ".lock")

    @contextmanager
    def _locked(self) -> Iterator[None]:
        """Serialize saves/recovery between app instances on Windows and Unix."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+b") as stream:
            if os.name == "nt":
                import msvcrt

                stream.seek(0, os.SEEK_END)
                if stream.tell() == 0:
                    stream.write(b"\0")
                    stream.flush()
                deadline = time.monotonic() + self._LOCK_TIMEOUT_SECONDS
                while True:
                    try:
                        stream.seek(0)
                        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise PaymentPromptSettingsError("支付设置正被另一个窗口保存，请稍后重试。")
                        time.sleep(0.05)
                try:
                    yield
                finally:
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                deadline = time.monotonic() + self._LOCK_TIMEOUT_SECONDS
                while True:
                    try:
                        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        if time.monotonic() >= deadline:
                            raise PaymentPromptSettingsError("支付设置正被另一个窗口保存，请稍后重试。")
                        time.sleep(0.05)
                try:
                    yield
                finally:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _revision_from_file(path: Path) -> int | None:
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
            return None
        if not isinstance(saved, dict):
            return None
        revision = saved.get("revision")
        if isinstance(revision, int) and not isinstance(revision, bool) and revision >= 1:
            return revision
        return None

    def _valid_candidates_locked(self) -> tuple[list[tuple[Path, dict[str, Any], bytes, int | None]], list[Exception]]:
        candidates: list[tuple[Path, dict[str, Any], bytes, int | None]] = []
        errors: list[Exception] = []
        for candidate in (self.path, self.backup_path):
            if not candidate.exists():
                continue
            try:
                payload = candidate.read_bytes()
                settings = self._parse_settings(json.loads(payload.decode("utf-8")))
                revision = self._revision_from_file(candidate)
                candidates.append((candidate, settings, payload, revision))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
                errors.append(exc)
        return candidates, errors

    def _choose_candidate_locked(
        self, candidates: list[tuple[Path, dict[str, Any], bytes, int | None]]
    ) -> tuple[Path, dict[str, Any], bytes, int | None] | None:
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]

        primary, backup = candidates
        primary_rev, backup_rev = primary[3], backup[3]
        if primary_rev is not None and backup_rev is not None and primary_rev != backup_rev:
            return primary if primary_rev > backup_rev else backup
        if primary_rev is not None and backup_rev is None:
            return primary
        if backup_rev is not None and primary_rev is None:
            return backup
        # Legacy files have no revision counter. A newer valid backup can be
        # the only remaining copy of a successful save after a stale writer.
        try:
            if self.backup_path.stat().st_mtime_ns > self.path.stat().st_mtime_ns:
                return backup
        except OSError:
            pass
        return primary

    @staticmethod
    def _digest(payload: bytes | None) -> str:
        return hashlib.sha256(payload if payload is not None else b"<missing-payment-settings>").hexdigest()

    def _load_snapshot_locked(self) -> tuple[dict[str, Any], str, bytes | None, list[tuple[Path, dict[str, Any], bytes, int | None]]]:
        candidates, errors = self._valid_candidates_locked()
        chosen = self._choose_candidate_locked(candidates)
        if chosen is None:
            if errors:
                raise PaymentPromptSettingsError(
                    "支付提示设置及其备份均无法读取；请在软件的‘支付方式与用途’中重新保存。"
                ) from errors[-1]
            settings = {"profiles": [], "default_index": None}
            return settings, self._digest(None), None, candidates

        source, settings, payload, source_revision = chosen
        if source != self.path or not self.path.exists() or self.path.read_bytes() != payload:
            if source != self.path and source_revision is None:
                # Mark a promoted legacy backup so its stale sibling cannot win
                # again merely because the recovery copy was written later.
                prior_revisions = [
                    revision for _path, _settings, _payload, revision in candidates
                    if revision is not None
                ]
                recovered = json.loads(payload.decode("utf-8"))
                recovered["revision"] = max(prior_revisions, default=0) + 1
                payload = json.dumps(
                    recovered, ensure_ascii=False, indent=2
                ).encode("utf-8")
            previous_primary: bytes | None = None
            try:
                if self.path.exists():
                    previous_primary = self.path.read_bytes()
                self._write_bytes_atomically(self.path, payload)
                # Keep the stale but valid primary recoverable after promoting
                # a newer legacy backup. If primary was corrupt/missing, retain
                # the selected valid backup as the recovery copy.
                if previous_primary is not None:
                    try:
                        self._parse_settings(json.loads(previous_primary.decode("utf-8")))
                    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
                        previous_primary = None
                    if previous_primary is not None:
                        self._write_bytes_atomically(self.backup_path, previous_primary)
            except OSError:
                # The selected payload remains usable in memory if repair is
                # blocked; subsequent saves will report the concrete I/O error.
                pass
        return settings, self._digest(payload), payload, candidates

    def load_snapshot(self) -> tuple[dict[str, Any], str]:
        """Return settings and an opaque token for stale-editor detection."""
        try:
            with self._locked():
                settings, revision, _payload, _candidates = self._load_snapshot_locked()
                return settings, revision
        except OSError as exc:
            raise PaymentPromptSettingsError("无法读取支付设置，请检查当前用户配置目录。") from exc

    def load(self) -> dict[str, Any]:
        return self.load_snapshot()[0]

    @staticmethod
    def _parse_settings(saved: Any) -> dict[str, Any]:
        if not isinstance(saved, dict) or saved.get("version") not in {1, 2}:
            raise ValueError("unsupported settings version")
        raw_profiles = saved.get("profiles")
        if not isinstance(raw_profiles, list):
            raise ValueError("profiles must be a list")
        profiles = []
        for raw in raw_profiles:
            if not isinstance(raw, dict):
                raise ValueError("profile must be an object")
            method = raw.get("payment_method")
            purpose = raw.get("purpose", "")
            currency = raw.get("currency", "")
            if not isinstance(method, str) or not isinstance(purpose, str):
                raise ValueError("profile fields must be text")
            if currency is None:
                currency = ""
            if not isinstance(currency, str):
                raise ValueError("profile currency must be text")
            method = method.strip()
            purpose = purpose.strip()
            currency = currency.strip().upper()
            if currency in {"不限", "ANY", "ALL"}:
                currency = ""
            if currency not in {"", "JPY", "CNY"}:
                raise ValueError("profile currency is unsupported")
            if not method:
                raise ValueError("payment method cannot be empty")
            profile = {"payment_method": method, "purpose": purpose}
            if "currency" in raw:
                profile["currency"] = currency
            if "account_order" in raw:
                raw_order = raw.get("account_order")
                if not isinstance(raw_order, list) or not raw_order:
                    raise ValueError("profile account order must be a non-empty list")
                account_order = [
                    item.strip() for item in raw_order
                    if isinstance(item, str) and item.strip()
                ]
                if len(account_order) != len(raw_order) or len(set(account_order)) != len(account_order):
                    raise ValueError("profile account order contains invalid or duplicate accounts")
                profile["account_order"] = account_order
            profiles.append(profile)
        default_index = saved.get("default_index")
        if not profiles:
            default_index = None
        elif default_index is not None and (
            isinstance(default_index, bool)
            or not isinstance(default_index, int)
            or not 0 <= default_index < len(profiles)
        ):
            raise ValueError("default profile is invalid")
        revision = saved.get("revision")
        if revision is not None and (
            isinstance(revision, bool) or not isinstance(revision, int) or revision < 1
        ):
            raise ValueError("settings revision is invalid")
        return {"profiles": profiles, "default_index": default_index}

    @classmethod
    def _load_file(cls, path: Path) -> dict[str, Any]:
        return cls._parse_settings(json.loads(path.read_text(encoding="utf-8")))

    @staticmethod
    def _write_bytes_atomically(path: Path, payload: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f"{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
        try:
            with temporary.open("wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            if os.name != "nt":
                try:
                    directory_fd = os.open(path.parent, os.O_RDONLY)
                    try:
                        os.fsync(directory_fd)
                    finally:
                        os.close(directory_fd)
                except OSError:
                    pass
        except OSError:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    def selected_profile(self) -> dict[str, Any] | None:
        settings = self.load()
        index = settings["default_index"]
        if index is None:
            return None
        return dict(settings["profiles"][index])

    def all_profiles(self) -> list[dict[str, Any]]:
        """Return all scenario-specific payment preferences."""
        return [dict(profile) for profile in self.load()["profiles"]]

    def save_profiles(
        self,
        profiles: Sequence[Mapping[str, Any]],
        *,
        expected_revision: str | None = None,
    ) -> str:
        """Save all profiles, optionally refusing to overwrite a stale editor."""
        return self._save(profiles, None, require_default=False, expected_revision=expected_revision)

    def save(
        self,
        profiles: Sequence[Mapping[str, Any]],
        default_index: int | None,
        *,
        expected_revision: str | None = None,
    ) -> str:
        """Compatibility API for older callers that still select one global default."""
        return self._save(profiles, default_index, require_default=True, expected_revision=expected_revision)

    def _save(
        self,
        profiles: Sequence[Mapping[str, Any]],
        default_index: int | None,
        *,
        require_default: bool,
        expected_revision: str | None,
    ) -> str:
        cleaned: list[dict[str, Any]] = []
        for profile in profiles:
            method = profile.get("payment_method", "").strip()
            purpose = profile.get("purpose", "").strip()
            if not method:
                raise PaymentPromptSettingsError("每种支付方式都要填写名称。")
            cleaned_profile = {"payment_method": method, "purpose": purpose}
            if "currency" in profile:
                currency = str(profile.get("currency") or "").strip().upper()
                if currency in {"不限", "ANY", "ALL"}:
                    currency = ""
                if currency not in {"", "JPY", "CNY"}:
                    raise PaymentPromptSettingsError("适用币种只能选择不限、JPY或CNY。")
                cleaned_profile["currency"] = currency
            if "account_order" in profile:
                raw_order = profile.get("account_order")
                if not isinstance(raw_order, Sequence) or isinstance(raw_order, (str, bytes)) or not raw_order:
                    raise PaymentPromptSettingsError("扣款顺序至少要选择一个账户。")
                account_order = [
                    item.strip() for item in raw_order
                    if isinstance(item, str) and item.strip()
                ]
                if len(account_order) != len(raw_order) or len(set(account_order)) != len(account_order):
                    raise PaymentPromptSettingsError("扣款顺序不能有空账户或重复账户。")
                cleaned_profile["account_order"] = account_order
            cleaned.append(cleaned_profile)
        if cleaned:
            if default_index is None and not require_default:
                pass
            elif isinstance(default_index, bool) or not isinstance(default_index, int) or not 0 <= default_index < len(cleaned):
                raise PaymentPromptSettingsError("请选择一个默认支付方式。")
        else:
            default_index = None

        try:
            with self._locked():
                current, current_revision, current_bytes, candidates = self._load_snapshot_locked()
                if expected_revision is not None and current_revision != expected_revision:
                    raise PaymentPromptSettingsConflict()
                previous_revisions = [
                    revision for _path, _settings, _payload, revision in candidates
                    if revision is not None
                ]
                next_revision = max(previous_revisions, default=0) + 1
                payload = json.dumps(
                    {
                        "version": 2,
                        "revision": next_revision,
                        "profiles": cleaned,
                        "default_index": default_index,
                    },
                    ensure_ascii=False,
                    indent=2,
                ).encode("utf-8")
                if current_bytes is not None:
                    self._write_bytes_atomically(self.backup_path, current_bytes)
                self._write_bytes_atomically(self.path, payload)
                saved = self._load_file(self.path)
                expected = {"profiles": cleaned, "default_index": default_index}
                if saved != expected:
                    raise PaymentPromptSettingsError("支付规则写入后校验不一致，已保留之前的备份；请重试保存。")
                return self._digest(payload)
        except PaymentPromptSettingsConflict:
            raise
        except PaymentPromptSettingsError:
            raise
        except OSError as exc:
            raise PaymentPromptSettingsError("无法保存支付设置，请检查当前用户配置目录权限。") from exc
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise PaymentPromptSettingsError("现有支付设置无法校验；请先恢复或删除损坏的设置文件。") from exc
