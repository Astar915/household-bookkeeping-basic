"""GitHub Device Flow implemented with asynchronous Workers fetch + D1 state."""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from workers import fetch

from auth import cookie_values, issue_session, require_user, secure_request
from secret_crypto import decrypt_text, encrypt_text


# Public GitHub App Client ID already used by the desktop and self-hosted web app.
from bookkeeping.github_app_config import GITHUB_APP_CLIENT_ID
DEVICE_CODE_URL = "https://github.com/login/device/code"
DEVICE_TOKEN_URL = "https://github.com/login/oauth/access_token"
API_USER_URL = "https://api.github.com/user"
DEVICE_URI = "https://github.com/login/device"


class GitHubFlowError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp(value: datetime) -> str:
    return value.isoformat()


def _field(row, name):
    if isinstance(row, dict):
        return row[name]
    return getattr(row, name)


def _meta_changes(result) -> int:
    meta = result.get("meta", {}) if isinstance(result, dict) else getattr(result, "meta", {})
    if isinstance(meta, dict):
        return int(meta.get("changes", 0) or 0)
    return int(getattr(meta, "changes", 0) or 0)


async def _request_json(url: str, *, method="GET", headers=None, body=None):
    try:
        response = await fetch(
            url,
            method=method,
            headers=headers or {"Accept": "application/json"},
            body=body,
            redirect="manual",
        )
    except Exception as exc:
        # Keep the underlying transport cause in Worker logs for diagnosis,
        # while never returning it to the browser or logging request bodies.
        print(f"GitHub OAuth fetch failed ({type(exc).__name__}): {str(exc)[:240]}")
        raise GitHubFlowError("无法连接 GitHub 授权服务，请稍后重试。", 502) from exc
    try:
        value = await response.json()
    except Exception as exc:
        raise GitHubFlowError("GitHub 返回的数据无法读取，请稍后重试。", 502) from exc
    if not response.ok:
        raise GitHubFlowError("GitHub 暂时无法完成授权，请稍后重试。", 502)
    return value


async def _limit_start(database, client_key: str):
    now = int(_now().timestamp())
    await database.batch([
        database.prepare(
            "INSERT OR IGNORE INTO rate_limit_buckets(bucket_key,window_started_at,request_count) VALUES(?,?,0)"
        ).bind(client_key, now),
        database.prepare(
            "UPDATE rate_limit_buckets SET window_started_at=?,request_count=0 "
            "WHERE bucket_key=? AND window_started_at<=?"
        ).bind(now, client_key, now - 600),
        database.prepare(
            "UPDATE rate_limit_buckets SET request_count=request_count+1 WHERE bucket_key=?"
        ).bind(client_key),
    ])
    row = await database.prepare(
        "SELECT request_count FROM rate_limit_buckets WHERE bucket_key=?"
    ).bind(client_key).first()
    if row is not None and int(_field(row, "request_count")) > 10:
        raise GitHubFlowError("GitHub 登录请求过多，请十分钟后再试。", 429)


def _valid_flow_cookie(request, flow_id: str):
    cookie = cookie_values(request).get("hh_gh_login", "")
    parts = cookie.split(".", 1)
    if len(parts) != 2 or parts[0] != flow_id or not parts[1]:
        raise GitHubFlowError("GitHub 登录已过期，请重新开始。", 401)
    return cookie, hashlib.sha256(parts[1].encode("utf-8")).hexdigest()


async def start_flow(database, request, body, *, env):
    mode = body.get("mode", "login")
    if mode not in {"login", "link"}:
        raise GitHubFlowError("登录模式无效。")
    link_user = None
    if mode == "link":
        link_user = (await require_user(database, request, csrf=True))["id"]

    ip = str(request.headers.get("CF-Connecting-IP", "unknown"))
    await _limit_start(database, hashlib.sha256(ip.encode()).hexdigest())

    old_cookie = cookie_values(request).get("hh_gh_login", "")
    old_parts = old_cookie.split(".", 1)
    if len(old_parts) == 2:
        await database.prepare(
            "UPDATE github_login_flows SET state='cancelled',result_json='{}' "
            "WHERE flow_id=? AND cookie_hash=? AND state IN ('pending','authorized')"
        ).bind(old_parts[0], hashlib.sha256(old_parts[1].encode()).hexdigest()).run()

    now = _now()
    form = urlencode({"client_id": GITHUB_APP_CLIENT_ID, "scope": "offline_access"})
    challenge = await _request_json(
        DEVICE_CODE_URL,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        body=form,
    )
    required = ("device_code", "user_code", "verification_uri", "interval", "expires_in")
    if not isinstance(challenge, dict) or any(key not in challenge for key in required):
        raise GitHubFlowError("无法开始 GitHub 授权，请稍后重试。", 502)
    if challenge.get("verification_uri") != DEVICE_URI:
        raise GitHubFlowError("GitHub 授权地址校验失败。", 502)

    flow_id = uuid.uuid4().hex
    secret = secrets.token_urlsafe(32)
    duration = min(max(int(challenge["expires_in"]), 1), 900)
    interval = max(5, int(challenge["interval"]))
    await database.prepare(
        "INSERT INTO github_login_flows(flow_id,cookie_hash,device_code,user_code,verification_uri,"
        "poll_interval_seconds,expires_at,last_polled_at,state,result_json,created_at) "
        "VALUES(?,?,?,?,?,?,?,NULL,'pending','{}',?)"
    ).bind(
        flow_id,
        hashlib.sha256(secret.encode()).hexdigest(),
        str(challenge["device_code"]),
        str(challenge["user_code"]),
        DEVICE_URI,
        interval,
        _stamp(now + timedelta(seconds=duration)),
        _stamp(now),
    ).run()
    # Linking is encoded in an opaque D1 result field; it is not sent to the
    # browser and is checked against the current session again at finish time.
    if link_user:
        await database.prepare(
            "UPDATE github_login_flows SET result_json=? WHERE flow_id=?"
        ).bind(json.dumps({"linkUser": link_user}, separators=(",", ":")), flow_id).run()
    cookie = f"{flow_id}.{secret}"
    return {
        "flow": {"flowId": flow_id, "userCode": str(challenge["user_code"]),
                 "verificationUri": DEVICE_URI, "expiresIn": duration, "state": "pending"},
        "cookie": cookie,
        "maxAge": duration,
    }


async def _flow_row(database, request, flow_id: str):
    _, cookie_hash = _valid_flow_cookie(request, flow_id)
    row = await database.prepare(
        "SELECT flow_id,cookie_hash,device_code,user_code,verification_uri,poll_interval_seconds,"
        "expires_at,last_polled_at,state,result_json FROM github_login_flows WHERE flow_id=? AND cookie_hash=?"
    ).bind(flow_id, cookie_hash).first()
    if row is None:
        raise GitHubFlowError("GitHub 登录已过期，请重新开始。", 401)
    expires_at = str(_field(row, "expires_at"))
    if expires_at <= _stamp(_now()):
        await database.prepare(
            "UPDATE github_login_flows SET state='expired',result_json='{}' WHERE flow_id=?"
        ).bind(flow_id).run()
        raise GitHubFlowError("GitHub 登录已过期，请重新开始。", 401)
    return row


async def _poll_device_flow(database, row, flow_id: str, *, env):
    now = _now()
    last = _field(row, "last_polled_at")
    interval = max(5, int(_field(row, "poll_interval_seconds")))
    if last:
        try:
            if (now - datetime.fromisoformat(str(last))).total_seconds() < interval:
                return
        except ValueError:
            pass
    now_text = _stamp(now)
    threshold = _stamp(now - timedelta(seconds=interval))
    claim = await database.prepare(
        "UPDATE github_login_flows SET last_polled_at=? WHERE flow_id=? AND state='pending' "
        "AND cookie_hash=? AND (last_polled_at IS NULL OR last_polled_at<=?)"
    ).bind(now_text, flow_id, str(_field(row, "cookie_hash")), threshold).run()
    if _meta_changes(claim) != 1:
        return

    form = urlencode({
        "client_id": GITHUB_APP_CLIENT_ID,
        "device_code": str(_field(row, "device_code")),
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
    })
    response = await _request_json(
        DEVICE_TOKEN_URL,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        body=form,
    )
    token = response.get("access_token") if isinstance(response, dict) else None
    if isinstance(token, str) and token:
        credentials = {
            "access_token": token,
            "refresh_token": str(response.get("refresh_token") or ""),
        }
        encrypted = await encrypt_text(json.dumps(credentials, separators=(",", ":")),
                                       str(env.TOKEN_ENCRYPTION_KEY), "github-flow:" + flow_id)
        try:
            existing_flow_state = json.loads(str(_field(row, "result_json") or "{}"))
        except (TypeError, ValueError):
            existing_flow_state = {}
        await database.prepare(
            "UPDATE github_login_flows SET state='authorized',result_json=? WHERE flow_id=? AND state='pending'"
        ).bind(json.dumps({"credentials": encrypted, "linkUser": existing_flow_state.get("linkUser")},
                          separators=(",", ":")), flow_id).run()
        return

    error = str(response.get("error") or "") if isinstance(response, dict) else ""
    if error in {"authorization_pending", "slow_down"}:
        if error == "slow_down":
            await database.prepare(
                "UPDATE github_login_flows SET poll_interval_seconds=poll_interval_seconds+5 WHERE flow_id=? AND state='pending'"
            ).bind(flow_id).run()
        return
    messages = {
        "expired_token": "GitHub 授权码已过期，请重新连接。",
        "access_denied": "你拒绝了 GitHub 授权。",
        "device_flow_disabled": "GitHub App 尚未启用 Device Flow，请检查 App 配置。",
        "incorrect_client_credentials": "GitHub App Client ID 无效，请检查 App 配置。",
        "bad_verification_code": "GitHub 验证码无效或已过期，请重新连接。",
        "unverified_user_email": "请先验证 GitHub 账号的主要邮箱，然后重新连接。",
    }
    message = messages.get(error, "GitHub 授权失败，请重新发起授权。")
    await database.prepare(
        "UPDATE github_login_flows SET state='failed',result_json=? WHERE flow_id=? AND state='pending'"
    ).bind(json.dumps({"error": message}, ensure_ascii=False), flow_id).run()


async def flow_status(database, request, flow_id: str, *, env):
    row = await _flow_row(database, request, flow_id)
    if str(_field(row, "state")) == "pending":
        await _poll_device_flow(database, row, flow_id, env=env)
        row = await _flow_row(database, request, flow_id)
    state = str(_field(row, "state"))
    result = json.loads(str(_field(row, "result_json") or "{}"))
    response = {"state": state, "userCode": str(_field(row, "user_code")), "verificationUri": DEVICE_URI}
    if state == "failed" and result.get("error"):
        response["error"] = result["error"]
    return response


async def cancel_flow(database, request, flow_id: str):
    await _flow_row(database, request, flow_id)
    await database.prepare(
        "UPDATE github_login_flows SET state='cancelled',result_json='{}' WHERE flow_id=?"
    ).bind(flow_id).run()


async def finish_flow(database, request, flow_id: str, *, env):
    row = await _flow_row(database, request, flow_id)
    if str(_field(row, "state")) != "authorized":
        raise GitHubFlowError("请先在 GitHub 完成授权。")
    result = json.loads(str(_field(row, "result_json") or "{}"))
    encrypted = result.get("credentials")
    if not encrypted:
        raise GitHubFlowError("GitHub 授权结果已过期，请重新开始。", 401)
    credentials = json.loads(await decrypt_text(
        encrypted, str(env.TOKEN_ENCRYPTION_KEY), "github-flow:" + flow_id
    ))
    token = str(credentials.get("access_token", ""))
    identity = await _request_json(
        API_USER_URL,
        headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "HouseholdBookkeeping"},
    )
    subject, login = str(identity.get("id", "")), str(identity.get("login", ""))
    if not re.fullmatch(r"[1-9][0-9]{0,20}", subject) or not re.fullmatch(r"[A-Za-z0-9-]{1,39}", login):
        raise GitHubFlowError("GitHub 身份校验失败，请重新登录。", 401)
    if identity.get("type") not in (None, "User"):
        raise GitHubFlowError("请使用个人 GitHub 账号登录。", 403)

    link_user = None
    try:
        flow_result = json.loads(str(_field(row, "result_json") or "{}"))
        link_user = flow_result.get("linkUser")
    except (TypeError, ValueError):
        pass
    if link_user:
        active = (await require_user(database, request, csrf=True))["id"]
        if active != link_user:
            raise GitHubFlowError("原账号会话已变化，请重新验证后关联。", 403)

    by_github_id = await database.prepare("SELECT id FROM cloud_users WHERE github_id=?").bind(subject).first()
    if by_github_id is not None:
        user_id = str(_field(by_github_id, "id"))
        if link_user and user_id != link_user:
            raise GitHubFlowError("这个 GitHub 已关联另一份账本，当前账本保持不变。", 409)
        await database.prepare("UPDATE cloud_users SET github_login=? WHERE id=?").bind(login, user_id).run()
    elif link_user:
        existing = await database.prepare("SELECT github_id FROM cloud_users WHERE id=?").bind(link_user).first()
        if existing is None:
            raise GitHubFlowError("原账号不存在，请重新登录。", 404)
        old_github_id = str(_field(existing, "github_id") or "")
        if not old_github_id.startswith("gitee:"):
            raise GitHubFlowError("当前账本已关联其他 GitHub，不能直接替换。", 409)
        login_owner = await database.prepare(
            "SELECT id FROM cloud_users WHERE github_login=? COLLATE NOCASE AND id<>?"
        ).bind(login, link_user).first()
        if login_owner is not None:
            raise GitHubFlowError("这个 GitHub 登录名已用于另一份账本，未关联账号。", 409)
        changed = await database.prepare(
            "UPDATE cloud_users SET github_login=?,github_id=? WHERE id=? AND github_id=?"
        ).bind(login, subject, link_user, old_github_id).run()
        if _meta_changes(changed) != 1:
            latest = await database.prepare("SELECT github_id FROM cloud_users WHERE id=?").bind(link_user).first()
            if latest is None or str(_field(latest, "github_id")) != subject:
                raise GitHubFlowError("当前账本关联状态已变化，请刷新后重试。", 409)
        user_id = link_user
    else:
        user_id = str(uuid.uuid4())
        now_text = _stamp(_now())
        initial_config = await encrypt_text(
            json.dumps({"onboardingCompleted": False, "onboardingStage": "base"}, separators=(",", ":")),
            str(env.TOKEN_ENCRYPTION_KEY), "user:" + user_id + ":mobile-config",
        )
        await database.batch([
            database.prepare(
                "INSERT INTO cloud_users(id,github_login,github_id,created_at) VALUES(?,?,?,?)"
            ).bind(user_id, login, subject, now_text),
            database.prepare(
                "INSERT INTO user_state_roots(user_id,revision,manifest_json,updated_at) VALUES(?,?,?,?)"
            ).bind(user_id, "0", "{}", now_text),
            database.prepare(
                "INSERT INTO user_secrets(user_id,secret_name,encrypted_value,updated_at) VALUES(?,?,?,?)"
            ).bind(user_id, "mobile-config", initial_config, now_text),
        ])

    # Keep the same post-login backup behavior as the full self-hosted app.
    # The OAuth credential is AES-GCM encrypted before it reaches D1.
    cloud_credentials = {
        "token": str(credentials.get("access_token", "")),
        "refresh_token": str(credentials.get("refresh_token", "")),
        "client_id": GITHUB_APP_CLIENT_ID,
        "auth_flow": "device",
        "repositoryName": "household-bookkeeping-data",
        "repository": f"{login}/household-bookkeeping-data",
        "lastSha": None,
    }
    secret = await encrypt_text(json.dumps(cloud_credentials, separators=(",", ":")),
                                str(env.TOKEN_ENCRYPTION_KEY), "user:" + user_id + ":github-sync")
    await database.prepare(
        "INSERT INTO user_secrets(user_id,secret_name,encrypted_value,updated_at) VALUES(?,?,?,?) "
        "ON CONFLICT(user_id,secret_name) DO UPDATE SET encrypted_value=excluded.encrypted_value,updated_at=excluded.updated_at"
    ).bind(user_id, "github-sync", secret, _stamp(_now())).run()

    await database.prepare(
        "UPDATE github_login_flows SET state='consumed',result_json='{}' WHERE flow_id=?"
    ).bind(flow_id).run()
    session_cookies = await issue_session(database, user_id, secure=secure_request(request))
    gitee_identity = await database.prepare(
        "SELECT gitee_login FROM cloud_gitee_identities WHERE user_id=?"
    ).bind(user_id).first()
    return {"user": {"id": user_id, "username": login, "authProvider": "github",
                      "giteeLinked": gitee_identity is not None, "githubLinked": True},
            "sessionCookies": session_cookies}
