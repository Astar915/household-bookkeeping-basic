"""AES-GCM credential encryption using the Workers Web Crypto runtime."""
from __future__ import annotations

import base64
import hashlib

from js import Object, Uint8Array, crypto
from pyodide.ffi import to_js


def _js(value):
    return to_js(value, dict_converter=Object.fromEntries)


def _buffer(data: bytes):
    # Pyodide converts Python's buffer protocol directly to a JS TypedArray.
    # Copying each byte through a Python loop exceeds the Workers Free CPU
    # budget for normal encrypted backup chunks.
    return to_js(data).buffer


def _bytes(buffer) -> bytes:
    view = Uint8Array.new(buffer)
    # to_py() performs the typed-array transfer in native buffer code instead
    # of a Python-level per-byte generator (which is especially costly for a
    # downloaded ledger archive).
    return view.to_py().tobytes()


def _key(env_secret: str, purpose: str) -> bytes:
    if not env_secret:
        raise RuntimeError("未配置云端凭据加密密钥。")
    root = env_secret.encode("utf-8")
    return hashlib.sha256(b"household-bookkeeping/python-d1/v1\0" + purpose.encode("utf-8") + b"\0" + root).digest()


async def encrypt_text(value: str, env_secret: str, purpose: str) -> str:
    key_bytes = _key(env_secret, purpose)
    key = await crypto.subtle.importKey(
        "raw", _buffer(key_bytes), _js({"name": "AES-GCM"}), False, _js(["encrypt"])
    )
    iv = Uint8Array.new(12)
    crypto.getRandomValues(iv)
    ciphertext = await crypto.subtle.encrypt(
        _js({"name": "AES-GCM", "iv": iv}), key, _buffer(value.encode("utf-8"))
    )
    return "v1." + base64.urlsafe_b64encode(_bytes(iv.buffer) + _bytes(ciphertext)).decode("ascii")


async def decrypt_text(value: str, env_secret: str, purpose: str) -> str:
    if not value.startswith("v1."):
        raise ValueError("加密凭据版本无效。")
    packed = base64.urlsafe_b64decode(value[3:].encode("ascii"))
    if len(packed) < 12 + 16:
        raise ValueError("加密凭据内容不完整。")
    iv, ciphertext = packed[:12], packed[12:]
    key = await crypto.subtle.importKey(
        "raw", _buffer(_key(env_secret, purpose)), _js({"name": "AES-GCM"}), False, _js(["decrypt"])
    )
    plaintext = await crypto.subtle.decrypt(_js({"name": "AES-GCM", "iv": _buffer(iv)}), key, _buffer(ciphertext))
    return _bytes(plaintext).decode("utf-8")
