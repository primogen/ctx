"""HTTP trust and token helpers for ctx-monitor."""

from __future__ import annotations

import ipaddress
from http.cookies import CookieError, SimpleCookie
from urllib.parse import urlsplit


MAX_POST_BODY_BYTES = 64 * 1024
READ_TOKEN_COOKIE = "ctx_monitor_read_token"


def host_allows_mutations(host: str) -> bool:
    normalized = (host or "").strip().strip("[]").rstrip(".").lower()
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def request_host_name(host_header: str) -> str:
    value = (host_header or "").strip()
    if not value:
        return ""
    if value.startswith("["):
        end = value.find("]")
        return value[1:end].rstrip(".").lower() if end != -1 else ""
    return value.rsplit(":", 1)[0].rstrip(".").lower()


def origin_host_name(origin: str) -> str:
    try:
        parsed = urlsplit(origin)
    except ValueError:
        return ""
    if parsed.scheme not in {"http", "https"}:
        return ""
    return (parsed.hostname or "").rstrip(".").lower()


def read_token_cookie(cookie_header: str) -> str:
    if not cookie_header:
        return ""
    try:
        cookie = SimpleCookie()
        cookie.load(cookie_header)
    except CookieError:
        return ""
    morsel = cookie.get(READ_TOKEN_COOKIE)
    return morsel.value if morsel is not None else ""
