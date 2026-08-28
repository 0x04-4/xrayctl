"""terminal styling."""
from __future__ import annotations

import os
import sys

RESET = "\x1b[0m"

_PINK = (255, 182, 213)
_BLUE = (173, 216, 230)

_vt_enabled = False


def enable_windows_vt() -> None:
    """cmd.exe needs ENABLE_VIRTUAL_TERMINAL_PROCESSING switched on before it
    will render ANSI escape codes instead of printing them literally."""
    global _vt_enabled
    if sys.platform != "win32":
        _vt_enabled = True
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
        _vt_enabled = True
    except Exception:
        _vt_enabled = False


def supports_color(stream=None) -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if not _vt_enabled:
        return False
    stream = stream if stream is not None else sys.stdout
    try:
        return stream.isatty()
    except Exception:
        return False


def _rgb(rgb) -> str:
    r, g, b = rgb
    return f"\x1b[38;2;{r};{g};{b}m"


def gradient(text: str, stream=None) -> str:
    """Colors `text` letter-by-letter from pastel pink to pastel blue."""
    if not text or not supports_color(stream):
        return text
    n = len(text)
    parts = []
    for i, ch in enumerate(text):
        t = i / (n - 1) if n > 1 else 0.0
        r = round(_PINK[0] + (_BLUE[0] - _PINK[0]) * t)
        g = round(_PINK[1] + (_BLUE[1] - _PINK[1]) * t)
        b = round(_PINK[2] + (_BLUE[2] - _PINK[2]) * t)
        parts.append(f"{_rgb((r, g, b))}{ch}")
    parts.append(RESET)
    return "".join(parts)


def bracket(symbol: str, stream=None) -> str:
    """The gradiented '[symbol]' marker on its own, e.g. bracket('!') -> '[!]'."""
    return gradient(f"[{symbol}]", stream=stream)


def ok(msg: str, stream=None) -> str:
    return f"{bracket('+', stream)} {msg}"


def info(msg: str, stream=None) -> str:
    return f"{bracket('!', stream)} {msg}"


def err(msg: str, stream=None) -> str:
    """`stream` should be passed explicitly when the caller is about to print
    to something other than stdout (cli.py's error path prints to stderr)."""
    return f"{bracket('-', stream)} {msg}"
