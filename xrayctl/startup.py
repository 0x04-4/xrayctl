"""windows startup integration."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from .errors import UsageError

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "xrayctl"


def _require_windows() -> None:
    if sys.platform != "win32":
        raise UsageError("startup is supported on windows only")


def _python(windowed: bool) -> Path:
    current = Path(sys.executable)
    wanted = "pythonw.exe" if windowed else "python.exe"
    if current.name.lower() == wanted:
        return current
    sibling = current.with_name(wanted)
    if sibling.exists():
        return sibling
    found = shutil.which(wanted)
    return Path(found) if found else current


def startup_command() -> str:
    _require_windows()
    return subprocess.list2cmdline([
        str(_python(windowed=True)), "-m", "xrayctl", "--tray",
    ])


def enable() -> str:
    _require_windows()
    import winreg

    command = startup_command()
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
        winreg.SetValueEx(key, _VALUE_NAME, 0, winreg.REG_SZ, command)
    return command


def disable() -> bool:
    _require_windows()
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, _VALUE_NAME)
            return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


def status() -> dict:
    _require_windows()
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            command = winreg.QueryValueEx(key, _VALUE_NAME)[0]
    except (FileNotFoundError, OSError):
        command = ""
    return {"enabled": bool(command), "command": command}
