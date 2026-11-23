"""WebView2 host embedded in a Tk frame (Windows only).

This module is intentionally optional: importing it must not require pythonnet
or the WebView2 SDK.  Call :meth:`WebViewHost.ensure` and handle a False return
when the runtime is unavailable.
"""

from __future__ import annotations

import ctypes
import logging
import os
import shutil
import sys
import tempfile
import time
import tkinter as tk
import uuid
import webbrowser
from ctypes import wintypes
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

log = logging.getLogger("rc")

WEBVIEW2_DIR = Path(__file__).resolve().parent / "webview2"

_GWL_STYLE = -16
_WS_CHILD = 0x40000000
_WS_VISIBLE = 0x10000000
_WS_POPUP = 0x80000000
_WS_CAPTION = 0x00C00000
_WS_THICKFRAME = 0x00040000
_SW_HIDE = 0
_SW_SHOW = 5


def _user32():
    if sys.platform != "win32":
        return None
    user32 = ctypes.windll.user32
    user32.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
    user32.SetParent.restype = wintypes.HWND
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongW.restype = ctypes.c_long
    user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
    user32.SetWindowLongW.restype = ctypes.c_long
    user32.MoveWindow.argtypes = [
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.BOOL,
    ]
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    return user32


class WebViewHost:
    """One WinForms WebView2 control parented into a Tk frame."""

    def __init__(
        self,
        frame,
        *,
        lib_dir: Path | str = WEBVIEW2_DIR,
        user_data: Path | str | None = None,
        on_lookup=None,
    ) -> None:
        self.frame = frame
        self.lib_dir = Path(lib_dir)
        self.user_data = (
            Path(user_data)
            if user_data
            else Path(tempfile.gettempdir())
            / f"interpres-webview2-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        )
        self.on_lookup = on_lookup
        self.error = ""
        self._panel = None
        self._webview = None
        self._hwnd = 0
        self._active = False
        self._pump_id = None
        self._pump_paused_until = 0.0
        self._active_until = 0.0
        self._configure_bound = False
        self._last_size = (0, 0)
        self._nav_handler = None
        self._window_handler = None
        try:
            self.frame.bind("<Destroy>", self._on_frame_destroy, add="+")
        except Exception as exc:  # noqa: BLE001
            log.debug("绑定 WebView 销毁事件失败: %s", exc)

    # ------------------------------------------------------------------ status
    @property
    def active(self) -> bool:
        return self._active

    def _fail(self, message: str) -> bool:
        self.error = message
        log.warning("WebView2: %s", message)
        return False

    # ------------------------------------------------------------------ setup
    def ensure(self) -> bool:
        if self._active:
            return True
        if sys.platform != "win32":
            return self._fail("WebView2 只支持 Windows")
        if not (self.lib_dir / "Microsoft.Web.WebView2.WinForms.dll").exists():
            return self._fail(f"找不到 WebView2 SDK：{self.lib_dir}")
        if not (self.lib_dir / "WebView2Loader.dll").exists():
            return self._fail(f"找不到 WebView2Loader.dll：{self.lib_dir}")

        try:
            import pythonnet

            try:
                pythonnet.load("netfx")
            except Exception as exc:  # noqa: BLE001 - 可能已经加载
                log.debug("pythonnet.load: %s", exc)
            import clr
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"pythonnet 不可用：{exc}")

        try:
            ctypes.windll.ole32.CoInitializeEx(None, 2)
        except Exception as exc:  # noqa: BLE001
            log.debug("WebView2 host: %s", exc)

        # .NET Framework 在部分用户目录（Documents/云同步）会把程序集当成
        # “网络位置”拒绝 LoadFrom；复制到本地临时目录再加载。
        load_dir = (
            Path(tempfile.gettempdir())
            / f"interpres-webview2-sdk-{os.getpid()}"
        )
        try:
            load_dir.mkdir(parents=True, exist_ok=True)
            for name in (
                "Microsoft.Web.WebView2.Core.dll",
                "Microsoft.Web.WebView2.WinForms.dll",
                "WebView2Loader.dll",
            ):
                source = self.lib_dir / name
                target = load_dir / name
                if not target.exists() or target.stat().st_size != source.stat().st_size:
                    shutil.copyfile(source, target)
        except OSError as exc:
            return self._fail(f"复制 WebView2 SDK 失败：{exc}")

        try:
            os.add_dll_directory(str(load_dir))
        except (AttributeError, OSError):
            pass

        try:
            clr.AddReference("System.Windows.Forms")
            clr.AddReference("System.Drawing")
            clr.AddReference(str(load_dir / "Microsoft.Web.WebView2.Core.dll"))
            clr.AddReference(str(load_dir / "Microsoft.Web.WebView2.WinForms.dll"))
            from System.Drawing import Color
            from System.Windows.Forms import Application, DockStyle, Panel
            from Microsoft.Web.WebView2.Core import CoreWebView2Environment
            from Microsoft.Web.WebView2.WinForms import WebView2
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"加载 WebView2 程序集失败：{exc}")

        self._Application = Application
        self._CoreWebView2Environment = CoreWebView2Environment

        try:
            Application.EnableVisualStyles()
            panel = Panel()
            panel.Dock = DockStyle.Fill
            panel.BackColor = Color.FromArgb(21, 27, 36)
            panel.CreateControl()
            hwnd = int(panel.Handle.ToInt64())
            parent = int(self.frame.winfo_id())

            user32 = _user32()
            if user32 is None:
                return self._fail("user32 不可用")
            user32.SetParent(hwnd, parent)
            style = user32.GetWindowLongW(hwnd, _GWL_STYLE)
            style = (style | _WS_CHILD | _WS_VISIBLE) & ~(_WS_POPUP | _WS_CAPTION | _WS_THICKFRAME)
            user32.SetWindowLongW(hwnd, _GWL_STYLE, style)

            webview = WebView2()
            webview.Dock = DockStyle.Fill
            panel.Controls.Add(webview)
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"创建 WebView2 控件失败：{exc}")

        self._panel = panel
        self._webview = webview
        self._hwnd = hwnd

        try:
            self.frame.bind("<Configure>", self._on_configure)
            self._configure_bound = True
            self._resize()

            env_task = CoreWebView2Environment.CreateAsync(None, str(self.user_data), None)
            if not self._wait_task(env_task, 10):
                return self._fail("WebView2 环境初始化超时（10 秒）")
            env = env_task.Result
            ensure_task = webview.EnsureCoreWebView2Async(env)
            if not self._wait_task(ensure_task, 10):
                return self._fail("WebView2 初始化超时（10 秒）")
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"WebView2 初始化失败：{exc}")

        try:
            settings = webview.CoreWebView2.Settings
            settings.AreDefaultContextMenusEnabled = False
            settings.AreDevToolsEnabled = False
            settings.IsStatusBarEnabled = False
            settings.AreDefaultScriptDialogsEnabled = False
        except Exception as exc:  # noqa: BLE001
            log.debug("WebView2 host: %s", exc)

        try:
            self._nav_handler = self._on_navigation_starting
            self._window_handler = self._on_new_window
            webview.CoreWebView2.NavigationStarting += self._nav_handler
            webview.CoreWebView2.NewWindowRequested += self._window_handler
        except Exception as exc:  # noqa: BLE001
            log.debug("WebView2 事件绑定失败: %s", exc)

        self._active = True
        self._touch(3.0)
        self._pump()
        return True

    # ------------------------------------------------------------------- loop
    def _on_frame_destroy(self, event) -> None:
        if event.widget is not self.frame:
            return
        self._active = False
        if self._pump_id is not None:
            try:
                self.frame.after_cancel(self._pump_id)
            except Exception as exc:  # noqa: BLE001
                log.debug("取消 WebView 定时器失败: %s", exc)
            self._pump_id = None

    def _wait_task(self, task, timeout: float) -> bool:
        end = time.time() + timeout
        while not task.IsCompleted and time.time() < end:
            self._do_events()
        return bool(task.IsCompleted)

    def _do_events(self) -> None:
        try:
            self._Application.DoEvents()
        except Exception as exc:  # noqa: BLE001
            log.debug("WebView2 host: %s", exc)
        try:
            self.frame.update()
        except Exception as exc:  # noqa: BLE001
            log.debug("WebView2 host: %s", exc)

    def _pump(self) -> None:
        if not self._active:
            self._pump_id = None
            return
        if time.time() < self._pump_paused_until:
            # 用户正在拖动/缩放 Tk 窗口时不要跑 DoEvents，否则会打断
            # Windows 的移动/缩放模态循环，表现为窗口跳回原位。
            try:
                self._pump_id = self.frame.after(30, self._pump)
            except Exception:
                self._pump_id = None
            return
        try:
            self._Application.DoEvents()
        except Exception as exc:  # noqa: BLE001
            log.debug("WebView2 host: %s", exc)
        interval = 15 if time.time() < self._active_until else 45
        try:
            self._pump_id = self.frame.after(interval, self._pump)
        except Exception:  # noqa: BLE001
            self._pump_id = None

    def pause(self, seconds: float = 0.25) -> None:
        """Pause the WinForms message pump while Tk is moving/resizing."""
        self._pump_paused_until = max(self._pump_paused_until, time.time() + seconds)

    def _touch(self, seconds: float = 2.0) -> None:
        self._active_until = max(self._active_until, time.time() + seconds)

    # ------------------------------------------------------------------ events
    def _on_navigation_starting(self, _sender, args) -> None:
        try:
            uri = str(args.Uri or "")
        except Exception:  # noqa: BLE001
            return
        low = uri.lower()
        if low.startswith("interpres://lookup"):
            try:
                args.Cancel = True
            except Exception as exc:  # noqa: BLE001
                log.debug("取消内部链接失败: %s", exc)
            word = (parse_qs(urlparse(uri).query).get("word") or [""])[0].strip()
            if word and self.on_lookup is not None:
                try:
                    self.frame.after(0, lambda w=word: self.on_lookup(w))
                except Exception as exc:  # noqa: BLE001
                    log.debug("WebView2 lookup callback: %s", exc)
            return
        if low.startswith(("http://", "https://")):
            host = (urlparse(uri).hostname or "").lower()
            if host not in ("127.0.0.1", "localhost"):
                try:
                    args.Cancel = True
                except Exception as exc:  # noqa: BLE001
                    log.debug("取消外部导航失败: %s", exc)
                try:
                    webbrowser.open(uri)
                except Exception as exc:  # noqa: BLE001
                    log.debug("打开外部链接失败: %s", exc)
            return
        if low.startswith(("file:", "javascript:", "vbscript:", "data:", "about:", "edge:", "ms-appx:", "ms-appdata:", "blob:")):
            try:
                args.Cancel = True
            except Exception as exc:  # noqa: BLE001
                log.debug("取消危险导航失败: %s", exc)

    def _on_new_window(self, _sender, args) -> None:
        try:
            args.Handled = True
            uri = str(args.Uri or "")
            if uri.lower().startswith(("http://", "https://")):
                webbrowser.open(uri)
        except Exception as exc:  # noqa: BLE001
            log.debug("处理新窗口失败: %s", exc)

    # ----------------------------------------------------------------- layout
    def _on_configure(self, _event=None) -> None:
        try:
            size = (self.frame.winfo_width(), self.frame.winfo_height())
        except tk.TclError:
            return
        if size == self._last_size:
            return
        self._last_size = size
        self._resize()

    def _resize(self) -> None:
        if not self._hwnd:
            return
        try:
            width = max(1, self.frame.winfo_width())
            height = max(1, self.frame.winfo_height())
            _user32().MoveWindow(self._hwnd, 0, 0, width, height, True)
        except Exception as exc:  # noqa: BLE001
            log.debug("WebView2 host: %s", exc)

    def resize(self) -> None:
        """Public resize hook for the owning Tk layout."""
        self._touch(0.6)
        self._resize()

    def show(self) -> None:
        if self._hwnd:
            try:
                _user32().ShowWindow(self._hwnd, _SW_SHOW)
            except Exception as exc:  # noqa: BLE001
                log.debug("WebView2 host: %s", exc)

    def hide(self) -> None:
        if self._hwnd:
            try:
                _user32().ShowWindow(self._hwnd, _SW_HIDE)
            except Exception as exc:  # noqa: BLE001
                log.debug("WebView2 host: %s", exc)

    # ---------------------------------------------------------------- content
    def load_url(self, url: str) -> bool:
        if not self.ensure():
            return False
        self._touch()
        try:
            self._webview.CoreWebView2.Navigate(url)
            return True
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"加载页面失败：{exc}")

    def load_html(self, html: str) -> bool:
        if not self.ensure():
            return False
        self._touch()
        try:
            self._webview.CoreWebView2.NavigateToString(html)
            return True
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"加载 HTML 失败：{exc}")

    def execute_script(self, script: str) -> Any:
        if not self.ensure():
            return None
        self._touch()
        try:
            return self._webview.CoreWebView2.ExecuteScriptAsync(script)
        except Exception as exc:  # noqa: BLE001
            self._fail(f"执行 JS 失败：{exc}")
            return None

    # ------------------------------------------------------------------ close
    def dispose(self) -> None:
        self._active = False
        if self._pump_id is not None:
            try:
                self.frame.after_cancel(self._pump_id)
            except Exception as exc:  # noqa: BLE001
                log.debug("WebView2 host: %s", exc)
            self._pump_id = None
        if self._configure_bound:
            try:
                self.frame.unbind("<Configure>")
            except Exception as exc:  # noqa: BLE001
                log.debug("WebView2 host: %s", exc)
            self._configure_bound = False
        self.hide()
        for attr in ("_webview", "_panel"):
            obj = getattr(self, attr, None)
            if obj is not None:
                try:
                    obj.Dispose()
                except Exception as exc:  # noqa: BLE001
                    log.debug("WebView2 host: %s", exc)
                setattr(self, attr, None)
        self._hwnd = 0
        try:
            shutil.rmtree(self.user_data, ignore_errors=True)
        except OSError:
            pass
