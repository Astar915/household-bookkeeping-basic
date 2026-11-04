"""Encrypted durable payloads and replayable external model calls for Workflows."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import uuid
from datetime import datetime, timezone
from email.message import Message
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request

JOB_CHUNK_BYTES = 192 * 1024
JOB_BATCH_CHUNKS = 8
MAX_MODEL_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_CLOUD_BUNDLE_BYTES = 60_000_000
MAX_FX_RESPONSE_BYTES = 256_000
HTTP_RECORD_GENERATION_PREFIX = "http1_"
MAX_HTTP_METADATA_BYTES = 16 * 1024
REPLAY_RESPONSE_HEADERS = frozenset({"etag", "last-modified", "content-type", "retry-after"})


def safe_response_headers(headers) -> dict[str, str]:
    """Persist only response metadata needed for HTTP replay; exclude cookies/auth."""
    return {
        str(key).lower(): str(value)
        for key, value in (headers or {}).items()
        if str(key).lower() in REPLAY_RESPONSE_HEADERS
        and len(str(value)) <= 2048 and "\r" not in str(value) and "\n" not in str(value)
    }


def encode_response_record(body: bytes, headers=None) -> bytes:
    metadata = json.dumps(safe_response_headers(headers), separators=(",", ":")).encode("utf-8")
    if len(metadata) > MAX_HTTP_METADATA_BYTES:
        raise ValueError("云端响应元数据超过安全上限。")
    return len(metadata).to_bytes(4, "big") + metadata + body


def decode_response_record(record: bytes, generation: str) -> tuple[bytes, dict[str, str]]:
    # Legacy generations contain the raw response body. The opaque generation
    # prefix versions the encrypted representation without a database migration.
    if not generation.startswith(HTTP_RECORD_GENERATION_PREFIX):
        return record, {}
    size = int.from_bytes(record[:4], "big")
    if len(record) < 4 or size > MAX_HTTP_METADATA_BYTES or len(record) < 4 + size:
        raise ValueError("已保存的云端响应元数据不完整。")
    metadata = json.loads(record[4:4 + size])
    if not isinstance(metadata, dict):
        raise ValueError("已保存的云端响应元数据格式无效。")
    return record[4 + size:], safe_response_headers(metadata)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _field(row: Any, name: str):
    return row[name] if isinstance(row, dict) else getattr(row, name)


def canonical_payload(action: str, data: dict[str, Any]) -> bytes:
    return json.dumps(
        [action, data], sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def request_envelope(request: Request, call_index: int, ledger_revision: str) -> dict[str, Any]:
    url = request.full_url
    method = request.get_method().upper()
    body = request.data or b""
    headers = dict(request.header_items())
    # Keep neither API credentials nor prompt text in durable rows or logs.
    # Hash the auth header too: if an API profile changes while a Workflow is
    # waiting for a model reply, a response from the old key must not be replayed
    # into a request made with the new configuration. Only the digest is stored.
    hashed_headers = json.dumps(
        sorted((str(name).lower(), str(value)) for name, value in headers.items()),
        ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8")
    request_hash = hashlib.sha256(
        method.encode("ascii") + b"\0" + url.encode("utf-8") + b"\0"
        + hashed_headers + b"\0" + body
    ).hexdigest()
    return {
        "url": url,
        "method": method,
        "headers": headers,
        "body": body,
        "requestHash": request_hash,
        "callIndex": call_index,
        "ledgerRevision": ledger_revision,
    }


class ModelRequestRequired(RuntimeError):
    """Signal a sync bookkeeping client that an async Worker fetch is required."""

    def __init__(self, envelope: dict[str, Any]):
        self.envelope = envelope
        super().__init__("需要继续执行云端模型请求。")


class _ReplayResponse:
    def __init__(self, body: bytes, status: int = 200, headers=None, url: str = ""):
        self._body = body
        self.status = self.code = status
        self.url = url
        self.headers = Message()
        for key, value in safe_response_headers(headers).items():
            self.headers[key] = value

    def getcode(self):
        return self.status

    def geturl(self):
        return self.url

    def info(self):
        return self.headers

    def getheader(self, name, default=None):
        return self.headers.get(name, default)

    def read(self, amount: int = -1) -> bytes:
        if amount is None or amount < 0:
            body, self._body = self._body, b""
            return body
        body, self._body = self._body[:amount], self._body[amount:]
        return body

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class ReplayOpener:
    """Replays completed responses, then yields one new request to the Workflow."""

    def __init__(self, replies: list[dict[str, Any]], ledger_revision: str):
        self.replies = replies
        self.ledger_revision = ledger_revision
        self.call_index = 0

    def __call__(self, request: Request, timeout: float | None = None):
        envelope = request_envelope(request, self.call_index, self.ledger_revision)
        if self.call_index >= len(self.replies):
            raise ModelRequestRequired(envelope)
        reply = self.replies[self.call_index]
        self.call_index += 1
        if reply.get("requestHash") != envelope["requestHash"]:
            raise RuntimeError("模型请求上下文已变化；为避免把旧结果用于新账本，本次操作已停止。")
        status = int(reply.get("status", 0))
        body = reply.get("body")
        if not isinstance(body, bytes):
            raise RuntimeError("已保存的模型响应无法读取；账本没有提交。")
        response = _ReplayResponse(body, status, reply.get("headers"), request.full_url)
        if status < 200 or status >= 300:
            raise HTTPError(request.full_url, status, "Cloud provider response", response.headers, io.BytesIO(body))
        return response


async def store_job_payload(database, env, user_id: str, operation_id: str,
                            action: str, data: dict[str, Any], payload_hash: str) -> None:
    from secret_crypto import encrypt_text

    raw = canonical_payload(action, data)
    if hashlib.sha256(raw).hexdigest() != payload_hash:
        raise ValueError("后台操作内容校验失败；账本没有被修改。")
    existing = await database.prepare(
        "SELECT payload_hash,action FROM app_job_payloads WHERE user_id=? AND operation_id=?"
    ).bind(user_id, operation_id).first()
    if existing is not None:
        if (str(_field(existing, "payload_hash")) != payload_hash
                or str(_field(existing, "action")) != action):
            raise ValueError("后台操作编号与已保存内容不一致。")
        return

    generation = uuid.uuid4().hex
    key = str(env.TOKEN_ENCRYPTION_KEY)
    chunks = [raw[offset:offset + JOB_CHUNK_BYTES] for offset in range(0, len(raw), JOB_CHUNK_BYTES)]
    statements = []
    for index, chunk in enumerate(chunks):
        ciphertext = await encrypt_text(
            base64.b64encode(chunk).decode("ascii"), key,
            f"job-payload:{user_id}:{operation_id}:{generation}:{index}",
        )
        statements.append(database.prepare(
            "INSERT INTO app_job_payload_chunks(user_id,operation_id,generation_id,chunk_index,ciphertext) "
            "VALUES(?,?,?,?,?)"
        ).bind(user_id, operation_id, generation, index, ciphertext))
    for offset in range(0, len(statements), JOB_BATCH_CHUNKS):
        await database.batch(statements[offset:offset + JOB_BATCH_CHUNKS])
    await database.prepare(
        "INSERT INTO app_job_payloads(user_id,operation_id,action,payload_hash,generation_id,payload_bytes,chunk_count,created_at) "
        "VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(user_id,operation_id) DO NOTHING"
    ).bind(user_id, operation_id, action, payload_hash, generation, len(raw), len(chunks), _now()).run()
    selected = await database.prepare(
        "SELECT payload_hash,action FROM app_job_payloads WHERE user_id=? AND operation_id=?"
    ).bind(user_id, operation_id).first()
    if (selected is None or str(_field(selected, "payload_hash")) != payload_hash
            or str(_field(selected, "action")) != action):
        raise ValueError("后台操作内容保存冲突；账本没有被修改。")


async def store_prepared_agent_payload(database, env, user_id: str,
                                       prepare_operation_id: str,
                                       data: dict[str, Any], payload_hash: str) -> str:
    """Store a prepared Agent delta under a D1 job row with a valid FK parent."""
    operation_id = "prepared_" + prepare_operation_id
    now = _now()
    await database.prepare(
        "INSERT INTO app_jobs(user_id,operation_id,action,fingerprint,state,message,result_json,"
        "cancel_requested,created_at,updated_at) VALUES(?,?, 'prepared_agent_payload', ?, 'done', ?, '{}',0,?,?) "
        "ON CONFLICT(user_id,operation_id) DO NOTHING"
    ).bind(
        user_id, operation_id, payload_hash, "Internal prepared Agent payload", now, now,
    ).run()
    parent = await database.prepare(
        "SELECT action FROM app_jobs WHERE user_id=? AND operation_id=?"
    ).bind(user_id, operation_id).first()
    if parent is None or str(_field(parent, "action")) != "prepared_agent_payload":
        raise ValueError("Agent 待同步数据准备失败；账本没有被修改。")
    try:
        await store_job_payload(
            database, env, user_id, operation_id,
            "prepared_agent", data, payload_hash,
        )
    except Exception:
        try:
            await cleanup_prepared_agent_payload(database, user_id, operation_id)
        except Exception:
            pass
        raise
    return operation_id


async def cleanup_prepared_agent_payload(database, user_id: str,
                                         payload_operation_id: str) -> None:
    """Delete the private prepared payload and its synthetic FK parent."""
    await database.prepare(
        "DELETE FROM app_jobs WHERE user_id=? AND operation_id=? AND action='prepared_agent_payload'"
    ).bind(user_id, payload_operation_id).run()


async def load_job_payload(database, env, user_id: str, operation_id: str,
                           expected_hash: str, expected_action: str):
    from secret_crypto import decrypt_text

    row = await database.prepare(
        "SELECT action,payload_hash,generation_id,payload_bytes,chunk_count FROM app_job_payloads "
        "WHERE user_id=? AND operation_id=?"
    ).bind(user_id, operation_id).first()
    if row is None:
        raise ValueError("后台操作数据已过期，请重新提交。")
    action = str(_field(row, "action"))
    payload_hash = str(_field(row, "payload_hash"))
    generation = str(_field(row, "generation_id"))
    expected_bytes = int(_field(row, "payload_bytes"))
    chunk_count = int(_field(row, "chunk_count"))
    if action != expected_action or payload_hash != expected_hash:
        raise ValueError("后台操作校验失败；账本没有被修改。")
    result = await database.prepare(
        "SELECT chunk_index,ciphertext FROM app_job_payload_chunks "
        "WHERE user_id=? AND operation_id=? AND generation_id=? ORDER BY chunk_index"
    ).bind(user_id, operation_id, generation).run()
    rows = list(result.get("results", []) if isinstance(result, dict) else getattr(result, "results", []) or [])
    if len(rows) != chunk_count:
        raise ValueError("后台操作数据暂时不完整，请重试。")
    pieces = []
    key = str(env.TOKEN_ENCRYPTION_KEY)
    for expected_index, chunk_row in enumerate(rows):
        index = int(_field(chunk_row, "chunk_index"))
        if index != expected_index:
            raise ValueError("后台操作数据顺序校验失败。")
        encoded = await decrypt_text(
            str(_field(chunk_row, "ciphertext")), key,
            f"job-payload:{user_id}:{operation_id}:{generation}:{index}",
        )
        pieces.append(base64.b64decode(encoded, validate=True))
    raw = b"".join(pieces)
    if len(raw) != expected_bytes or hashlib.sha256(raw).hexdigest() != payload_hash:
        raise ValueError("后台操作数据完整性校验失败。")
    decoded = json.loads(raw.decode("utf-8"))
    if (not isinstance(decoded, list) or len(decoded) != 2 or decoded[0] != action
            or not isinstance(decoded[1], dict)):
        raise ValueError("后台操作数据格式无效。")
    return action, decoded[1]


async def load_model_replies(database, env, user_id: str, operation_id: str):
    from secret_crypto import decrypt_text

    result = await database.prepare(
        "SELECT call_index,request_hash,ledger_revision,generation_id,response_status,response_bytes,chunk_count "
        "FROM app_job_model_calls WHERE user_id=? AND operation_id=? ORDER BY call_index"
    ).bind(user_id, operation_id).run()
    rows = list(result.get("results", []) if isinstance(result, dict) else getattr(result, "results", []) or [])
    replies = []
    base_revision = None
    key = str(env.TOKEN_ENCRYPTION_KEY)
    for expected_index, row in enumerate(rows):
        index = int(_field(row, "call_index"))
        revision = str(_field(row, "ledger_revision"))
        if index != expected_index or (base_revision is not None and revision != base_revision):
            raise ValueError("模型请求记录顺序或账本版本校验失败。")
        base_revision = revision
        generation = str(_field(row, "generation_id"))
        response = await database.prepare(
            "SELECT chunk_index,ciphertext FROM app_job_model_call_chunks "
            "WHERE user_id=? AND operation_id=? AND call_index=? AND generation_id=? ORDER BY chunk_index"
        ).bind(user_id, operation_id, index, generation).run()
        pieces = list(response.get("results", []) if isinstance(response, dict) else getattr(response, "results", []) or [])
        count = int(_field(row, "chunk_count"))
        if len(pieces) != count:
            raise ValueError("已保存的模型响应不完整；账本没有提交。")
        body_parts = []
        for chunk_index, chunk_row in enumerate(pieces):
            if int(_field(chunk_row, "chunk_index")) != chunk_index:
                raise ValueError("已保存的模型响应顺序校验失败。")
            encoded = await decrypt_text(
                str(_field(chunk_row, "ciphertext")), key,
                f"job-model:{user_id}:{operation_id}:{index}:{generation}:{chunk_index}",
            )
            body_parts.append(base64.b64decode(encoded, validate=True))
        body, headers = decode_response_record(b"".join(body_parts), generation)
        if len(body) != int(_field(row, "response_bytes")):
            raise ValueError("已保存的模型响应大小校验失败。")
        replies.append({
            "requestHash": str(_field(row, "request_hash")),
            "status": int(_field(row, "response_status")),
            "body": body,
            "headers": headers,
        })
    return replies, base_revision


async def save_model_response(database, env, user_id: str, operation_id: str,
                              envelope: dict[str, Any], status: int, body: bytes,
                              *, max_bytes: int = MAX_MODEL_RESPONSE_BYTES,
                              response_headers=None) -> None:
    from secret_crypto import encrypt_text

    if len(body) > max_bytes:
        raise ValueError("云端服务响应超过安全上限，本次没有写入账本。")
    index = int(envelope["callIndex"])
    request_hash = str(envelope["requestHash"])
    revision = str(envelope["ledgerRevision"])
    existing = await database.prepare(
        "SELECT request_hash,ledger_revision,generation_id,chunk_count FROM app_job_model_calls "
        "WHERE user_id=? AND operation_id=? AND call_index=?"
    ).bind(user_id, operation_id, index).first()
    if existing is not None:
        if (str(_field(existing, "request_hash")) != request_hash
                or str(_field(existing, "ledger_revision")) != revision):
            raise ValueError("模型响应与当前账本版本不匹配。")
        saved_chunks = await database.prepare(
            "SELECT COUNT(*) AS chunk_count FROM app_job_model_call_chunks "
            "WHERE user_id=? AND operation_id=? AND call_index=? AND generation_id=?"
        ).bind(user_id, operation_id, index, str(_field(existing, "generation_id"))).first()
        if int(_field(saved_chunks, "chunk_count")) == int(_field(existing, "chunk_count")):
            return
        # A worker can be interrupted between bounded chunk batches. Remove
        # that incomplete response (cascade deletes its chunks) and rewrite it.
        await database.prepare(
            "DELETE FROM app_job_model_calls WHERE user_id=? AND operation_id=? AND call_index=?"
        ).bind(user_id, operation_id, index).run()

    generation = HTTP_RECORD_GENERATION_PREFIX + uuid.uuid4().hex
    key = str(env.TOKEN_ENCRYPTION_KEY)
    record = encode_response_record(body, response_headers)
    chunks = [record[offset:offset + JOB_CHUNK_BYTES] for offset in range(0, len(record), JOB_CHUNK_BYTES)]
    if not chunks:
        chunks = [b""]
    statements = []
    for chunk_index, chunk in enumerate(chunks):
        ciphertext = await encrypt_text(
            base64.b64encode(chunk).decode("ascii"), key,
            f"job-model:{user_id}:{operation_id}:{index}:{generation}:{chunk_index}",
        )
        statements.append(database.prepare(
            "INSERT INTO app_job_model_call_chunks(user_id,operation_id,call_index,generation_id,chunk_index,ciphertext) "
            "VALUES(?,?,?,?,?,?)"
        ).bind(user_id, operation_id, index, generation, chunk_index, ciphertext))
    # The chunks have a foreign key to this parent row, so commit the response
    # descriptor before inserting them in bounded D1 batches.
    await database.prepare(
        "INSERT INTO app_job_model_calls(user_id,operation_id,call_index,request_hash,ledger_revision,generation_id,"
        "response_status,response_bytes,chunk_count,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)"
    ).bind(user_id, operation_id, index, request_hash, revision, generation,
          int(status), len(body), len(chunks), _now()).run()
    for offset in range(0, len(statements), JOB_BATCH_CHUNKS):
        await database.batch(statements[offset:offset + JOB_BATCH_CHUNKS])
    chosen = await database.prepare(
        "SELECT request_hash,ledger_revision FROM app_job_model_calls "
        "WHERE user_id=? AND operation_id=? AND call_index=?"
    ).bind(user_id, operation_id, index).first()
    if (chosen is None or str(_field(chosen, "request_hash")) != request_hash
            or str(_field(chosen, "ledger_revision")) != revision):
        raise ValueError("模型响应保存冲突；账本没有被修改。")


async def cleanup_job_private_state(database, user_id: str, operation_id: str) -> None:
    await database.batch([
        database.prepare("DELETE FROM app_job_model_call_chunks WHERE user_id=? AND operation_id=?")
        .bind(user_id, operation_id),
        database.prepare("DELETE FROM app_job_model_calls WHERE user_id=? AND operation_id=?")
        .bind(user_id, operation_id),
        database.prepare("DELETE FROM app_job_payload_chunks WHERE user_id=? AND operation_id=?")
        .bind(user_id, operation_id),
        database.prepare("DELETE FROM app_job_payloads WHERE user_id=? AND operation_id=?")
        .bind(user_id, operation_id),
    ])
