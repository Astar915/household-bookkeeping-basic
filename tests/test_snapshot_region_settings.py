from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime, timezone
import importlib
import io
import sys
import tempfile
import types
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace


PACKAGE_NAME = "web_snapshot_region_under_test"
WORKER_SOURCE = Path(__file__).resolve().parents[1] / "cloudflare-full" / "python-d1" / "src"
WORKER_BOOKKEEPING = WORKER_SOURCE / "bookkeeping"
sys.path.insert(0, str(WORKER_SOURCE))
if PACKAGE_NAME not in sys.modules:
    package = types.ModuleType(PACKAGE_NAME)
    package.__path__ = [str(WORKER_BOOKKEEPING)]
    sys.modules[PACKAGE_NAME] = package
worker_storage = importlib.import_module(f"{PACKAGE_NAME}.storage")
worker_web_features = importlib.import_module(f"{PACKAGE_NAME}.web_features")
worker_backup_scope = importlib.import_module(f"{PACKAGE_NAME}.backup_scope")
sys.path.remove(str(WORKER_SOURCE))


class SnapshotRegionSettingsTests(unittest.TestCase):
    def test_web_backup_carries_region_for_local_restore(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            ledger_dir = root / "ledgers"
            ledger_dir.mkdir()
            workspace = object.__new__(worker_web_features.MobileWorkspace)
            workspace.server = SimpleNamespace(ledger_dir=ledger_dir)
            workspace.root = root / "mobile"
            workspace.lock = lambda _uid: nullcontext()
            workspace.config = lambda _uid: {
                "timeZone": "America/Los_Angeles",
                "scope": dict(worker_backup_scope.DEFAULT_BACKUP_SCOPE),
            }
            workspace.local_now = lambda _uid: datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)

            db = worker_storage.Database(workspace.db_path("a" * 32))
            db.initialize()
            db.add_account(
                name="Test bank", account_type="bank", currency="JPY",
                opening_balance="100", opening_date="2026-01-01",
            )
            db.close()

            _name, body = workspace.backup("a" * 32)
            with zipfile.ZipFile(io.BytesIO(body)) as archive:
                restored_path = root / "restored.sqlite3"
                restored_path.write_bytes(archive.read("ledger.sqlite3"))
            restored = worker_storage.Database(restored_path)
            try:
                restored.initialize()
                self.assertEqual(restored.get_setting("time_zone"), "America/Los_Angeles")
            finally:
                restored.close()


if __name__ == "__main__":
    unittest.main()
