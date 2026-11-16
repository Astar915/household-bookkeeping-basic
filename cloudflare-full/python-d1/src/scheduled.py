"""Bounded Cloudflare Cron work for due ledger entries and opt-in auto sync."""
from __future__ import annotations

import uuid
import hashlib
from datetime import datetime, timedelta, timezone

from api import _start_job
from d1_snapshot_store import SnapshotConflict
from ledger_runtime import load_mobile_config, process_scheduled_entries
from model_jobs import expire_stale_queued_cloud_jobs


MAX_USERS_PER_TICK = 10
MAX_AUTO_SYNC_ATTEMPTS = 5
AUTO_SYNC_RETRY_DELAY = timedelta(minutes=1)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _field(row, name):
    return row[name] if isinstance(row, dict) else getattr(row, name)


def _changes(result):
    meta = result.get("meta", {}) if isinstance(result, dict) else getattr(result, "meta", {})
    return int(meta.get("changes", 0) or 0) if isinstance(meta, dict) else int(getattr(meta, "changes", 0) or 0)


async def _active_job_exists(database, user_id):
    # Old cloud jobs that never started must not hold the durable backup queue
    # forever. A live Workflow moves its row to `running` before doing work.
    await expire_stale_queued_cloud_jobs(database, user_id)
    row = await database.prepare(
        "SELECT 1 AS active FROM app_jobs WHERE user_id=? AND state IN ('queued','running') LIMIT 1"
    ).bind(user_id).first()
    return row is not None


async def _mark_noop(database, user_id, revision):
    await database.prepare(
        "UPDATE auto_sync_queue SET state='done',operation_id=NULL,attempts=0,updated_at=? "
        "WHERE user_id=? AND revision=? AND state='pending'"
    ).bind(_now(), user_id, revision).run()


async def _queue_auto_sync(database, env, user_id):
    row = await database.prepare(
        "SELECT revision,state,operation_id,attempts,updated_at FROM auto_sync_queue WHERE user_id=?"
    ).bind(user_id).first()
    if row is None:
        return
    state = str(_field(row, "state"))
    if state == "failed":
        attempts = int(_field(row, "attempts") or 0)
        if attempts >= MAX_AUTO_SYNC_ATTEMPTS:
            return
        try:
            failed_at = datetime.fromisoformat(str(_field(row, "updated_at")))
            if failed_at.tzinfo is None:
                failed_at = failed_at.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            return
        if datetime.now(timezone.utc) - failed_at.astimezone(timezone.utc) < AUTO_SYNC_RETRY_DELAY:
            return
        revision = str(_field(row, "revision"))
        reset = await database.prepare(
            "UPDATE auto_sync_queue SET state='pending',operation_id=NULL,updated_at=? "
            "WHERE user_id=? AND revision=? AND state='failed' AND attempts=? AND updated_at=?"
        ).bind(_now(), user_id, revision, attempts, str(_field(row, "updated_at"))).run()
        if _changes(reset) != 1:
            return
        row = await database.prepare(
            "SELECT revision,state,operation_id,attempts,updated_at FROM auto_sync_queue WHERE user_id=?"
        ).bind(user_id).first()
        if row is None:
            return
        state = str(_field(row, "state"))
    if state != "pending":
        return
    if await _active_job_exists(database, user_id):
        return

    revision = str(_field(row, "revision"))
    try:
        config = await load_mobile_config(database, env, user_id)
    except Exception:
        await database.prepare(
            "UPDATE auto_sync_queue SET state='failed',operation_id=NULL,attempts=attempts+1,updated_at=? "
            "WHERE user_id=? AND revision=? AND state='pending'"
        ).bind(_now(), user_id, revision).run()
        return

    providers = [
        name for name, cloud in config.get("cloud", {}).items()
        if name in {"github", "gitee"} and cloud.get("token") and cloud.get("repository")
    ]
    if not config.get("autoSync", False) or not providers:
        await _mark_noop(database, user_id, revision)
        return

    operation_id = uuid.uuid4().hex
    claim = await database.prepare(
        "UPDATE auto_sync_queue SET state='queued',operation_id=?,attempts=attempts+1,updated_at=? "
        "WHERE user_id=? AND revision=? AND state='pending'"
    ).bind(operation_id, _now(), user_id, revision).run()
    if _changes(claim) != 1:
        return

    try:
        job = await _start_job(database, env, {"id": user_id}, {
            "action": "cloud_auto_sync",
            "data": {"automatic": True},
            "opId": operation_id,
        })
    except Exception:
        await database.prepare(
            "UPDATE auto_sync_queue SET state='failed',operation_id=NULL,updated_at=? "
            "WHERE user_id=? AND operation_id=?"
        ).bind(_now(), user_id, operation_id).run()
        return
    if job.get("state") != "running":
        await database.prepare(
            "UPDATE auto_sync_queue SET state='failed',operation_id=NULL,updated_at=? "
            "WHERE user_id=? AND operation_id=?"
        ).bind(_now(), user_id, operation_id).run()


async def dispatch_queued_backup(database, env, user_id):
    """Best-effort immediate dispatch; the durable D1 queue and Cron remain authoritative."""
    try:
        await _queue_auto_sync(database, env, user_id)
    except Exception as exc:
        # The queue row was committed with the ledger. Cron can dispatch it if
        # this fast path encounters a temporary D1 or Workflow API error.
        print(f"Auto-sync dispatch deferred ({type(exc).__name__}).")


async def run_scheduled(env):
    """Process a rotating batch so a larger account table does not starve."""
    database = env.DB
    cursor_row = await database.prepare(
        "SELECT state_value FROM worker_maintenance_state WHERE state_key='user_cursor'"
    ).first()
    cursor = str(_field(cursor_row, "state_value")) if cursor_row is not None else ""
    result = await database.prepare(
        "SELECT id FROM cloud_users WHERE id>? ORDER BY id LIMIT ?"
    ).bind(cursor, MAX_USERS_PER_TICK).run()
    users = list(result.get("results", []) if isinstance(result, dict) else getattr(result, "results", []) or [])
    if not users:
        result = await database.prepare(
            "SELECT id FROM cloud_users ORDER BY id LIMIT ?"
        ).bind(MAX_USERS_PER_TICK).run()
        users = list(result.get("results", []) if isinstance(result, dict) else getattr(result, "results", []) or [])
    if not users:
        return

    for row in users:
        user_id = str(_field(row, "id"))
        external_schedule_job = False
        try:
            if not await _active_job_exists(database, user_id):
                try:
                    await process_scheduled_entries(database, env, user_id)
                except Exception as exc:
                    if exc.__class__.__name__ != "ModelRequestRequired":
                        raise
                    # Recurring entries can need a transaction-date FX rate.
                    # Keep the quick Cron path for cached/same-currency plans,
                    # then hand only the external-fetch case to a durable job.
                    slot = int(datetime.now(timezone.utc).timestamp() // 900)
                    owner_tag = hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:20]
                    job = await _start_job(database, env, {"id": user_id}, {
                        "action": "process_scheduled",
                        "data": {},
                        "opId": f"schedule-{owner_tag}-{slot}",
                    })
                    external_schedule_job = job.get("state") == "running"
                if not external_schedule_job:
                    await _queue_auto_sync(database, env, user_id)
        except SnapshotConflict:
            # Another device saved first; this user's scheduled entries are
            # reconsidered on the next rotating tick.
            pass
        except Exception:
            # Do not abort the rest of this bounded batch because one ledger
            # has a damaged optional schedule or a transient D1 problem.
            pass
        await database.prepare(
            "INSERT INTO worker_maintenance_state(state_key,state_value,updated_at) VALUES('user_cursor',?,?) "
            "ON CONFLICT(state_key) DO UPDATE SET state_value=excluded.state_value,updated_at=excluded.updated_at"
        ).bind(user_id, _now()).run()
