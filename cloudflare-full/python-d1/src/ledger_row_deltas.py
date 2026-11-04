"""SQLite row-change capture used by the D1 snapshot adapter.

The Worker keeps a periodic SQLite base snapshot for import/export and puts
subsequent changes in D1 as row upserts/deletes. TEMP triggers ensure the
existing bookkeeping SQL remains the single source of transaction rules.
"""
from __future__ import annotations

import base64
import json
import sqlite3
from pathlib import Path
from typing import Any


LOG_TABLE = "__d1_row_change_log"
SIDECAR_SUFFIX = ".d1delta.json"


def _quote(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _encode(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"__d1_bytes_base64__": base64.b64encode(value).decode("ascii")}
    return value


def _decode(value: Any) -> Any:
    if isinstance(value, dict) and set(value) == {"__d1_bytes_base64__"}:
        return base64.b64decode(value["__d1_bytes_base64__"], validate=True)
    return value


def _table_info(connection: sqlite3.Connection, table: str) -> tuple[list[str], list[str]]:
    info = connection.execute(f"PRAGMA table_info({_quote(table)})").fetchall()
    columns = [str(row["name"] if isinstance(row, sqlite3.Row) else row[1]) for row in info]
    primary = sorted(
        ((int(row["pk"] if isinstance(row, sqlite3.Row) else row[5]),
          str(row["name"] if isinstance(row, sqlite3.Row) else row[1]))
         for row in info
         if int(row["pk"] if isinstance(row, sqlite3.Row) else row[5]) > 0),
        key=lambda item: item[0],
    )
    return columns, [name for _index, name in primary]


def install_change_tracking(connection: sqlite3.Connection) -> None:
    """Install connection-local triggers after schema initialization."""
    connection.execute(
        f"CREATE TEMP TABLE IF NOT EXISTS {_quote(LOG_TABLE)}("
        "table_name TEXT NOT NULL,row_key TEXT NOT NULL,operation TEXT NOT NULL,"
        "PRIMARY KEY(table_name,row_key))"
    )
    table_rows = connection.execute(
        "SELECT name FROM main.sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    for item in table_rows:
        table = str(item["name"] if isinstance(item, sqlite3.Row) else item[0])
        if table == LOG_TABLE:
            continue
        columns, primary = _table_info(connection, table)
        if not columns:
            continue
        # All current ledger tables have primary keys. rowid is a safe fallback
        # for any future ordinary SQLite table without one.
        old_key = ("json_array(" + ",".join(f"OLD.{_quote(name)}" for name in primary) + ")"
                   if primary else "json_array(OLD.rowid)")
        new_key = ("json_array(" + ",".join(f"NEW.{_quote(name)}" for name in primary) + ")"
                   if primary else "json_array(NEW.rowid)")
        safe = base64.urlsafe_b64encode(table.encode("utf-8")).decode("ascii").rstrip("=")
        target = f"main.{_quote(table)}"
        connection.executescript(
            f"CREATE TEMP TRIGGER IF NOT EXISTS {_quote('d1i_' + safe)} AFTER INSERT ON {target} BEGIN "
            f"INSERT OR REPLACE INTO {_quote(LOG_TABLE)} VALUES('{table.replace(chr(39), chr(39)*2)}',{new_key},'upsert'); END;"
            f"CREATE TEMP TRIGGER IF NOT EXISTS {_quote('d1u_' + safe)} AFTER UPDATE ON {target} BEGIN "
            f"INSERT OR REPLACE INTO {_quote(LOG_TABLE)} VALUES('{table.replace(chr(39), chr(39)*2)}',{old_key},'delete');"
            f"INSERT OR REPLACE INTO {_quote(LOG_TABLE)} VALUES('{table.replace(chr(39), chr(39)*2)}',{new_key},'upsert'); END;"
            f"CREATE TEMP TRIGGER IF NOT EXISTS {_quote('d1d_' + safe)} AFTER DELETE ON {target} BEGIN "
            f"INSERT OR REPLACE INTO {_quote(LOG_TABLE)} VALUES('{table.replace(chr(39), chr(39)*2)}',{old_key},'delete'); END;"
        )


def clear_change_log(connection: sqlite3.Connection) -> None:
    try:
        connection.execute(f"DELETE FROM temp.{_quote(LOG_TABLE)}")
        connection.commit()
    except sqlite3.Error:
        pass


def capture_changes(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    """Resolve trigger keys to final row values before a ledger connection closes."""
    try:
        log_rows = connection.execute(
            f"SELECT table_name,row_key,operation FROM temp.{_quote(LOG_TABLE)} ORDER BY table_name,row_key"
        ).fetchall()
    except sqlite3.Error:
        return []
    changes: list[dict[str, Any]] = []
    for log_row in log_rows:
        table = str(log_row["table_name"])
        key_text = str(log_row["row_key"])
        operation = str(log_row["operation"])
        columns, primary = _table_info(connection, table)
        try:
            key_values = json.loads(key_text)
        except (TypeError, ValueError):
            continue
        if not isinstance(key_values, list):
            continue
        row_json = None
        if operation == "upsert":
            select_columns = columns if primary else ["rowid", *columns]
            key_columns = primary if primary else ["rowid"]
            where = " AND ".join(f"{_quote(name)}=?" for name in key_columns)
            row = connection.execute(
                f"SELECT {','.join(_quote(name) for name in select_columns)} FROM main.{_quote(table)} WHERE {where}",
                tuple(_decode(value) for value in key_values),
            ).fetchone()
            if row is None:
                operation = "delete"
            else:
                payload = dict(row)
                row_json = json.dumps(
                    {name: _encode(value) for name, value in payload.items()},
                    ensure_ascii=False, separators=(",", ":"),
                )
        changes.append({
            "table_name": table,
            "row_key": key_text,
            "operation": operation,
            "row_json": row_json,
        })
    return changes


def write_pending_changes(path: Path, changes: list[dict[str, Any]]) -> None:
    if not changes:
        return
    sidecar = Path(str(path) + SIDECAR_SUFFIX)
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    if sidecar.is_file():
        try:
            for item in json.loads(sidecar.read_text("utf-8")):
                merged[(str(item["table_name"]), str(item["row_key"]))] = item
        except (OSError, TypeError, ValueError, KeyError):
            merged.clear()
    for item in changes:
        merged[(str(item["table_name"]), str(item["row_key"]))] = item
    sidecar.write_text(json.dumps(list(merged.values()), ensure_ascii=False, separators=(",", ":")), "utf-8")


def read_pending_changes(path: Path, *, delete: bool = True) -> list[dict[str, Any]]:
    sidecar = Path(str(path) + SIDECAR_SUFFIX)
    try:
        changes = json.loads(sidecar.read_text("utf-8"))
        if not isinstance(changes, list):
            return []
        if delete:
            sidecar.unlink(missing_ok=True)
        return changes
    except (OSError, TypeError, ValueError):
        return []


def apply_changes(connection: sqlite3.Connection, changes: list[dict[str, Any]], *, validate_foreign_keys=False) -> None:
    """Replay committed D1 row overrides on top of the last base SQLite file."""
    tables = {
        str(row[0]) for row in connection.execute(
            "SELECT name FROM main.sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }
    connection.commit()
    connection.execute("PRAGMA foreign_keys=OFF")
    connection.execute("BEGIN IMMEDIATE")
    try:
        for item in changes:
            table = str(item.get("table_name", ""))
            if table not in tables:
                continue
            columns, primary = _table_info(connection, table)
            try:
                keys = json.loads(str(item.get("row_key", "[]")))
            except (TypeError, ValueError):
                raise ValueError("云端账本增量主键格式无效。") from None
            if not isinstance(keys, list):
                raise ValueError("云端账本增量主键格式无效。")
            key_columns = primary if primary else ["rowid"]
            if len(key_columns) != len(keys):
                raise ValueError("云端账本增量主键字段数不匹配。")
            where = " AND ".join(f"{_quote(name)}=?" for name in key_columns)
            values = tuple(_decode(value) for value in keys)
            if item.get("operation") == "delete":
                connection.execute(f"DELETE FROM main.{_quote(table)} WHERE {where}", values)
                continue
            if item.get("operation") != "upsert":
                raise ValueError("云端账本增量操作类型无效。")
            try:
                payload = json.loads(str(item.get("row_json", "{}")))
            except (TypeError, ValueError):
                raise ValueError("云端账本增量内容格式无效。") from None
            if not isinstance(payload, dict) or not payload or any(name not in columns for name in payload):
                raise ValueError("云端账本增量字段与 SQLite 结构不匹配。")
            decoded_payload = {name: _decode(value) for name, value in payload.items()}
            if any(name not in decoded_payload for name in key_columns) or any(
                decoded_payload[name] != key for name, key in zip(key_columns, values)
            ):
                raise ValueError("云端账本增量主键与记录内容不匹配。")
            names = list(payload)
            row_values = [decoded_payload[name] for name in names]
            connection.execute(
                f"INSERT OR REPLACE INTO main.{_quote(table)}({','.join(_quote(name) for name in names)}) "
                f"VALUES({','.join('?' for _ in names)})",
                row_values,
            )
        if validate_foreign_keys and connection.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("云端账本增量的关联检查失败。")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.execute("PRAGMA foreign_keys=ON")
