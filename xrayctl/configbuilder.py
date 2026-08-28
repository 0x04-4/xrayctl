"""proxy core configuration builders."""
from __future__ import annotations

from .errors import CoreError
from .models import RoutingProfile, Server, Settings



def _split_geo(values: list, geo_prefix: str):
    """Splits ['geosite:cn', 'example.com'] into (['example.com'], ['cn'])."""
    plain, geo = [], []
    prefix = geo_prefix + ":"
    for v in values or []:
        if v.startswith(prefix):
            geo.append(v[len(prefix):])
        else:
            plain.append(v)
    return plain, geo


def _default_routing_profile() -> RoutingProfile:
    return RoutingProfile(name="default")




def _xray_stream_settings(p: dict, net_key="type", tls_key="security"):
    network = p.get(net_key) or p.get("type", "tcp")
    security = p.get(tls_key) or p.get("security", "none")
    stream = {"network": network, "security": security}
    if network == "ws":
        stream["wsSettings"] = {
            "path": p.get("path", "/"),
            "headers": {"Host": p["host"]} if p.get("host") else {},
        }
    elif network == "grpc":
        stream["grpcSettings"] = {"serviceName": p.get("serviceName", p.get("path", ""))}
    if security == "tls":
        stream["tlsSettings"] = {
            "serverName": p.get("sni", ""),
            "fingerprint": p.get("fp", ""),
            "alpn": p["alpn"].split(",") if p.get("alpn") else [],
        }
    elif security == "reality":
        stream["realitySettings"] = {
            "serverName": p.get("sni", ""),
            "fingerprint": p.get("fp", "chrome"),
            "publicKey": p.get("pbk", ""),
            "shortId": p.get("sid", ""),
            "spiderX": p.get("spx", ""),
        }
    sockopt = {}
    if p.get("fragment"):
        length, interval, packets = (p["fragment"].split(",") + ["", "", ""])[:3]
        sockopt["fragment"] = {"packets": packets or "tlshello", "length": length, "interval": interval}
    if p.get("noises"):
        ntype, packet, delay = (p["noises"].split(",") + ["", "", ""])[:3]
        sockopt["noises"] = [{"type": ntype or "rand", "packet": packet, "delay": delay}]
    if sockopt:
        stream["sockopt"] = sockopt
    return stream


def _xray_outbound(server: Server) -> dict:
    p = server.params
    proto = server.protocol

    if proto == "vless":
        user = {"id": p.get("uuid", ""), "encryption": p.get("encryption", "none")}
        if p.get("flow"):
            user["flow"] = p["flow"]
        return {
            "tag": "proxy", "protocol": "vless",
            "settings": {"vnext": [{"address": server.address, "port": server.port, "users": [user]}]},
            "streamSettings": _xray_stream_settings(p),
        }
    if proto == "vmess":
        user = {"id": p.get("id", ""), "alterId": int(p.get("aid", 0) or 0), "security": p.get("scy", "auto")}
        return {
            "tag": "proxy", "protocol": "vmess",
            "settings": {"vnext": [{"address": server.address, "port": server.port, "users": [user]}]},
            "streamSettings": _xray_stream_settings(p, net_key="net", tls_key="tls"),
        }
    if proto == "trojan":
        return {
            "tag": "proxy", "protocol": "trojan",
            "settings": {"servers": [{"address": server.address, "port": server.port, "password": p.get("password", "")}]},
            "streamSettings": _xray_stream_settings(p),
        }
    if proto == "ss":
        return {
            "tag": "proxy", "protocol": "shadowsocks",
            "settings": {"servers": [{
                "address": server.address, "port": server.port,
                "method": p.get("method", "aes-256-gcm"), "password": p.get("password", ""),
            }]},
        }
    if proto == "socks":
        entry = {"address": server.address, "port": server.port}
        if p.get("user"):
            entry["users"] = [{"user": p.get("user", ""), "pass": p.get("password", "")}]
        return {"tag": "proxy", "protocol": "socks", "settings": {"servers": [entry]}}
    if proto == "wireguard":
        return {
            "tag": "proxy", "protocol": "wireguard",
            "settings": {
                "secretKey": p.get("private_key", ""),
                "address": [a.strip() for a in p.get("address", "").split(",") if a.strip()],
                "peers": [{
                    "publicKey": p.get("public_key", ""),
                    "endpoint": f"{server.address}:{server.port}",
                    "allowedIPs": [a.strip() for a in p.get("allowed_ips", "0.0.0.0/0").split(",") if a.strip()],
                }],
                "mtu": int(p.get("mtu") or 1420),
            },
        }
    if proto == "json":
        obj = dict(server.raw_json or {})
        obj.setdefault("tag", "proxy")
        return obj
    if proto == "hysteria2":
        raise CoreError(
            "Xray-core has no native Hysteria2 outbound. Switch cores: "
            "`xrayctl config set core_type singbox`."
        )
    raise CoreError(f"unsupported protocol for Xray-core outbound: {proto}")


def _xray_inbounds(settings: Settings) -> list:
    inbounds = [
        {"tag": "socks-in", "protocol": "socks", "listen": "127.0.0.1", "port": settings.socks_port,
         "settings": {"auth": "noauth", "udp": True}, "sniffing": {"enabled": True, "destOverride": ["http", "tls"]}},
        {"tag": "http-in", "protocol": "http", "listen": "127.0.0.1", "port": settings.http_port, "settings": {}},
    ]
    return inbounds


def _rule(domain_list, ip_list, tag):
    rule = {"type": "field", "outboundTag": tag}
    if domain_list:
        rule["domain"] = list(domain_list)
    if ip_list:
        rule["ip"] = list(ip_list)
    return rule if (domain_list or ip_list) else None


def _xray_routing(profile: RoutingProfile) -> dict:
    if profile.global_proxy:
        return {"domainStrategy": profile.domain_strategy, "rules": [
            {"type": "field", "port": "0-65535", "outboundTag": "proxy"}
        ]}
    rules = []
    for r in (
        _rule(profile.block_sites, profile.block_ip, "block"),
        _rule(profile.direct_sites, profile.direct_ip, "direct"),
        _rule(profile.proxy_sites, profile.proxy_ip, "proxy"),
    ):
        if r:
            rules.append(r)
    rules.append({"type": "field", "port": "0-65535", "outboundTag": "proxy"})
    return {"domainStrategy": profile.domain_strategy, "rules": rules}


def _xray_dns(profile: RoutingProfile) -> dict:
    servers = []
    remote = profile.remote_dns_ip or profile.remote_dns_domain
    if remote:
        servers.append(remote)
    domestic = profile.domestic_dns_ip or profile.domestic_dns_domain
    if domestic and domestic != remote:
        servers.append(domestic)
    if not servers:
        servers = ["1.1.1.1"]
    dns = {"servers": servers}
    if profile.dns_hosts:
        dns["hosts"] = dict(profile.dns_hosts)
    if profile.fake_dns:
        dns["fakedns"] = [{"ipPool": "198.18.0.0/15", "poolSize": 65535}]
    return dns


def build_xray_config(server: Server, profile: RoutingProfile, settings: Settings) -> dict:
    if settings.mode == "tun":
        raise CoreError(
            "Xray-core has no native TUN inbound. Either run in proxy mode "
            "(`xrayctl mode proxy`) and bridge it yourself with tun2socks (spec 9.3), "
            "or switch cores: `xrayctl config set core_type singbox`."
        )
    outbound = _xray_outbound(server)
    outbounds = [outbound, {"tag": "direct", "protocol": "freedom", "settings": {}},
                 {"tag": "block", "protocol": "blackhole", "settings": {}}]
    return {
        "log": {"loglevel": "warning"},
        "inbounds": _xray_inbounds(settings),
        "outbounds": outbounds,
        "dns": _xray_dns(profile),
        "routing": _xray_routing(profile),
    }




def _singbox_apply_tls(base: dict, p: dict, tls_key="security"):
    sec = p.get(tls_key) or p.get("security", "")
    if sec not in ("tls", "reality"):
        return
    tls = {"enabled": True, "server_name": p.get("sni", "")}
    if p.get("fp"):
        tls["utls"] = {"enabled": True, "fingerprint": p["fp"]}
    if sec == "reality":
        tls["reality"] = {"enabled": True, "public_key": p.get("pbk", ""), "short_id": p.get("sid", "")}
    base["tls"] = tls


def _singbox_apply_transport(base: dict, p: dict, net_key="type"):
    net = p.get(net_key) or p.get("type", "tcp")
    if net == "ws":
        base["transport"] = {
            "type": "ws", "path": p.get("path", "/"),
            "headers": ({"Host": p["host"]} if p.get("host") else {}),
        }
    elif net == "grpc":
        base["transport"] = {"type": "grpc", "service_name": p.get("serviceName", p.get("path", ""))}


def _singbox_outbound(server: Server) -> dict:
    p = server.params
    proto = server.protocol
    base = {"tag": "proxy"}

    if proto == "vless":
        base.update({"type": "vless", "server": server.address, "server_port": server.port,
                     "uuid": p.get("uuid", "")})
        if p.get("flow"):
            base["flow"] = p["flow"]
        _singbox_apply_tls(base, p)
        _singbox_apply_transport(base, p)
    elif proto == "vmess":
        base.update({"type": "vmess", "server": server.address, "server_port": server.port,
                     "uuid": p.get("id", ""), "alter_id": int(p.get("aid", 0) or 0),
                     "security": p.get("scy", "auto")})
        _singbox_apply_tls(base, p, tls_key="tls")
        _singbox_apply_transport(base, p, net_key="net")
    elif proto == "trojan":
        base.update({"type": "trojan", "server": server.address, "server_port": server.port,
                     "password": p.get("password", "")})
        _singbox_apply_tls(base, p)
        _singbox_apply_transport(base, p)
    elif proto == "ss":
        base.update({"type": "shadowsocks", "server": server.address, "server_port": server.port,
                     "method": p.get("method", "aes-256-gcm"), "password": p.get("password", "")})
    elif proto == "socks":
        base.update({"type": "socks", "server": server.address, "server_port": server.port})
        if p.get("user"):
            base.update({"username": p.get("user", ""), "password": p.get("password", "")})
    elif proto == "hysteria2":
        base.update({"type": "hysteria2", "server": server.address, "server_port": server.port,
                     "password": p.get("auth", "")})
        if p.get("obfs"):
            base["obfs"] = {"type": p["obfs"], "password": p.get("obfs-password", p.get("obfs_password", ""))}
        base["tls"] = {"enabled": True, "server_name": p.get("sni", "")}
    elif proto == "wireguard":
        base.update({
            "type": "wireguard", "server": server.address, "server_port": server.port,
            "private_key": p.get("private_key", ""), "peer_public_key": p.get("public_key", ""),
            "local_address": [a.strip() for a in p.get("address", "").split(",") if a.strip()],
            "mtu": int(p.get("mtu") or 1420),
        })
    elif proto == "json":
        base = dict(server.raw_json or {})
        base.setdefault("tag", "proxy")
    else:
        raise CoreError(f"unsupported protocol for sing-box outbound: {proto}")
    return base


def _singbox_inbounds(settings: Settings) -> list:
    inbounds = [
        {"type": "socks", "tag": "socks-in", "listen": "127.0.0.1", "listen_port": settings.socks_port},
        {"type": "http", "tag": "http-in", "listen": "127.0.0.1", "listen_port": settings.http_port},
    ]
    if settings.mode == "tun":
        inbounds.append({
            "type": "tun", "tag": "tun-in", "interface_name": "xrayctl-tun",
            "address": ["172.19.0.1/30", "fdfe:dcba:9876::1/126"],
            "mtu": 9000, "auto_route": True, "strict_route": True,
            "stack": settings.tun_stack,
        })
    return inbounds


def _singbox_rule(domain_list, ip_list, tag):
    plain_domains, geosites = _split_geo(domain_list, "geosite")
    plain_ips, geoips = _split_geo(ip_list, "geoip")
    rule = {"outbound": tag}
    if plain_domains:
        rule["domain"] = plain_domains
    if geosites:
        rule["geosite"] = geosites
    if plain_ips:
        rule["ip_cidr"] = plain_ips
    if geoips:
        rule["geoip"] = geoips
    return rule if (plain_domains or geosites or plain_ips or geoips) else None


def _singbox_route(profile: RoutingProfile) -> dict:
    if profile.global_proxy:
        return {"rules": [], "final": "proxy"}
    rules = []
    for r in (
        _singbox_rule(profile.block_sites, profile.block_ip, "block"),
        _singbox_rule(profile.direct_sites, profile.direct_ip, "direct"),
        _singbox_rule(profile.proxy_sites, profile.proxy_ip, "proxy"),
    ):
        if r:
            rules.append(r)
    return {"rules": rules, "final": "proxy"}


def _singbox_dns(profile: RoutingProfile) -> dict:
    servers = []
    remote = profile.remote_dns_ip or profile.remote_dns_domain
    if remote:
        servers.append({"address": remote, "tag": "remote-dns"})
    domestic = profile.domestic_dns_ip or profile.domestic_dns_domain
    if domestic and domestic != remote:
        servers.append({"address": domestic, "tag": "domestic-dns"})
    if not servers:
        servers = [{"address": "1.1.1.1", "tag": "remote-dns"}]
    dns = {"servers": servers}
    if profile.fake_dns:
        dns["fakeip"] = {"enabled": True, "inet4_range": "198.18.0.0/15"}
    return dns


def build_singbox_config(server: Server, profile: RoutingProfile, settings: Settings) -> dict:
    outbound = _singbox_outbound(server)
    outbounds = [outbound, {"type": "direct", "tag": "direct"}, {"type": "block", "tag": "block"}]
    return {
        "log": {"level": "warn"},
        "dns": _singbox_dns(profile),
        "inbounds": _singbox_inbounds(settings),
        "outbounds": outbounds,
        "route": _singbox_route(profile),
    }




def build_core_config(server: Server, profile: RoutingProfile, settings: Settings) -> dict:
    if server is None:
        raise CoreError("no active server selected — run `xrayctl use <id>` first")
    profile = profile or _default_routing_profile()
    if settings.core_type == "singbox":
        return build_singbox_config(server, profile, settings)
    if settings.core_type == "xray":
        return build_xray_config(server, profile, settings)
    raise CoreError(f"unknown core_type: {settings.core_type!r} (expected 'xray' or 'singbox')")
