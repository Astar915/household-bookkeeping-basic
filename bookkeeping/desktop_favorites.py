from __future__ import annotations

import json
import os
from pathlib import Path

from .user_data import app_data_directory


DEFAULT_FAVORITES = ("accounts", "payments", "reports")
VALID_FAVORITES = frozenset({
    "accounts", "cash", "credit", "payments", "reports", "fixed_assets", "food", "backup", "skills",
})


class DesktopFavoriteStore:
    """Persist the desktop sidebar shortcuts as a local, device-only preference."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or app_data_directory() / "desktop_favorites.json"

    def load(self) -> list[str]:
        if not self.path.exists():
            return list(DEFAULT_FAVORITES)
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return list(DEFAULT_FAVORITES)
        values = payload.get("favorites") if isinstance(payload, dict) else None
        if not isinstance(values, list):
            return list(DEFAULT_FAVORITES)
        result: list[str] = []
        for value in values:
            if isinstance(value, str) and value in VALID_FAVORITES and value not in result:
                result.append(value)
        return result

    def save(self, favorites: list[str]) -> None:
        values = []
        for value in favorites:
            if value in VALID_FAVORITES and value not in values:
                values.append(value)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(
                json.dumps({"version": 1, "favorites": values}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(temporary, self.path)
        except OSError:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise
