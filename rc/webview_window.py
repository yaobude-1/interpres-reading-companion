"""Standalone original-layout window backed by the same WebView2 host as the panel."""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import messagebox

from .theme import BG

log = logging.getLogger("rc")


class WebViewEntryWindow:
    def __init__(self, root: tk.Tk, title: str = "原版条目", on_lookup=None) -> None:
        self.root = root
        self.on_lookup = on_lookup
        self.win = tk.Toplevel(root)
        self.win.title(title)
        self.win.configure(bg=BG)
        self.win.geometry("900x800")
        self.win.attributes("-topmost", True)
        self.frame = tk.Frame(self.win, bg=BG)
        self.frame.pack(fill="both", expand=True)
        self.host = None
        self.win.protocol("WM_DELETE_WINDOW", self.close)

    def ensure(self) -> bool:
        if self.host is not None:
            return True
        try:
            from .webview_host import WebViewHost

            self.host = WebViewHost(self.frame, on_lookup=self._lookup)
        except Exception as exc:  # noqa: BLE001 - 原版不可用时只影响这个窗口
            messagebox.showerror("原版不可用", f"WebView2 初始化失败：{exc}", parent=self.win)
            self.close()
            return False
        if self.host.ensure():
            return True
        messagebox.showerror(
            "原版不可用",
            self.host.error or "WebView2 初始化失败",
            parent=self.win,
        )
        self.close()
        return False

    def show(self, url: str, word: str = "") -> None:
        if not self.ensure():
            return
        self.win.title(f"原版 · {word}" if word else "原版条目")
        self.win.deiconify()
        self.win.lift()
        self.host.load_url(url)

    def load(self, url: str, word: str = "") -> None:
        if self.host is None:
            self.show(url, word)
            return
        self.win.title(f"原版 · {word}" if word else "原版条目")
        self.host.load_url(url)

    def _lookup(self, word: str) -> None:
        if self.on_lookup is not None:
            try:
                self.on_lookup(word)
            except Exception as exc:  # noqa: BLE001 - 页面内跳转失败只记录
                log.debug("原版内部跳转失败: %s", exc)

    def close(self) -> None:
        if self.host is not None:
            try:
                self.host.dispose()
            except Exception as exc:  # noqa: BLE001 - 关闭时 WebView 失败不影响窗口销毁
                log.debug("关闭原版窗口失败: %s", exc)
            self.host = None
        try:
            self.win.destroy()
        except tk.TclError:
            pass
