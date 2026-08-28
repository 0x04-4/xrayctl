"""network helpers."""
from __future__ import annotations

import socket
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from .models import Server


def tcp_ping(host: str, port: int, timeout: float = 3.0) -> Optional[int]:
    """Returns round-trip time in milliseconds, or None on failure."""
    if not host or not port:
        return None
    start = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            pass
    except OSError:
        return None
    return int((time.monotonic() - start) * 1000)


def ping_all(servers: list, timeout: float = 3.0, max_workers: int = 20) -> dict:
    """Returns {server.id: latency_ms_or_None}."""
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(tcp_ping, s.address, s.port, timeout): s.id
            for s in servers
        }
        for future in futures:
            results[futures[future]] = future.result()
    return results


def pick_best(servers: list) -> Optional[Server]:
    candidates = [s for s in servers if s.latency_ms is not None]
    if not candidates:
        return None
    return min(candidates, key=lambda s: s.latency_ms)
