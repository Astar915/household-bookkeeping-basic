"""Versioned durable storage for the existing SQLite-backed app files.

The full product already has a mature SQLite schema and file-oriented backup,
Skill, and sync formats. This adapter keeps those formats intact while moving
durability to D1; the files are staged in the Worker ephemeral filesystem for
one request and are never treated as durable local storage.
"""
from __future__ import annotations

import base64
import hashlib
import json
import posixpath
import uuid
from datetime import datetime, timezone
from typing import Any


CHUNK_BYTES = 96 * 1024
MAX_USER_STATE_BYTES = 450 * 1024 * 1024
GENESIS_REVISION = "0"
LEDGER_ROWS_META_KEY = "__ledger_rows_v1__"


class SnapshotError(RuntimeError):
    """Stored state is missing, corrupt, or too large to safely restore."""


class SnapshotConflict(SnapshotError):
    """Another request committed a newer account state first."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_path(value: str) -> str:
    path = str(value).replace("\\", "/")
    normalized = posixpath.normpath(path)
    if (
        not path
        or path.startswith("/")
        or "\x00" in path
        or normalized in {"", ".", ".."}
        or normalized.startswith("../")
        or len(normalized) > 240
    ):
        raise SnapshotError("账本文件路径无效，云端数据未被覆盖。")
    # Receipt image archiving is intentionally disabled for the web edition.
    if any(part.casefold() in {"receipt_images", "receipts"} for part in normalized.split("/")):
        raise SnapshotError("网页云端不归档小票图片；图片识别仍可临时使用。")
    return normalized


def _results(result: Any) -> list[Any]:
    if isinstance(result, dict):
        rows = result.get("results", [])
    else:
        rows = getattr(result, "results", [])
    return list(rows or [])


def _field(row: Any, name: str) -> Any:
    if isinstance(row, dict):
        return row[name]
    return getattr(row, name)


class D1SnapshotStore:
    """Store a per-user virtual data directory as checksummed D1 chunks."""

    def __init__(self, database: Any):
        self.database = database
        self.ledger_rows_enabled = False
        self.ledger_schema_hash = ""
        self.ledger_row_deltas: list[dict[str, Any]] = []

    async def ensure_user(self, user_id: str) -> None:
        """Create an empty manifest root after a user is provisioned."""
        await self.database.prepare(
            "INSERT OR IGNORE INTO user_state_roots(user_id,revision,manifest_json,updated_at) "
            "VALUES(?,?,?,?)"
        ).bind(user_id, GENESIS_REVISION, "{}", _now()).run()

    async def load(self, user_id: str) -> tuple[str, dict[str, bytes]]:
        root = await self.database.prepare(
            "SELECT revision,manifest_json FROM user_state_roots WHERE user_id=?"
        ).bind(user_id).first()
        if root is None:
            raise SnapshotError("云端账本索引不存在；请重新登录以初始化账号。")

        try:
            revision = str(_field(root, "revision"))
            manifest = json.loads(str(_field(root, "manifest_json")))
            if not isinstance(manifest, dict):
                raise ValueError("manifest is not an object")
        except (TypeError, ValueError, KeyError) as exc:
            raise SnapshotError("云端账本索引损坏；为保护数据，本次操作已停止。") from exc

        query = await self.database.prepare(
            "SELECT c.file_path,c.file_revision,c.chunk_index,c.payload_base64 "
            "FROM user_state_chunks AS c "
            "JOIN json_each((SELECT manifest_json FROM user_state_roots WHERE user_id=?)) AS m "
            "  ON m.key=c.file_path AND json_extract(m.value,'$.revision')=c.file_revision "
            "WHERE c.user_id=? ORDER BY c.file_path,c.chunk_index"
        ).bind(user_id, user_id).run()

        pieces: dict[str, list[tuple[int, bytes]]] = {}
        for row in _results(query):
            path = _safe_path(str(_field(row, "file_path")))
            encoded = str(_field(row, "payload_base64"))
            try:
                payload = base64.b64decode(encoded, validate=True)
                index = int(_field(row, "chunk_index"))
            except (ValueError, TypeError) as exc:
                raise SnapshotError("云端账本分块损坏；为保护数据，本次操作已停止。") from exc
            pieces.setdefault(path, []).append((index, payload))

        files: dict[str, bytes] = {}
        aggregate_size = 0
        meta = manifest.get(LEDGER_ROWS_META_KEY)
        if meta is not None:
            if not isinstance(meta, dict):
                raise SnapshotError("云端账本增量索引格式无效；本次操作已停止。")
            try:
                version = int(meta.get("version", 0))
            except (TypeError, ValueError) as exc:
                raise SnapshotError("云端账本增量索引格式无效；本次操作已停止。") from exc
            if version != 1:
                raise SnapshotError("云端账本增量版本不受支持；本次操作已停止。")
            schema_hash = str(meta.get("schemaHash", ""))
            if len(schema_hash) != 64 or any(char not in "0123456789abcdef" for char in schema_hash):
                raise SnapshotError("云端账本结构校验信息无效；本次操作已停止。")
            self.ledger_rows_enabled = True
            self.ledger_schema_hash = schema_hash
        for raw_path, entry in manifest.items():
            if raw_path == LEDGER_ROWS_META_KEY:
                continue
            path = _safe_path(raw_path)
            if not isinstance(entry, dict):
                raise SnapshotError("云端账本文件索引格式无效。")
            chunks = sorted(pieces.get(path, []), key=lambda item: item[0])
            expected_count = int(entry.get("chunks", 0))
            if len(chunks) != expected_count or [i for i, _ in chunks] != list(range(expected_count)):
                raise SnapshotError(f"云端账本文件 {path} 不完整；本次操作已停止。")
            body = b"".join(part for _, part in chunks)
            if len(body) != int(entry.get("size", -1)):
                raise SnapshotError(f"云端账本文件 {path} 大小校验失败。")
            if hashlib.sha256(body).hexdigest() != str(entry.get("sha256", "")):
                raise SnapshotError(f"云端账本文件 {path} 校验失败。")
            aggregate_size += len(body)
            files[path] = body
        if aggregate_size > MAX_USER_STATE_BYTES:
            raise SnapshotError("该账号的云端数据超过当前安全恢复上限。")
        if self.ledger_rows_enabled:
            deltas = await self.database.prepare(
                "SELECT table_name,row_key,operation,row_json FROM user_ledger_row_deltas "
                "WHERE user_id=? ORDER BY table_name,row_key"
            ).bind(user_id).run()
            self.ledger_row_deltas = []
            for row in _results(deltas):
                item = {
                    "table_name": str(_field(row, "table_name") or ""),
                    "row_key": str(_field(row, "row_key") or ""),
                    "operation": str(_field(row, "operation") or ""),
                    "row_json": _field(row, "row_json"),
                }
                try:
                    keys = json.loads(item["row_key"])
                    row_value = json.loads(item["row_json"]) if item["row_json"] is not None else None
                except (TypeError, ValueError) as exc:
                    raise SnapshotError("云端账本增量记录损坏；本次操作已停止。") from exc
                if (not item["table_name"] or not isinstance(keys, list)
                        or item["operation"] not in {"upsert", "delete"}
                        or (item["operation"] == "upsert" and not isinstance(row_value, dict))
                        or (item["operation"] == "delete" and item["row_json"] is not None)):
                    raise SnapshotError("云端账本增量记录格式无效；本次操作已停止。")
                self.ledger_row_deltas.append(item)
        return revision, files

    async def commit(
        self,
        user_id: str,
        expected_revision: str,
        old_files: dict[str, bytes],
        new_files: dict[str, bytes],
        *,
        final_statements: list[Any] | None = None,
        force_revision: bool = False,
        job_id: str | None = None,
        job_result_json: str = "{}",
        queue_auto_sync: bool = False,
        auto_sync_complete_operation_id: str | None = None,
        ledger_row_changes: list[dict[str, Any]] | None = None,
        ledger_storage_meta: dict[str, Any] | None = None,
        clear_ledger_row_deltas: bool = False,
    ) -> str:
        """Atomically advance the manifest after all changed files are staged."""
        old_paths = {_safe_path(path) for path in old_files}
        normalized: dict[str, bytes] = {}
        total_size = 0
        for raw_path, body in new_files.items():
            path = _safe_path(raw_path)
            if not isinstance(body, bytes):
                raise SnapshotError("内部文件状态格式无效。")
            total_size += len(body)
            normalized[path] = body
        if total_size > MAX_USER_STATE_BYTES:
            raise SnapshotError("云端数据已接近 D1 安全容量，未提交本次更改。请先下载备份并清理旧备份。")

        root = await self.database.prepare(
            "SELECT revision,manifest_json FROM user_state_roots WHERE user_id=?"
        ).bind(user_id).first()
        if root is None:
            raise SnapshotError("云端账本索引不存在；本次更改未保存。")
        current_revision = str(_field(root, "revision"))
        if current_revision != expected_revision:
            raise SnapshotConflict("此账号的数据已在另一设备更新；请刷新后重试，离线队列仍保留。")
        old_manifest = json.loads(str(_field(root, "manifest_json")))
        manifest = dict(old_manifest)
        changed: dict[str, bytes] = {}
        removed = old_paths - set(normalized)
        for path in removed:
            manifest.pop(path, None)
        for path, body in normalized.items():
            previous = old_files.get(path)
            if previous == body and path in manifest:
                continue
            changed[path] = body

        row_stage_id = None
        staged_ledger_rows = list(ledger_row_changes or [])
        if staged_ledger_rows:
            row_stage_id = uuid.uuid4().hex
            staged = []
            for item in staged_ledger_rows:
                table_name = str(item.get("table_name", ""))
                row_key = str(item.get("row_key", ""))
                operation = str(item.get("operation", ""))
                row_json = item.get("row_json")
                if (not table_name or len(table_name) > 128 or not row_key or len(row_key) > 2048
                        or operation not in {"upsert", "delete"}
                        or (operation == "upsert" and not isinstance(row_json, str))
                        or (operation == "delete" and row_json is not None)):
                    raise SnapshotError("账本增量格式无效；本次操作没有保存。")
                if isinstance(row_json, str) and len(row_json.encode("utf-8")) > 1_900_000:
                    raise SnapshotError("单条账本记录超过 D1 单行上限；本次操作没有保存。")
                staged.append(self.database.prepare(
                    "INSERT OR REPLACE INTO user_ledger_row_delta_stage "
                    "(user_id,stage_id,table_name,row_key,operation,row_json) VALUES(?,?,?,?,?,?)"
                ).bind(user_id, row_stage_id, table_name, row_key, operation, row_json))
            try:
                for offset in range(0, len(staged), 40):
                    await self.database.batch(staged[offset:offset + 40])
            except Exception:
                await self.database.prepare(
                    "DELETE FROM user_ledger_row_delta_stage WHERE user_id=? AND stage_id=?"
                ).bind(user_id, row_stage_id).run()
                raise

        new_root_revision = uuid.uuid4().hex
        if callable(final_statements):
            final_statements = final_statements(new_root_revision)
        else:
            final_statements = list(final_statements or [])
        if (not changed and not removed and not force_revision and not final_statements
                and not row_stage_id and not clear_ledger_row_deltas and ledger_storage_meta is None):
            return current_revision

        statements = []
        file_revisions: dict[str, str] = {}
        for path, body in changed.items():
            file_revision = uuid.uuid4().hex
            file_revisions[path] = file_revision
            parts = [body[index:index + CHUNK_BYTES] for index in range(0, len(body), CHUNK_BYTES)]
            for index, part in enumerate(parts):
                encoded = base64.b64encode(part).decode("ascii")
                statements.append(self.database.prepare(
                    "INSERT INTO user_state_chunks(user_id,file_path,file_revision,chunk_index,payload_base64) "
                    "VALUES(?,?,?,?,?)"
                ).bind(user_id, path, file_revision, index, encoded))
            manifest[path] = {
                "revision": file_revision,
                "chunks": len(parts),
                "size": len(body),
                "sha256": hashlib.sha256(body).hexdigest(),
            }
        if ledger_storage_meta is not None:
            manifest[LEDGER_ROWS_META_KEY] = {
                "version": 1,
                "schemaHash": str(ledger_storage_meta.get("schemaHash", "")),
            }

        # D1 batches are transactional, but keeping each staging batch small
        # avoids binding/request limits for ledgers with many changed files.
        for offset in range(0, len(statements), 40):
            await self.database.batch(statements[offset:offset + 40])

        manifest_json = json.dumps(manifest, ensure_ascii=False, separators=(",", ":"))
        commit_statement = self.database.prepare(
            "UPDATE user_state_roots SET revision=?,manifest_json=?,updated_at=? "
            "WHERE user_id=? AND revision=?"
            + (" AND EXISTS (SELECT 1 FROM app_jobs WHERE user_id=? AND operation_id=? "
               "AND state='running' AND cancel_requested=0)" if job_id else "")
        )
        commit_params = [new_root_revision, manifest_json, _now(), user_id, expected_revision]
        if job_id:
            commit_params.extend([user_id, job_id])
        final_batch = [commit_statement.bind(*commit_params)]
        final_batch.extend(final_statements)
        if clear_ledger_row_deltas:
            final_batch.append(self.database.prepare(
                "DELETE FROM user_ledger_row_deltas WHERE user_id=? AND EXISTS "
                "(SELECT 1 FROM user_state_roots WHERE user_id=? AND revision=?)"
            ).bind(user_id, user_id, new_root_revision))
        if row_stage_id:
            final_batch.append(self.database.prepare(
                "INSERT INTO user_ledger_row_deltas "
                "(user_id,table_name,row_key,operation,row_json,updated_at) "
                "SELECT s.user_id,s.table_name,s.row_key,s.operation,s.row_json,? "
                "FROM user_ledger_row_delta_stage AS s WHERE s.user_id=? AND s.stage_id=? AND EXISTS "
                "(SELECT 1 FROM user_state_roots WHERE user_id=? AND revision=?) "
                "ON CONFLICT(user_id,table_name,row_key) DO UPDATE SET "
                "operation=excluded.operation,row_json=excluded.row_json,updated_at=excluded.updated_at"
            ).bind(_now(), user_id, row_stage_id, user_id, new_root_revision))
            final_batch.append(self.database.prepare(
                "DELETE FROM user_ledger_row_delta_stage WHERE user_id=? AND stage_id=?"
            ).bind(user_id, row_stage_id))
        if job_id:
            final_batch.append(self.database.prepare(
                "UPDATE app_jobs SET state='done',message='已完成',result_json=?,updated_at=? "
                "WHERE user_id=? AND operation_id=? AND state='running' AND cancel_requested=0 "
                "AND EXISTS (SELECT 1 FROM user_state_roots WHERE user_id=? AND revision=?)"
            ).bind(
                job_result_json, _now(),
                user_id, job_id, user_id, new_root_revision,
            ))
        if auto_sync_complete_operation_id:
            final_batch.append(self.database.prepare(
                "UPDATE auto_sync_queue SET state='done',operation_id=NULL,attempts=0,updated_at=? "
                "WHERE user_id=? AND operation_id=? AND EXISTS "
                "(SELECT 1 FROM user_state_roots WHERE user_id=? AND revision=?)"
            ).bind(_now(), user_id, auto_sync_complete_operation_id, user_id, new_root_revision))
        if queue_auto_sync and (changed or removed or row_stage_id or clear_ledger_row_deltas):
            final_batch.append(self.database.prepare(
                "INSERT INTO auto_sync_queue(user_id,revision,state,operation_id,attempts,updated_at) "
                "SELECT ?,?,'pending',NULL,0,? WHERE EXISTS "
                "(SELECT 1 FROM user_state_roots WHERE user_id=? AND revision=?) "
                "ON CONFLICT(user_id) DO UPDATE SET revision=excluded.revision,state='pending',"
                "operation_id=NULL,attempts=0,updated_at=excluded.updated_at"
            ).bind(user_id, new_root_revision, _now(), user_id, new_root_revision))
        try:
            results = await self.database.batch(final_batch)
        except Exception:
            if row_stage_id:
                await self.database.prepare(
                    "DELETE FROM user_ledger_row_delta_stage WHERE user_id=? AND stage_id=?"
                ).bind(user_id, row_stage_id).run()
            raise
        commit_result = results[0] if results else None
        meta = _field(commit_result, "meta") if commit_result is not None else None
        changes = _field(meta, "changes") if meta is not None else 0
        if int(changes or 0) != 1:
            # Remove only this request's staged chunks. The committed manifest
            # and its files remain untouched.
            for path, file_revision in file_revisions.items():
                await self.database.prepare(
                    "DELETE FROM user_state_chunks WHERE user_id=? AND file_path=? AND file_revision=?"
                ).bind(user_id, path, file_revision).run()
            if job_id:
                job = await self.database.prepare(
                    "SELECT state,cancel_requested FROM app_jobs WHERE user_id=? AND operation_id=?"
                ).bind(user_id, job_id).first()
                if job is not None and (str(_field(job, "state")) != "running" or int(_field(job, "cancel_requested"))):
                    raise SnapshotError("操作已取消，本次更改没有写入账本。")
            raise SnapshotConflict("另一设备先保存了新版本；本次更改没有覆盖它，请刷新后重试。")


        # The root revision is the commit point. Garbage collection runs only
        # after it advances, and removes chunks not referenced by its manifest.
        await self.database.prepare(
            "DELETE FROM user_state_chunks WHERE user_id=? AND NOT EXISTS ("
            "SELECT 1 FROM json_each((SELECT manifest_json FROM user_state_roots WHERE user_id=?)) AS m "
            "WHERE m.key=user_state_chunks.file_path "
            "AND json_extract(m.value,'$.revision')=user_state_chunks.file_revision"
            ")"
        ).bind(user_id, user_id).run()
        return new_root_revision
