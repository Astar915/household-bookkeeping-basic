"""Device appearance preference; no ledger or authorization data."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile

from .user_data import app_data_directory

APPEARANCE_CHOICES = (("system", "跟随系统"), ("light", "浅色模式"), ("dark", "深色模式"))


def load_appearance() -> str:
    try:
        value = json.loads((app_data_directory() / "appearance.json").read_text(encoding="utf-8"))
        mode = value.get("mode", "system")
        return mode if mode in {"system", "light", "dark"} else "system"
    except (OSError, ValueError, AttributeError):
        return "system"


def save_appearance(mode: str) -> None:
    if mode not in {"system", "light", "dark"}:
        raise ValueError("Invalid appearance mode")
    directory = app_data_directory()
    directory.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix="appearance-", suffix=".tmp", dir=directory)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump({"mode": mode}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(directory / "appearance.json")
    finally:
        temporary.unlink(missing_ok=True)
