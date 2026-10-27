from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .user_data import app_data_directory


BACKUP_SCOPE_KEYS = (
    "settings",
    "bills",
    "payment_methods",
    "recurring_payments",
    "bank_accounts",
    "credit_cards",
    "assets",
)
DEFAULT_BACKUP_SCOPE = {key: True for key in BACKUP_SCOPE_KEYS}


class BackupScopeError(RuntimeError):
    """Raised when the local cloud-backup inclusion settings cannot be used."""


def normalize_backup_scope(value: Any) -> dict[str, bool]:
    if not isinstance(value, dict):
        raise BackupScopeError("云备份范围设置格式无效。")
    normalized: dict[str, bool] = {}
    for key in BACKUP_SCOPE_KEYS:
        item = value.get(key, True)
        if not isinstance(item, bool):
            raise BackupScopeError(f"云备份范围“{key}”必须是布尔值。")
        normalized[key] = item
    return normalized


class BackupScopeStore:
    """Stores non-sensitive cloud-backup preferences on this Windows account."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or app_data_directory() / "cloud_backup_scope.json"

    def load(self) -> dict[str, bool]:
        if not self.path.exists():
            return dict(DEFAULT_BACKUP_SCOPE)
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or payload.get("version") != 1:
                raise ValueError("unsupported version")
            return normalize_backup_scope(payload.get("include"))
        except (OSError, UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise BackupScopeError(f"云备份范围设置无法读取：{exc}") from exc

    def save(self, scope: Any) -> dict[str, bool]:
        normalized = normalize_backup_scope(scope)
        if not any(normalized.values()):
            raise BackupScopeError("至少选择一项云备份内容。")
        payload = {"version": 1, "include": normalized}
        fd: int | None = None
        temporary: Path | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary_name = tempfile.mkstemp(
                prefix=f"{self.path.name}.", suffix=".tmp", dir=self.path.parent
            )
            temporary = Path(temporary_name)
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                fd = None
                json.dump(payload, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        except OSError as exc:
            if fd is not None:
                os.close(fd)
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            raise BackupScopeError(f"云备份范围设置无法保存：{exc}") from exc
        return normalized
