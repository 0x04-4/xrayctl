"""proxy link parsers."""
from __future__ import annotations

import base64
import json
import string
from urllib.parse import parse_qsl, quote, unquote, urlencode

from .errors import ParseError
from .models import Server



def b64decode_safe(s: str):
    """Best-effort base64 decode accepting both standard and urlsafe alphabets
    and missing padding. Returns decoded text, or None if it can't be decoded."""
    if not s:
        return None
    s = s.strip().replace("-", "+").replace("_", "/")
    s += "=" * ((-len(s)) % 4)
    try:
        return base64.b64decode(s).decode("utf-8")
    except Exception:
        return None


def _looks_textual(s: str) -> bool:
    if not s:
        return False
    printable = set(string.printable) - {"\x0b", "\x0c"}
    return all(ch in printable for ch in s)


def _split_hostport(hostport: str):
    hostport = hostport.strip()
    if hostport.startswith("["):
        host, _, tail = hostport[1:].partition("]")
        port_str = tail.lstrip(":")
    else:
        host, sep, port_str = hostport.rpartition(":")
        if not sep:
            host, port_str = port_str, ""
    try:
        port = int(port_str) if port_str else 0
    except ValueError:
        port = 0
    return host, port


def _parse_remarks(fragment: str):
    """fragment is the raw text after '#'. Handles the documented
    '#Title?serverDescription=<base64_or_plain>' sub-syntax."""
    if not fragment:
        return "", {}
    name_part, _, qs = fragment.partition("?")
    name = unquote(name_part)
    extra = {}
    if qs:
        for k, v in parse_qsl(qs, keep_blank_values=True):
            if k == "serverDescription":
                decoded = b64decode_safe(v)
                extra[k] = decoded if (decoded and _looks_textual(decoded)) else unquote(v)
            else:
                extra[k] = unquote(v)
    return name, extra


def _parse_generic(uri: str):
    """Parses the common '<userinfo>@host:port?query#fragment' shape used by
    vless/trojan/hysteria2/wireguard-ish links."""
    scheme, _, rest = uri.partition("://")
    rest, frag = rest.split("#", 1) if "#" in rest else (rest, "")
    remarks, desc = _parse_remarks(frag)
    if "@" not in rest:
        raise ParseError(f"{scheme}://: missing '@host:port' section")
    userinfo, hostpart = rest.rsplit("@", 1)
    hostpart, query_str = hostpart.split("?", 1) if "?" in hostpart else (hostpart, "")
    host, port = _split_hostport(hostpart)
    query = dict(parse_qsl(query_str, keep_blank_values=True)) if query_str else {}
    return scheme, unquote(userinfo), host, port, query, remarks, desc




def parse_vless(uri: str) -> Server:
    _scheme, uuid, host, port, query, remarks, extra = _parse_generic(uri)
    params = dict(query)
    params.update(extra)
    params["uuid"] = uuid
    return Server(remarks=remarks or host, protocol="vless", address=host, port=port,
                  raw_uri=uri, params=params)


def parse_trojan(uri: str) -> Server:
    _scheme, password, host, port, query, remarks, extra = _parse_generic(uri)
    params = dict(query)
    params.update(extra)
    params["password"] = password
    return Server(remarks=remarks or host, protocol="trojan", address=host, port=port,
                  raw_uri=uri, params=params)


def parse_hysteria2(uri: str) -> Server:
    _scheme, auth, host, port, query, remarks, extra = _parse_generic(uri)
    params = dict(query)
    params.update(extra)
    params["auth"] = auth
    return Server(remarks=remarks or host, protocol="hysteria2", address=host, port=port,
                  raw_uri=uri, params=params)


def parse_wireguard(uri: str) -> Server:
    _scheme, private_key, host, port, query, remarks, extra = _parse_generic(uri)
    params = dict(query)
    params.update(extra)
    params["private_key"] = private_key
    return Server(remarks=remarks or host, protocol="wireguard", address=host, port=port,
                  raw_uri=uri, params=params)


def parse_wireguard_conf(text: str, remarks: str = "") -> Server:
    """Import a standard wg-quote [Interface]/[Peer] .conf file."""
    section = None
    iface, peer = {}, {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip().lower()
            continue
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip().lower(), v.strip()
        if section == "interface":
            iface[k] = v
        elif section == "peer":
            peer[k] = v
    endpoint = peer.get("endpoint", "")
    host, port = _split_hostport(endpoint) if ":" in endpoint else (endpoint, 0)
    params = {
        "private_key": iface.get("privatekey", ""),
        "address": iface.get("address", ""),
        "dns": iface.get("dns", ""),
        "mtu": iface.get("mtu", ""),
        "public_key": peer.get("publickey", ""),
        "preshared_key": peer.get("presharedkey", ""),
        "allowed_ips": peer.get("allowedips", "0.0.0.0/0"),
    }
    if not params["public_key"]:
        raise ParseError("wireguard conf: missing [Peer] PublicKey")
    return Server(remarks=remarks or host or "wireguard", protocol="wireguard",
                  address=host, port=port, params=params)


def parse_vmess(uri: str) -> Server:
    _scheme, _, rest = uri.partition("://")
    rest, frag = rest.split("#", 1) if "#" in rest else (rest, "")
    remarks_override, extra = _parse_remarks(frag) if frag else ("", {})
    decoded = b64decode_safe(rest)
    if decoded is None:
        raise ParseError("vmess://: payload is not valid base64")
    try:
        obj = json.loads(decoded)
    except json.JSONDecodeError as e:
        raise ParseError(f"vmess://: payload is not valid JSON ({e})")
    host = obj.get("add", "")
    try:
        port = int(obj.get("port", 0))
    except (TypeError, ValueError):
        port = 0
    remarks = remarks_override or obj.get("ps", "") or host
    params = {k: v for k, v in obj.items() if k not in ("add", "port", "ps")}
    params.update(extra)
    return Server(remarks=remarks, protocol="vmess", address=host, port=port,
                  raw_uri=uri, params=params)


def parse_ss(uri: str) -> Server:
    _scheme, _, rest = uri.partition("://")
    rest, frag = rest.split("#", 1) if "#" in rest else (rest, "")
    remarks, extra = _parse_remarks(frag) if frag else ("", {})
    query = {}
    if "?" in rest:
        rest, qs = rest.split("?", 1)
        query = dict(parse_qsl(qs, keep_blank_values=True))
    if "@" in rest:
        userinfo, hostport = rest.rsplit("@", 1)
        decoded = b64decode_safe(unquote(userinfo))
        if decoded and ":" in decoded:
            method, _, password = decoded.partition(":")
        elif ":" in unquote(userinfo):
            method, _, password = unquote(userinfo).partition(":")
        else:
            raise ParseError("ss://: could not determine method:password from link")
        host, port = _split_hostport(hostport)
    else:
        decoded_all = b64decode_safe(rest)
        if not decoded_all or "@" not in decoded_all:
            raise ParseError("ss://: could not decode legacy fully-base64 form")
        userinfo, hostport = decoded_all.rsplit("@", 1)
        method, _, password = userinfo.partition(":")
        host, port = _split_hostport(hostport)
    params = dict(query)
    params.update(extra)
    params["method"] = method
    params["password"] = password
    return Server(remarks=remarks or host, protocol="ss", address=host, port=port,
                  raw_uri=uri, params=params)


def parse_socks(uri: str) -> Server:
    _scheme, _, rest = uri.partition("://")
    rest, frag = rest.split("#", 1) if "#" in rest else (rest, "")
    remarks, extra = _parse_remarks(frag) if frag else ("", {})
    if "@" in rest:
        userinfo, hostport = rest.rsplit("@", 1)
        raw_userinfo = unquote(userinfo)
        if ":" in raw_userinfo:
            user, _, password = raw_userinfo.partition(":")
        else:
            decoded = b64decode_safe(raw_userinfo)
            if decoded and ":" in decoded:
                user, _, password = decoded.partition(":")
            else:
                user, password = (decoded or raw_userinfo), ""
        host, port = _split_hostport(hostport)
    else:
        decoded_all = b64decode_safe(rest)
        if not decoded_all or "@" not in decoded_all:
            raise ParseError("socks://: could not decode fully-base64 form")
        userinfo, hostport = decoded_all.rsplit("@", 1)
        user, _, password = userinfo.partition(":")
        host, port = _split_hostport(hostport)
    params = dict(extra)
    params["user"] = user
    params["password"] = password
    return Server(remarks=remarks or host, protocol="socks", address=host, port=port,
                  raw_uri=uri, params=params)


def _extract_address_port_from_outbound_json(obj: dict):
    settings = obj.get("settings", obj) if isinstance(obj, dict) else {}
    for key in ("vnext", "servers"):
        arr = settings.get(key) if isinstance(settings, dict) else None
        if isinstance(arr, list) and arr and isinstance(arr[0], dict):
            entry = arr[0]
            return entry.get("address", ""), int(entry.get("port", 0) or 0)
    if isinstance(obj, dict) and obj.get("address"):
        try:
            return obj.get("address", ""), int(obj.get("port", 0) or 0)
        except (TypeError, ValueError):
            return obj.get("address", ""), 0
    return "", 0


def parse_json_text(text: str, remarks: str = "") -> Server:
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as e:
        raise ParseError(f"invalid JSON outbound: {e}")
    address, port = _extract_address_port_from_outbound_json(obj)
    return Server(remarks=remarks or address or "json-server", protocol="json",
                  address=address, port=port, raw_json=obj)


SCHEME_PARSERS = {
    "vless": parse_vless,
    "trojan": parse_trojan,
    "vmess": parse_vmess,
    "ss": parse_ss,
    "shadowsocks": parse_ss,
    "socks": parse_socks,
    "socks5": parse_socks,
    "hysteria2": parse_hysteria2,
    "hy2": parse_hysteria2,
    "wireguard": parse_wireguard,
    "wg": parse_wireguard,
}


def import_links_blob(text: str, remarks_hint: str = ""):
    """Best-effort import for `server add --file`: a single link, a wg-quote
    conf, or a subscription-shaped blob (plaintext or base64) with one link
    per line. Returns a list[Server]; raises ParseError if nothing usable
    was found."""
    stripped = text.strip()
    if not stripped:
        raise ParseError("file is empty")
    lower = stripped.lower()
    if "[interface]" in lower and "[peer]" in lower:
        return [parse_wireguard_conf(stripped, remarks=remarks_hint)]
    if "\n" not in stripped and "://" in stripped:
        return [parse_uri(stripped)]

    body = stripped
    decoded = b64decode_safe(stripped)
    if decoded and "://" in decoded:
        body = decoded

    servers = []
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            servers.append(parse_uri(line))
        except ParseError:
            continue
    if not servers:
        raise ParseError("no recognizable server links found")
    return servers


def parse_uri(uri: str) -> Server:
    uri = uri.strip()
    if not uri or "://" not in uri:
        raise ParseError(f"not a recognized link: {uri!r}")
    scheme = uri.split("://", 1)[0].lower()
    fn = SCHEME_PARSERS.get(scheme)
    if not fn:
        raise ParseError(f"unsupported scheme: {scheme}://")
    try:
        return fn(uri)
    except ParseError:
        raise
    except Exception as e:
        raise ParseError(f"failed to parse {scheme}:// link: {e}")




def _build_vless(s: Server) -> str:
    p = dict(s.params)
    uuid = p.pop("uuid", "")
    q = urlencode({k: v for k, v in p.items() if v not in (None, "")})
    return f"vless://{uuid}@{s.address}:{s.port}?{q}#{quote(s.remarks)}"


def _build_trojan(s: Server) -> str:
    p = dict(s.params)
    password = p.pop("password", "")
    q = urlencode({k: v for k, v in p.items() if v not in (None, "")})
    return f"trojan://{password}@{s.address}:{s.port}?{q}#{quote(s.remarks)}"


def _build_hysteria2(s: Server) -> str:
    p = dict(s.params)
    auth = p.pop("auth", "")
    q = urlencode({k: v for k, v in p.items() if v not in (None, "")})
    return f"hysteria2://{auth}@{s.address}:{s.port}?{q}#{quote(s.remarks)}"


def _build_wireguard(s: Server) -> str:
    p = dict(s.params)
    priv = p.pop("private_key", "")
    q = urlencode({k: v for k, v in p.items() if v not in (None, "")})
    return f"wireguard://{priv}@{s.address}:{s.port}?{q}#{quote(s.remarks)}"


def _build_vmess(s: Server) -> str:
    obj = dict(s.params)
    obj["v"] = obj.get("v", "2")
    obj["ps"] = s.remarks
    obj["add"] = s.address
    obj["port"] = str(s.port)
    payload = json.dumps(obj, ensure_ascii=False)
    b64 = base64.b64encode(payload.encode("utf-8")).decode("ascii")
    return f"vmess://{b64}"


def _build_ss(s: Server) -> str:
    p = s.params
    userinfo = base64.b64encode(
        f"{p.get('method', '')}:{p.get('password', '')}".encode()
    ).decode().rstrip("=")
    return f"ss://{userinfo}@{s.address}:{s.port}#{quote(s.remarks)}"


def _build_socks(s: Server) -> str:
    p = s.params
    userinfo = base64.b64encode(
        f"{p.get('user', '')}:{p.get('password', '')}".encode()
    ).decode().rstrip("=")
    return f"socks://{userinfo}@{s.address}:{s.port}#{quote(s.remarks)}"


_BUILDERS = {
    "vless": _build_vless,
    "trojan": _build_trojan,
    "hysteria2": _build_hysteria2,
    "wireguard": _build_wireguard,
    "vmess": _build_vmess,
    "ss": _build_ss,
    "socks": _build_socks,
}


def build_uri(server: Server) -> str:
    if server.raw_uri:
        return server.raw_uri
    if server.protocol == "json":
        return json.dumps(server.raw_json or {}, ensure_ascii=False)
    builder = _BUILDERS.get(server.protocol)
    if not builder:
        raise ParseError(f"export not supported for protocol: {server.protocol}")
    return builder(server)
