"""Durable execution for mobile actions and replayable Agent model calls."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlsplit

from workers import fetch

from ledger_runtime import execute_action, load_mobile_config
from secret_crypto import encrypt_text
from model_jobs import (
    MAX_CLOUD_BUNDLE_BYTES,
    MAX_FX_RESPONSE_BYTES,
    MAX_MODEL_RESPONSE_BYTES,
    ModelRequestRequired,
    cleanup_job_private_state,
    load_job_payload,
    load_model_replies,
    save_model_response,
    safe_response_headers,
)


MAX_MODEL_CALLS_PER_JOB = 32
MAX_RATE_LOOKUPS_PER_JOB = 128
MAX_PRODUCT_SEARCH_RESPONSE_BYTES = 128 * 1024
PRODUCT_SEARCH_HOSTS = {
    "zh.wikipedia.org", "ja.wikipedia.org", "en.wikipedia.org",
    "html.duckduckgo.com", "world.openfoodfacts.org",
}


def _field(row, key):
    return row[key] if isinstance(row, dict) else getattr(row, key)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _json_result(job):
    try:
        return json.loads(str(_field(job, "result_json") or "{}"))
    except (TypeError, ValueError):
        return {"error": "后台操作结果无法读取，请刷新并核对账本。"}


async def _read_job(database, user_id: str, operation_id: str):
    job = await database.prepare(
        "SELECT action,fingerprint,state,cancel_requested,result_json,created_at FROM app_jobs "
        "WHERE user_id=? AND operation_id=?"
    ).bind(user_id, operation_id).first()
    if job is None:
        raise ValueError("找不到后台操作记录。")
    return job


async def _ensure_active(database, user_id: str, operation_id: str):
    job = await _read_job(database, user_id, operation_id)
    state = str(_field(job, "state"))
    if state == "done":
        return False, job
    if state == "cancelled" or int(_field(job, "cancel_requested")):
        await database.prepare(
            "UPDATE app_jobs SET state='cancelled',message='已取消',updated_at=? "
            "WHERE user_id=? AND operation_id=? AND state!='done'"
        ).bind(_now(), user_id, operation_id).run()
        raise RuntimeError("操作已取消，本次更改没有写入账本。")
    if state not in {"queued", "running"}:
        raise RuntimeError("此操作已结束，请刷新页面后重试。")
    await database.prepare(
        "UPDATE app_jobs SET state='running',message='正在处理…',updated_at=? "
        "WHERE user_id=? AND operation_id=? AND state IN ('queued','running') AND cancel_requested=0"
    ).bind(_now(), user_id, operation_id).run()
    return True, job


async def _provider_fetch(envelope: dict, *, max_bytes=MAX_MODEL_RESPONSE_BYTES):
    """Call the configured model via Workers fetch; persist only bounded bytes."""
    source_parts = urlsplit(envelope["url"])
    source_host = (source_parts.hostname or "").lower()
    request_method = str(envelope.get("method", "GET")).upper()
    try:
        standard_https = (
            source_parts.scheme == "https"
            and source_parts.port in (None, 443)
            and source_parts.username is None
            and source_parts.password is None
        )
    except ValueError:
        standard_https = False
    wikipedia_search = (
        standard_https
        and source_host in {"zh.wikipedia.org", "ja.wikipedia.org", "en.wikipedia.org"}
        and source_parts.path == "/w/api.php"
        and request_method == "GET"
    )
    duckduckgo_search = (
        standard_https
        and source_host == "html.duckduckgo.com"
        and source_parts.path == "/html/"
        and request_method == "GET"
    )
    open_food_facts_search = (
        standard_https
        and source_host == "world.openfoodfacts.org"
        and source_parts.path == "/cgi/search.pl"
        and request_method == "GET"
    )
    is_product_search = wikipedia_search or duckduckgo_search or open_food_facts_search
    if source_host in PRODUCT_SEARCH_HOSTS and not is_product_search:
        raise ValueError("商品查询只能访问受限的公开搜索接口。")
    if is_product_search:
        query = parse_qs(source_parts.query, keep_blank_values=True)
        if wikipedia_search:
            try:
                search_limit = int((query.get("srlimit") or ["0"])[0] or "0")
            except (TypeError, ValueError):
                search_limit = 0
            valid_query = (
                query.get("action") == ["query"]
                and query.get("list") == ["search"]
                and query.get("srprop") == ["snippet"]
                and query.get("srwhat") == ["text"]
                and query.get("format") == ["json"]
                and query.get("utf8") == ["1"]
                and bool((query.get("srsearch") or [""])[0].strip())
                and 1 <= search_limit <= 3
                and set(query) == {"action", "list", "srsearch", "srwhat", "srprop", "srlimit", "format", "utf8"}
            )
        elif duckduckgo_search:
            search_term = (query.get("q") or [""])[0].strip()
            valid_query = (
                set(query) == {"q"}
                and bool(search_term)
                and len(query.get("q", [])) == 1
                and len(search_term) <= 96
                and not any(ord(character) < 32 for character in search_term)
            )
        else:
            search_term = (query.get("search_terms") or [""])[0].strip()
            try:
                product_limit = int((query.get("page_size") or ["0"])[0] or "0")
            except (TypeError, ValueError):
                product_limit = 0
            valid_query = (
                set(query) == {"search_terms", "search_simple", "action", "json", "page_size", "fields"}
                and bool(search_term)
                and len(search_term) <= 96
                and query.get("search_simple") == ["1"]
                and query.get("action") == ["process"]
                and query.get("json") == ["1"]
                and 1 <= product_limit <= 4
                and query.get("fields") == ["product_name,brands,categories,categories_tags,labels"]
            )
        if not valid_query:
            raise ValueError("商品查询参数超出允许范围。")
        request_headers = envelope.get("headers") or {}
        if not isinstance(request_headers, dict):
            raise ValueError("商品查询请求头无效。")
        headers = {str(key).lower(): str(value) for key, value in request_headers.items()}
        if set(headers) - {"accept", "user-agent"} or envelope.get("body"):
            raise ValueError("商品查询请求不允许携带账户或 API 凭据。")
        max_bytes = min(max_bytes, MAX_PRODUCT_SEARCH_RESPONSE_BYTES)
    # Workers does not support redirect="error": it throws before sending.
    # Follow GitHub's API redirects, but keep other providers manual so an
    # Authorization header is never forwarded to an arbitrary redirect host.
    redirect = "follow" if source_host == "api.github.com" else "manual"
    options = {
        "method": envelope["method"],
        "headers": envelope["headers"],
        "redirect": redirect,
    }
    if envelope["body"]:
        options["body"] = envelope["body"].decode("utf-8")
    try:
        response = await fetch(envelope["url"], **options)
    except BaseException as exc:
        # Cloudflare's Pyodide bridge can surface fetch transport failures as
        # JsException (which is not consistently caught by ``Exception`` on
        # every deployed runtime). Let cancellations and process-control
        # exceptions propagate, but keep provider connection failures inside
        # the durable request flow instead of exposing a Python socket stack.
        import asyncio
        if isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt, SystemExit, GeneratorExit)):
            raise
        # Keep diagnostics useful without logging the request path, headers,
        # credentials, or user-provided prompt/body.
        safe_host = "".join(char for char in source_host if char.isalnum() or char in ".-")[:253]
        safe_host = safe_host or "unknown host"
        error_type = type(exc).__name__
        print(f"External service fetch failed (host={safe_host}, error={error_type}).")
        # GET requests here are safe to replay. A synthetic HTTP failure lets
        # the currency resolver try its next independent source (and lets
        # optional product lookup fall back locally). Never retry a POST:
        # the provider may have processed it already, which could incur a
        # duplicate model charge.
        if request_method == "GET" and not envelope.get("body"):
            return 503, b"", {}
        raise RuntimeError(
            f"连接外部服务（{safe_host}）失败；请稍后重试。本次操作尚未写入账本。"
        ) from None
    if source_host == "api.github.com":
        final_host = (urlsplit(str(getattr(response, "url", envelope["url"]))).hostname or "").lower()
        if final_host not in {"api.github.com", "raw.githubusercontent.com"}:
            raise ValueError("GitHub 下载跳转到了未允许的地址。")
    elif 300 <= int(response.status) < 400 and int(response.status) != 304:
        raise RuntimeError(
            "外部服务要求跳转；为保护 API 密钥，已停止请求。请把接口地址改为最终的 HTTPS 地址。"
        )
    response_length = response.headers.get("content-length")
    if response_length:
        try:
            response_size = int(response_length)
        except (TypeError, ValueError):
            response_size = 0
        if response_size > max_bytes:
            raise ValueError("云端服务响应超过安全上限；账本没有写入。")

    body = await response.bytes()
    if len(body) > max_bytes:
        raise ValueError("云端服务响应超过安全上限；账本没有写入。")
    return int(response.status), body, safe_response_headers(response.headers)


async def advance_job(database, env, user_id: str, operation_id: str):
    """Advance one replay-safe unit of work; the slim JS Workflow checkpoints each call."""
    action = ""
    data = {}
    try:
        active, job = await _ensure_active(database, user_id, operation_id)
        if not active:
            await cleanup_job_private_state(database, user_id, operation_id)
            return {"state": str(_field(job, "state")), "result": _json_result(job)}

        action = str(_field(job, "action"))
        fingerprint = str(_field(job, "fingerprint"))
        request_now = datetime.fromisoformat(str(_field(job, "created_at")))
        if request_now.tzinfo is None:
            request_now = request_now.replace(tzinfo=timezone.utc)
        request_now = request_now.astimezone(timezone.utc)
        action, data = await load_job_payload(
            database, env, user_id, operation_id, fingerprint, action,
        )
        replies, expected_revision = await load_model_replies(
            database, env, user_id, operation_id,
        )

        await _ensure_active(database, user_id, operation_id)
        try:
            await execute_action(
                database, env, user_id, action, data, operation_id,
                provider_replies=replies, expected_revision=expected_revision,
                request_now=request_now,
            )
        except ModelRequestRequired as request_required:
            if action not in {
                "agent", "agent_prepare", "cloud_connect", "github_auth", "cloud_upload", "cloud_auto_sync",
                "cloud_restore", "startup_pull", "sync", "process_scheduled",
                "reconcile", "recurring", "run_due", "edit_transaction",
            }:
                raise RuntimeError("此操作意外要求外部服务请求，本次没有写入账本。")
            envelope = request_required.envelope
            call_index = int(envelope["callIndex"])
            if call_index != len(replies):
                raise RuntimeError("外部请求顺序校验失败；本次没有写入账本。")
            call_limit = (
                MAX_RATE_LOOKUPS_PER_JOB
                if action in {"sync", "process_scheduled", "run_due"}
                else MAX_MODEL_CALLS_PER_JOB
            )
            if call_index >= call_limit:
                raise RuntimeError("本次外部服务步骤过多，请缩短请求后重试。")

            active, _latest = await _ensure_active(database, user_id, operation_id)
            if not active:
                raise RuntimeError("操作已取消，本次更改没有写入账本。")
            saved, saved_revision = await load_model_replies(
                database, env, user_id, operation_id,
            )
            if len(saved) > call_index:
                existing = saved[call_index]
                if (existing["requestHash"] != envelope["requestHash"]
                        or saved_revision != envelope["ledgerRevision"]):
                    raise RuntimeError("外部服务响应与当前账本请求不匹配；本次没有写入。")
                return {"state": "continue"}
            if len(saved) != call_index:
                raise RuntimeError("外部服务响应记录不连续；本次没有写入账本。")

            response_limit = (
                MAX_CLOUD_BUNDLE_BYTES
                if action in {"cloud_restore", "startup_pull"}
                else MAX_FX_RESPONSE_BYTES
                if action in {"sync", "process_scheduled", "run_due"}
                else MAX_MODEL_RESPONSE_BYTES
            )
            status, body, response_headers = await _provider_fetch(envelope, max_bytes=response_limit)
            active, _latest = await _ensure_active(database, user_id, operation_id)
            if not active:
                raise RuntimeError("操作已取消，本次更改没有写入账本。")
            await save_model_response(
                database, env, user_id, operation_id,
                envelope, status, body, max_bytes=response_limit,
                response_headers=response_headers,
            )
            return {"state": "continue"}

        latest = await _read_job(database, user_id, operation_id)
        if str(_field(latest, "state")) == "done":
            # The ledger commit and its outbox row are already durable. Start
            # GitHub/Gitee backup as a separate persistent Workflow now; never
            # make the foreground operation wait for the provider upload.
            from scheduled import dispatch_queued_backup
            await dispatch_queued_backup(database, env, user_id)
        await cleanup_job_private_state(database, user_id, operation_id)
        return {"state": str(_field(latest, "state")), "result": _json_result(latest)}
    except Exception as exc:
        # Only known validation/domain errors are shown to the user. Other
        # failures may contain provider or runtime details and stay private.
        import traceback
        frames = traceback.extract_tb(exc.__traceback__)
        locations = " -> ".join(
            f"{frame.filename.replace(chr(92), '/').rsplit('/', 1)[-1]}:{frame.lineno}"
            for frame in frames[-5:]
        )
        safe_detail = f"; {str(exc)[:180]}" if type(exc).__name__ == "IntegrityError" else ""
        print(f"App job failed ({type(exc).__name__}) at {locations}{safe_detail}.")
        if action in {"cloud_upload", "cloud_auto_sync"}:
            try:
                from backup_status import backup_warning_kind, classify_backup_failure
                provider = str(data.get("provider", "github")).lower() if action == "cloud_upload" else "github"
                kind, backup_message = classify_backup_failure(provider, exc)
                config = await load_mobile_config(database, env, user_id)
                config["autoStatus"] = backup_message
                config["autoStatusKind"] = backup_warning_kind([kind])
                encoded = json.dumps(config, ensure_ascii=False, separators=(",", ":"))
                encrypted = await encrypt_text(
                    encoded, str(env.TOKEN_ENCRYPTION_KEY), "user:" + user_id + ":mobile-config",
                )
                await database.prepare(
                    "INSERT INTO user_secrets(user_id,secret_name,encrypted_value,updated_at) "
                    "VALUES(?,'mobile-config',?,?) ON CONFLICT(user_id,secret_name) DO UPDATE SET "
                    "encrypted_value=excluded.encrypted_value,updated_at=excluded.updated_at"
                ).bind(user_id, encrypted, _now()).run()
            except Exception as status_error:
                print(f"Could not persist cloud backup warning ({type(status_error).__name__}).")
        if isinstance(exc, (ValueError, RuntimeError)):
            message = str(exc)
        else:
            # Keep exception messages private: provider errors can contain
            # request data. A type plus source basename/line is safe and gives
            # the owner enough information to diagnose an unexpected failure.
            diagnostic = f"（内部错误 {type(exc).__name__}"
            if locations:
                diagnostic += f"；{locations}"
            message = "操作未完成，请刷新后核对账本。" + diagnostic + "）"
        try:
            try:
                config = await load_mobile_config(database, env, user_id)
                for profile in config.get("profiles", []):
                    secret = str(profile.get("api_key", ""))
                    if secret:
                        message = message.replace(secret, "••••")
                for cloud in config.get("cloud", {}).values():
                    for key in ("token", "refresh_token"):
                        secret = str(cloud.get(key, ""))
                        if secret:
                            message = message.replace(secret, "••••")
            except Exception:
                pass
            for secret_name in ("token", "api_key", "refresh_token"):
                secret = data.get(secret_name) if isinstance(data, dict) else None
                if isinstance(secret, str) and secret:
                    message = message.replace(secret, "••••")
            latest = await _read_job(database, user_id, operation_id)
            if str(_field(latest, "state")) != "done":
                cancelled = int(_field(latest, "cancel_requested")) != 0
                message = "操作已取消，本次更改没有写入账本。" if cancelled else message
                terminal_state = "cancelled" if cancelled else "failed"
                await database.prepare(
                    "UPDATE app_jobs SET state=?,message=?,result_json=?,updated_at=? "
                    "WHERE user_id=? AND operation_id=? AND state!='done'"
                ).bind(
                    terminal_state, message,
                    json.dumps({"error": message}, ensure_ascii=False, separators=(",", ":")),
                    _now(), user_id, operation_id,
                ).run()
            else:
                return {"state": "done", "result": _json_result(latest)}
            await cleanup_job_private_state(database, user_id, operation_id)
            if action == "cloud_auto_sync":
                await database.prepare(
                    "UPDATE auto_sync_queue SET state='failed',operation_id=NULL,updated_at=? "
                    "WHERE user_id=? AND operation_id=?"
                ).bind(_now(), user_id, operation_id).run()
            from scheduled import dispatch_queued_backup
            await dispatch_queued_backup(database, env, user_id)
        except Exception:
            raise
        return {"state": terminal_state, "result": {"error": message}}
