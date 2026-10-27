import io
import sqlite3
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "container"))
import gateway


class GatewayArchiveTests(unittest.TestCase):
    def test_application_is_not_ready_before_it_starts(self):
        instance = gateway.Gateway.__new__(gateway.Gateway)
        instance.app_process = None
        self.assertFalse(instance.application_ready())

    def test_round_trip_keeps_database_and_configuration(self):
        with tempfile.TemporaryDirectory(prefix="household-cloud-archive-test-") as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            database = source / "ledger.sqlite3"
            connection = sqlite3.connect(database)
            try:
                connection.execute("CREATE TABLE entries(id INTEGER PRIMARY KEY, description TEXT)")
                connection.execute("INSERT INTO entries(description) VALUES(?)", ("smoke test",))
                connection.commit()
            finally:
                connection.close()
            (source / "settings.enc").write_bytes(b"encrypted-test-settings")
            gateway.DATA_DIR = source
            archive_path = gateway.build_archive()
            try:
                gateway.DATA_DIR = root / "restored"
                gateway.restore_archive(archive_path.read_bytes())
                restored = gateway.DATA_DIR / "ledger.sqlite3"
                connection = sqlite3.connect(restored)
                try:
                    result = connection.execute("SELECT description FROM entries WHERE id=1").fetchone()
                    integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
                finally:
                    connection.close()
                self.assertEqual(result, ("smoke test",))
                self.assertEqual(integrity, "ok")
                self.assertEqual((gateway.DATA_DIR / "settings.enc").read_bytes(), b"encrypted-test-settings")
            finally:
                archive_path.unlink(missing_ok=True)

    def test_restore_rejects_parent_traversal(self):
        with tempfile.TemporaryDirectory(prefix="household-cloud-archive-test-") as temporary:
            root = Path(temporary)
            gateway.DATA_DIR = root / "restored"
            stream = io.BytesIO()
            with tarfile.open(fileobj=stream, mode="w:gz") as archive:
                content = b"not allowed"
                entry = tarfile.TarInfo("../escape.txt")
                entry.size = len(content)
                archive.addfile(entry, io.BytesIO(content))
            with self.assertRaises(ValueError):
                gateway.restore_archive(stream.getvalue())
            self.assertFalse((root / "escape.txt").exists())

    def test_request_body_reader_accepts_chunked_proxy_bodies(self):
        handler = object.__new__(gateway.Handler)
        handler.headers = {"Transfer-Encoding": "chunked"}
        handler.rfile = io.BytesIO(b"4\r\ntest\r\n3\r\n123\r\n0\r\nX-Test: ok\r\n\r\n")
        self.assertEqual(handler._read_body(16), b"test123")

    def test_request_body_reader_rejects_oversized_chunked_bodies(self):
        handler = object.__new__(gateway.Handler)
        handler.headers = {"Transfer-Encoding": "chunked"}
        handler.rfile = io.BytesIO(b"5\r\nlarge\r\n0\r\n\r\n")
        with self.assertRaises(OverflowError):
            handler._read_body(4)


if __name__ == "__main__":
    unittest.main()
