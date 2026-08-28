"""proxy core process management."""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from . import storage
from .configbuilder import build_core_config
from .errors import CoreError
from .models import RoutingProfile, Server, Settings

_BINARY_NAMES = {
    "xray": ["xray", "xray.exe"],
    "singbox": ["sing-box", "sing-box.exe"],
}


def resolve_core_path(settings: Settings) -> Optional[str]:
    if settings.core_path:
        if Path(settings.core_path).exists():
            return settings.core_path
        return None
    for name in _BINARY_NAMES.get(settings.core_type, []):
        found = shutil.which(name)
        if found:
            return found
    return None


def _read_state() -> Optional[dict]:
    path = storage.state_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError:
        return None


def _write_state(state: Optional[dict]) -> None:
    path = storage.state_path()
    if state is None:
        if path.exists():
            path.unlink()
        return
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def is_pid_alive(pid: int) -> bool:
    if sys.platform == "win32":
        try:
            out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True, text=True, timeout=5,
            ).stdout
            return str(pid) in out
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def start(server: Server, profile: Optional[RoutingProfile], settings: Settings) -> dict:
    existing = _read_state()
    if existing and is_pid_alive(existing.get("pid", -1)):
        raise CoreError(f"already connected (pid {existing['pid']}) — run `xrayctl disconnect` first")

    config = build_core_config(server, profile, settings)
    config_path = storage.generated_config_path()
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

    core_path = resolve_core_path(settings)
    if not core_path:
        raise CoreError(
            f"no '{settings.core_type}' binary found (checked core_path setting and PATH). "
            f"Config was still generated at {config_path} for inspection. "
            f"Install {settings.core_type} yourself and either put it on PATH or run "
            f"`xrayctl config set core_path <path-to-executable>`."
        )

    with open(storage.log_path(), "ab") as log_file:
        try:
            proc = subprocess.Popen(
                [core_path, "run", "-c", str(config_path)],
                stdout=log_file, stderr=subprocess.STDOUT,
                cwd=str(config_path.parent),
            )
        except OSError as e:
            raise CoreError(f"failed to start {core_path}: {e}")

    state = {
        "pid": proc.pid,
        "core_path": core_path,
        "core_type": settings.core_type,
        "config_path": str(config_path),
        "server_id": server.id,
        "mode": settings.mode,
        "connected_at": time.time(),
    }
    _write_state(state)
    return state


def stop() -> None:
    state = _read_state()
    if not state:
        raise CoreError("not connected")
    pid = state.get("pid")
    if pid and is_pid_alive(pid):
        try:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, timeout=10)
            else:
                os.kill(pid, signal.SIGTERM)
        except Exception as e:
            raise CoreError(f"failed to stop process {pid}: {e}")
    _write_state(None)


def status() -> dict:
    state = _read_state()
    if not state:
        return {"connected": False}
    alive = is_pid_alive(state.get("pid", -1))
    if not alive:
        _write_state(None)
        return {"connected": False, "note": "process had exited; state cleared"}
    return {
        "connected": True,
        "pid": state["pid"],
        "server_id": state.get("server_id"),
        "mode": state.get("mode"),
        "core_type": state.get("core_type"),
        "uptime_seconds": int(time.time() - state.get("connected_at", time.time())),
    }


def read_logs(lines: int = 50) -> str:
    path = storage.log_path()
    if not path.exists():
        return ""
    data = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(data[-lines:])


def follow_logs():
    """Generator yielding new log lines as they're appended. Caller Ctrl+C's out."""
    path = storage.log_path()
    path.touch(exist_ok=True)
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        f.seek(0, os.SEEK_END)
        while True:
            line = f.readline()
            if line:
                yield line.rstrip("\n")
            else:
                time.sleep(0.5)
