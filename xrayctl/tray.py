"""windows system tray integration."""
from __future__ import annotations

import ctypes
import subprocess
import sys
import threading
from pathlib import Path

from . import services
from .errors import UsageError, XrayctlError


def _require_windows() -> None:
    if sys.platform != "win32":
        raise UsageError("the tray is supported on windows only")


def _console_window() -> int:
    return int(ctypes.windll.kernel32.GetConsoleWindow())


def _hide_console() -> None:
    hwnd = _console_window()
    if hwnd:
        ctypes.windll.user32.ShowWindow(hwnd, 0)


def _show_console() -> bool:
    hwnd = _console_window()
    if not hwnd:
        return False
    ctypes.windll.user32.ShowWindow(hwnd, 5)
    ctypes.windll.user32.SetForegroundWindow(hwnd)
    return True


def _ensure_dependencies():
    try:
        import pystray
    except ImportError as exc:
        raise UsageError("the tray requires pystray") from exc
    try:
        from PIL import Image
    except ImportError as exc:
        raise UsageError("the tray requires pillow") from exc
    return pystray, Image


def _open_console() -> None:
    current = Path(sys.executable)
    python = current.with_name("python.exe")
    if not python.exists():
        python = current
    subprocess.Popen(
        [str(python), "-m", "xrayctl"],
        creationflags=subprocess.CREATE_NEW_CONSOLE,
        close_fds=True,
    )


def _image():
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:
        raise UsageError("the tray requires pillow") from exc

    image = Image.new("RGBA", (64, 64), (20, 24, 32, 255))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((4, 4, 60, 60), radius=12, fill=(92, 75, 190, 255))
    draw.line((19, 19, 45, 45), fill=(255, 255, 255, 255), width=6)
    draw.line((45, 19, 19, 45), fill=(255, 255, 255, 255), width=6)
    return image


class TrayApp:
    def __init__(self, connect_last: bool = False, close_on_show: bool = False):
        self.connect_last = connect_last
        self.close_on_show = close_on_show
        self.icon = None
        self.exit_requested = False
        self.closed = threading.Event()

    def _notify(self, message: str) -> None:
        if self.icon is not None:
            try:
                self.icon.notify(message, "xrayctl")
            except Exception:
                pass

    def _show(self, icon, item) -> None:
        shown = _show_console()
        if not shown:
            _open_console()
        elif self.close_on_show:
            icon.stop()

    def _status(self, icon, item) -> None:
        state = services.connection_status()
        if state.get("connected"):
            self._notify(f"connected: {state.get('server_remarks', state.get('server_id'))}")
        else:
            self._notify("not connected")

    def _connect(self, icon, item) -> None:
        try:
            services.connect()
        except XrayctlError as exc:
            self._notify(str(exc))
        else:
            self._notify("connected")

    def _disconnect(self, icon, item) -> None:
        try:
            services.disconnect()
        except XrayctlError as exc:
            self._notify(str(exc))
        else:
            self._notify("disconnected")

    def _exit(self, icon, item) -> None:
        self.exit_requested = True
        try:
            if services.connection_status().get("connected"):
                services.disconnect()
        except XrayctlError:
            pass
        if self.close_on_show:
            _show_console()
        icon.stop()

    def _connect_last(self) -> None:
        if not self.connect_last:
            return
        try:
            services.connect()
        except XrayctlError as exc:
            self._notify(str(exc))
        else:
            self._notify("connected to the last server")

    def run(self) -> int:
        _require_windows()
        pystray, _ = _ensure_dependencies()

        self.icon = pystray.Icon(
            "xrayctl",
            _image(),
            "xrayctl",
            menu=pystray.Menu(
                pystray.MenuItem("show", self._show, default=True),
                pystray.MenuItem("status", self._status),
                pystray.MenuItem("connect", self._connect),
                pystray.MenuItem("disconnect", self._disconnect),
                pystray.MenuItem("exit", self._exit),
            ),
        )
        try:
            self.icon.run(setup=lambda icon: self._connect_last())
        finally:
            self.closed.set()
        return 0

    def start(self) -> "TrayApp":
        thread = threading.Thread(target=self.run, name="xrayctl-tray", daemon=False)
        thread.start()
        return self

    def wait(self) -> bool:
        self.closed.wait()
        return self.exit_requested


def run_tray(connect_last: bool = True, hide_console: bool = True) -> int:
    _require_windows()
    _ensure_dependencies()
    if hide_console:
        _hide_console()
    return TrayApp(connect_last=connect_last).run()


def hide_current() -> bool:
    _require_windows()
    _ensure_dependencies()
    app = TrayApp(connect_last=False, close_on_show=True)
    app.start()
    _hide_console()
    return app.wait()
