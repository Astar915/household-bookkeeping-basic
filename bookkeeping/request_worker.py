from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path
from typing import Any, Callable

from .natural_language import (
    ImageAttachment,
    NaturalLanguageError,
    NaturalLanguageSession,
    OpenAICompatibleClient,
)
from .storage import Database


class RequestMergeError(RuntimeError):
    """Raised when a finished isolated request cannot be safely committed."""


def receive_request_result(connection, worker, results, fallback):
    """Drain even large/partial pipe messages without blocking Tk's event loop."""
    try:
        message = connection.recv()
    except (EOFError, OSError, ValueError):
        message = fallback
    if not isinstance(message, tuple) or len(message) != 5 or message[0] not in {'ok', 'error'}:
        message = fallback
    try:
        worker.join(timeout=2)
    except (OSError, ValueError):
        pass
    results.put(('received', message))


def commit_request_result(message, live, baseline, candidate, results, fallback):
    status, answer, history, pending, usage = message
    inserted = []
    if status == 'ok':
        try:
            inserted = merge_isolated_database(live, baseline, candidate)
        except Exception as exc:
            message = ('error', str(exc), fallback[2], fallback[3], None)
    results.put(('finished', message, inserted))


def run_isolated_request(
    live_database_path: str,
    baseline_path: str,
    candidate_path: str,
    client_config: dict[str, Any],
    user_text: str,
    history_snapshot: list[dict[str, Any]],
    pending_snapshot: dict[str, Any] | None,
    payment_hints: list[dict[str, str]],
    skill_content: str,
    images: list[ImageAttachment],
    agent_mode: str,
    response_language: str,
    result_connection: Any,
) -> None:
    """Run one API turn against a disposable copy of the local ledger."""
    try:
        message = run_isolated_request_result(
            live_database_path,
            baseline_path,
            candidate_path,
            client_config,
            user_text,
            history_snapshot,
            pending_snapshot,
            payment_hints,
            skill_content,
            images,
            agent_mode,
            response_language,
        )
    except Exception:
        message = (
            "error",
            "程序暂时无法完成请求。请检查账本文件和 API 配置后重试。",
            history_snapshot,
            pending_snapshot,
            None,
        )

    try:
        result_connection.send(message)
    finally:
        result_connection.close()


def run_isolated_request_result(
    live_database_path: str,
    baseline_path: str,
    candidate_path: str,
    client_config: dict[str, Any],
    user_text: str,
    history_snapshot: list[dict[str, Any]],
    pending_snapshot: dict[str, Any] | None,
    payment_hints: list[dict[str, str]],
    skill_content: str,
    images: list[ImageAttachment],
    agent_mode: str,
    response_language: str,
    *,
    opener: Any = None,
) -> tuple[str, Any, Any, Any, Any]:
    """Run one turn and return its result instead of crossing a process pipe.

    Cloudflare Workflows supplies an opener that replays completed model calls
    and raises ``ModelRequestRequired`` when the next async Worker fetch is
    needed. That signal must escape this function unchanged so the Workflow
    can persist the provider response and replay the isolated turn safely.
    Desktop callers keep using ``run_isolated_request`` above.
    """
    database: Database | None = None
    client: OpenAICompatibleClient | None = None
    try:
        live_path = Path(live_database_path).resolve()
        baseline = Path(baseline_path).resolve()
        candidate = Path(candidate_path).resolve()
        source_uri = live_path.as_uri() + "?mode=ro"
        source_connection = sqlite3.connect(source_uri, uri=True, timeout=30)
        baseline_connection = sqlite3.connect(baseline)
        try:
            source_connection.backup(baseline_connection)
        finally:
            baseline_connection.close()
            source_connection.close()
        shutil.copyfile(baseline, candidate)

        database = Database(candidate)
        database.initialize()
        client = OpenAICompatibleClient(
            str(client_config.get("api_key", "")),
            api_url=str(client_config["api_url"]),
            model=str(client_config["model"]),
            thinking_enabled=client_config.get("thinking_enabled", False),
            reasoning_effort=str(client_config.get("reasoning_effort", "low")),
            timeout=float(client_config["timeout"]),
            opener=opener,
        )
        session = NaturalLanguageSession(
            database,
            client,
            payment_hints=payment_hints,
            loaded_skill=skill_content,
            response_language=response_language,
        )
        session.history = history_snapshot
        session.pending_state = pending_snapshot
        answer = session.handle(user_text, images=images, agent_mode=agent_mode)
        message = (
            "ok",
            answer,
            session.history,
            session.pending_state,
            client.usage_snapshot(),
        )
    except NaturalLanguageError as exc:
        message = (
            "error",
            str(exc),
            history_snapshot,
            pending_snapshot,
            client.usage_snapshot() if client is not None else None,
        )
    except Exception as exc:
        if opener is not None and exc.__class__.__name__ == "ModelRequestRequired":
            raise
        # Keep unexpected failures diagnosable without logging request text,
        # model responses, credentials, or exception messages (which may
        # contain provider data). The basename and line number are enough to
        # locate the failing code in local and Worker logs.
        import traceback
        frames = traceback.extract_tb(exc.__traceback__)
        locations = " -> ".join(
            f"{frame.filename.replace(chr(92), '/').rsplit('/', 1)[-1]}:{frame.lineno}"
            for frame in frames[-5:]
        )
        error_type = type(exc).__name__
        print(f"Isolated Agent request failed ({error_type}) at {locations}.")
        message = (
            "error",
            f"程序处理请求时发生内部错误（{error_type}），本次没有写入账本。请稍后重试。",
            history_snapshot,
            pending_snapshot,
            client.usage_snapshot() if client is not None else None,
        )
    finally:
        if database is not None:
            database.close()
    return message


def _table_state(connection: sqlite3.Connection) -> dict[str, tuple[list[str], list[str], dict[tuple[Any, ...], tuple[Any, ...]]]]:
    table_names = [
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    result: dict[str, tuple[list[str], list[str], dict[tuple[Any, ...], tuple[Any, ...]]]] = {}
    for table in table_names:
        escaped_table = table.replace('"', '""')
        info = connection.execute(f'PRAGMA table_info("{escaped_table}")').fetchall()
        columns = [str(row[1]) for row in info]
        primary_key = [str(row[1]) for row in sorted(info, key=lambda item: int(item[5]) or 10**9) if int(row[5])]
        if not primary_key:
            raise RequestMergeError(f"无法安全合并没有主键的账本表：{table}")
        order_by = ",".join(f'"{column.replace(chr(34), chr(34) * 2)}"' for column in primary_key)
        rows = {
            tuple(row[column] for column in primary_key): tuple(row[column] for column in columns)
            for row in connection.execute(f'SELECT * FROM "{escaped_table}" ORDER BY {order_by}')
        }
        result[table] = (columns, primary_key, rows)
    return result


def merge_isolated_database(
    live_database_path: str | Path,
    baseline_path: str | Path,
    candidate_path: str | Path,
    *,
    prepare_live_connection: Callable[[sqlite3.Connection], None] | None = None,
    after_live_commit: Callable[[sqlite3.Connection], None] | None = None,
) -> list[int]:
    """Atomically merge supported request changes after verifying the ledger is unchanged.

    Optional hooks let the isolated D1 adapter observe the rows changed by the
    merge without changing the desktop caller's default behavior.
    """
    baseline_uri = Path(baseline_path).resolve().as_uri() + "?mode=ro"
    candidate_uri = Path(candidate_path).resolve().as_uri() + "?mode=ro"
    baseline_connection = sqlite3.connect(baseline_uri, uri=True)
    candidate_connection = sqlite3.connect(candidate_uri, uri=True)
    live_connection = sqlite3.connect(Path(live_database_path), timeout=5)
    baseline_connection.row_factory = sqlite3.Row
    candidate_connection.row_factory = sqlite3.Row
    live_connection.row_factory = sqlite3.Row
    live_connection.execute("PRAGMA foreign_keys=ON")
    live_connection.execute("PRAGMA busy_timeout=5000")
    try:
        if prepare_live_connection is not None:
            prepare_live_connection(live_connection)
        baseline_state = _table_state(baseline_connection)
        candidate_state = _table_state(candidate_connection)
        live_connection.execute("BEGIN IMMEDIATE")
        live_state = _table_state(live_connection)

        if set(baseline_state) != set(candidate_state) or set(baseline_state) != set(live_state):
            raise RequestMergeError("请求期间账本结构发生变化，本次结果没有写入。请重新打开软件后重试。")

        additions: dict[str, list[tuple[Any, ...]]] = {}
        deletions: dict[str, list[tuple[Any, ...]]] = {}
        updates: dict[str, list[tuple[tuple[Any, ...], tuple[Any, ...]]]] = {}
        allowed_tables = {"fx_rates", "transactions", "food_purchase_items", "credit_limit_recovery_points"}
        for table, (columns, primary_key, baseline_rows) in baseline_state.items():
            candidate_columns, candidate_key, candidate_rows = candidate_state[table]
            live_columns, live_key, live_rows = live_state[table]
            if columns != candidate_columns or columns != live_columns or primary_key != candidate_key or primary_key != live_key:
                raise RequestMergeError("请求期间账本结构发生变化，本次结果没有写入。请重新打开软件后重试。")
            if live_rows != baseline_rows:
                raise RequestMergeError("请求期间账本已有其他变更，本次结果没有写入。请核对账本后重试。")
            deleted_keys = set(baseline_rows) - set(candidate_rows)
            changed_rows = [
                (key, candidate_rows[key])
                for key, original_row in baseline_rows.items()
                if candidate_rows[key] != original_row
            ]
            new_keys = set(candidate_rows) - set(baseline_rows)
            if (deleted_keys or changed_rows or new_keys) and table not in allowed_tables:
                raise RequestMergeError(f"请求结果包含不支持的账本变更（{table}），本次结果没有写入。")
            if deleted_keys:
                deletions[table] = sorted(deleted_keys, key=repr)
            if changed_rows:
                updates[table] = changed_rows
            if new_keys:
                additions[table] = [candidate_rows[key] for key in sorted(new_keys, key=repr)]

        inserted_transaction_ids: list[int] = []
        # Apply removals from child to parent, then updates, then additions
        # from parent to child. This preserves the app's supported request
        # changes while keeping them inside one transaction.
        delete_order = ("food_purchase_items", "credit_limit_recovery_points", "transactions", "fx_rates")
        for table in delete_order:
            keys = deletions.get(table, [])
            if not keys:
                continue
            columns, primary_key, _ = baseline_state[table]
            where = " AND ".join(
                f'"{column.replace(chr(34), chr(34) * 2)}"=?' for column in primary_key
            )
            escaped_table = table.replace('"', '""')
            for key in keys:
                live_connection.execute(
                    f'DELETE FROM "{escaped_table}" WHERE {where}', key
                )

        for table in ("fx_rates", "transactions", "credit_limit_recovery_points", "food_purchase_items"):
            for key, row in updates.get(table, []):
                columns, primary_key, _ = baseline_state[table]
                key_columns = set(primary_key)
                update_columns = [column for column in columns if column not in key_columns]
                assignments = ",".join(
                    f'"{column.replace(chr(34), chr(34) * 2)}"=?' for column in update_columns
                )
                where = " AND ".join(
                    f'"{column.replace(chr(34), chr(34) * 2)}"=?' for column in primary_key
                )
                values = [row[columns.index(column)] for column in update_columns]
                escaped_table = table.replace('"', '""')
                live_connection.execute(
                    f'UPDATE "{escaped_table}" SET {assignments} WHERE {where}',
                    (*values, *key),
                )

        for table in ("fx_rates", "transactions", "credit_limit_recovery_points", "food_purchase_items"):
            rows = additions.get(table, [])
            if not rows:
                continue
            columns = baseline_state[table][0]
            column_list = ",".join(f'"{column.replace(chr(34), chr(34) * 2)}"' for column in columns)
            placeholders = ",".join("?" for _ in columns)
            escaped_table = table.replace('"', '""')
            live_connection.executemany(
                f'INSERT INTO "{escaped_table}" ({column_list}) VALUES ({placeholders})',
                rows,
            )
            if table == "transactions":
                id_index = columns.index("id")
                inserted_transaction_ids = [int(row[id_index]) for row in rows]

        violations = live_connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RequestMergeError("账本关联校验未通过，本次结果没有写入。")
        live_connection.commit()
        if after_live_commit is not None:
            after_live_commit(live_connection)
        return sorted(inserted_transaction_ids)
    except Exception:
        live_connection.rollback()
        raise
    finally:
        live_connection.close()
        candidate_connection.close()
        baseline_connection.close()
