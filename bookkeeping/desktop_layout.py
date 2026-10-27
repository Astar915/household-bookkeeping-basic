"""Device-only desktop layout preferences."""
from __future__ import annotations

import json
import os
from pathlib import Path

from .user_data import app_data_directory


DEFAULT_SIDEBAR_WIDTH = 370
MIN_SIDEBAR_WIDTH = 220
MAX_SIDEBAR_WIDTH = 480
MIN_CONTENT_WIDTH = 440
SASH_WIDTH = 8


class DesktopLayoutStore:
    """Persist resizable desktop pane dimensions outside the financial ledger."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or app_data_directory() / "desktop_layout.json"

    def load_sidebar_width(self) -> int:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return DEFAULT_SIDEBAR_WIDTH
        width = payload.get("sidebar_width") if isinstance(payload, dict) else None
        if isinstance(width, bool) or not isinstance(width, int):
            return DEFAULT_SIDEBAR_WIDTH
        return max(MIN_SIDEBAR_WIDTH, min(MAX_SIDEBAR_WIDTH, width))

    def save_sidebar_width(self, width: int) -> None:
        if isinstance(width, bool) or not isinstance(width, int):
            raise ValueError("Sidebar width must be an integer")
        value = max(MIN_SIDEBAR_WIDTH, min(MAX_SIDEBAR_WIDTH, width))
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(
                json.dumps({"version": 1, "sidebar_width": value}, indent=2),
                encoding="utf-8",
            )
            os.replace(temporary, self.path)
        except OSError:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise
