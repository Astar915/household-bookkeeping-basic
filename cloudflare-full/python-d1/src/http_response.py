"""Small Fetch Response helpers that preserve multiple Set-Cookie headers."""
from __future__ import annotations

import json

from js import Headers, Object, Response as JSResponse, Uint8Array
from pyodide.ffi import to_js


def json_response(value, *, status=200, headers=()):
    response_headers = Headers.new()
    response_headers.set("content-type", "application/json; charset=utf-8")
    response_headers.set("cache-control", "no-store")
    response_headers.set("x-content-type-options", "nosniff")
    response_headers.set("referrer-policy", "no-referrer")
    response_headers.set("x-frame-options", "DENY")
    response_headers.set("cross-origin-resource-policy", "same-origin")
    for name, content in headers:
        response_headers.append(name, content)
    options = to_js({"status": status, "headers": response_headers}, dict_converter=Object.fromEntries)
    body = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return JSResponse.new(body, options)


def bytes_response(body: bytes, content_type: str, *, status=200, headers=()):
    """Return a binary body without expanding it to a Python list of bytes."""
    response_headers = Headers.new()
    response_headers.set("content-type", content_type)
    response_headers.set("cache-control", "no-store")
    response_headers.set("x-content-type-options", "nosniff")
    response_headers.set("referrer-policy", "no-referrer")
    response_headers.set("x-frame-options", "DENY")
    response_headers.set("cross-origin-resource-policy", "same-origin")
    for name, content in headers:
        response_headers.append(name, content)
    options = to_js({"status": status, "headers": response_headers}, dict_converter=Object.fromEntries)
    # A Python bytes object passed directly to the JS constructor becomes its
    # repr string in this runtime; explicitly wrap it as a binary typed array.
    return JSResponse.new(Uint8Array.new(body), options)


def redirect_response(location: str, *, headers=()):
    response_headers = Headers.new()
    response_headers.set("location", location)
    response_headers.set("cache-control", "no-store")
    response_headers.set("referrer-policy", "no-referrer")
    response_headers.set("x-content-type-options", "nosniff")
    for name, content in headers:
        response_headers.append(name, content)
    options = to_js({"status": 302, "headers": response_headers}, dict_converter=Object.fromEntries)
    return JSResponse.new(None, options)


def clear_flow_cookie(*, secure: bool):
    suffix = "; Secure" if secure else ""
    return "hh_gh_login=; Path=/api/auth/github; Max-Age=0; HttpOnly; SameSite=Strict" + suffix


def set_flow_cookie(value: str, duration: int, *, secure: bool):
    suffix = "; Secure" if secure else ""
    return (
        f"hh_gh_login={value}; Path=/api/auth/github; Max-Age={duration}; "
        f"HttpOnly; SameSite=Strict{suffix}"
    )


def clear_gitee_flow_cookie(*, secure: bool):
    suffix = "; Secure" if secure else ""
    return "hh_gitee_oauth=; Path=/api/auth/gitee/callback; Max-Age=0; HttpOnly; SameSite=Lax" + suffix


def set_gitee_flow_cookie(value: str, duration: int, *, secure: bool):
    suffix = "; Secure" if secure else ""
    return (
        f"hh_gitee_oauth={value}; Path=/api/auth/gitee/callback; Max-Age={duration}; "
        f"HttpOnly; SameSite=Lax{suffix}"
    )
