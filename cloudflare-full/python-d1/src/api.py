"""D1-backed API adapter for the full mobile bookkeeping application."""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import uuid
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlencode, urlsplit

from workers import fetch

from auth import (
    AuthError,
    clear_session,
    cookie_values,
    origin_is_valid,
    require_user,
    secure_request,
)
from d1_snapshot_store import SnapshotConflict, SnapshotError
from github_oauth import GitHubFlowError, cancel_flow, finish_flow, flow_status, start_flow
from gitee_oauth import GiteeOAuthError, finish_flow as finish_gitee_flow, start_flow as start_gitee_flow
from http_response import (
    bytes_response, clear_flow_cookie, clear_gitee_flow_cookie, json_response,
    redirect_response, set_flow_cookie, set_gitee_flow_cookie,
)
from ledger_runtime import (
    bootstrap,
    create_account,
    create_category,
    export_ledger,
    import_ledger,
    list_transactions,
    load_mobile_config,
    read_backup,
    restore_bundle,
    first_run_setup_required,
    workspace_snapshot,
)


MAX_JSON_BODY_BYTES = 32 * 1024 * 1024
MAX_BINARY_BODY_BYTES = 50 * 1024 * 1024
OPERATION_ID_RE = re.compile(r"[A-Za-z0-9_-]{12,80}\Z")


def _field(row, name):
    return row[name] if isinstance(row, dict) else getattr(row, name)


def _changes(result) -> int:
    meta = result.get("meta", {}) if isinstance(result, dict) else getattr(result, "meta", {})
    if isinstance(meta, dict):
        return int(meta.get("changes", 0) or 0)
    return int(getattr(meta, "changes", 0) or 0)


def _content_length(request):
    raw = str(request.headers.get("Content-Length", "") or "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValueError("请求长度无效。")
    if value < 0:
        raise ValueError("请求长度无效。")
    return value


async def _json_body(request):
    size = _content_length(request)
    if size is not None and size > MAX_JSON_BODY_BYTES:
        raise OverflowError("请求内容过大。")
    try:
        value = await request.json()
    except Exception as exc:
        raise ValueError("请求内容不是有效 JSON。") from exc
    if not isinstance(value, dict):
        raise ValueError("请求内容格式无效。")
    return value


async def _binary_body(request, limit=MAX_BINARY_BODY_BYTES):
    size = _content_length(request)
    if size is not None and size > limit:
        raise OverflowError("上传文件超过大小限制。")
    body = await request.bytes()
    if len(body) > limit:
        raise OverflowError("上传文件超过大小限制。")
    return body


def _safe_filename(value: str) -> str:
    # GitHub logins are restricted to ASCII, but keep header construction
    # defensive in case the identity provider changes its validation.
    clean = re.sub(r"[^A-Za-z0-9._-]", "_", value)[:64] or "account"
    return clean


async def _job(database, user_id: str, operation_id: str):
    if not OPERATION_ID_RE.fullmatch(operation_id):
        raise ValueError("操作编号无效。")
    row = await database.prepare(
        "SELECT operation_id,state,message,result_json FROM app_jobs WHERE user_id=? AND operation_id=?"
    ).bind(user_id, operation_id).first()
    if row is None:
        raise FileNotFoundError("找不到此操作。")
    try:
        result = json.loads(str(_field(row, "result_json") or "{}"))
    except (TypeError, ValueError):
        result = {"error": "后台操作结果无法读取，请刷新并核对账本。"}
    state = str(_field(row, "state"))
    # Keep the existing mobile client contract: queued and running are polled
    # in the same way; terminal states include a result object.
    return {"id": operation_id, "state": "running" if state in {"queued", "running"} else state,
            "message": str(_field(row, "message") or ""), "result": result}


async def _model_balance(database, env, user_id: str, agent: str, vision: bool):
    """Read a supported provider balance without exposing saved credentials."""
    if agent not in {"bookkeeping", "food_health"}:
        raise ValueError("Agent 无效。")
    config = await load_mobile_config(database, env, user_id)
    group = "visionAgents" if vision else "agents"
    profile_id = str(config.get(group, {}).get(agent) or "")
    profile = next((row for row in config.get("profiles", [])
                    if str(row.get("id") or "") == profile_id), None)
    if not profile:
        return {"available": False, "reason": "not_configured"}
    endpoint = urlsplit(str(profile.get("api_url") or ""))
    if endpoint.scheme != "https" or (endpoint.hostname or "").lower() != "api.deepseek.com":
        return {"available": False, "reason": "unsupported_provider"}
    api_key = str(profile.get("api_key") or "").strip()
    if not api_key:
        return {"available": False, "reason": "not_configured"}
    try:
        response = await fetch(
            "https://api.deepseek.com/user/balance",
            method="GET",
            headers={"Authorization": "Bearer " + api_key, "Accept": "application/json"},
            redirect="manual",
        )
        status = int(response.status)
        if 300 <= status < 400:
            return {"available": False, "reason": "provider_error"}
        if status < 200 or status >= 300:
            return {"available": False, "reason": "provider_error", "status": status}
        raw = await response.bytes()
        if len(raw) > 64 * 1024:
            return {"available": False, "reason": "provider_error"}
        payload = json.loads(raw.decode("utf-8"))
        balances = payload.get("balance_infos") if isinstance(payload, dict) else None
        safe_balances = []
        for item in balances if isinstance(balances, list) else []:
            if not isinstance(item, dict):
                continue
            currency = str(item.get("currency") or "").upper()
            total = item.get("total_balance")
            if currency and isinstance(total, (str, int, float)):
                safe_balances.append({"currency": currency, "total": str(total)})
        return {"available": bool(payload.get("is_available")), "balances": safe_balances}
    except Exception:
        # Never return provider response bodies, exception strings, or secrets.
        return {"available": False, "reason": "provider_error"}


async def _run_local_inline_job(env, workflow_params):
    # Miniflare acknowledges local Workflow creation but does not run instances
    # in this environment. This dev-only loop calls the same idempotent unit
    # the durable JS Workflow invokes through its private service binding.
    from app_workflow import advance_job
    for _ in range(34):
        outcome = await advance_job(
            env.DB, env, str(workflow_params.get("userId", "")),
            str(workflow_params.get("operationId", "")),
        )
        if outcome.get("state") != "continue":
            return
    raise RuntimeError("本地操作超过单次模型请求上限。")


async def _start_job(database, env, user, body):
    action = str(body.get("action", "")).strip()
    data = body.get("data", {})
    operation_id = str(body.get("opId", ""))
    local_inline_workflow = str(getattr(env, "WORKFLOW_LOCAL_INLINE", "")) == "1"
    if not local_inline_workflow and not str(getattr(env, "APP_JOB_SHARED_SECRET", "") or ""):
        raise RuntimeError("后台处理服务尚未配置；账本没有被修改。")
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,48}", action) or not isinstance(data, dict):
        raise ValueError("后台操作参数无效。")
    if not OPERATION_ID_RE.fullmatch(operation_id):
        raise ValueError("操作编号无效，请重新打开页面。")

    canonical = json.dumps([action, data], sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    now = datetime.now(timezone.utc).isoformat()
    inserted = await database.prepare(
        "INSERT OR IGNORE INTO app_jobs(user_id,operation_id,action,fingerprint,state,message,result_json,"
        "cancel_requested,created_at,updated_at) VALUES(?,?,?,?,'queued','正在排队…','{}',0,?,?)"
    ).bind(user["id"], operation_id, action, fingerprint, now, now).run()
    row = await database.prepare(
        "SELECT fingerprint,state FROM app_jobs WHERE user_id=? AND operation_id=?"
    ).bind(user["id"], operation_id).first()
    if row is None or str(_field(row, "fingerprint")) != fingerprint:
        raise ValueError("同一操作编号对应的数据不同；请刷新页面后重试。")

    row_state = str(_field(row, "state"))
    is_new_job = _changes(inserted) == 1
    if local_inline_workflow and not is_new_job:
        # Do not execute a duplicate local request while its original is active.
        return await _job(database, user["id"], operation_id)
    if is_new_job or row_state == "queued":
        # Workflow events/checkpoints contain identifiers only. User text,
        # receipt images, and API credentials are encrypted before the durable
        # job is started, then removed when the job reaches a terminal state.
        from model_jobs import cleanup_job_private_state, store_job_payload
        try:
            await store_job_payload(
                database, env, user["id"], operation_id, action, data, fingerprint,
            )
        except Exception as exc:
            # Keep payloads, keys, and provider details out of logs; the class
            # alone is enough to distinguish D1, encoding, and runtime errors.
            import traceback
            frames = traceback.extract_tb(exc.__traceback__)
            locations = " -> ".join(f"{frame.filename.rsplit('/', 1)[-1]}:{frame.lineno}" for frame in frames[-5:])
            print(f"Encrypted job payload persistence failed ({type(exc).__name__}) at {locations}.")
            await cleanup_job_private_state(database, user["id"], operation_id)
            message = "后台操作数据未能安全保存；账本没有被修改。"
            await database.prepare(
                "UPDATE app_jobs SET state='failed',message=?,result_json=?,updated_at=? "
                "WHERE user_id=? AND operation_id=? AND state='queued'"
            ).bind(
                message, json.dumps({"error": message}, ensure_ascii=False, separators=(",", ":")),
                datetime.now(timezone.utc).isoformat(), user["id"], operation_id,
            ).run()
            return await _job(database, user["id"], operation_id)

        # The workflow event contains identifiers and a non-sensitive action
        # name only. The private gateway uses the action to retry only the
        # replay-safe Agent preparation path on the secondary Python engine.
        workflow_params = {
            "userId": user["id"], "operationId": operation_id, "action": action,
        }
        if local_inline_workflow:
            await _run_local_inline_job(env, workflow_params)
            return await _job(database, user["id"], operation_id)

        workflow_exists = False
        try:
            existing_instance = await env.APP_JOBS.get(operation_id)
            await existing_instance.status()
            workflow_exists = True
        except Exception:
            pass
        if not workflow_exists:
            try:
                await env.APP_JOBS.create(id=operation_id, params=workflow_params)
            except Exception as create_exc:
                import traceback
                frames = traceback.extract_tb(create_exc.__traceback__)
                locations = " -> ".join(
                    f"{frame.filename.rsplit('/', 1)[-1]}:{frame.lineno}"
                    for frame in frames[-5:]
                )
                print(f"Durable job workflow creation failed ({type(create_exc).__name__}) at {locations}.")
                # Another concurrent retry may have created the same
                # idempotent instance after our get() check.
                try:
                    existing_instance = await env.APP_JOBS.get(operation_id)
                    await existing_instance.status()
                    workflow_exists = True
                except Exception:
                    workflow_exists = False
                if not workflow_exists:
                    message = "后台处理服务暂时无法启动；账本没有被修改。"
                    await database.prepare(
                        "UPDATE app_jobs SET state='failed',message=?,result_json=?,updated_at=? "
                        "WHERE user_id=? AND operation_id=? AND state='queued'"
                    ).bind(message, json.dumps({"error": message}, ensure_ascii=False),
                          datetime.now(timezone.utc).isoformat(), user["id"], operation_id).run()
                    await cleanup_job_private_state(database, user["id"], operation_id)
                    return await _job(database, user["id"], operation_id)
    return await _job(database, user["id"], operation_id)


async def _cancel_job(database, user_id: str, operation_id: str):
    if not OPERATION_ID_RE.fullmatch(operation_id):
        raise ValueError("操作编号无效。")
    result = await database.prepare(
        "UPDATE app_jobs SET cancel_requested=1,state=CASE WHEN state='queued' THEN 'cancelled' ELSE state END,"
        "message=CASE WHEN state='queued' THEN '已取消' ELSE '正在中断…' END,updated_at=? "
        "WHERE user_id=? AND operation_id=? AND state IN ('queued','running')"
    ).bind(datetime.now(timezone.utc).isoformat(), user_id, operation_id).run()
    if _changes(result) == 0:
        row = await database.prepare(
            "SELECT operation_id,state FROM app_jobs WHERE user_id=? AND operation_id=?"
        ).bind(user_id, operation_id).first()
        if row is None:
            raise FileNotFoundError("找不到此操作。")
    else:
        row = await database.prepare(
            "SELECT operation_id,state FROM app_jobs WHERE user_id=? AND operation_id=?"
        ).bind(user_id, operation_id).first()
    if row is not None and str(_field(row, "state")) in {"cancelled", "failed", "done"}:
        from model_jobs import cleanup_job_private_state
        await cleanup_job_private_state(database, user_id, operation_id)
    return {"ok": True}


async def _start_sync_job(database, env, user, operations):
    """Join a matching active sync, but allow a fresh attempt after errors."""
    job_data = {"operations": operations}
    canonical = json.dumps(["sync", job_data], sort_keys=True, ensure_ascii=False,
                           separators=(",", ":"))
    base_id = "sync-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    for attempt in range(10_000_000):
        operation_id = base_id if attempt == 0 else f"{base_id}-r{attempt}"
        row = await database.prepare(
            "SELECT state,result_json FROM app_jobs WHERE user_id=? AND operation_id=?"
        ).bind(user["id"], operation_id).first()
        if row is None:
            break
        state = str(_field(row, "state"))
        if state in {"queued", "running"}:
            return await _job(database, user["id"], operation_id)
        if state == "done":
            try:
                saved = json.loads(str(_field(row, "result_json") or "{}"))
                results = saved.get("results", [])
            except (TypeError, ValueError):
                results = []
            if isinstance(results, list) and all(
                isinstance(result, dict) and result.get("ok") for result in results
            ):
                return await _job(database, user["id"], operation_id)
        # A terminal failed/cancelled job or a completed batch with rejected
        # items gets a new job id. Per-entry operation ids keep successful
        # entries idempotent while allowing transient failures to be retried.
    else:
        raise ValueError("同步重试次数过多，请稍后再试。")
    return await _start_job(database, env, user, {
        "action": "sync", "data": job_data, "opId": operation_id,
    })


async def dispatch(request, env):
    database = env.DB
    parsed = urlsplit(str(request.url))
    path, method = parsed.path, str(request.method).upper()
    query = parse_qs(parsed.query, keep_blank_values=True)
    secure = secure_request(request)

    if method == "OPTIONS":
        return json_response({"ok": True}, status=200)

    if path == "/api/auth/gitee/callback" and method == "GET":
        clear_cookie = ("Set-Cookie", clear_gitee_flow_cookie(secure=secure))
        try:
            result = await finish_gitee_flow(database, request, env=env)
        except GiteeOAuthError as exc:
            location = "/?" + urlencode({"gitee_error": exc.code})
            return redirect_response(location, headers=(clear_cookie,))
        except AuthError:
            location = "/?" + urlencode({"gitee_error": "session_expired"})
            return redirect_response(location, headers=(clear_cookie,))
        headers = [clear_cookie]
        headers.extend(("Set-Cookie", cookie) for cookie in result["sessionCookies"])
        return redirect_response("/?" + result["redirectQuery"], headers=tuple(headers))

    if path == "/api/config" and method == "GET":
        gitee_enabled = bool(
            str(getattr(env, "GITEE_CLIENT_ID", "") or "").strip()
            and str(getattr(env, "GITEE_CLIENT_SECRET", "") or "").strip()
            and str(getattr(env, "GITEE_REDIRECT_URI", "") or "").strip()
        )
        return json_response({
            "requiresInvite": False, "authMode": "oauth", "authProviders": ["github"] + (["gitee"] if gitee_enabled else []),
            "giteeAuthEnabled": gitee_enabled, "appVersion": "mobile-7",
            "secure": secure, "deploymentMode": "cloud",
        })

    if path == "/api/session" and method == "GET":
        try:
            user = await require_user(database, request)
        except AuthError as exc:
            if exc.status == 401:
                return json_response({"user": None})
            return json_response({"error": str(exc)}, status=exc.status)
        return json_response({"user": user, "csrfToken": cookie_values(request).get("hh_csrf", "")})

    if method in {"GET", "HEAD"}:
        try:
            user = await require_user(database, request)
            user_id = user["id"]
            language = query.get("lang", ["zh-CN"])[0]
            if language not in {"zh-CN", "ja-JP", "en-US"}:
                language = "zh-CN"

            if path == "/api/bootstrap":
                return json_response(await bootstrap(database, user, language, env))
            if path == "/api/workspace":
                report_date = query.get("asOf", [None])[0]
                return json_response(await workspace_snapshot(
                    database, user_id, language, report_date, env,
                    bootstrap_user=user if query.get("includeBootstrap", [""])[0] == "1" else None,
                ))
            if path == "/api/transactions":
                start = query.get("start", ["1900-01-01"])[0]
                end = query.get("end", ["2199-12-31"])[0]
                return json_response(await list_transactions(database, env, user_id, start, end))
            if path == "/api/model-balance":
                agent = query.get("agent", ["bookkeeping"])[0]
                vision = query.get("vision", ["0"])[0] == "1"
                return json_response(await _model_balance(database, env, user_id, agent, vision))
            if path == "/api/default-skills":
                from bookkeeping.web_features import WEB_DEFAULTS
                return json_response({
                    "bookkeeping": (WEB_DEFAULTS / "bookkeeping.md").read_text(encoding="utf-8"),
                    "food_health": (WEB_DEFAULTS / "food-health.md").read_text(encoding="utf-8"),
                })
            if path == "/api/job":
                return json_response(await _job(database, user_id, query.get("id", [""])[0]))
            if path == "/api/backup":
                name = query.get("name", [""])[0]
                body = await read_backup(database, env, user_id, name)
                return bytes_response(body, "application/zip", headers=(
                    ("Content-Disposition", f'attachment; filename="{name}"'),
                ))
            if path == "/api/receipt":
                return json_response({"error": "网页云端不归档小票图片；图片仍可临时用于识别。"}, status=404)
            if path == "/api/export-ledger":
                body = await export_ledger(database, user_id)
                filename = f"household-ledger-{_safe_filename(user['username'])}.sqlite3"
                return bytes_response(body, "application/vnd.sqlite3", headers=(
                    ("Content-Disposition", f'attachment; filename="{filename}"'),
                ))
            return json_response({"error": "找不到接口。"}, status=404)
        except AuthError as exc:
            return json_response({"error": str(exc)}, status=exc.status)
        except SnapshotConflict as exc:
            return json_response({"error": str(exc)}, status=409)
        except SnapshotError as exc:
            return json_response({"error": str(exc)}, status=409)
        except FileNotFoundError as exc:
            return json_response({"error": str(exc)}, status=404)
        except (ValueError, TypeError, OverflowError) as exc:
            return json_response({"error": str(exc) or "请求参数无效。"}, status=400)
        except Exception as exc:
            import traceback
            frames = traceback.extract_tb(exc.__traceback__)
            locations = " -> ".join(f"{frame.filename.rsplit('/', 1)[-1]}:{frame.lineno}" for frame in frames[-5:])
            print(f"D1 API request failed ({type(exc).__name__}) at {locations}.")
            return json_response({"error": "服务暂时无法读取账本，请稍后重试。"}, status=500)

    if path == "/__internal/job/advance":
        # This route is reachable only through the separate Workflow worker's
        # service binding. The shared secret protects it from public callers.
        expected_secret = str(getattr(env, "APP_JOB_SHARED_SECRET", "") or "")
        supplied_secret = str(request.headers.get("X-App-Job-Secret", "") or "")
        if not expected_secret or not hmac.compare_digest(expected_secret, supplied_secret):
            return json_response({"error": "找不到接口。"}, status=404)
        if method != "POST":
            return json_response({"error": "不支持此请求方法。"}, status=405)
        try:
            body = await _json_body(request)
            user_id = str(body.get("userId", ""))
            operation_id = str(body.get("operationId", ""))
            if not user_id or len(user_id) > 80 or not OPERATION_ID_RE.fullmatch(operation_id):
                raise ValueError("后台操作参数无效。")
            from app_workflow import advance_job
            outcome = await advance_job(database, env, user_id, operation_id)
            # Workflow checkpoints contain only a terminal/continue marker;
            # user text, ledger data, and credentials stay in D1 or memory.
            return json_response({"state": str(outcome.get("state", "failed"))})
        except (ValueError, TypeError) as exc:
            return json_response({"error": str(exc) or "后台操作参数无效。"}, status=400)
        except Exception as exc:
            import traceback
            frames = traceback.extract_tb(exc.__traceback__)
            locations = " -> ".join(
                f"{frame.filename.replace(chr(92), '/').rsplit('/', 1)[-1]}:{frame.lineno}"
                for frame in frames[-5:]
            )
            print(f"Internal job step failed ({type(exc).__name__}) at {locations}.")
            # This safe diagnostic lets the Workflow surface the Python failure
            # without exposing exception text, request bodies, or credentials.
            return json_response({
                "error": "后台操作暂时无法继续。",
                "diagnostic": {"type": type(exc).__name__, "locations": locations},
            }, status=500)

    if method != "POST":
        return json_response({"error": "不支持此请求方法。"}, status=405)
    if not origin_is_valid(request):
        return json_response({"error": "请求来源校验失败。"}, status=403)

    try:
        if path == "/api/auth/gitee/start":
            body = await _json_body(request)
            started = await start_gitee_flow(database, request, body, env=env)
            return json_response(
                {"authorizationUrl": started["authorizationUrl"]},
                headers=(("Set-Cookie", set_gitee_flow_cookie(
                    started["state"], started["maxAge"], secure=secure,
                )),),
            )

        if path in {"/api/auth/github/start", "/api/auth/github/status", "/api/auth/github/cancel",
                    "/api/auth/github/finish"}:
            body = await _json_body(request)
            if path == "/api/auth/github/start":
                started = await start_flow(database, request, body, env=env)
                return json_response(started["flow"], headers=(
                    ("Set-Cookie", set_flow_cookie(started["cookie"], started["maxAge"], secure=secure)),
                ))
            flow_id = str(body.get("flowId", ""))
            if path == "/api/auth/github/status":
                return json_response(await flow_status(database, request, flow_id, env=env))
            if path == "/api/auth/github/cancel":
                await cancel_flow(database, request, flow_id)
                return json_response({"ok": True}, headers=(("Set-Cookie", clear_flow_cookie(secure=secure)),))
            try:
                await require_user(database, request, csrf=True)
            except AuthError as exc:
                if exc.status != 401:
                    raise
            result = await finish_flow(database, request, flow_id, env=env)
            old_cookies = await clear_session(database, request, secure=secure)
            headers = [("Set-Cookie", cookie) for cookie in old_cookies]
            headers.extend(("Set-Cookie", cookie) for cookie in result["sessionCookies"])
            headers.append(("Set-Cookie", clear_flow_cookie(secure=secure)))
            return json_response({"user": result["user"]}, headers=headers)

        if path == "/api/import-ledger":
            user = await require_user(database, request, csrf=True)
            if await first_run_setup_required(database, env, user["id"]):
                return json_response({"error": "请先完成新手引导：设置账本、账户、API、Agent 和 Skill。", "onboardingRequired": True}, status=403)
            content_type = str(request.headers.get("Content-Type", "")).split(";", 1)[0].strip().lower()
            if content_type != "application/vnd.sqlite3":
                return json_response({"error": "账本文件格式无效，请选择SQLite数据库文件。"}, status=415)
            body = await _binary_body(request)
            return json_response(await import_ledger(database, env, user, body))

        if path == "/api/restore-bundle":
            user = await require_user(database, request, csrf=True)
            if await first_run_setup_required(database, env, user["id"]):
                return json_response({"error": "请先完成新手引导：设置账本、账户、API、Agent 和 Skill。", "onboardingRequired": True}, status=403)
            if str(request.headers.get("X-Confirm-Restore", "")) != "confirmed-once":
                return json_response({"error": "请确认恢复操作后重试。"}, status=400)
            content_type = str(request.headers.get("Content-Type", "")).split(";", 1)[0].strip().lower()
            if content_type != "application/zip":
                return json_response({"error": "备份包格式无效。"}, status=415)
            body = await _binary_body(request)
            return json_response(await restore_bundle(database, env, user, body))

        body = await _json_body(request)
        user = await require_user(database, request, csrf=True)
        if path != "/api/logout" and await first_run_setup_required(database, env, user["id"]):
            setup_data = body.get("data")
            setup_step = setup_data.get("onboardingStep") if isinstance(setup_data, dict) else ""
            is_setup_submission = (
                path == "/api/action"
                and body.get("action") == "settings"
                and isinstance(setup_data, dict)
                and setup_step in {"base", "api", "agents", "skills"}
                and "baseCurrency" in setup_data
                and "billingCycleStartDay" in setup_data
            )
            setup_settings = setup_data.get("settings") if isinstance(setup_data, dict) else None
            setup_confirmations = setup_data.get("setupConfirmations") if isinstance(setup_data, dict) else None
            is_tutorial_completion = (
                path == "/api/action"
                and body.get("action") == "onboarding_save"
                and isinstance(setup_settings, dict)
                and setup_settings.get("onboardingStep") == "skills"
                and setup_settings.get("completeOnboarding") is True
                and "baseCurrency" in setup_settings
                and "billingCycleStartDay" in setup_settings
                and isinstance(setup_confirmations, dict)
                and setup_confirmations.get("baseCurrency") is True
                and setup_confirmations.get("billingCycleStartDay") is True
            )
            is_account_setup = path == "/api/accounts" and body.get("onboardingStep") == "accounts"
            if not (is_setup_submission or is_tutorial_completion or is_account_setup):
                return json_response({"error": "请先完成新手引导：设置账本、账户、API、Agent 和 Skill。", "onboardingRequired": True}, status=403)
        if path == "/api/auth/github/start":
            return json_response({"error": "GitHub 登录流程无效。"}, status=400)
        if path == "/api/logout":
            cookies = await clear_session(database, request, secure=secure)
            return json_response({"ok": True}, headers=tuple(("Set-Cookie", item) for item in cookies))
        if path == "/api/action":
            return json_response(await _start_job(database, env, user, body), status=202)
        if path == "/api/cancel-job":
            return json_response(await _cancel_job(database, user["id"], str(body.get("id", ""))))
        if path == "/api/accounts":
            return json_response(await create_account(database, env, user, body), status=201)
        if path == "/api/categories":
            return json_response(await create_category(database, env, user, body), status=201)
        if path == "/api/transactions":
            operation = body.get("operation") or {
                "type": "transaction", "opId": str(body.get("opId") or uuid.uuid4().hex), "data": body,
            }
            return json_response(await _start_sync_job(database, env, user, [operation]), status=202)
        if path == "/api/sync":
            operations = body.get("operations")
            if not isinstance(operations, list) or len(operations) > 100:
                return json_response({"error": "同步队列格式无效或超过100项。"}, status=400)
            if not operations:
                return json_response({"results": []})
            return json_response(await _start_sync_job(database, env, user, operations), status=202)
        return json_response({"error": "找不到接口。"}, status=404)
    except AuthError as exc:
        return json_response({"error": str(exc)}, status=exc.status)
    except GitHubFlowError as exc:
        return json_response({"error": str(exc)}, status=exc.status)
    except GiteeOAuthError as exc:
        return json_response({"error": str(exc)}, status=exc.status)
    except SnapshotConflict as exc:
        return json_response({"error": str(exc)}, status=409)
    except SnapshotError as exc:
        return json_response({"error": str(exc)}, status=409)
    except FileNotFoundError as exc:
        return json_response({"error": str(exc)}, status=404)
    except OverflowError as exc:
        return json_response({"error": str(exc)}, status=413)
    except (ValueError, TypeError) as exc:
        return json_response({"error": str(exc) or "请求参数无效。"}, status=400)
    except Exception as exc:
        import traceback
        frames = traceback.extract_tb(exc.__traceback__)
        locations = " -> ".join(f"{frame.filename.rsplit('/', 1)[-1]}:{frame.lineno}" for frame in frames[-5:])
        print(f"D1 API write failed ({type(exc).__name__}) at {locations}.")
        return json_response({"error": "服务器暂时无法完成此操作，请稍后重试。"}, status=500)
