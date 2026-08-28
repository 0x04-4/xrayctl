"""happ deep-link parsing."""
from __future__ import annotations

import json

from .errors import ParseError, UnsupportedError
from .parsers import b64decode_safe

ROUTING_ADD_PREFIX = "happ://routing/add/"
ROUTING_ONADD_PREFIX = "happ://routing/onadd/"
ROUTING_OFF = "happ://routing/off"


def _decode_profile_payload(payload: str) -> dict:
    payload = payload.rstrip("/")
    decoded = b64decode_safe(payload)
    if decoded is None:
        raise ParseError("routing deep link: payload is not valid base64")
    try:
        return json.loads(decoded)
    except json.JSONDecodeError as e:
        raise ParseError(f"routing deep link: payload is not valid JSON ({e})")


def parse_happ_link(link: str):
    """Returns (kind, payload) where kind is one of:
    'routing_off' (payload=None), 'routing_add'/'routing_onadd' (payload=dict profile JSON).
    Raises UnsupportedError for happ://crypt4|crypt5 (see docstring below)."""
    link = link.strip()

    if link.startswith("happ://crypt4/") or link.startswith("happ://crypt5/"):
        raise UnsupportedError(
            "Ссылки happ://crypt4/... и happ://crypt5/... шифруются приватным "
            "RSA-4096 ключом, который встроен ТОЛЬКО в официальный клиент Happ и "
            "нигде публично не задокументирован. Эта CLI-реализация не может (и "
            "не должна пытаться) их расшифровать — это дало бы либо ошибку, либо "
            "тихо неверный результат. Используйте обычную (не-crypto) подписку в "
            "открытом виде, либо официальное приложение Happ для этой ссылки."
        )
    if link == ROUTING_OFF or link.startswith(ROUTING_OFF):
        return ("routing_off", None)
    if link.startswith(ROUTING_ONADD_PREFIX):
        return ("routing_onadd", _decode_profile_payload(link[len(ROUTING_ONADD_PREFIX):]))
    if link.startswith(ROUTING_ADD_PREFIX):
        return ("routing_add", _decode_profile_payload(link[len(ROUTING_ADD_PREFIX):]))
    if link.startswith("happ://"):
        raise ParseError(f"unrecognized happ:// deep link: {link}")
    raise ParseError(f"not a happ:// deep link: {link}")
