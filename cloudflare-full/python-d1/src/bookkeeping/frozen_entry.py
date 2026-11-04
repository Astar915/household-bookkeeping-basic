from __future__ import annotations

import multiprocessing
import os
from pathlib import Path
import sys


def _portable_data_directory() -> Path:
    app_data = os.environ.get("APPDATA")
    roaming = Path(app_data) if app_data else Path.home() / "AppData" / "Roaming"
    return roaming / "HouseholdBookkeeping-Portable"


if getattr(sys, "frozen", False):
    os.environ.setdefault("HOUSEHOLD_BOOKKEEPING_APP_DATA", str(_portable_data_directory()))


if __name__ == "__main__":
    multiprocessing.freeze_support()
    from bookkeeping.gui import main

    main()
