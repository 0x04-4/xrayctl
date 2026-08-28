"""package entry point."""
from __future__ import annotations

import os
import sys


def _ensure_utf8_console() -> None:
    """Windows consoles often default stdin/stdout/stderr to a legacy codepage
    (e.g. cp1252) that can't encode the QR block characters or Cyrillic
    remarks — reconfigure to UTF-8 so output never crashes on encoding, and
    so typed/piped Cyrillic or emoji input isn't mis-decoded on the way in."""
    for stream_name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, stream_name)
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure and (stream.encoding or "").lower() != "utf-8":
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def _clear_interactive_screen() -> None:
    if len(sys.argv) != 1:
        return
    try:
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            return
    except Exception:
        return
    if sys.platform == "win32":
        os.system("cls")
    else:
        sys.stdout.write("\x1b[2J\x1b[H")
        sys.stdout.flush()


def main() -> int:
    _ensure_utf8_console()
    from .style import enable_windows_vt
    enable_windows_vt()
    _clear_interactive_screen()
    from .cli import main as cli_main
    return cli_main()


if __name__ == "__main__":
    sys.exit(main())
