"""persistent data models."""
from __future__ import annotations

import time
import uuid as _uuid
from dataclasses import dataclass, field, asdict
from typing import Optional


def new_id() -> str:
    return _uuid.uuid4().hex[:8]


@dataclass
class Server:
    id: str = field(default_factory=new_id)
    subscription_id: Optional[str] = None
    remarks: str = ""
    protocol: str = ""
    address: str = ""
    port: int = 0
    params: dict = field(default_factory=dict)
    raw_uri: str = ""
    raw_json: Optional[dict] = None
    latency_ms: Optional[int] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Server":
        return Server(**d)


@dataclass
class Subscription:
    id: str = field(default_factory=new_id)
    url: str = ""
    is_crypto: bool = False
    crypto_version: str = "none"
    title: str = ""
    update_interval_hours: int = 24
    userinfo: dict = field(default_factory=dict)
    support_url: str = ""
    web_page_url: str = ""
    announce: str = ""
    user_agent: str = "xrayctl/1.0"
    last_updated: Optional[float] = None
    servers: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Subscription":
        return Subscription(**d)


@dataclass
class RoutingProfile:
    id: str = field(default_factory=new_id)
    name: str = "default"
    subscription_id: Optional[str] = None
    is_active: bool = False
    global_proxy: bool = False
    remote_dns_type: str = "udp"
    remote_dns_domain: str = ""
    remote_dns_ip: str = "1.1.1.1"
    domestic_dns_type: str = "udp"
    domestic_dns_domain: str = ""
    domestic_dns_ip: str = "223.5.5.5"
    geoip_url: str = ""
    geosite_url: str = ""
    last_updated: Optional[float] = None
    domain_strategy: str = "IPIfNonMatch"
    fake_dns: bool = False
    direct_sites: list = field(default_factory=list)
    direct_ip: list = field(default_factory=list)
    proxy_sites: list = field(default_factory=list)
    proxy_ip: list = field(default_factory=list)
    block_sites: list = field(default_factory=list)
    block_ip: list = field(default_factory=list)
    dns_hosts: dict = field(default_factory=dict)
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "RoutingProfile":
        return RoutingProfile(**d)


@dataclass
class Settings:
    socks_port: int = 10808
    http_port: int = 10809
    mode: str = "proxy"
    tun_stack: str = "system"
    active_server_id: Optional[str] = None
    active_routing_profile_id: Optional[str] = None
    core_type: str = "xray"
    core_path: str = ""
    subscription_user_agent: str = "xrayctl/1.0"
    auto_start: bool = False
    language: str = "ru"

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Settings":
        base = Settings()
        base_dict = asdict(base)
        base_dict.update({k: v for k, v in d.items() if k in base_dict})
        return Settings(**base_dict)
