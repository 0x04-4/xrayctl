"""local json storage."""
from __future__ import annotations

import json
import os
import sys
import threading
import uuid
from pathlib import Path
from .models import RoutingProfile, Server, Settings, Subscription

_lock = threading.Lock()


def _valid_hwid(value: str) -> bool:
    return 10 <= len(value) <= 64 and all(
        ch in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789=-"
        for ch in value
    )


def data_dir() -> Path:
    override = os.environ.get("XRAYCTL_HOME")
    base = Path(override) if override else Path.home() / ".xrayctl"
    base.mkdir(parents=True, exist_ok=True)
    return base


def device_hwid() -> str:
    """Return one stable HWID in the Happ/Remnawave-compatible format."""
    path = _path("hwid")
    with _lock:
        if path.exists():
            saved = path.read_text(encoding="ascii", errors="ignore").strip()
            if _valid_hwid(saved):
                return saved

        value = ""
        if sys.platform == "win32":
            try:
                import winreg

                with winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SOFTWARE\Microsoft\Cryptography",
                ) as key:
                    value = str(winreg.QueryValueEx(key, "MachineGuid")[0])
                    value = value.strip().strip("{}").replace("-", "").lower()
            except (OSError, ValueError, TypeError):
                pass
        if not _valid_hwid(value):
            value = uuid.uuid4().hex

        tmp = Path(str(path) + ".tmp")
        tmp.write_text(value, encoding="ascii")
        tmp.replace(path)
        return value


def _path(name: str) -> Path:
    return data_dir() / name


def _read_list(path: Path) -> list:
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read().strip()
        if not raw:
            return []
        return json.loads(raw)


def _write_list(path: Path, items: list) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


class Store:
    """Thin repository wrapper around one JSON list file."""

    def __init__(self, filename: str, model_cls):
        self._path = _path(filename)
        self._model_cls = model_cls

    def all(self) -> list:
        with _lock:
            return [self._model_cls.from_dict(d) for d in _read_list(self._path)]

    def get(self, id_: str):
        for item in self.all():
            if item.id == id_:
                return item
        return None

    def save(self, item) -> None:
        with _lock:
            items = _read_list(self._path)
            items = [d for d in items if d.get("id") != item.id]
            items.append(item.to_dict())
            _write_list(self._path, items)

    def delete(self, id_: str) -> bool:
        with _lock:
            items = _read_list(self._path)
            new_items = [d for d in items if d.get("id") != id_]
            if len(new_items) == len(items):
                return False
            _write_list(self._path, new_items)
            return True

    def replace_all(self, items: list) -> None:
        with _lock:
            _write_list(self._path, [i.to_dict() for i in items])


servers = Store("servers.json", Server)
subscriptions = Store("subscriptions.json", Subscription)
routing_profiles = Store("routing_profiles.json", RoutingProfile)


def load_settings() -> Settings:
    path = _path("settings.json")
    if not path.exists():
        return Settings()
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read().strip()
        if not raw:
            return Settings()
        return Settings.from_dict(json.loads(raw))


def save_settings(settings: Settings) -> None:
    path = _path("settings.json")
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(settings.to_dict(), f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def state_path() -> Path:
    """Runtime connection state (pid, config path, connected_at) — see core.py."""
    return _path("state.json")


def log_path() -> Path:
    return _path("core.log")


def generated_config_path() -> Path:
    return _path("xray_config.json")
