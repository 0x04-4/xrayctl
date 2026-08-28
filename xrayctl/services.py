"""application service layer."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from . import core, storage
from .deeplink import parse_happ_link
from .errors import NetworkError, NotFoundError, ParseError, UsageError
from .models import Server, Settings, Subscription
from .netutil import ping_all, tcp_ping
from .parsers import build_uri, import_links_blob, parse_json_text, parse_uri
from .routing import profile_from_json
from .subscriptions import fetch_subscription


def _read_file_text(path: str) -> str:
    """Read a text file and convert filesystem errors to usage errors."""
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        raise UsageError(f"file not found: {path}")
    except OSError as e:
        raise UsageError(f"could not read {path}: {e}")




def _resolve(items: list, ref: str, kind: str):
    ref = str(ref).strip()
    if not ref:
        raise NotFoundError(f"no such {kind}: {ref}")
    for item in items:
        if item.id == ref:
            return item
    if ref.isdigit():
        index = int(ref) - 1
        if 0 <= index < len(items):
            return items[index]
    matches = [item for item in items if item.id.lower().startswith(ref.lower())]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise NotFoundError(f"ambiguous {kind}: {ref}")
    raise NotFoundError(f"no such {kind}: {ref}")


def list_servers() -> list:
    return storage.servers.all()


def get_server(server_id: str) -> Server:
    return _resolve(storage.servers.all(), server_id, "server")


def add_server_from_uri(uri: str) -> Server:
    server = parse_uri(uri)
    storage.servers.save(server)
    return server


def add_server_from_file(path: str) -> list:
    text = _read_file_text(path)
    servers = import_links_blob(text, remarks_hint=Path(path).stem)
    for s in servers:
        storage.servers.save(s)
    return servers


def add_server_from_json_file(path: str) -> Server:
    text = _read_file_text(path)
    server = parse_json_text(text, remarks=Path(path).stem)
    storage.servers.save(server)
    return server


def import_clipboard() -> list:
    text = _read_clipboard()
    servers = import_links_blob(text)
    for s in servers:
        storage.servers.save(s)
    return servers


def _read_clipboard() -> str:
    if sys.platform == "win32":
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode != 0:
            raise UsageError(f"could not read clipboard: {out.stderr.strip()}")
        return out.stdout
    for cmd in (["xclip", "-selection", "clipboard", "-o"], ["pbpaste"]):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if out.returncode == 0:
                return out.stdout
        except FileNotFoundError:
            continue
    raise UsageError("no clipboard tool found for this platform")


def rename_server(server_id: str, name: str) -> Server:
    server = get_server(server_id)
    server.remarks = name
    server.updated_at = time.time()
    storage.servers.save(server)
    return server


def remove_server(server_id: str) -> None:
    server = get_server(server_id)
    storage.servers.delete(server.id)


def export_server(server_id: str) -> str:
    return build_uri(get_server(server_id))




def list_subscriptions() -> list:
    return storage.subscriptions.all()


def get_subscription(sub_id: str) -> Subscription:
    return _resolve(storage.subscriptions.all(), sub_id, "subscription")


def add_subscription(url: str) -> Subscription:
    if url.startswith("happ://"):
        parse_happ_link(url)
        raise ParseError(f"not a fetchable subscription URL: {url}")
    settings = storage.load_settings()
    sub = Subscription(url=url, user_agent=settings.subscription_user_agent)
    _refresh_subscription(sub)
    storage.subscriptions.save(sub)
    return sub


_FALLBACK_USER_AGENTS = ["v2rayTun", "v2rayNG", "Happ", "clash-verge", "sing-box", "NekoBox", "Shadowrocket"]


def _looks_blocked(servers: list) -> bool:
    """Heuristic for a panel's 'unsupported client' placeholder response:
    every entry point at 0.0.0.0 or a dummy port instead of a real server."""
    if not servers:
        return False
    return all((s.address in ("0.0.0.0", "") or s.port in (0, 1)) for s in servers)


def _fetch_with_fallback_ua(sub: Subscription):
    servers, meta = fetch_subscription(sub.url, user_agent=sub.user_agent)
    if not _looks_blocked(servers):
        return servers, meta
    for ua in _FALLBACK_USER_AGENTS:
        if ua == sub.user_agent:
            continue
        try:
            candidate_servers, candidate_meta = fetch_subscription(sub.url, user_agent=ua)
        except NetworkError:
            continue
        if candidate_servers and not _looks_blocked(candidate_servers):
            sub.user_agent = ua
            return candidate_servers, candidate_meta
    return servers, meta


def _refresh_subscription(sub: Subscription) -> None:
    servers, meta = _fetch_with_fallback_ua(sub)
    for old in storage.servers.all():
        if old.subscription_id == sub.id:
            storage.servers.delete(old.id)
    for s in servers:
        s.subscription_id = sub.id
        storage.servers.save(s)
    sub.servers = [s.id for s in servers]
    sub.title = meta.get("profile-title", sub.title)
    sub.support_url = meta.get("support-url", sub.support_url)
    sub.web_page_url = meta.get("profile-web-page-url", sub.web_page_url)
    sub.announce = meta.get("announce", sub.announce)
    if "profile-update-interval" in meta:
        try:
            sub.update_interval_hours = int(meta["profile-update-interval"])
        except ValueError:
            pass
    if "subscription-userinfo" in meta:
        sub.userinfo = meta["subscription-userinfo"]
    sub.last_updated = time.time()


def update_subscription(sub_id: str) -> Subscription:
    sub = get_subscription(sub_id)
    _refresh_subscription(sub)
    storage.subscriptions.save(sub)
    return sub


def update_all_subscriptions() -> list:
    updated = []
    for sub in storage.subscriptions.all():
        _refresh_subscription(sub)
        storage.subscriptions.save(sub)
        updated.append(sub)
    return updated


def remove_subscription(sub_id: str) -> None:
    sub = get_subscription(sub_id)
    storage.subscriptions.delete(sub.id)
    for s in storage.servers.all():
        if s.subscription_id == sub_id:
            storage.servers.delete(s.id)




def list_routing_profiles() -> list:
    return storage.routing_profiles.all()


def get_routing_profile(profile_id: str):
    return _resolve(storage.routing_profiles.all(), profile_id, "routing profile")


def import_routing_link(text: str):
    """`xrayctl routing add "<happ://routing/...|file>"`. Returns the new
    profile, or None if the link was `happ://routing/off`."""
    text = text.strip()
    if text.startswith("happ://"):
        kind, payload = parse_happ_link(text)
        if kind == "routing_off":
            routing_off()
            return None
        activate = kind == "routing_onadd"
        profile = profile_from_json(payload, activate=activate)
    else:
        content = _read_file_text(text)
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as e:
            raise ParseError(f"{text}: invalid JSON routing profile ({e})")
        profile = profile_from_json(payload)
        activate = False
    storage.routing_profiles.save(profile)
    if activate:
        use_routing_profile(profile.id)
    return profile


def use_routing_profile(profile_id: str):
    target = get_routing_profile(profile_id)
    for p in storage.routing_profiles.all():
        if p.is_active and p.id != profile_id:
            p.is_active = False
            storage.routing_profiles.save(p)
    target.is_active = True
    storage.routing_profiles.save(target)
    settings = storage.load_settings()
    settings.active_routing_profile_id = target.id
    storage.save_settings(settings)
    return target


def routing_off():
    for p in storage.routing_profiles.all():
        if p.is_active:
            p.is_active = False
            storage.routing_profiles.save(p)
    settings = storage.load_settings()
    settings.active_routing_profile_id = None
    storage.save_settings(settings)


def get_active_routing_profile():
    settings = storage.load_settings()
    if not settings.active_routing_profile_id:
        return None
    return storage.routing_profiles.get(settings.active_routing_profile_id)




def get_settings() -> Settings:
    return storage.load_settings()


def use_server(server_id: str) -> Server:
    server = get_server(server_id)
    settings = storage.load_settings()
    settings.active_server_id = server.id
    storage.save_settings(settings)
    return server


def set_mode(mode: str) -> Settings:
    if mode not in ("proxy", "tun"):
        raise UsageError("mode must be 'proxy' or 'tun'")
    settings = storage.load_settings()
    settings.mode = mode
    storage.save_settings(settings)
    return settings


def connect(server_id: Optional[str] = None) -> dict:
    settings = storage.load_settings()
    target_id = server_id or settings.active_server_id
    if not target_id:
        raise UsageError("no server specified and no active server — run `xrayctl use <id>` first")
    server = get_server(target_id)
    profile = get_active_routing_profile()
    state = core.start(server, profile, settings)
    if server_id:
        settings.active_server_id = server.id
        storage.save_settings(settings)
    return state


def disconnect() -> None:
    core.stop()


def connection_status() -> dict:
    st = core.status()
    if st.get("connected") and st.get("server_id"):
        try:
            st["server_remarks"] = get_server(st["server_id"]).remarks
        except NotFoundError:
            pass
    return st




def ping_one(server_id: str) -> Optional[int]:
    server = get_server(server_id)
    latency = tcp_ping(server.address, server.port)
    server.latency_ms = latency
    storage.servers.save(server)
    return latency


def ping_all_servers() -> dict:
    servers = storage.servers.all()
    results = ping_all(servers)
    for s in servers:
        s.latency_ms = results.get(s.id)
        storage.servers.save(s)
    return results


def pick_best() -> Optional[Server]:
    servers = [s for s in storage.servers.all() if s.latency_ms is not None]
    if not servers:
        return None
    best = min(servers, key=lambda s: s.latency_ms)
    use_server(best.id)
    return best



_INT_KEYS = {"socks_port", "http_port"}
_BOOL_KEYS = {"auto_start"}


def config_set(key: str, value: str) -> Settings:
    settings = storage.load_settings()
    if not hasattr(settings, key):
        raise UsageError(f"unknown setting: {key}")
    if key in _INT_KEYS:
        try:
            value = int(value)
        except ValueError:
            raise UsageError(f"{key} must be an integer")
    elif key in _BOOL_KEYS:
        value = value.strip().lower() in ("1", "true", "yes", "on")
    setattr(settings, key, value)
    storage.save_settings(settings)
    return settings


def config_get(key: Optional[str] = None):
    settings = storage.load_settings()
    if key is None:
        return settings.to_dict()
    if not hasattr(settings, key):
        raise UsageError(f"unknown setting: {key}")
    return getattr(settings, key)
