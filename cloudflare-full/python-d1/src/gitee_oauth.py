"""Gitee OAuth login and explicit linking to a household ledger."""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlencode, urlsplit

from workers import fetch

from auth import AuthError, _changes, cookie_values, issue_session, require_user, secure_request
from secret_crypto import encrypt_text


AUTHORIZE_URL = "https://gitee.com/oauth/authorize"
TOKEN_URL = "https://gitee.com/oauth/token"
USER_URL = "https://gitee.com/api/v5/user"
CALLBACK_PATH = "/api/auth/gitee/callback"
EXPECTED_REDIRECT_URI = "https://household-bookkeeping-python-d1-stage.household-bookkeeping-cloud-test.workers.dev/api/auth/gitee/callback"
FLOW_COOKIE = "hh_gitee_oauth"
FLOW_TTL_SECONDS = 600


class GiteeOAuthError(ValueError):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.status = status


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp(value: datetime) -> str:
    return value.isoformat()


def _field(row, name):
    if isinstance(row, dict):
        return row[name]
    return getattr(row, name)


def _config(env):
    client_id = str(getattr(env, "GITEE_CLIENT_ID", "") or "").strip()
    client_secret = str(getattr(env, "GITEE_CLIENT_SECRET", "") or "").strip()
    redirect_uri = str(getattr(env, "GITEE_REDIRECT_URI", "") or "").strip()
    parsed = urlsplit(redirect_uri)
    if (not client_id or not client_secret or redirect_uri != EXPECTED_REDIRECT_URI
            or parsed.scheme != "https" or parsed.path != CALLBACK_PATH
            or parsed.query or parsed.fragment):
        raise GiteeOAuthError("not_configured", "Gitee 登录尚未配置。", 503)
    return client_id, client_secret, redirect_uri


async def _limit_start(database, client_ip: str):
    now = int(_now().timestamp())
    bucket = hashlib.sha256(("gitee:" + client_ip).encode("utf-8")).hexdigest()
    await database.batch([
        database.prepare(
            "INSERT OR IGNORE INTO rate_limit_buckets(bucket_key,window_started_at,request_count) VALUES(?,?,0)"
        ).bind(bucket, now),
        database.prepare(
            "UPDATE rate_limit_buckets SET window_started_at=?,request_count=0 "
            "WHERE bucket_key=? AND window_started_at<=?"
        ).bind(now, bucket, now - 600),
        database.prepare(
            "UPDATE rate_limit_buckets SET request_count=request_count+1 WHERE bucket_key=?"
        ).bind(bucket),
    ])
    row = await database.prepare(
        "SELECT request_count FROM rate_limit_buckets WHERE bucket_key=?"
    ).bind(bucket).first()
    if row is not None and int(_field(row, "request_count")) > 10:
        raise GiteeOAuthError("rate_limited", "Gitee 登录请求过多，请十分钟后再试。", 429)


async def start_flow(database, request, body, *, env):
    client_id, _, redirect_uri = _config(env)
    mode = body.get("mode", "login")
    if mode not in {"login", "link"}:
        raise GiteeOAuthError("invalid_mode", "Gitee 登录模式无效。")

    link_user_id = None
    if mode == "link":
        link_user_id = (await require_user(database, request, csrf=True))["id"]
    else:
        try:
            await require_user(database, request)
        except AuthError as exc:
            if exc.status != 401:
                raise GiteeOAuthError("session_error", str(exc), exc.status) from exc
        else:
            raise GiteeOAuthError("already_signed_in", "请在已登录的原账本中关联 Gitee。", 409)

    await _limit_start(database, str(request.headers.get("CF-Connecting-IP", "unknown")))
    now = _now()
    state = secrets.token_urlsafe(32)
    flow_id = uuid.uuid4().hex
    await database.prepare(
        "INSERT INTO gitee_login_flows(flow_id,state_hash,mode,link_user_id,redirect_uri,expires_at,state,created_at) "
        "VALUES(?,?,?,?,?,?,'pending',?)"
    ).bind(
        flow_id,
        hashlib.sha256(state.encode("utf-8")).hexdigest(),
        mode,
        link_user_id,
        redirect_uri,
        _stamp(now + timedelta(seconds=FLOW_TTL_SECONDS)),
        _stamp(now),
    ).run()

    authorization_url = AUTHORIZE_URL + "?" + urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "user_info",
        "state": state,
    })
    return {"authorizationUrl": authorization_url, "state": state, "maxAge": FLOW_TTL_SECONDS}


async def _provider_json(url: str, *, method="GET", headers=None, body=None):
    try:
        response = await fetch(
            url,
            method=method,
            headers=headers or {"Accept": "application/json"},
            body=body,
            redirect="manual",
        )
    except Exception as exc:
        raise GiteeOAuthError("provider_unavailable", "无法连接 Gitee 授权服务，请稍后重试。", 502) from exc
    try:
        payload = await response.json()
    except Exception as exc:
        raise GiteeOAuthError("provider_response", "Gitee 返回的数据无法读取，请稍后重试。", 502) from exc
    if not response.ok or not isinstance(payload, dict):
        raise GiteeOAuthError("provider_rejected", "Gitee 暂时无法完成授权，请稍后重试。", 502)
    return payload


async def _claim_flow(database, request):
    query = parse_qs(urlsplit(str(request.url)).query, keep_blank_values=True)
    state = str((query.get("state") or [""])[0])
    cookie_state = cookie_values(request).get(FLOW_COOKIE, "")
    if not state or not cookie_state or not hmac.compare_digest(state, cookie_state):
        raise GiteeOAuthError("invalid_state", "Gitee 登录校验失败，请重新开始。", 401)

    state_hash = hashlib.sha256(state.encode("utf-8")).hexdigest()
    row = await database.prepare(
        "SELECT flow_id,state_hash,mode,link_user_id,redirect_uri,expires_at,state "
        "FROM gitee_login_flows WHERE state_hash=?"
    ).bind(state_hash).first()
    if row is None or str(_field(row, "expires_at")) <= _stamp(_now()):
        raise GiteeOAuthError("expired", "Gitee 登录已过期，请重新开始。", 401)
    claim = await database.prepare(
        "UPDATE gitee_login_flows SET state='processing' WHERE flow_id=? AND state_hash=? AND state='pending'"
    ).bind(str(_field(row, "flow_id")), state_hash).run()
    if _changes(claim) != 1:
        raise GiteeOAuthError("replayed", "Gitee 登录已处理或已过期，请重新开始。", 409)
    return row, query


async def _exchange_identity(code: str, redirect_uri: str, *, env):
    client_id, client_secret, _ = _config(env)
    token = await _provider_json(
        TOKEN_URL,
        method="POST",
        headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
        body=urlencode({
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
        }),
    )
    access_token = token.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise GiteeOAuthError("token_failed", "Gitee 未返回有效授权令牌，请重新登录。", 401)
    profile_url = USER_URL + "?" + urlencode({"access_token": access_token})
    profile = await _provider_json(profile_url, headers={"Accept": "application/json", "User-Agent": "HouseholdBookkeeping"})
    raw_id = profile.get("id")
    subject = str(raw_id) if isinstance(raw_id, (str, int)) and not isinstance(raw_id, bool) else ""
    login = profile.get("login")
    if not re.fullmatch(r"[1-9][0-9]{0,20}", subject) or not isinstance(login, str):
        raise GiteeOAuthError("identity_invalid", "Gitee 身份信息无效，请重新登录。", 401)
    login = login.strip()
    if not login or len(login) > 100 or any(ord(char) < 32 for char in login):
        raise GiteeOAuthError("identity_invalid", "Gitee 身份信息无效，请重新登录。", 401)
    return subject, login


async def _create_gitee_account(database, subject: str, login: str, env) -> tuple[str, bool]:
    """Create a Gitee-only account without requiring a GitHub identity.

    The current D1 schema requires legacy GitHub columns on cloud_users. A
    reserved, non-GitHub-shaped value keeps that schema compatible while the
    real Gitee identity remains authoritative in cloud_gitee_identities.
    """
    user_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "household-bookkeeping:gitee:" + subject))
    placeholder_github_id = "gitee:" + subject
    placeholder_github_login = "@gitee:" + subject
    now_text = _stamp(_now())
    initial_config = await encrypt_text(
        json.dumps({"onboardingCompleted": False, "onboardingStage": "base"}, separators=(",", ":")),
        str(env.TOKEN_ENCRYPTION_KEY), "user:" + user_id + ":mobile-config",
    )
    await database.batch([
        database.prepare(
            "INSERT OR IGNORE INTO cloud_users(id,github_login,github_id,created_at) VALUES(?,?,?,?)"
        ).bind(user_id, placeholder_github_login, placeholder_github_id, now_text),
        database.prepare(
            "INSERT OR IGNORE INTO user_state_roots(user_id,revision,manifest_json,updated_at) VALUES(?,?,?,?)"
        ).bind(user_id, "0", "{}", now_text),
        database.prepare(
            "INSERT OR IGNORE INTO user_secrets(user_id,secret_name,encrypted_value,updated_at) VALUES(?,?,?,?)"
        ).bind(user_id, "mobile-config", initial_config, now_text),
        database.prepare(
            "INSERT INTO cloud_gitee_identities(gitee_id,user_id,gitee_login,created_at,updated_at) "
            "VALUES(?,?,?,?,?) ON CONFLICT(gitee_id) DO UPDATE SET "
            "gitee_login=excluded.gitee_login,updated_at=excluded.updated_at"
        ).bind(subject, user_id, login, now_text, now_text),
    ])
    identity = await database.prepare(
        "SELECT user_id FROM cloud_gitee_identities WHERE gitee_id=?"
    ).bind(subject).first()
    if identity is None:
        raise GiteeOAuthError("account_create_failed", "无法创建 Gitee 账本，请稍后重试。", 500)
    resolved_user_id = str(_field(identity, "user_id"))
    created = resolved_user_id == user_id
    if not created:
        # A concurrent link may have claimed this Gitee identity after the
        # initial lookup. Remove only the unused placeholder created above.
        await database.prepare(
            "DELETE FROM cloud_users WHERE id=? AND github_id=? AND NOT EXISTS ("
            "SELECT 1 FROM cloud_gitee_identities WHERE user_id=?)"
        ).bind(user_id, placeholder_github_id, user_id).run()
    return resolved_user_id, created


async def finish_flow(database, request, *, env):
    _config(env)
    row, query = await _claim_flow(database, request)
    flow_id = str(_field(row, "flow_id"))
    state_hash = str(_field(row, "state_hash"))
    try:
        provider_error = str((query.get("error") or [""])[0])
        if provider_error:
            raise GiteeOAuthError("denied", "你取消或拒绝了 Gitee 授权。", 401)
        code = str((query.get("code") or [""])[0])
        if not code or len(code) > 4096:
            raise GiteeOAuthError("code_missing", "Gitee 没有返回授权码，请重新开始。", 401)

        subject, login = await _exchange_identity(code, str(_field(row, "redirect_uri")), env=env)
        mode = str(_field(row, "mode"))
        if mode == "link":
            try:
                active = await require_user(database, request)
            except AuthError as exc:
                raise GiteeOAuthError("session_expired", "原账本登录已过期，请重新登录后再关联 Gitee。", 401) from exc
            link_user_id = str(_field(row, "link_user_id") or "")
            if active["id"] != link_user_id:
                raise GiteeOAuthError("account_changed", "登录账号已变化，请用原账本重新关联 Gitee。", 403)
            identity = await database.prepare(
                "SELECT user_id FROM cloud_gitee_identities WHERE gitee_id=?"
            ).bind(subject).first()
            if identity is not None and str(_field(identity, "user_id")) != link_user_id:
                raise GiteeOAuthError("identity_in_use", "这个 Gitee 账号已关联另一份账本。", 409)
            other = await database.prepare(
                "SELECT gitee_id FROM cloud_gitee_identities WHERE user_id=?"
            ).bind(link_user_id).first()
            if other is not None and str(_field(other, "gitee_id")) != subject:
                raise GiteeOAuthError("another_identity", "当前账本已关联另一个 Gitee 账号。", 409)
            now_text = _stamp(_now())
            await database.prepare(
                "INSERT INTO cloud_gitee_identities(gitee_id,user_id,gitee_login,created_at,updated_at) "
                "VALUES(?,?,?,?,?) ON CONFLICT(gitee_id) DO UPDATE SET gitee_login=excluded.gitee_login,updated_at=excluded.updated_at"
            ).bind(subject, link_user_id, login, now_text, now_text).run()
            await database.prepare(
                "UPDATE gitee_login_flows SET state='consumed' WHERE flow_id=? AND state='processing'"
            ).bind(flow_id).run()
            return {"mode": "link", "redirectQuery": "gitee_linked=1", "sessionCookies": ()}

        identity = await database.prepare(
            "SELECT user_id FROM cloud_gitee_identities WHERE gitee_id=?"
        ).bind(subject).first()
        created = False
        if identity is None:
            user_id, created = await _create_gitee_account(database, subject, login, env)
        else:
            user_id = str(_field(identity, "user_id"))
        await database.prepare(
            "UPDATE cloud_gitee_identities SET gitee_login=?,updated_at=? WHERE gitee_id=?"
        ).bind(login, _stamp(_now()), subject).run()
        await database.prepare(
            "UPDATE gitee_login_flows SET state='consumed' WHERE flow_id=? AND state='processing'"
        ).bind(flow_id).run()
        session_cookies = await issue_session(
            database, user_id, secure=secure_request(request), auth_provider="gitee", same_site="Lax",
        )
        redirect_query = "gitee_login=1&gitee_created=1" if created else "gitee_login=1"
        return {"mode": "login", "redirectQuery": redirect_query, "sessionCookies": session_cookies}
    except Exception:
        await database.prepare(
            "UPDATE gitee_login_flows SET state='failed' WHERE flow_id=? AND state='processing'"
        ).bind(flow_id).run()
        raise


async def fail_flow(database, request):
    """Consume an OAuth-denial callback after validating its state cookie."""
    row, _ = await _claim_flow(database, request)
    await database.prepare(
        "UPDATE gitee_login_flows SET state='cancelled' WHERE flow_id=? AND state='processing'"
    ).bind(str(_field(row, "flow_id"))).run()
