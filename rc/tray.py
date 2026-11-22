"""系统托盘图标：隐藏主窗口后仍能从任务栏托盘打开/退出。

依赖 pystray（打包在 vendor 目录里）。pystray 的回调运行在它自己的线程，
这里只负责把动作转成回调，交给主线程的 Tk 事件队列处理。
"""

from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path
from typing import Callable

log = logging.getLogger("rc")


def _ensure_vendor() -> None:
    root = Path(__file__).resolve().parent.parent
    vendor = root / "vendor"
    if vendor.is_dir() and str(vendor) not in sys.path and not getattr(sys, "frozen", False):
        sys.path.insert(0, str(vendor))


class TrayIcon:
    def __init__(
        self,
        icon_path: Path,
        on_open_panel: Callable[[], None],
        on_open_settings: Callable[[], None],
        on_quit: Callable[[], None],
        title: str = "Interpres",
    ) -> None:
        self.icon_path = Path(icon_path)
        self.on_open_panel = on_open_panel
        self.on_open_settings = on_open_settings
        self.on_quit = on_quit
        self.title = title
        self._icon = None
        self._thread: threading.Thread | None = None
        self._failed = False
        self._error = ""

    @property
    def active(self) -> bool:
        return self._icon is not None and self._thread is not None and self._thread.is_alive()

    @property
    def error(self) -> str:
        return self._error

    def start(self) -> bool:
        if self.active:
            return True
        try:
            _ensure_vendor()
            import pystray
            from PIL import Image
        except Exception as exc:  # noqa: BLE001
            self._failed = True
            self._error = f"{type(exc).__name__}: {exc}"
            return False
        try:
            image = Image.open(self.icon_path)
            menu = pystray.Menu(
                pystray.MenuItem("打开主面板", self._open_panel, default=True),
                pystray.MenuItem("打开设置", self._open_settings),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("退出 Interpres", self._quit),
            )
            self._icon = pystray.Icon("Interpres", image, self.title, menu)
            self._thread = threading.Thread(
                target=self._run, name="tray", daemon=True
            )
            self._thread.start()
            return True
        except Exception as exc:  # noqa: BLE001
            self._failed = True
            self._error = f"{type(exc).__name__}: {exc}"
            self._icon = None
            return False

    def _run(self) -> None:
        try:
            if self._icon is not None:
                self._icon.run()
        except Exception as exc:  # noqa: BLE001
            self._failed = True
            self._error = f"{type(exc).__name__}: {exc}"

    # pystray 会传 (icon, item)，这里的转发都只是往队列里放动作
    def _open_panel(self, *_args) -> None:
        self.on_open_panel()

    def _open_settings(self, *_args) -> None:
        self.on_open_settings()

    def _quit(self, *_args) -> None:
        self.on_quit()

    def notify(self, message: str, title: str = "Interpres") -> None:
        try:
            if self._icon is not None:
                self._icon.notify(message, title)
        except (OSError, RuntimeError) as exc:  # noqa: BLE001 - 通知失败可忽略
            log.debug("托盘通知失败: %s", exc)

    def stop(self) -> None:
        icon = self._icon
        self._icon = None
        if icon is not None:
            try:
                icon.stop()
            except (OSError, RuntimeError) as exc:  # noqa: BLE001 - 退出时尽力停止
                log.debug("停止托盘图标失败: %s", exc)
        thread = self._thread
        self._thread = None
        if thread is not None and thread.is_alive():
            try:
                thread.join(timeout=1.0)
            except RuntimeError as exc:  # noqa: BLE001 - 线程未启动时 join 会报错
                log.debug("等待托盘线程退出失败: %s", exc)
