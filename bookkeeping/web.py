from __future__ import annotations

import argparse
import hashlib
import hmac
import http.cookies
import json
import mimetypes
import os
import re
import secrets
import shutil
import ssl
import sqlite3
import threading
import time
import uuid
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse, parse_qs

from .storage import DEFAULT_CATEGORIES, Database, LedgerError, parse_date, to_minor_allow_zero


APP_ROOT = Path(__file__).resolve().parent
STATIC_ROOT = APP_ROOT / "web_static"
SESSION_MAX_AGE = 60 * 60 * 24 * 30
MAX_JSON_BYTES = 48 * 1024 * 1024
MAX_LEDGER_BYTES = 50 * 1024 * 1024
USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,32}$")
PASSWORD_MIN_LENGTH = 12
JST = timezone(timedelta(hours=9), "JST")
_user_locks: dict[str, threading.RLock] = {}
_locks_guard = threading.Lock()
_login_attempts: dict[str, list[float]] = {}


class WebError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _jst_today() -> date:
    return datetime.now(JST).date()


def _password_hash(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32, maxmem=128 * 1024 * 1024)


def _ensure_auth_schema(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as connection:
        old_tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "web_users" in old_tables and "web_identities" not in old_tables:
            backup_dir = path.parent / "auth-backups"
            backup_dir.mkdir(exist_ok=True)
            with closing(sqlite3.connect(backup_dir / f"before-github-{uuid.uuid4().hex}.sqlite3")) as backup:
                connection.backup(backup)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS web_users (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_salt BLOB NOT NULL,
                password_hash BLOB NOT NULL,
                recovery_salt BLOB NOT NULL,
                recovery_hash BLOB NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS web_sessions (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES web_users(id) ON DELETE CASCADE,
                csrf_hash TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_web_sessions_user ON web_sessions(user_id);
            """
        )
        from .web_github_auth import ensure_identity_schema
        ensure_identity_schema(connection)


def _get_user_lock(user_id: str) -> threading.RLock:
    with _locks_guard:
        return _user_locks.setdefault(user_id, threading.RLock())


class BookkeepingWebServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], data_dir: Path, public_origin: str = ""):
        self.data_dir = data_dir.resolve()
        self.ledger_dir = self.data_dir / "ledgers"
        self.ledger_dir.mkdir(parents=True, exist_ok=True)
        self.auth_path = self.data_dir / "web-auth.sqlite3"
        self.public_origin = public_origin.rstrip("/")
        self.invite_code = os.environ.get("HOUSEHOLD_WEB_INVITE_CODE", "")
        self.remote_allowed = os.environ.get("HOUSEHOLD_WEB_ALLOW_REMOTE", "") == "1"
        self.secure_cookie = self.public_origin.startswith("https://")
        _ensure_auth_schema(self.auth_path)
        from .web_features import MobileWorkspace
        self.workspace = MobileWorkspace(self)
        from .web_github_auth import GitHubSignIn
        self.github_sign_in = GitHubSignIn(self)
        super().__init__(address, BookkeepingRequestHandler)

    def server_close(self) -> None:
        self.workspace.stop_event.set()
        self.github_sign_in.close()
        super().server_close()


class BookkeepingRequestHandler(BaseHTTPRequestHandler):
    server: BookkeepingWebServer
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:
        # Do not log request bodies, usernames, or financial descriptions.
        return

    def _send_bytes(self, status: int, body: bytes, content_type: str, extra_headers: tuple[tuple[str, str], ...] = ()) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'self'; connect-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data: blob:; manifest-src 'self'; worker-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        if self._secure_request():
            self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        for key, value in extra_headers:
            self.send_header(key, value)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _json(self, value: Any, status: int = 200, headers: tuple[tuple[str, str], ...] = ()) -> None:
        body = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self._send_bytes(status, body, "application/json; charset=utf-8", headers)

    def _error(self, message: str, status: int = 400, headers: tuple[tuple[str, str], ...] = ()) -> None:
        self._json({"error": message}, status, headers)

    def _read_body(self, limit: int = MAX_JSON_BYTES) -> bytes:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise WebError("请求长度无效。", 411) from exc
        if length < 0 or length > limit:
            raise WebError("请求内容过大。", 413)
        if length == 0:
            return b""
        body = self.rfile.read(length)
        if len(body) != length:
            raise WebError("请求内容不完整。", 400)
        return body

    def _read_json(self) -> dict[str, Any]:
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            raise WebError("请求格式必须为 JSON。", 415)
        try:
            value = json.loads(self._read_body())
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WebError("请求内容不是有效 JSON。", 400) from exc
        if not isinstance(value, dict):
            raise WebError("请求内容格式无效。", 400)
        return value

    def _origin_ok(self) -> bool:
        origin = self.headers.get("Origin", "").rstrip("/")
        if not origin:
            return False
        forwarded_host = self.headers.get("X-Forwarded-Host", "").strip()
        forwarded_proto = self.headers.get("X-Forwarded-Proto", "").strip().lower()
        if forwarded_host and forwarded_proto in {"http", "https"}:
            expected = f"{forwarded_proto}://{forwarded_host}".rstrip("/")
        else:
            expected = self.server.public_origin
            if not expected:
                expected = f"http://{self.headers.get('Host', '')}".rstrip("/")
        return hmac.compare_digest(origin.lower(), expected.lower())

    def _secure_request(self) -> bool:
        return self.server.secure_cookie or self.headers.get("X-Forwarded-Proto", "").strip().lower() == "https"

    def _cookie_values(self) -> dict[str, str]:
        cookies = http.cookies.SimpleCookie()
        try:
            cookies.load(self.headers.get("Cookie", ""))
        except http.cookies.CookieError:
            return {}
        return {key: morsel.value for key, morsel in cookies.items()}

    def _auth_db(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.server.auth_path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _auth_write(self, callback: Any) -> Any:
        connection = self._auth_db()
        try:
            with connection:
                return callback(connection)
        finally:
            connection.close()

    def _require_user(self, csrf: bool = False) -> dict[str, str]:
        cookie_values = self._cookie_values()
        token = cookie_values.get("hh_session", "")
        if not token:
            raise WebError("请先登录。", 401)
        token_hash = hashlib.sha256(token.encode("ascii", "ignore")).hexdigest()
        connection = self._auth_db()
        try:
            row = connection.execute(
                "SELECT s.user_id,s.csrf_hash,s.expires_at,COALESCE(i.login,u.username) AS username,"
                "i.provider AS provider FROM web_sessions s JOIN web_users u ON u.id=s.user_id "
                "LEFT JOIN web_identities i ON i.user_id=u.id AND i.provider='github' WHERE s.token_hash=?",
                (token_hash,),
            ).fetchone()
            if row is None or row["expires_at"] <= _utc_now().isoformat():
                raise WebError("登录已过期，请重新登录。", 401)
            owner = self.headers.get("X-Ledger-Owner", "")
            if owner and owner != str(row["user_id"]):
                raise WebError("登录账号已变化，请刷新页面后再操作，待同步记录仍然保留。", 409)
            if csrf:
                csrf_value = cookie_values.get("hh_csrf", "")
                supplied = self.headers.get("X-CSRF-Token", "")
                candidate = hashlib.sha256(csrf_value.encode("ascii", "ignore")).hexdigest()
                if not csrf_value or not supplied or not hmac.compare_digest(candidate, row["csrf_hash"]) or not hmac.compare_digest(supplied, csrf_value):
                    raise WebError("安全校验失败，请刷新页面后重试。", 403)
            return {"id": str(row["user_id"]), "username": str(row["username"]),
                    "authProvider": row["provider"] or "legacy"}
        finally:
            connection.close()

    def _ledger(self, user_id: str) -> Database:
        path = self.server.ledger_dir / f"{user_id}.sqlite3"
        if not path.exists():
            raise WebError("找不到此账号的账本文件，请联系管理员检查备份。", 500)
        database = Database(path)
        database.connection.execute(
            """CREATE TABLE IF NOT EXISTS web_sync_operations (
                operation_id TEXT PRIMARY KEY,
                payload_hash TEXT NOT NULL,
                resource_type TEXT NOT NULL,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )
        database.connection.commit()
        return database

    def _set_session(self, user_id: str) -> tuple[tuple[str, str], ...]:
        session_token = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(24)
        token_hash = hashlib.sha256(session_token.encode("ascii")).hexdigest()
        csrf_hash = hashlib.sha256(csrf_token.encode("ascii")).hexdigest()
        now = _utc_now()
        def save_session(connection: sqlite3.Connection) -> None:
            connection.execute(
                "INSERT INTO web_sessions(token_hash,user_id,csrf_hash,expires_at,created_at) VALUES(?,?,?,?,?)",
                (token_hash, user_id, csrf_hash, (now + timedelta(seconds=SESSION_MAX_AGE)).isoformat(), now.isoformat()),
            )
            connection.execute("DELETE FROM web_sessions WHERE expires_at < ?", (now.isoformat(),))
        self._auth_write(save_session)
        secure = "; Secure" if self._secure_request() else ""
        session_cookie = f"hh_session={session_token}; Path=/; Max-Age={SESSION_MAX_AGE}; HttpOnly; SameSite=Strict{secure}"
        csrf_cookie = f"hh_csrf={csrf_token}; Path=/; Max-Age={SESSION_MAX_AGE}; SameSite=Strict{secure}"
        return (("Set-Cookie", session_cookie), ("Set-Cookie", csrf_cookie))

    def _clear_session(self) -> tuple[tuple[str, str], ...]:
        cookies = self._cookie_values()
        token = cookies.get("hh_session", "")
        if token:
            token_hash = hashlib.sha256(token.encode("ascii", "ignore")).hexdigest()
            self._auth_write(lambda connection: connection.execute("DELETE FROM web_sessions WHERE token_hash=?", (token_hash,)))
        secure = "; Secure" if self._secure_request() else ""
        return (
            ("Set-Cookie", f"hh_session=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict{secure}"),
            ("Set-Cookie", f"hh_csrf=; Path=/; Max-Age=0; SameSite=Strict{secure}"),
        )

    def _static(self, raw_path: str) -> None:
        route = unquote(urlparse(raw_path).path)
        if route == "/":
            filename = "index.html"
        else:
            filename = route.lstrip("/")
        allowed = {"index.html", "app.js", "mobile.js", "github-login.js", "appearance.js", "style.css", "mobile.css", "manifest.webmanifest", "sw.js", "icon.svg", "icon-192.png", "icon-512.png", "apple-touch-icon.png"}
        if filename not in allowed:
            self._error("找不到页面。", 404)
            return
        target = STATIC_ROOT / filename
        try:
            body = target.read_bytes()
        except OSError:
            self._error("Web界面文件缺失。", 500)
            return
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if target.suffix in {".js", ".css", ".html", ".webmanifest", ".svg"}:
            content_type += "; charset=utf-8"
        headers: tuple[tuple[str, str], ...] = ()
        if target.name == "sw.js":
            headers = (("Service-Worker-Allowed", "/"),)
        self._send_bytes(200, body, content_type, headers)

    def do_GET(self) -> None:
        try:
            route = urlparse(self.path).path
            if route.startswith("/api/"):
                if route == "/api/config":
                    self._json({"requiresInvite": False, "authMode": "github", "appVersion": "mobile-7",
                                "secure": self._secure_request(),
                                "deploymentMode": "cloud" if os.environ.get("HOUSEHOLD_WEB_CLOUD_RUNTIME") == "1" else "selfhosted"})
                    return
                if route == "/api/session":
                    try:
                        user = self._require_user()
                    except WebError as exc:
                        if exc.status == 401:
                            self._json({"user": None})
                            return
                        raise
                    csrf_token = self._cookie_values().get("hh_csrf", "")
                    self._json({"user": user, "csrfToken": csrf_token})
                    return
                if route == "/api/bootstrap":
                    user = self._require_user()
                    params = urlparse(self.path).query
                    language = "zh-CN"
                    for part in params.split("&"):
                        if part.startswith("lang="):
                            language = unquote(part[5:])
                    if language not in {"zh-CN", "ja-JP", "en-US"}:
                        language = "zh-CN"
                    self._json(self._bootstrap(user, language))
                    return
                if route == "/api/workspace":
                    user = self._require_user()
                    params = parse_qs(urlparse(self.path).query)
                    self._json(self.server.workspace.snapshot(user["id"], params.get("lang", ["zh-CN"])[0], params.get("asOf", [None])[0]))
                    return
                if route == "/api/transactions":
                    user = self._require_user()
                    params = parse_qs(urlparse(self.path).query)
                    start = parse_date(params.get("start", ["1900-01-01"])[0]).isoformat()
                    end = parse_date(params.get("end", ["2199-12-31"])[0]).isoformat()
                    if end < start:
                        raise WebError("结束日期不能早于开始日期。")
                    db = self._ledger(user["id"])
                    try:
                        with _get_user_lock(user["id"]):
                            rows = [dict(row) for row in db.transactions_between(start, end)]
                        from .web_features import serial
                        self._json(serial(rows))
                    finally:
                        db.close()
                    return
                if route == "/api/default-skills":
                    self._require_user()
                    from .web_features import WEB_DEFAULTS
                    self._json({
                        "bookkeeping": (WEB_DEFAULTS / "bookkeeping.md").read_text(encoding="utf-8"),
                        "food_health": (WEB_DEFAULTS / "food-health.md").read_text(encoding="utf-8"),
                    })
                    return
                if route == "/api/job":
                    user = self._require_user()
                    params = parse_qs(urlparse(self.path).query)
                    self._json(self.server.workspace.job(user["id"], params.get("id", [""])[0]))
                    return
                if route == "/api/backup":
                    user = self._require_user()
                    params = parse_qs(urlparse(self.path).query)
                    file = self.server.workspace.backup_file(user["id"], params.get("name", [""])[0])
                    self._send_bytes(200, file.read_bytes(), "application/zip",
                                     (("Content-Disposition", f'attachment; filename="{file.name}"'),))
                    return
                if route == "/api/receipt":
                    user = self._require_user()
                    params = parse_qs(urlparse(self.path).query)
                    name = params.get("name", [""])[0]
                    if not re.fullmatch(r"[\w.-]+\.(jpg|jpeg|png|webp)", name, re.I):
                        raise WebError("图片名称无效。")
                    file = self.server.workspace.folder(user["id"]) / "receipt_images" / name
                    if not file.is_file() or file.is_symlink():
                        raise WebError("图片不存在。", 404)
                    self._send_bytes(200, file.read_bytes(), mimetypes.guess_type(name)[0] or "image/jpeg")
                    return
                if route == "/api/export-ledger":
                    user = self._require_user()
                    db = self._ledger(user["id"])
                    temp = self.server.ledger_dir / f".{user['id']}-{uuid.uuid4().hex}.export.sqlite3"
                    try:
                        with _get_user_lock(user["id"]):
                            db.backup(temp)
                        body = temp.read_bytes()
                    finally:
                        db.close()
                        temp.unlink(missing_ok=True)
                    filename = f"household-ledger-{user['username']}.sqlite3"
                    self._send_bytes(200, body, "application/vnd.sqlite3", (("Content-Disposition", f'attachment; filename="{filename}"'),))
                    return
                self._error("找不到接口。", 404)
                return
            if route == "/test-ca.cer" and os.environ.get("HOUSEHOLD_WEB_TEST_CA"):
                file = Path(os.environ["HOUSEHOLD_WEB_TEST_CA"])
                self._send_bytes(200, file.read_bytes(), "application/x-x509-ca-cert")
                return
            if route == "/sw.js":
                self._static("/sw.js")
                return
            self._static(self.path)
        except WebError as exc:
            self._error(str(exc), exc.status)
        except (OSError, sqlite3.Error, LedgerError, RuntimeError, ValueError) as exc:
            self._error(str(exc) if isinstance(exc, LedgerError) else "读取账本失败，请稍后重试。", 500)

    def _bootstrap(self, user: dict[str, str], language: str) -> dict[str, Any]:
        db = self._ledger(user["id"])
        try:
            account_rows = db.connection.execute(
                "SELECT a.id,a.name,a.account_type,a.currency,a.opening_date,c.minor_digits "
                "FROM accounts a JOIN currencies c ON c.code=a.currency ORDER BY a.name COLLATE NOCASE"
            ).fetchall()
            accounts = []
            for row in account_rows:
                account_id = int(row["id"])
                accounts.append({
                    "id": account_id,
                    "name": str(row["name"]),
                    "type": str(row["account_type"]),
                    "currency": str(row["currency"]),
                    "minorDigits": int(row["minor_digits"]),
                    "openingDate": str(row["opening_date"]),
                    "balanceMinor": str(db.account_balance_minor(account_id)),
                })
            categories = db.connection.execute(
                "SELECT c.id,c.name,c.kind,COALESCE(t.translated_name,c.name) AS display_name "
                "FROM categories c LEFT JOIN category_translations t "
                "ON t.category_id=c.id AND t.language=? WHERE c.is_active=1 ORDER BY c.kind,c.name",
                (language,),
            ).fetchall()
            transactions = db.connection.execute(
                """SELECT t.id,t.occurred_on,t.kind,t.amount_minor,t.currency,t.description,
                          t.balance_effect,t.needs_review,t.account_amount_minor,
                          COALESCE(ct.translated_name,c.name) AS category_name,
                          a.name AS account_name,a.account_type AS account_type,
                          x.name AS to_account_name,x.currency AS to_currency,x.account_type AS to_account_type,t.to_amount_minor,
                          to_cur.minor_digits AS to_minor_digits,cur.minor_digits
                   FROM transactions t
                   LEFT JOIN categories c ON c.id=t.category_id
                   LEFT JOIN category_translations ct ON ct.category_id=c.id AND ct.language=?
                   LEFT JOIN accounts a ON a.id=t.account_id
                   LEFT JOIN accounts x ON x.id=t.to_account_id
                   LEFT JOIN currencies to_cur ON to_cur.code=x.currency
                   JOIN currencies cur ON cur.code=t.currency
                   ORDER BY t.occurred_on DESC,t.id DESC LIMIT 100""",
                (language,),
            ).fetchall()
            return {
                "user": user,
                "accounts": accounts,
                "categories": [dict(row) for row in categories],
                "transactions": [
                    {
                        **dict(row),
                        "amount_minor": str(row["amount_minor"]),
                        "to_amount_minor": str(row["to_amount_minor"]) if row["to_amount_minor"] is not None else None,
                        "account_amount_minor": str(row["account_amount_minor"]) if row["account_amount_minor"] is not None else None,
                    }
                    for row in transactions
                ],
                "serverDate": _jst_today().isoformat(),
            }
        finally:
            db.close()

    def do_POST(self) -> None:
        # Several early validation paths reject a request before consuming its
        # body; close the connection so unread bytes cannot become another request.
        self.close_connection = True
        response_headers: tuple[tuple[str, str], ...] = ()
        try:
            if not self._origin_ok():
                raise WebError("请求来源校验失败。", 403)
            route = urlparse(self.path).path
            if route.startswith("/api/auth/github/"):
                payload = self._read_json()
                cookie = self._cookie_values().get("hh_gh_login", "")
                secure = "; Secure" if self._secure_request() else ""
                def flow_cookie(value, duration=0):
                    return (("Set-Cookie", f"hh_gh_login={value}; Path=/api/auth/github; Max-Age={duration}; HttpOnly; SameSite=Strict{secure}"),)
                if route == "/api/auth/github/start":
                    mode = payload.get("mode", "login")
                    if mode not in {"login", "link"}:
                        raise WebError("登录模式无效。")
                    link_user = self._require_user(csrf=True)["id"] if mode == "link" else None
                    result, value = self.server.github_sign_in.start(self.client_address[0],
                        link_user=link_user, previous_cookie=cookie)
                    self._json(result, 200, flow_cookie(value, result["expiresIn"]))
                    return
                flow_id = str(payload.get("flowId", ""))
                if route == "/api/auth/github/status":
                    self._json(self.server.github_sign_in.status(cookie, flow_id))
                    return
                if route == "/api/auth/github/cancel":
                    self.server.github_sign_in.cancel(cookie, flow_id)
                    self._json({"ok": True}, 200, flow_cookie(""))
                    return
                if route == "/api/auth/github/finish":
                    try:
                        active_user = self._require_user(csrf=True)["id"]
                    except WebError as error:
                        if error.status != 401:
                            raise
                        active_user = None
                    user = self.server.github_sign_in.finish(cookie, flow_id, current_user=active_user)
                    response_headers = self._clear_session() + self._set_session(user["id"]) + flow_cookie("")
                    self._json({"user": user}, 200, response_headers)
                    return
                raise WebError("找不到接口。", 404)
            if route == "/api/register":
                raise WebError("已改为使用 GitHub 登录，无需注册。", 410)
            if route == "/api/login":
                payload = self._read_json()
                user = self._login(payload)
                response_headers = self._set_session(user["id"])
                self._json({"user": user}, 200, response_headers)
                return
            if route == "/api/recover":
                payload = self._read_json()
                recovery = self._recover(payload)
                self._json({"recoveryCode": recovery, "message": "密码已重置，请使用新密码登录。"})
                return
            user = self._require_user(csrf=True)
            if route == "/api/action":
                payload = self._read_json()
                result = self.server.workspace.start(
                    user["id"], str(payload.get("action", "")), payload.get("data", {}),
                    str(payload.get("opId", "")))
                self._json(result, 202)
                return
            if route == "/api/cancel-job":
                payload = self._read_json()
                self._json(self.server.workspace.cancel(user["id"], str(payload.get("id", ""))))
                return
            if route == "/api/restore-bundle":
                if self.headers.get("X-Confirm-Restore") != "confirmed-once":
                    raise WebError("请确认恢复操作后重试。")
                with _get_user_lock(user["id"]):
                    result = self.server.workspace.restore(user["id"], self._read_body(60 * 1024 * 1024))
                self._json(result)
                return
            if route == "/api/logout":
                headers = self._clear_session()
                self._json({"ok": True}, 200, headers)
                return
            if route == "/api/accounts":
                result = self._create_account(user, self._read_json())
                self._json(result, 201)
                return
            if route == "/api/transactions":
                payload = self._read_json()
                op = payload.get("operation") or {"type": "transaction", "opId": str(uuid.uuid4()), "data": payload}
                result = self._apply_operation(user, op)
                self._json(result, 201)
                return
            if route == "/api/sync":
                payload = self._read_json()
                operations = payload.get("operations")
                if not isinstance(operations, list) or len(operations) > 100:
                    raise WebError("同步队列格式无效或超过100项。", 400)
                results = []
                for operation in operations:
                    try:
                        results.append(self._apply_operation(user, operation))
                    except WebError as exc:
                        results.append({"opId": operation.get("opId") if isinstance(operation, dict) else None, "ok": False, "error": str(exc)})
                    except (LedgerError, ValueError, sqlite3.Error) as exc:
                        results.append({"opId": operation.get("opId") if isinstance(operation, dict) else None, "ok": False, "error": str(exc) or "无法同步此条记录。"})
                self._json({"results": results})
                return
            if route == "/api/categories":
                self._create_category(user, self._read_json())
                self._json({"ok": True}, 201)
                return
            if route == "/api/import-ledger":
                result = self._import_ledger(user)
                self._json(result)
                return
            self._error("找不到接口。", 404)
        except WebError as exc:
            self._error(str(exc), exc.status, response_headers)
        except (LedgerError, ValueError, RuntimeError) as exc:
            self._error(str(exc), 400, response_headers)
        except (sqlite3.Error, OSError) as exc:
            self._error("保存失败，账本未能完成此操作。请检查数据目录空间或文件权限。", 500, response_headers)

    def _register(self, payload: dict[str, Any]) -> tuple[dict[str, str], str]:
        username = str(payload.get("username", "")).strip()
        password = str(payload.get("password", ""))
        invite = str(payload.get("inviteCode", ""))
        if not USERNAME_RE.fullmatch(username):
            raise WebError("用户名请使用3到32位英文字母、数字、点、下划线或连字符。")
        if len(password) < PASSWORD_MIN_LENGTH:
            raise WebError(f"密码至少需要{PASSWORD_MIN_LENGTH}个字符。")
        if len(password) > 1024:
            raise WebError("密码过长。")
        if self.server.invite_code and not hmac.compare_digest(invite, self.server.invite_code):
            raise WebError("邀请码不正确。", 403)
        user_id = str(uuid.uuid4())
        password_salt = secrets.token_bytes(16)
        recovery_code = secrets.token_urlsafe(20)
        recovery_salt = secrets.token_bytes(16)
        now = _utc_now().isoformat()
        try:
            self._auth_write(lambda connection: connection.execute(
                "INSERT INTO web_users(id,username,password_salt,password_hash,recovery_salt,recovery_hash,created_at) VALUES(?,?,?,?,?,?,?)",
                (user_id, username, password_salt, _password_hash(password, password_salt), recovery_salt, _password_hash(recovery_code, recovery_salt), now),
            ))
        except sqlite3.IntegrityError as exc:
            raise WebError("此用户名已被使用。", 409) from exc
        ledger_path = self.server.ledger_dir / f"{user_id}.sqlite3"
        try:
            db = Database(ledger_path)
            try:
                db.initialize()
            finally:
                db.close()
        except Exception:
            self._auth_write(lambda connection: connection.execute("DELETE FROM web_users WHERE id=?", (user_id,)))
            ledger_path.unlink(missing_ok=True)
            raise
        return {"id": user_id, "username": username}, recovery_code

    def _login(self, payload: dict[str, Any]) -> dict[str, str]:
        username = str(payload.get("username", "")).strip()
        password = str(payload.get("password", ""))
        client = self.client_address[0]
        now = time.monotonic()
        attempts = [stamp for stamp in _login_attempts.get(client, []) if now - stamp < 300]
        if len(attempts) >= 8:
            _login_attempts[client] = attempts
            raise WebError("登录尝试过多，请5分钟后再试。", 429)
        _login_attempts[client] = attempts + [now]
        connection = self._auth_db()
        try:
            row = connection.execute(
                "SELECT id,username,password_salt,password_hash FROM web_users WHERE username=? COLLATE NOCASE AND NOT EXISTS (SELECT 1 FROM web_identities i WHERE i.user_id=web_users.id)",
                (username,),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            # Perform a dummy scrypt so a missing username is not substantially faster.
            _password_hash(password[:1024], b"household-web-dummy-salt")
            raise WebError("用户名或密码不正确。", 401)
        try:
            candidate = _password_hash(password[:1024], bytes(row["password_salt"]))
        except (ValueError, UnicodeError):
            raise WebError("用户名或密码不正确。", 401)
        if not hmac.compare_digest(candidate, bytes(row["password_hash"])):
            raise WebError("用户名或密码不正确。", 401)
        _login_attempts.pop(client, None)
        return {"id": str(row["id"]), "username": str(row["username"]), "authProvider": "legacy"}

    def _recover(self, payload: dict[str, Any]) -> str:
        username = str(payload.get("username", "")).strip()
        recovery_code = str(payload.get("recoveryCode", "")).strip()
        new_password = str(payload.get("newPassword", ""))
        if len(new_password) < PASSWORD_MIN_LENGTH:
            raise WebError(f"新密码至少需要{PASSWORD_MIN_LENGTH}个字符。")
        if len(new_password) > 1024 or len(recovery_code) > 1024:
            raise WebError("恢复信息过长。")
        client = f"recover:{self.client_address[0]}"
        now = time.monotonic()
        attempts = [stamp for stamp in _login_attempts.get(client, []) if now - stamp < 300]
        if len(attempts) >= 8:
            _login_attempts[client] = attempts
            raise WebError("恢复尝试过多，请5分钟后再试。", 429)
        _login_attempts[client] = attempts + [now]
        connection = self._auth_db()
        try:
            row = connection.execute(
                "SELECT id,recovery_salt,recovery_hash FROM web_users WHERE username=? COLLATE NOCASE AND NOT EXISTS (SELECT 1 FROM web_identities i WHERE i.user_id=web_users.id)",
                (username,),
            ).fetchone()
            if row is None:
                _password_hash(recovery_code, b"household-web-dummy-salt")
                raise WebError("用户名或恢复码不正确。", 401)
            try:
                valid = hmac.compare_digest(
                    _password_hash(recovery_code[:1024], bytes(row["recovery_salt"])),
                    bytes(row["recovery_hash"]),
                )
            except ValueError:
                valid = False
            if not valid:
                raise WebError("用户名或恢复码不正确。", 401)
            password_salt = secrets.token_bytes(16)
            next_recovery_code = secrets.token_urlsafe(20)
            recovery_salt = secrets.token_bytes(16)
            connection.execute(
                "UPDATE web_users SET password_salt=?,password_hash=?,recovery_salt=?,recovery_hash=? WHERE id=?",
                (password_salt, _password_hash(new_password, password_salt), recovery_salt, _password_hash(next_recovery_code, recovery_salt), row["id"]),
            )
            connection.execute("DELETE FROM web_sessions WHERE user_id=?", (row["id"],))
            connection.commit()
            _login_attempts.pop(client, None)
            return next_recovery_code
        finally:
            connection.close()

    def _create_account(self, user: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name", "")).strip()
        account_type = str(payload.get("type", ""))
        currency = str(payload.get("currency", "")).upper()
        opening_balance = str(payload.get("openingBalance", "0")).strip()
        opening_date = str(payload.get("openingDate", _jst_today().isoformat()))
        completeness = str(payload.get("completeness", "known"))
        note = str(payload.get("note", "")).strip()
        db = self._ledger(user["id"])
        try:
            with _get_user_lock(user["id"]):
                existing = db.connection.execute("SELECT * FROM accounts WHERE name=?", (name,)).fetchone()
                if existing is not None:
                    curr = db.currency(currency)
                    expected = to_minor_allow_zero(opening_balance, currency, int(curr["minor_digits"]))
                    if str(existing["account_type"]) == account_type and str(existing["currency"]) == currency and int(existing["opening_balance_minor"]) == expected and str(existing["opening_date"]) == parse_date(opening_date).isoformat():
                        return {"ok": True, "accountId": int(existing["id"]), "alreadyExists": True}
                    raise LedgerError(f"账户名称“{name}”已存在，请使用不同名称。")
                account_id = db.add_account(
                    name=name,
                    account_type=account_type,
                    currency=currency,
                    opening_balance=opening_balance,
                    opening_date=opening_date,
                    completeness=completeness,
                    note=note,
                )
                return {"ok": True, "accountId": account_id}
        finally:
            db.close()

    def _create_category(self, user: dict[str, str], payload: dict[str, Any]) -> None:
        name = str(payload.get("name", "")).strip()
        kind = str(payload.get("kind", ""))
        if not name or len(name) > 80 or kind not in {"income", "expense"}:
            raise LedgerError("类别名称或类型无效。")
        db = self._ledger(user["id"])
        try:
            with db.connection:
                db.connection.execute("INSERT INTO categories(name,kind,is_active) VALUES(?,?,1)", (name, kind))
        except sqlite3.IntegrityError as exc:
            raise LedgerError("该类别名称已存在。") from exc
        finally:
            db.close()

    def _apply_operation(self, user: dict[str, str], operation: Any) -> dict[str, Any]:
        if not isinstance(operation, dict):
            raise WebError("同步项目格式无效。")
        if operation.get("ownerId") and operation["ownerId"] != user["id"]:
            raise WebError("待同步记录属于另一个账号，已停止写入。", 409)
        op_id = str(operation.get("opId", ""))
        operation_type = str(operation.get("type", ""))
        data = operation.get("data")
        if not re.fullmatch(r"[A-Za-z0-9_-]{12,80}", op_id) or not isinstance(data, dict):
            raise WebError("同步项目缺少有效编号或数据。")
        if operation_type not in {"transaction", "account", "category"}:
            raise WebError("不支持此同步项目类型。")
        canonical_payload = json.dumps({"type": operation_type, "data": data}, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        payload_hash = hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()
        db = self._ledger(user["id"])
        try:
            with _get_user_lock(user["id"]):
                previous = db.connection.execute(
                    "SELECT payload_hash,result_json FROM web_sync_operations WHERE operation_id=?", (op_id,)
                ).fetchone()
                if previous:
                    if not hmac.compare_digest(str(previous["payload_hash"]), payload_hash):
                        raise WebError("此同步编号对应的数据不同，已停止以保护账本。", 409)
                    return json.loads(previous["result_json"])
                if operation_type == "transaction":
                    result = self._save_web_transaction(db, op_id, payload_hash, data)
                    result.update({"opId": op_id, "ok": True, "type": operation_type})
                elif operation_type == "account":
                    result = self._save_web_account(db, data)
                    result.update({"opId": op_id, "ok": True, "type": operation_type})
                else:
                    name = str(data.get("name", "")).strip()
                    kind = str(data.get("kind", ""))
                    if not name or len(name) > 80 or kind not in {"income", "expense"}:
                        raise LedgerError("类别名称或类型无效。")
                    exists = db.connection.execute("SELECT kind FROM categories WHERE name=?", (name,)).fetchone()
                    if exists is None:
                        db.connection.execute("INSERT INTO categories(name,kind,is_active) VALUES(?,?,1)", (name, kind))
                        db.connection.commit()
                    elif str(exists["kind"]) != kind:
                        raise LedgerError("同名类别已存在，但类别类型不同。")
                    result = {"categoryName": name, "opId": op_id, "ok": True, "type": operation_type}
                encoded_result = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
                db.connection.execute(
                    "INSERT INTO web_sync_operations(operation_id,payload_hash,resource_type,result_json,created_at) VALUES(?,?,?,?,?)",
                    (op_id, payload_hash, operation_type, encoded_result, _utc_now().isoformat()),
                )
                db.connection.commit()
                self.server.workspace.after_write(user["id"])
                return result
        finally:
            db.close()

    def _save_web_account(self, db: Database, data: dict[str, Any]) -> dict[str, Any]:
        name = str(data.get("name", "")).strip()
        account_type = str(data.get("type", ""))
        currency = str(data.get("currency", "")).upper()
        opening_balance = str(data.get("openingBalance", "0")).strip()
        opening_date = str(data.get("openingDate", _jst_today().isoformat()))
        completeness = str(data.get("completeness", "known"))
        existing = db.connection.execute("SELECT * FROM accounts WHERE name=?", (name,)).fetchone()
        if existing is not None:
            curr = db.currency(currency)
            expected = to_minor_allow_zero(opening_balance, currency, int(curr["minor_digits"]))
            if str(existing["account_type"]) == account_type and str(existing["currency"]) == currency and int(existing["opening_balance_minor"]) == expected and str(existing["opening_date"]) == parse_date(opening_date).isoformat():
                return {"accountId": int(existing["id"]), "alreadyExists": True}
            raise LedgerError(f"账户名称“{name}”已存在，请使用不同名称。")
        account_id = db.add_account(
            name=name,
            account_type=account_type,
            currency=currency,
            opening_balance=opening_balance,
            opening_date=opening_date,
            completeness=completeness,
            note=str(data.get("note", "")),
        )
        return {"accountId": account_id}

    def _save_web_transaction(self, db: Database, op_id: str, payload_hash: str, data: dict[str, Any]) -> dict[str, Any]:
        source_marker = f"websync:{op_id}:{payload_hash}"
        existing = db.connection.execute("SELECT id FROM transactions WHERE source=?", (source_marker,)).fetchone()
        if existing:
            return {"transactionId": int(existing["id"]), "recoveredAfterRetry": True}
        kind = str(data.get("kind", ""))
        currency = str(data.get("currency", "")).upper()
        description = str(data.get("description", "")).strip()
        account_name = str(data.get("accountName", "")).strip()
        if kind not in {"income", "expense", "transfer"}:
            raise LedgerError("请选择收入、支出或转账。")
        if not description or len(description) > 240:
            raise LedgerError("说明不能为空，且最多240个字符。")
        if kind in {"income", "expense"}:
            category_name = str(data.get("categoryName", "")).strip()
            db.currency(currency)
            account = db.account(account_name)
            if str(account["currency"]) != currency:
                raise LedgerError("此Web版本的收支必须使用与账户相同的币种；跨币种账单后续版本再支持。")
            transaction_id = db.add_transaction(
                occurred_on=str(data.get("date", "")),
                kind=kind,
                amount=str(data.get("amount", "")),
                currency=currency,
                description=description,
                category_name=category_name,
                account_name=account_name,
                source=source_marker,
            )
        else:
            to_account_name = str(data.get("toAccountName", "")).strip()
            source_account = db.account(account_name)
            destination_account = db.account(to_account_name)
            if account_name == to_account_name:
                raise LedgerError("转出账户和转入账户不能相同。")
            if str(source_account["currency"]) != currency:
                raise LedgerError("转出金额币种必须与转出账户一致。")
            to_amount = data.get("toAmount")
            if not to_amount and str(destination_account["currency"]) != currency:
                raise LedgerError("跨币种转账必须填写实际转入金额。")
            transaction_id = db.add_transaction(
                occurred_on=str(data.get("date", "")),
                kind="transfer",
                amount=str(data.get("amount", "")),
                currency=currency,
                description=description,
                account_name=account_name,
                to_account_name=to_account_name,
                to_amount=str(to_amount) if to_amount else None,
                source=source_marker,
            )
        return {"transactionId": transaction_id}

    def _import_ledger(self, user: dict[str, str]) -> dict[str, Any]:
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/vnd.sqlite3":
            raise WebError("账本文件格式无效，请选择SQLite数据库文件。", 415)
        body = self._read_body(MAX_LEDGER_BYTES)
        if not body.startswith(b"SQLite format 3\x00"):
            raise WebError("所选文件不是有效的SQLite账本。", 400)
        lock = _get_user_lock(user["id"])
        with lock:
            live_path = self.server.ledger_dir / f"{user['id']}.sqlite3"
            live_db = self._ledger(user["id"])
            try:
                existing_counts = (
                    int(live_db.connection.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]),
                    int(live_db.connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]),
                    int(live_db.connection.execute("SELECT COUNT(*) FROM web_sync_operations").fetchone()[0]),
                    int(live_db.connection.execute(
                        "SELECT COUNT(*) FROM categories WHERE name NOT IN (" + ",".join("?" for _ in DEFAULT_CATEGORIES) + ")",
                        tuple(name for name, _kind in DEFAULT_CATEGORIES),
                    ).fetchone()[0]),
                )
            finally:
                live_db.close()
            if any(existing_counts):
                raise WebError("只有尚未建立账户、流水或自定义内容的空Web账本可以导入，以免覆盖云端数据。", 409)
            temp_path = self.server.ledger_dir / f".{user['id']}-{uuid.uuid4().hex}.upload.sqlite3"
            try:
                temp_path.write_bytes(body)
                check = sqlite3.connect(temp_path)
                try:
                    integrity = check.execute("PRAGMA integrity_check").fetchone()
                    tables = {str(row[0]) for row in check.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                    if not integrity or integrity[0] != "ok" or not {"accounts", "transactions", "categories", "currencies"}.issubset(tables):
                        raise WebError("账本完整性检查失败，文件未导入。", 400)
                finally:
                    check.close()
                imported = Database(temp_path)
                try:
                    imported.initialize()
                    account_count = int(imported.connection.execute("SELECT COUNT(*) FROM accounts").fetchone()[0])
                    transaction_count = int(imported.connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0])
                    imported.connection.execute(
                        """CREATE TABLE IF NOT EXISTS web_sync_operations (
                            operation_id TEXT PRIMARY KEY,payload_hash TEXT NOT NULL,
                            resource_type TEXT NOT NULL,result_json TEXT NOT NULL,created_at TEXT NOT NULL
                        )"""
                    )
                    imported.connection.commit()
                    if str(imported.connection.execute("PRAGMA journal_mode").fetchone()[0]).lower() == "wal":
                        imported.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                        imported.connection.execute("PRAGMA journal_mode=DELETE")
                finally:
                    imported.close()
                backup_path = self.server.ledger_dir / f"{user['id']}-before-import-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}.sqlite3"
                if live_path.exists():
                    shutil.copy2(live_path, backup_path)
                Path(f"{live_path}-wal").unlink(missing_ok=True)
                Path(f"{live_path}-shm").unlink(missing_ok=True)
                os.replace(temp_path, live_path)
                return {"ok": True, "accounts": account_count, "transactions": transaction_count}
            finally:
                temp_path.unlink(missing_ok=True)

    def do_OPTIONS(self) -> None:
        self._send_bytes(204, b"", "application/json")


def main() -> int:
    parser = argparse.ArgumentParser(description="启动家庭记账系统的本机优先Web版")
    parser.add_argument("--host", default=os.environ.get("HOUSEHOLD_WEB_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("HOUSEHOLD_WEB_PORT", "8000")))
    parser.add_argument("--data-dir", default=os.environ.get("HOUSEHOLD_WEB_DATA_DIR", "data/web"))
    parser.add_argument("--public-origin", default=os.environ.get("HOUSEHOLD_WEB_PUBLIC_ORIGIN", ""))
    parser.add_argument("--tls-cert", default="")
    parser.add_argument("--tls-key", default="")
    args = parser.parse_args()
    host = args.host
    is_loopback = host in {"127.0.0.1", "localhost", "::1"}
    remote_allowed = os.environ.get("HOUSEHOLD_WEB_ALLOW_REMOTE", "") == "1"
    public_origin = args.public_origin.rstrip("/")
    if not is_loopback:
        if not remote_allowed:
            parser.error("默认仅本机访问。绑定局域网或公网必须设置 HOUSEHOLD_WEB_ALLOW_REMOTE=1。")
        if not public_origin.startswith("https://"):
            parser.error("远程访问必须配置 HTTPS 地址 HOUSEHOLD_WEB_PUBLIC_ORIGIN。")
    server = BookkeepingWebServer((host, args.port), Path(args.data_dir), public_origin)
    if args.tls_cert and args.tls_key:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(args.tls_cert, args.tls_key)
        server.socket = context.wrap_socket(server.socket, server_side=True)
    print(f"家庭记账 Web 已启动：{public_origin or f'http://{host}:{args.port}'}  数据目录：{server.data_dir}")
    if not is_loopback:
        print(f"公网地址由HTTPS反向代理提供：{public_origin}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nWeb服务已停止。")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
