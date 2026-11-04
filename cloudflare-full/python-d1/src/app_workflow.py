"""Durable execution for mobile actions and replayable Agent model calls."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from workers import fetch

from ledger_runtime import execute_action, load_mobile_config
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
    source_host = (urlsplit(envelope["url"]).hostname or "").lower()
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
    except Exception as exc:
        # Keep diagnostics useful without logging the request path, headers,
        # credentials, or user-provided prompt/body.
        safe_host = "".join(char for char in source_host if char.isalnum() or char in ".-")[:253]
        safe_host = safe_host or "unknown host"
        error_type = type(exc).__name__
        print(f"External service fetch failed (host={safe_host}, error={error_type}).")
        raise RuntimeError(
            f"连接外部服务（{safe_host}）失败；请检查网络、接口地址和服务状态。本次操作尚未写入账本。"
        ) from exc
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
        request_now = datetime.fromisoformat(
            str(_field(job, "created_at"))
        ).astimezone(timezone(timedelta(hours=9)))
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
        print(f"App job failed ({type(exc).__name__}) at {locations}.")
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
        except Exception:
            raise
        return {"state": terminal_state, "result": {"error": message}}
