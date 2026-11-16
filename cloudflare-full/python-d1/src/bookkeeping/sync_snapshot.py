"""Versioned, file-oriented cloud snapshots used by the web cloud sync path.

The repository stores one JSON file per database row plus a small manifest.
Providers commit a complete file delta and the new manifest atomically.  The
legacy ZIP format remains supported by the caller as a migration fallback.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sqlite3
import tempfile
from typing import Any
import zipfile
from io import BytesIO

from .backup_scope import DEFAULT_BACKUP_SCOPE, normalize_backup_scope
from .storage import Database


SNAPSHOT_ROOT = "household-bookkeeping/snapshot-v1"
SNAPSHOT_FORMAT = "household-bookkeeping-folder-snapshot"
SNAPSHOT_VERSION = 1
MAX_SNAPSHOT_BYTES = 60_000_000
MAX_SNAPSHOT_UNPACKED_BYTES = 512_000_000
MAX_ARCHIVE_BYTES = 120_000_000
_TABLE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class SnapshotFormatError(ValueError):
    """The versioned cloud snapshot is incomplete or unsafe to restore."""


@dataclass(frozen=True)
class SnapshotPlan:
    manifest: dict[str, Any]
    manifest_bytes: bytes
    files: dict[str, bytes]
    changed: dict[str, bytes]
    deleted: tuple[str, ...]
    unchanged: bool
    created_at: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _encode_sql_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"$sqlite_blob": base64.b64encode(value).decode("ascii")}
    return value


def _decode_sql_value(value: Any) -> Any:
    if isinstance(value, dict) and set(value) == {"$sqlite_blob"}:
        try:
            return base64.b64decode(value["$sqlite_blob"], validate=True)
        except (ValueError, TypeError) as exc:
            raise SnapshotFormatError("快照中的二进制字段无效。") from exc
    if isinstance(value, (str, int, float, bytes)) or value is None:
        return value
    raise SnapshotFormatError("快照包含不支持的数据库字段。")


def _safe_relative_path(value: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise SnapshotFormatError("快照文件路径无效。")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise SnapshotFormatError("快照文件路径无效。")
    return path.as_posix()


def _table_section(table: str, row: dict[str, Any], account_types: dict[int, str]) -> str:
    if table in {"transactions", "food_purchase_items", "food_consumption_records", "fx_rates"}:
        return "ledger"
    if table in {"categories", "category_translations", "currencies", "settings"}:
        return "settings"
    if table == "accounts":
        return "credit_cards" if row.get("account_type") == "credit" else "accounts"
    if table == "account_balance_snapshots":
        return "credit_cards" if account_types.get(row.get("account_id")) == "credit" else "accounts"
    if table.startswith("credit_"):
        return "credit_cards"
    if table.startswith("recurring_"):
        return "recurring_payments"
    if table == "fixed_assets":
        return "fixed_assets"
    return "settings"


def _store_json_file(files: dict[str, bytes], relative: str, value: Any) -> None:
    path = _safe_relative_path(relative)
    if path in files:
        raise SnapshotFormatError("快照中出现重复文件路径。")
    files[path] = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def build_snapshot(
    database_path: Path,
    *,
    payment_store=None,
    bookkeeping_skill_store=None,
    food_skill_store=None,
    receipt_image_directory: Path | None = None,
    include_scope: dict[str, bool] | None = None,
    include_receipt_images: bool = True,
    previous_manifest: dict[str, Any] | None = None,
    created_at: datetime | str | None = None,
) -> SnapshotPlan:
    """Prepare a deterministic file map and only the content that changed."""
    from .github_sync import (
        GitHubSyncError, _apply_backup_scope_to_database, _remove_local_settings_from_database,
    )
    from .payment_preferences import PaymentPromptStore
    from .skill_settings import BookkeepingSkillStore, FoodHealthSkillStore

    scope = normalize_backup_scope(include_scope or DEFAULT_BACKUP_SCOPE)
    if not any(scope.values()):
        raise SnapshotFormatError("至少选择一项云备份内容。")
    previous = previous_manifest if _valid_manifest(previous_manifest) else None
    previous_files = previous.get("files", {}) if previous else {}
    previous_sections = previous.get("sections", {}) if previous else {}
    if isinstance(created_at, datetime):
        normalized_created = (created_at.replace(tzinfo=timezone.utc) if created_at.tzinfo is None
                              else created_at.astimezone(timezone.utc)).isoformat(timespec="microseconds")
    elif isinstance(created_at, str) and created_at:
        normalized_created = created_at
    else:
        normalized_created = _utc_now()
    now = normalized_created
    files: dict[str, bytes] = {}
    table_columns: dict[str, list[str]] = {}
    account_types: dict[int, str] = {}
    image_dir = receipt_image_directory or Path(database_path).parent / "receipt_images"
    payment_store = payment_store or PaymentPromptStore()
    bookkeeping_skill_store = bookkeeping_skill_store or BookkeepingSkillStore()
    food_skill_store = food_skill_store or FoodHealthSkillStore()

    with tempfile.TemporaryDirectory(prefix="household-folder-snapshot-") as temp_name:
        snapshot_db = Path(temp_name) / "ledger.sqlite3"
        source = Database(database_path)
        try:
            source.backup(snapshot_db)
        except Exception as exc:
            raise SnapshotFormatError("无法制作账本同步快照。") from exc
        finally:
            source.close()
        try:
            _remove_local_settings_from_database(snapshot_db)
            _apply_backup_scope_to_database(snapshot_db, scope)
            connection = sqlite3.connect(snapshot_db)
            connection.row_factory = sqlite3.Row
            try:
                tables = [str(row[0]) for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'web_%' ORDER BY name"
                )]
                account_types = {
                    int(row[0]): str(row[1]) for row in connection.execute("SELECT id,account_type FROM accounts")
                } if "accounts" in tables else {}
                schema: dict[str, Any] = {}
                for table in tables:
                    if not _TABLE_NAME.fullmatch(table):
                        raise SnapshotFormatError("账本包含无法安全同步的数据表。")
                    info = connection.execute(f'PRAGMA table_info("{table}")').fetchall()
                    columns = [str(item[1]) for item in info]
                    table_columns[table] = columns
                    schema[table] = {"columns": columns, "primary_key": [str(item[1]) for item in sorted(info, key=lambda c: int(c[5])) if int(item[5]) > 0]}
                    pk_columns = schema[table]["primary_key"]
                    select = f'SELECT * FROM "{table}"'
                    if pk_columns:
                        select += " ORDER BY " + ",".join('"' + c.replace('"', '""') + '"' for c in pk_columns)
                    rows = connection.execute(select).fetchall()
                    pk_columns = schema[table]["primary_key"]
                    for row in rows:
                        raw_row = {column: _encode_sql_value(row[column]) for column in columns}
                        section = _table_section(table, dict(row), account_types)
                        key = ({column: raw_row[column] for column in pk_columns}
                               if pk_columns else raw_row)
                        item_key = hashlib.sha256(_canonical(key)).hexdigest()
                        _store_json_file(
                            files,
                            f"data/{section}/{table}/{item_key}.json",
                            {"table": table, "row": raw_row},
                        )
                _store_json_file(files, "meta/schema.json", schema)
            finally:
                connection.close()
        except GitHubSyncError as exc:
            raise SnapshotFormatError(str(exc)) from exc
        except sqlite3.Error as exc:
            raise SnapshotFormatError("无法读取本机账本以生成分区备份。") from exc

    if scope["payment_methods"]:
        payment_settings = payment_store.load()
        payment_settings.setdefault("version", 2)
        _store_json_file(files, "payment/methods.json", payment_settings)
    if scope["settings"]:
        for name, store in (("bookkeeping.md", bookkeeping_skill_store), ("food_health.md", food_skill_store)):
            loaded = store.load()
            if loaded:
                path = _safe_relative_path(f"skills/{name}")
                files[path] = str(loaded["content"]).encode("utf-8")
    if include_receipt_images and scope["bills"] and image_dir.exists():
        for image in sorted(image_dir.rglob("*"), key=lambda item: item.relative_to(image_dir).as_posix()):
            if image.is_symlink() or not image.is_file():
                continue
            relative = image.relative_to(image_dir).as_posix()
            files[_safe_relative_path(f"receipts/{relative}")] = image.read_bytes()

    total_bytes = sum(len(body) for body in files.values())
    if total_bytes > MAX_SNAPSHOT_BYTES:
        raise SnapshotFormatError("分区同步内容超过 60 MB；请减少小票图片后重试。")

    manifest_files: dict[str, dict[str, Any]] = {}
    for path, body in sorted(files.items()):
        digest = hashlib.sha256(body).hexdigest()
        old = previous_files.get(path, {}) if isinstance(previous_files, dict) else {}
        section = path.split("/", 1)[0]
        if path.startswith("data/"):
            section = path.split("/", 3)[1]
        updated_at = old.get("updated_at") if old.get("sha256") == digest else now
        manifest_files[path] = {
            "sha256": digest,
            "size": len(body),
            "section": section,
            "updated_at": updated_at if isinstance(updated_at, str) else now,
        }
    deleted = tuple(sorted(set(previous_files) - set(manifest_files))) if isinstance(previous_files, dict) else ()
    changed = {
        path: body for path, body in files.items()
        if not isinstance(previous_files, dict)
        or previous_files.get(path, {}).get("sha256") != manifest_files[path]["sha256"]
    }
    scope_changed = previous is None or previous.get("scope") != scope
    section_names = sorted({entry["section"] for entry in manifest_files.values()} | set(previous_sections))
    sections: dict[str, dict[str, str]] = {}
    for section in section_names:
        items = [(path, meta["sha256"]) for path, meta in sorted(manifest_files.items()) if meta["section"] == section]
        section_hash = hashlib.sha256(_canonical(items)).hexdigest()
        old = previous_sections.get(section, {}) if isinstance(previous_sections, dict) else {}
        unchanged_section = old.get("sha256") == section_hash and not scope_changed
        sections[section] = {
            "sha256": section_hash,
            "updated_at": old.get("updated_at", now) if unchanged_section else now,
        }

    unchanged = previous is not None and not changed and not deleted and not scope_changed
    created_at = previous.get("created_at", now) if unchanged else now
    manifest = {
        "format": SNAPSHOT_FORMAT,
        "version": SNAPSHOT_VERSION,
        "created_at": created_at,
        "scope": scope,
        "sections": sections,
        "files": manifest_files,
        "tables": table_columns,
        "excludes": [
            "api_credentials", "github_authorization", "gitee_authorization",
            "interface_language", "local_preferences", "local_backup_history",
        ],
    }
    manifest_bytes = _canonical(manifest)
    return SnapshotPlan(manifest, manifest_bytes, files, changed, deleted, unchanged, str(created_at))


def _valid_manifest(value: Any) -> bool:
    if not isinstance(value, dict) or value.get("format") != SNAPSHOT_FORMAT or value.get("version") != SNAPSHOT_VERSION:
        return False
    if (not isinstance(value.get("files"), dict) or not isinstance(value.get("scope"), dict)
            or not isinstance(value.get("sections"), dict) or not isinstance(value.get("tables"), dict)):
        return False
    for path, item in value["files"].items():
        try:
            _safe_relative_path(path)
        except SnapshotFormatError:
            return False
        if (not isinstance(item, dict)
                or not re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256", "")))
                or not isinstance(item.get("section"), str) or not item["section"]
                or not isinstance(item.get("updated_at"), str) or not item["updated_at"]):
            return False
        if (isinstance(item.get("size"), bool) or not isinstance(item.get("size"), int)
                or item["size"] < 0):
            return False
        if not (path.startswith("data/") or path == "meta/schema.json"
                or path == "payment/methods.json" or path.startswith("skills/")
                or path.startswith("receipts/")):
            return False
    for section, item in value["sections"].items():
        if (not isinstance(section, str) or not section or not isinstance(item, dict)
                or not re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256", "")))
                or not isinstance(item.get("updated_at"), str) or not item["updated_at"]):
            return False
    if any(not isinstance(table, str) or not _TABLE_NAME.fullmatch(table)
           or not isinstance(columns, list) or not columns
           or any(not isinstance(column, str) for column in columns)
           for table, columns in value["tables"].items()):
        return False
    try:
        normalize_backup_scope(value["scope"])
    except Exception:
        return False
    return True


def parse_manifest(payload: bytes) -> dict[str, Any]:
    if len(payload) > 4_000_000:
        raise SnapshotFormatError("云端分区清单超过安全大小限制。")
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SnapshotFormatError("云端分区清单无法读取。") from exc
    if not _valid_manifest(value):
        raise SnapshotFormatError("云端分区清单格式无效或版本不兼容。")
    created = value.get("created_at")
    if not isinstance(created, str):
        raise SnapshotFormatError("云端分区清单缺少更新时间。")
    try:
        parsed = datetime.fromisoformat(created.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SnapshotFormatError("云端分区清单更新时间无效。") from exc
    if parsed.tzinfo is None:
        raise SnapshotFormatError("云端分区清单更新时间缺少时区。")
    return value


def snapshot_manifest_bytes(manifest: dict[str, Any]) -> bytes:
    if not _valid_manifest(manifest):
        raise SnapshotFormatError("无法生成有效的云端分区清单。")
    return _canonical(manifest)


def materialize_snapshot_bundle(manifest: dict[str, Any], file_blobs: dict[str, bytes]) -> bytes:
    """Rebuild a validated legacy restore bundle from versioned repository files."""
    from .github_sync import MAX_UNPACKED_BUNDLE_BYTES

    if not _valid_manifest(manifest):
        raise SnapshotFormatError("云端分区清单无效；本机数据保持不变。")
    entries = manifest["files"]
    if set(file_blobs) != set(entries):
        raise SnapshotFormatError("云端分区文件不完整；本机数据保持不变。")
    extracted: dict[str, bytes] = {}
    total = 0
    for path, descriptor in entries.items():
        safe = _safe_relative_path(path)
        if not (safe.startswith("data/") or safe == "meta/schema.json"
                or safe == "payment/methods.json" or safe.startswith("skills/")
                or safe.startswith("receipts/")):
            raise SnapshotFormatError("云端分区包含不支持的文件路径。")
        body = file_blobs[path]
        if not isinstance(body, bytes) or len(body) != descriptor["size"]:
            raise SnapshotFormatError("云端分区文件长度不匹配；本机数据保持不变。")
        if hashlib.sha256(body).hexdigest() != descriptor["sha256"]:
            raise SnapshotFormatError("云端分区文件校验失败；本机数据保持不变。")
        total += len(body)
        if total > MAX_UNPACKED_BUNDLE_BYTES:
            raise SnapshotFormatError("云端分区内容超过 512 MB；本机数据保持不变。")
        extracted[safe] = body

    schema_raw = extracted.get("meta/schema.json")
    if not schema_raw:
        raise SnapshotFormatError("云端分区备份缺少数据库结构说明。")
    try:
        schema = json.loads(schema_raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SnapshotFormatError("云端数据库结构说明无效。") from exc
    if not isinstance(schema, dict):
        raise SnapshotFormatError("云端数据库结构说明无效。")

    with tempfile.TemporaryDirectory(prefix="household-folder-materialize-") as temp_name:
        root = Path(temp_name)
        ledger_path = root / "ledger.sqlite3"
        db = Database(ledger_path)
        try:
            db.initialize(seed_default_settings=False)
            connection = db.connection
            connection.execute("PRAGMA foreign_keys=OFF")
            known = {str(row[0]) for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ) if not str(row[0]).startswith("web_")}
            if any(not isinstance(table, str) or not _TABLE_NAME.fullmatch(table) or table not in known for table in schema):
                raise SnapshotFormatError("备份所需的账本结构与当前版本不兼容；本机数据保持不变。")
            for table, definition in schema.items():
                columns = definition.get("columns") if isinstance(definition, dict) else None
                if not isinstance(columns, list) or not columns or any(not isinstance(c, str) for c in columns):
                    raise SnapshotFormatError("云端数据库结构说明无效。")
                current_columns = {str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")')}
                if not set(columns).issubset(current_columns):
                    raise SnapshotFormatError("备份使用了较新版本的账本结构；请先更新网页版再恢复。")
            connection.execute("BEGIN")
            for table in known:
                connection.execute(f'DELETE FROM "{table}"')
            for path, raw in sorted(extracted.items()):
                if not path.startswith("data/") or not path.endswith(".json"):
                    continue
                try:
                    row = json.loads(raw.decode("utf-8"))
                except UnicodeDecodeError as exc:
                    raise SnapshotFormatError("云端账目记录不是有效 UTF-8。") from exc
                except json.JSONDecodeError as exc:
                    raise SnapshotFormatError("云端账目记录 JSON 无效。") from exc
                table = row.get("table") if isinstance(row, dict) else None
                values = row.get("row") if isinstance(row, dict) else None
                if table not in schema or not isinstance(values, dict):
                    raise SnapshotFormatError("云端账目记录内容无效。")
                columns = list(values)
                if not columns or any(column not in schema[table]["columns"] for column in columns):
                    raise SnapshotFormatError("云端账目记录字段与清单不一致。")
                quoted = ",".join('"' + column.replace('"', '""') + '"' for column in columns)
                marks = ",".join("?" for _ in columns)
                decoded = [_decode_sql_value(values[column]) for column in columns]
                connection.execute(f'INSERT INTO "{table}" ({quoted}) VALUES ({marks})', decoded)
            connection.commit()
            connection.execute("PRAGMA foreign_keys=ON")
            violations = connection.execute("PRAGMA foreign_key_check").fetchall()
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
            if violations or not integrity or integrity[0] != "ok":
                raise SnapshotFormatError("云端账本完整性校验失败；本机数据保持不变。")
            db.close()
        except BaseException:
            try:
                db.connection.rollback()
            except Exception:
                pass
            db.close()
            raise

        manifest_v3 = {
            "version": 3,
            "created_at": manifest["created_at"],
            "scope": manifest["scope"],
            "includes": {
                "ledger": True,
                "payment_rules": "payment/methods.json" in extracted,
                "bookkeeping_skill": "skills/bookkeeping.md" in extracted,
                "food_health_skill": "skills/food_health.md" in extracted,
                "receipt_images": any(path.startswith("receipts/") for path in extracted),
            },
            "excludes": manifest.get("excludes", []),
        }
        output = BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            archive.write(ledger_path, "ledger.sqlite3")
            archive.writestr("manifest.json", json.dumps(manifest_v3, ensure_ascii=False).encode("utf-8"))
            if "payment/methods.json" in extracted:
                archive.writestr("payment_prompts.json", extracted["payment/methods.json"])
            for source, target in (("skills/bookkeeping.md", "skills/bookkeeping.md"), ("skills/food_health.md", "skills/food_health.md")):
                if source in extracted:
                    archive.writestr(target, extracted[source])
            for path, body in extracted.items():
                if path.startswith("receipts/"):
                    archive.writestr(f"receipt_images/{path[len('receipts/'):]}", body)
        body = output.getvalue()
        if len(body) > MAX_UNPACKED_BUNDLE_BYTES:
            raise SnapshotFormatError("生成的兼容恢复包超过 512 MB。")
        return body


def snapshot_from_repository_archive(archive_body: bytes, expected_revision: str) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Read only our snapshot directory from a provider's repository ZIP archive."""
    if len(archive_body) > MAX_ARCHIVE_BYTES:
        raise SnapshotFormatError("云端目录备份压缩包超过安全大小限制。")
    try:
        archive = zipfile.ZipFile(BytesIO(archive_body))
    except (zipfile.BadZipFile, OSError) as exc:
        raise SnapshotFormatError("云端目录备份压缩包损坏。") from exc
    with archive:
        manifest_members = [
            item for item in archive.infolist()
            if not item.is_dir() and item.filename.replace("\\", "/").endswith(f"/{SNAPSHOT_ROOT}/manifest.json")
        ]
        if len(manifest_members) != 1:
            raise SnapshotFormatError("压缩包中找不到唯一的分区备份清单。")
        if manifest_members[0].file_size > 4_000_000:
            raise SnapshotFormatError("云端分区清单超过安全大小限制。")
        prefix = manifest_members[0].filename.replace("\\", "/")[:-len("manifest.json")]
        manifest_payload = archive.read(manifest_members[0])
        manifest = parse_manifest(manifest_payload)
        manifest_sha = hashlib.sha1(f"blob {len(manifest_payload)}\0".encode("ascii") + manifest_payload).hexdigest()
        if expected_revision and manifest_sha != expected_revision:
            raise SnapshotFormatError("下载期间云端目录版本发生变化，请重新恢复。")
        total = 0
        blobs: dict[str, bytes] = {}
        for relative, descriptor in manifest["files"].items():
            safe = _safe_relative_path(relative)
            member_name = prefix + safe
            try:
                info = archive.getinfo(member_name)
            except KeyError as exc:
                raise SnapshotFormatError("云端目录备份缺少数据文件。") from exc
            total += info.file_size
            if total > MAX_SNAPSHOT_UNPACKED_BYTES:
                raise SnapshotFormatError("云端目录备份超过 512 MB。")
            blobs[safe] = archive.read(info)
    return manifest, blobs


def materialize_snapshot_delta(
    manifest: dict[str, Any],
    local_files: dict[str, bytes],
    fetch_file,
) -> bytes:
    """Build a restore bundle, fetching only snapshot objects changed remotely."""
    if not _valid_manifest(manifest) or not isinstance(local_files, dict):
        raise SnapshotFormatError("增量恢复所需的快照信息无效；本机数据保持不变。")
    merged: dict[str, bytes] = {}
    total = 0
    for path, descriptor in manifest["files"].items():
        safe = _safe_relative_path(path)
        body = local_files.get(safe)
        if (not isinstance(body, bytes) or len(body) != descriptor["size"]
                or hashlib.sha256(body).hexdigest() != descriptor["sha256"]):
            body = fetch_file(safe, descriptor)
        if (not isinstance(body, bytes) or len(body) != descriptor["size"]
                or hashlib.sha256(body).hexdigest() != descriptor["sha256"]):
            raise SnapshotFormatError("云端分区文件校验失败；本机数据保持不变。")
        total += len(body)
        if total > MAX_SNAPSHOT_UNPACKED_BYTES:
            raise SnapshotFormatError("云端分区内容超过 512 MB；本机数据保持不变。")
        merged[safe] = body
    return materialize_snapshot_bundle(manifest, merged)
