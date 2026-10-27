from __future__ import annotations

import os
from pathlib import Path


def app_data_directory() -> Path:
    """Return this app's per-user settings directory, with an optional isolated override."""
    override = os.environ.get("HOUSEHOLD_BOOKKEEPING_APP_DATA")
    if override:
        return Path(override).expanduser()
    roaming = os.environ.get("APPDATA")
    base = Path(roaming) if roaming else Path.home() / "AppData" / "Roaming"
    return base / "HouseholdBookkeeping"
