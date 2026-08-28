"""routing profile conversion."""
from __future__ import annotations

from .models import RoutingProfile

_FIELD_MAP = {
    "Name": "name",
    "GlobalProxy": "global_proxy",
    "RemoteDNSType": "remote_dns_type",
    "RemoteDNSDomain": "remote_dns_domain",
    "RemoteDNSIP": "remote_dns_ip",
    "DomesticDNSType": "domestic_dns_type",
    "DomesticDNSDomain": "domestic_dns_domain",
    "DomesticDNSIP": "domestic_dns_ip",
    "Geoipurl": "geoip_url",
    "Geositeurl": "geosite_url",
    "LastUpdated": "last_updated",
    "DomainStrategy": "domain_strategy",
    "FakeDNS": "fake_dns",
    "DirectSites": "direct_sites",
    "DirectIp": "direct_ip",
    "ProxySites": "proxy_sites",
    "ProxyIp": "proxy_ip",
    "BlockSites": "block_sites",
    "BlockIp": "block_ip",
    "DnsHosts": "dns_hosts",
}
_REVERSE_MAP = {v: k for k, v in _FIELD_MAP.items()}


def profile_from_json(payload: dict, subscription_id=None, activate=False) -> RoutingProfile:
    profile = RoutingProfile()
    if subscription_id:
        profile.subscription_id = subscription_id
    profile.is_active = activate
    for key, value in (payload or {}).items():
        field = _FIELD_MAP.get(key)
        if field:
            setattr(profile, field, value)
        else:
            profile.extra[key] = value
    return profile


def profile_to_json(profile: RoutingProfile) -> dict:
    out = {}
    for field, key in _REVERSE_MAP.items():
        out[key] = getattr(profile, field)
    return out
