from __future__ import annotations

import gzip
import hmac
import http.client
import io
import os
import shutil
import signal
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit


DATA_DIR = Path(os.environ.get("HOUSEHOLD_WEB_DATA_DIR", "/data")).resolve()
APP_DIR = Path(os.environ.get("HOUSEHOLD_APP_DIR", "/app")).resolve()
APP_PORT = int(os.environ.get("HOUSEHOLD_WEB_PORT", "8001"))
GATEWAY_PORT = 8000
MAX_ARCHIVE_BYTES = 1024 * 1024 * 1024
MAX_UNPACKED_BYTES = 2 * 1024 * 1024 * 1024
MAX_PROXY_BODY_BYTES = 64 * 1024 * 1024
SECRET = os.environ.get("HOUSEHOLD_PERSIST_SECRET", "")
HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade",
}


class Gateway(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self):
        self.state_lock = threading.RLock()
        self.app_process: subprocess.Popen | None = None
        super().__init__(("0.0.0.0", GATEWAY_PORT), Handler)

    def initialize_app(self, archive: bytes):
        with self.state_lock:
            if self.app_process and self.app_process.poll() is None:
                raise RuntimeError("Cloud app is already initialized")
            if archive:
                restore_archive(archive)
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            environment = os.environ.copy()
            environment["PYTHONIOENCODING"] = "utf-8"
            environment["PYTHONUTF8"] = "1"
            environment["HOUSEHOLD_WEB_CLOUD_RUNTIME"] = "1"
            origin = environment.get("HOUSEHOLD_WEB_PUBLIC_ORIGIN", "").rstrip("/")
            command = [
                sys.executable, "-m", "bookkeeping.web",
                "--host", "127.0.0.1", "--port", str(APP_PORT),
                "--data-dir", str(DATA_DIR), "--public-origin", origin,
            ]
            self.app_process = subprocess.Popen(
                command, cwd=APP_DIR, env=environment,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        deadline = time.monotonic() + 60
        last_error = None
        while time.monotonic() < deadline:
            if self.app_process.poll() is not None:
                raise RuntimeError("Cloud app process exited during startup")
            try:
                connection = http.client.HTTPConnection("127.0.0.1", APP_PORT, timeout=2)
                connection.request("GET", "/api/config")
                response = connection.getresponse()
                response.read()
                connection.close()
                if response.status == 200:
                    return
            except OSError as error:
                last_error = error
            time.sleep(0.2)
        raise RuntimeError(f"Cloud app readiness timeout: {type(last_error).__name__ if last_error else 'unknown'}")

    def close_app(self):
        with self.state_lock:
            process = self.app_process
            self.app_process = None
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)

    def application_ready(self) -> bool:
        process = self.app_process
        if not process or process.poll() is not None:
            return False
        try:
            connection = http.client.HTTPConnection("127.0.0.1", APP_PORT, timeout=2)
            connection.request("GET", "/api/config")
            response = connection.getresponse()
            response.read()
            connection.close()
            return response.status == 200
        except OSError:
            return False


def safe_member_path(name: str) -> PurePosixPath:
    path = PurePosixPath(name.replace("\\", "/"))
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("Archive path is invalid")
    return path


def restore_archive(body: bytes):
    if len(body) > MAX_ARCHIVE_BYTES:
        raise ValueError("Archive is too large")
    DATA_DIR.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="household-restore-") as temporary:
        staging = Path(temporary) / "state"
        staging.mkdir()
        total = 0
        with tarfile.open(fileobj=io.BytesIO(body), mode="r:gz") as archive:
            for member in archive.getmembers():
                relative = safe_member_path(member.name)
                if member.issym() or member.islnk() or not (member.isdir() or member.isfile()):
                    raise ValueError("Archive contains an unsupported entry")
                total += max(0, member.size)
                if total > MAX_UNPACKED_BYTES:
                    raise ValueError("Archive expands beyond the allowed size")
                target = staging.joinpath(*relative.parts)
                if not target.resolve().is_relative_to(staging.resolve()):
                    raise ValueError("Archive path escapes the data directory")
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    raise ValueError("Archive file is unreadable")
                with source, target.open("xb") as destination:
                    shutil.copyfileobj(source, destination, length=1024 * 1024)
        if DATA_DIR.exists():
            shutil.rmtree(DATA_DIR)
        DATA_DIR.parent.mkdir(parents=True, exist_ok=True)
        staging.replace(DATA_DIR)


def build_archive() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temporary = tempfile.NamedTemporaryFile(prefix="household-state-", suffix=".tar.gz", delete=False)
    archive_path = Path(temporary.name)
    temporary.close()
    try:
        with tempfile.TemporaryDirectory(prefix="household-state-copy-") as temporary_dir:
            staging = Path(temporary_dir) / "state"
            staging.mkdir()
            for source in DATA_DIR.rglob("*"):
                if source.is_symlink() or not source.is_file():
                    continue
                if source.name.endswith(("-wal", "-shm")):
                    continue
                relative = source.relative_to(DATA_DIR)
                destination = staging / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                if source.suffix.lower() in {".sqlite", ".sqlite3", ".db"}:
                    src = None
                    dst = None
                    try:
                        src = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True, timeout=20)
                        dst = sqlite3.connect(destination, timeout=20)
                        src.backup(dst)
                    except sqlite3.Error:
                        destination.unlink(missing_ok=True)
                        raise
                    finally:
                        if dst is not None:
                            dst.close()
                        if src is not None:
                            src.close()
                else:
                    shutil.copy2(source, destination)
            with tarfile.open(archive_path, mode="w:gz", compresslevel=3) as archive:
                for child in staging.iterdir():
                    archive.add(child, arcname=child.name, recursive=True)
        if archive_path.stat().st_size > MAX_ARCHIVE_BYTES:
            raise ValueError("Cloud state archive exceeds the size limit")
        return archive_path
    except BaseException:
        archive_path.unlink(missing_ok=True)
        raise


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, _format, *_args):
        return

    def _authorized_internal(self) -> bool:
        supplied = self.headers.get("x-household-persist-secret", "")
        return bool(SECRET and supplied and hmac.compare_digest(SECRET, supplied))

    def _reply(self, status: int, body: bytes = b"", content_type="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _internal(self):
        if not self._authorized_internal():
            self._reply(404)
            return True
        route = urlsplit(self.path).path
        if route == "/__internal/ready" and self.command == "GET":
            process = self.server.app_process
            if process and process.poll() is None and not self.server.application_ready():
                self._reply(503, b"starting", "text/plain; charset=utf-8")
                return True
            self._reply(200, b"ready", "text/plain; charset=utf-8")
            return True
        if route == "/__internal/initialize" and self.command == "POST":
            try:
                archive = self._read_body(MAX_ARCHIVE_BYTES)
                self.server.initialize_app(archive)
            except OverflowError:
                self._reply(413)
                return True
            except Exception:
                self._reply(500)
                return True
            self._reply(204)
            return True
        if route == "/__internal/export" and self.command == "GET":
            if not self.server.application_ready():
                self._reply(503, b"application is not initialized", "text/plain; charset=utf-8")
                return True
            try:
                archive = build_archive()
                size = archive.stat().st_size
                self.send_response(200)
                self.send_header("Content-Type", "application/gzip")
                self.send_header("Content-Length", str(size))
                self.send_header("Cache-Control", "private, no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                with archive.open("rb") as source:
                    shutil.copyfileobj(source, self.wfile, length=1024 * 1024)
            except Exception:
                self._reply(500)
            finally:
                if "archive" in locals():
                    archive.unlink(missing_ok=True)
            return True
        return False

    def _read_body(self, maximum: int) -> bytes:
        transfer_encoding = self.headers.get("Transfer-Encoding", "").strip().lower()
        content_length = self.headers.get("Content-Length")
        if transfer_encoding:
            if content_length is not None or transfer_encoding != "chunked":
                raise ValueError("Request framing is invalid")
            chunks = []
            total = 0
            trailer_bytes = 0
            while True:
                line = self.rfile.readline(8192)
                if not line.endswith(b"\r\n"):
                    raise ValueError("Chunk header is incomplete")
                try:
                    size = int(line[:-2].split(b";", 1)[0], 16)
                except ValueError as error:
                    raise ValueError("Chunk size is invalid") from error
                if size < 0 or total + size > maximum:
                    raise OverflowError("Request body exceeds its limit")
                if size == 0:
                    while True:
                        trailer = self.rfile.readline(8192)
                        trailer_bytes += len(trailer)
                        if trailer_bytes > 64 * 1024 or not trailer.endswith(b"\r\n"):
                            raise ValueError("Request trailers are invalid")
                        if trailer == b"\r\n":
                            break
                    return b"".join(chunks)
                chunk = self.rfile.read(size)
                if len(chunk) != size or self.rfile.read(2) != b"\r\n":
                    raise ValueError("Request chunk is incomplete")
                chunks.append(chunk)
                total += size

        try:
            length = int(content_length or "0")
        except ValueError as error:
            raise ValueError("Content-Length is invalid") from error
        if length < 0:
            raise ValueError("Content-Length is invalid")
        if length > maximum:
            raise OverflowError("Request body exceeds its limit")
        body = self.rfile.read(length) if length else b""
        if len(body) != length:
            raise ValueError("Request body is incomplete")
        return body

    def _proxy(self):
        with self.server.state_lock:
            process = self.server.app_process
            ready = bool(process and process.poll() is None)
        if not ready:
            self._reply(503, '{"error":"云端服务正在启动。"}'.encode("utf-8"))
            return
        try:
            body = self._read_body(MAX_PROXY_BODY_BYTES)
            if len(body) > MAX_PROXY_BODY_BYTES:
                self._reply(413, '{"error":"请求内容过大。"}'.encode("utf-8"))
                return
            headers = {
                key: value for key, value in self.headers.items()
                if key.lower() not in HOP_BY_HOP and key.lower() not in {"content-length", "host"}
            }
            headers["Host"] = self.headers.get("x-forwarded-host", "localhost")
            connection = http.client.HTTPConnection("127.0.0.1", APP_PORT, timeout=300)
            connection.request(self.command, self.path, body=body if body else None, headers=headers)
            upstream = connection.getresponse()
            self.send_response(upstream.status, upstream.reason)
            for key, value in upstream.getheaders():
                if key.lower() not in HOP_BY_HOP and key.lower() != "content-length":
                    self.send_header(key, value)
            payload_length = upstream.getheader("Content-Length")
            if payload_length is not None:
                self.send_header("Content-Length", payload_length)
            else:
                self.send_header("Connection", "close")
                self.close_connection = True
            self.end_headers()
            shutil.copyfileobj(upstream, self.wfile, length=1024 * 1024)
            connection.close()
        except OverflowError:
            self._reply(413, '{"error":"请求内容过大。"}'.encode("utf-8"))
        except (OSError, ValueError, http.client.HTTPException):
            self._reply(502, '{"error":"云端服务暂时不可用。"}'.encode("utf-8"))

    def _handle(self):
        if urlsplit(self.path).path.startswith("/__internal/"):
            if self._internal():
                return
            self._reply(404)
            return
        self._proxy()

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = _handle


def main():
    if not SECRET:
        raise SystemExit("Cloud persistence secret is required")
    gateway = Gateway()

    def stop(_signum, _frame):
        threading.Thread(target=gateway.shutdown, daemon=True).start()
        gateway.close_app()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        gateway.serve_forever(poll_interval=0.5)
    finally:
        gateway.close_app()
        gateway.server_close()


if __name__ == "__main__":
    main()
