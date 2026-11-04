"""D1-backed GitHub identity sessions and same-origin/CSRF checks."""
from __future__ import annotations

import hashlib
import hmac
import http.cookies
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit


SESSION_MAX_AGE = 60 * 60 * 24 * 30


class AuthError(ValueError):
    def __init__(self, message: str, status: int = 401):
        super().__init__(message)
        self.status = status


def cookie_values(request: Any) -> dict[str, str]:
    jar = http.cookies.SimpleCookie()
    try:
        jar.load(request.headers.get("Cookie", ""))
    except http.cookies.CookieError:
        return {}
    return {name: item.value for name, item in jar.items()}


def secure_request(request: Any) -> bool:
    forwarded = str(request.headers.get("X-Forwarded-Proto", "")).strip().lower()
    return forwarded == "https" or urlsplit(str(request.url)).scheme == "https"


def origin_is_valid(request: Any) -> bool:
    origin = str(request.headers.get("Origin", "")).rstrip("/").lower()
    if not origin:
        return False
    expected = f"{urlsplit(str(request.url)).scheme}://{urlsplit(str(request.url)).netloc}".rstrip("/").lower()
    return hmac.compare_digest(origin, expected)


def csrf_is_valid(request: Any) -> bool:
    cookies = cookie_values(request)
    cookie_token = cookies.get("hh_csrf", "")
    supplied = str(request.headers.get("X-CSRF-Token", ""))
    return bool(cookie_token and supplied and hmac.compare_digest(cookie_token, supplied))


def _response_meta(result: Any) -> Any:
    if isinstance(result, dict):
        return result.get("meta", {})
    return getattr(result, "meta", {})


def _changes(result: Any) -> int:
    meta = _response_meta(result)
    if isinstance(meta, dict):
        return int(meta.get("changes", 0) or 0)
    return int(getattr(meta, "changes", 0) or 0)


async def issue_session(
    database: Any, user_id: str, *, secure: bool, auth_provider: str = "github",
    same_site: str = "Strict",
) -> tuple[str, str]:
    if auth_provider not in {"github", "gitee"}:
        raise ValueError("Unsupported authentication provider.")
    if same_site not in {"Strict", "Lax"}:
        raise ValueError("Unsupported session cookie policy.")
    session = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(24)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(seconds=SESSION_MAX_AGE)
    await database.batch([
        database.prepare(
            "INSERT INTO cloud_sessions(token_hash,user_id,csrf_hash,expires_at,created_at,auth_provider) "
            "VALUES(?,?,?,?,?,?)"
        ).bind(
            hashlib.sha256(session.encode("ascii")).hexdigest(),
            user_id,
            hashlib.sha256(csrf.encode("ascii")).hexdigest(),
            expires.isoformat(),
            now.isoformat(),
            auth_provider,
        ),
        database.prepare("DELETE FROM cloud_sessions WHERE expires_at < ?").bind(now.isoformat()),
    ])
    secure_suffix = "; Secure" if secure else ""
    session_cookie = (
        f"hh_session={session}; Path=/; Max-Age={SESSION_MAX_AGE}; "
        f"HttpOnly; SameSite={same_site}{secure_suffix}"
    )
    csrf_cookie = f"hh_csrf={csrf}; Path=/; Max-Age={SESSION_MAX_AGE}; SameSite={same_site}{secure_suffix}"
    return session_cookie, csrf_cookie


async def clear_session(database: Any, request: Any, *, secure: bool) -> tuple[str, str]:
    token = cookie_values(request).get("hh_session", "")
    if token:
        await database.prepare("DELETE FROM cloud_sessions WHERE token_hash=?").bind(
            hashlib.sha256(token.encode("ascii", "ignore")).hexdigest()
        ).run()
    secure_suffix = "; Secure" if secure else ""
    return (
        f"hh_session=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict{secure_suffix}",
        f"hh_csrf=; Path=/; Max-Age=0; SameSite=Strict{secure_suffix}",
    )


async def require_user(database: Any, request: Any, *, csrf: bool = False) -> dict[str, str]:
    token = cookie_values(request).get("hh_session", "")
    if not token:
        raise AuthError("请先登录。")
    token_hash = hashlib.sha256(token.encode("ascii", "ignore")).hexdigest()
    row = await database.prepare(
        "SELECT s.user_id,s.csrf_hash,s.expires_at,s.auth_provider,u.github_login,u.github_id,gi.gitee_login, "
        "EXISTS(SELECT 1 FROM cloud_gitee_identities AS linked WHERE linked.user_id=u.id) AS gitee_linked "
        "FROM cloud_sessions AS s JOIN cloud_users AS u ON u.id=s.user_id "
        "LEFT JOIN cloud_gitee_identities AS gi ON gi.user_id=u.id "
        "WHERE s.token_hash=?"
    ).bind(token_hash).first()
    if row is None:
        raise AuthError("登录已过期，请重新登录。")
    now = datetime.now(timezone.utc).isoformat()
    if str(row["expires_at"]) <= now:
        await database.prepare("DELETE FROM cloud_sessions WHERE token_hash=?").bind(token_hash).run()
        raise AuthError("登录已过期，请重新登录。")

    user_id = str(row["user_id"])
    owner = str(request.headers.get("X-Ledger-Owner", ""))
    if owner and owner != user_id:
        raise AuthError("登录账号已变化，请刷新页面；待同步记录仍会保留。", 409)

    if csrf:
        cookies = cookie_values(request)
        csrf_cookie = cookies.get("hh_csrf", "")
        supplied = str(request.headers.get("X-CSRF-Token", ""))
        csrf_hash = hashlib.sha256(csrf_cookie.encode("ascii", "ignore")).hexdigest()
        if (
            not csrf_cookie
            or not supplied
            or not hmac.compare_digest(csrf_hash, str(row["csrf_hash"]))
            or not hmac.compare_digest(supplied, csrf_cookie)
        ):
            raise AuthError("安全校验失败，请刷新页面后重试。", 403)
    provider = str(row["auth_provider"] or "github")
    username = str(row["gitee_login"] or row["github_login"]) if provider == "gitee" else str(row["github_login"])
    return {
        "id": user_id,
        "username": username,
        "authProvider": provider,
        "giteeLinked": bool(row["gitee_linked"]),
        "githubLinked": not str(row["github_id"] or "").startswith("gitee:"),
    }
