"""subscription fetching and parsing."""
from __future__ import annotations

import platform
import urllib.error
import urllib.request

from . import storage
from .errors import NetworkError, ParseError
from .parsers import b64decode_safe, _looks_textual, parse_uri

KNOWN_HEADERS = [
    "profile-title",
    "profile-update-interval",
    "subscription-userinfo",
    "support-url",
    "profile-web-page-url",
    "announce",
    "socks-auth-mode",
    "http-auth-mode",
    "routing-enable",
    "new-url",
    "new-domain",
    "fallback-url",
]


def _parse_userinfo(value: str) -> dict:
    result = {}
    for part in value.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        k, _, v = part.partition("=")
        result[k.strip()] = v.strip()
    return result


def _maybe_b64(value: str) -> str:
    decoded = b64decode_safe(value)
    return decoded if (decoded and _looks_textual(decoded)) else value


def _request_headers(user_agent: str) -> dict:
    os_name = platform.system() or "Unknown"
    return {
        "User-Agent": user_agent,
        "X-HWID": storage.device_hwid(),
        "X-Device-OS": os_name,
        "X-Ver-OS": platform.version() or "unknown",
        "X-Device-Model": (
            "Windows PC" if os_name == "Windows" else (platform.machine() or "Unknown")
        ),
    }


def extract_meta_from_headers(headers: dict) -> dict:
    lower_headers = {k.lower(): v for k, v in headers.items()}
    meta = {}
    for name in KNOWN_HEADERS:
        if name in lower_headers:
            meta[name] = lower_headers[name]
    if "subscription-userinfo" in meta:
        meta["subscription-userinfo"] = _parse_userinfo(meta["subscription-userinfo"])
    return meta


def _parse_meta_line(line: str) -> dict:
    """A subscription-body line like '#profile-title: Name VPN'."""
    body = line.lstrip("#").strip()
    if ":" in body:
        k, _, v = body.partition(":")
    elif "=" in body:
        k, _, v = body.partition("=")
    else:
        return {}
    k = k.strip().lower()
    v = v.strip()
    if k not in KNOWN_HEADERS:
        return {}
    if k == "subscription-userinfo":
        return {k: _parse_userinfo(v)}
    return {k: v}


def fetch_subscription(url: str, user_agent: str = "xrayctl/1.0", timeout: int = 15):
    """Returns (servers: list[Server], meta: dict)."""
    try:
        req = urllib.request.Request(url, headers=_request_headers(user_agent))
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            headers = dict(resp.headers.items())
    except (urllib.error.URLError, ValueError) as e:
        raise NetworkError(f"failed to fetch subscription {url}: {e}")

    meta = extract_meta_from_headers(headers)
    text = raw.decode("utf-8", errors="replace")

    body = text
    decoded = b64decode_safe(text.strip())
    if decoded and "://" in decoded:
        body = decoded

    servers = []
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            meta.update(_parse_meta_line(line))
            continue
        try:
            servers.append(parse_uri(line))
        except ParseError:
            continue

    if "profile-title" in meta:
        meta["profile-title"] = _maybe_b64(meta["profile-title"])
    if "announce" in meta:
        meta["announce"] = _maybe_b64(meta["announce"])

    return servers, meta
