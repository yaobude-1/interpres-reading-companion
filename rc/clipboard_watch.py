"""Clipboard watcher: reading-app copies become lookup/translation requests."""

from __future__ import annotations

import ctypes
import logging
import re
import tkinter as tk

from . import textutil
from .selection import foreground_exe

log = logging.getLogger("rc")

_OWN_EXES = {"python.exe", "pythonw.exe", "interpres.exe"}
_URL = re.compile(r"^(?:https?://|www\.|mailto:)", re.IGNORECASE)
_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_PATH = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\)")
_NUMBERS = re.compile(r"^[\d\s.,%+\-]+$")


class _Point(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def _cursor_pos() -> tuple[int, int]:
    try:
        point = _Point()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
        return int(point.x), int(point.y)
    except Exception:
        return 200, 200


class ClipboardWatcher:
    def __init__(self, root: tk.Tk, config, on_text) -> None:
        self.root = root
        self.config = config
        self.on_text = on_text
        self._last_text = ""
        self._seq = self._sequence()

    @staticmethod
    def _sequence() -> int:
        try:
            return int(ctypes.windll.user32.GetClipboardSequenceNumber())
        except Exception:
            return 0

    def _enabled(self) -> bool:
        selection = self.config.get("selection") or {}
        return bool(selection.get("clipboard_enabled", True))

    def _allowed_app(self) -> bool:
        try:
            exe = (foreground_exe() or "").lower()
        except Exception:
            return False
        if not exe or exe in _OWN_EXES:
            return False
        selection = self.config.get("selection") or {}
        allowed = [str(item).lower() for item in (selection.get("whitelist") or [])]
        return not allowed or exe in allowed

    @staticmethod
    def _usable(text: str) -> str:
        text = textutil.normalize(text or "")
        if not text or len(text) > 4000:
            return ""
        if _URL.match(text) or _EMAIL.match(text) or _PATH.match(text) or _NUMBERS.match(text):
            return ""
        if text.count("\n") > 40:
            return ""
        return text

    def poll(self) -> None:
        sequence = self._sequence()
        if sequence == self._seq:
            return
        self._seq = sequence
        if not self._enabled():
            self._last_text = ""
            return
        if not self._allowed_app():
            return
        try:
            text = self.root.clipboard_get()
        except (tk.TclError, UnicodeDecodeError):
            return
        text = self._usable(text)
        if not text or text == self._last_text:
            return
        self._last_text = text
        try:
            self.on_text(text, _cursor_pos())
        except Exception as exc:  # noqa: BLE001 - clipboard callback must not kill pump
            log.debug("剪贴板事件处理失败: %s", exc)
