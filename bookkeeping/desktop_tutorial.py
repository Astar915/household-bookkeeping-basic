from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from .user_data import app_data_directory


class DesktopTutorialStore:
    """Keep first-run tutorial state on this device, keyed to the local ledger."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or app_data_directory() / "desktop_tutorial.json"

    @staticmethod
    def _ledger_key(database_path: Path) -> str:
        normalized = str(database_path.expanduser().resolve()).casefold()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def is_complete(self, database_path: Path) -> bool:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return False
        completed = payload.get("completed", []) if isinstance(payload, dict) else []
        return self._ledger_key(database_path) in completed if isinstance(completed, list) else False

    def mark_complete(self, database_path: Path) -> None:
        completed: list[str] = []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            values = payload.get("completed", []) if isinstance(payload, dict) else []
            if isinstance(values, list):
                completed = [value for value in values if isinstance(value, str)]
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            pass
        key = self._ledger_key(database_path)
        if key not in completed:
            completed.append(key)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(
                json.dumps({"version": 1, "completed": completed}, indent=2),
                encoding="utf-8",
            )
            os.replace(temporary, self.path)
        except OSError:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
