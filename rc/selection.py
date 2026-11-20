"""划词检测。

Windows 没有「选区变化」的全局事件，所以这里用最通用的办法：

1. 轮询鼠标，发现「拖选」或「双击选词」；
2. 只对白名单里的程序下手（终端、编辑器绝不碰）；
3. 替你按一次 Ctrl+C 取出选中文字，再把你原来的剪贴板文本还回去。

整个过程在你松手后约 0.15 秒内完成，然后弹出「译」按钮。
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import threading
import time
from pathlib import Path

from . import capture

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

VK_LBUTTON = 0x01
VK_SHIFT = 0x10
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
GMEM_MOVEABLE = 0x0002

user32.WindowFromPoint.restype = wt.HWND
user32.WindowFromPoint.argtypes = [wt.POINT]
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.GetAncestor.argtypes = [wt.HWND, wt.UINT]
user32.GetAncestor.restype = wt.HWND
kernel32.OpenProcess.restype = wt.HANDLE
kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
kernel32.QueryFullProcessImageNameW.argtypes = [
    wt.HANDLE,
    wt.DWORD,
    wt.LPWSTR,
    ctypes.POINTER(wt.DWORD),
]
kernel32.GlobalAlloc.restype = ctypes.c_void_p
kernel32.GlobalAlloc.argtypes = [wt.UINT, ctypes.c_size_t]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
user32.SetClipboardData.argtypes = [wt.UINT, wt.HANDLE]
user32.SetClipboardData.restype = wt.HANDLE

GA_ROOT = 2
CF_UNICODETEXT = 13


# ---------------------------------------------------------------- 进程 / 窗口
def exe_name(pid: int) -> str:
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(520)
        size = wt.DWORD(520)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return ""
        return Path(buf.value).name.lower()
    finally:
        kernel32.CloseHandle(handle)


def window_pid(hwnd: int) -> int:
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)


def foreground_exe() -> str:
    return exe_name(window_pid(user32.GetForegroundWindow()))


def pid_at_point(x: int, y: int) -> int:
    point = wt.POINT(x, y)
    hwnd = user32.WindowFromPoint(point)
    if not hwnd:
        return 0
    return window_pid(user32.GetAncestor(hwnd, GA_ROOT) or hwnd)


# ------------------------------------------------------------------- 剪贴板
def clipboard_has_text() -> bool:
    return bool(user32.IsClipboardFormatAvailable(CF_UNICODETEXT))


def set_clipboard_text(text: str) -> bool:
    data = text.encode("utf-16-le") + b"\x00\x00"
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
    if not handle:
        return False
    pointer = kernel32.GlobalLock(handle)
    if not pointer:
        kernel32.GlobalFree(handle)
        return False
    ctypes.memmove(pointer, data, len(data))
    kernel32.GlobalUnlock(handle)
    if not user32.OpenClipboard(None):
        kernel32.GlobalFree(handle)
        return False
    try:
        user32.EmptyClipboard()
        user32.SetClipboardData(CF_UNICODETEXT, handle)
    finally:
        user32.CloseClipboard()
    return True


def capture_selected_text(timeout: float = 1.2) -> str | None:
    """模拟 Ctrl+C 取选区文字，并尽量还原原来的剪贴板文本。"""
    original = capture.read_clipboard()
    had_text = clipboard_has_text()
    before = capture.clipboard_sequence()
    capture.send_copy()

    deadline = time.time() + timeout
    text: str | None = None
    while time.time() < deadline:
        if capture.clipboard_sequence() != before:
            text = capture.read_clipboard()
            break
        time.sleep(0.02)

    if text and had_text and original is not None and text != original:
        try:
            set_clipboard_text(original)
        except Exception:
            pass
    return text


# ------------------------------------------------------------------ 鼠标监听
class MouseWatcher(threading.Thread):
    def __init__(self, config, on_selection, on_press=None) -> None:
        super().__init__(daemon=True, name="mouse")
        self.config = config
        self.on_selection = on_selection
        self.on_press = on_press
        self._stop = threading.Event()
        self._own_pid = ctypes.windll.kernel32.GetCurrentProcessId()

    def run(self) -> None:
        down = False
        press_at = (0, 0)
        last_click_time = 0.0
        last_fire = 0.0

        while not self._stop.is_set():
            state = bool(user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000)
            now = time.time()
            pos = capture.cursor_pos()

            if state and not down:
                down = True
                press_at = pos
                self._notify_press(pos)
            elif not state and down:
                down = False
                dx = pos[0] - press_at[0]
                dy = pos[1] - press_at[1]
                moved = (dx * dx + dy * dy) ** 0.5
                # 不再限制按住时长：选长段落经常要拖好几秒
                dragged = moved > 6
                double = (now - last_click_time) < 0.42 and moved <= 6
                shift_down = bool(user32.GetAsyncKeyState(VK_SHIFT) & 0x8000)
                shift_click = shift_down and moved <= 6

                if moved <= 6:
                    last_click_time = now
                else:
                    last_click_time = 0.0

                cfg = self.config.get("selection") or {}
                want = (dragged and cfg.get("drag", True)) or (
                    shift_click and cfg.get("drag", True)
                ) or (double and cfg.get("double_click", True))
                if want and (now - last_fire) > 0.45:
                    last_fire = now
                    try:
                        self._maybe_fire(pos)
                    except Exception:
                        pass
            time.sleep(0.02)

    def _notify_press(self, pos: tuple[int, int]) -> None:
        """任何点在「别的程序」上的点击，通知上层收起按钮/气泡。"""
        if not self.on_press:
            return
        try:
            if pid_at_point(*pos) == self._own_pid:
                return
            self.on_press(pos)
        except Exception:
            pass

    def _maybe_fire(self, pos: tuple[int, int]) -> None:
        cfg = self.config.get("selection") or {}
        if not cfg.get("enabled", True):
            return
        # 鼠标在自己窗口上（点按钮、拖气泡）不触发
        if pid_at_point(*pos) == self._own_pid:
            return
        exe = foreground_exe()
        if not exe or exe in ("pythonw.exe", "python.exe"):
            return
        allowed = [str(x).lower() for x in (cfg.get("whitelist") or [])]
        if allowed and exe not in allowed:
            return
        self.on_selection(pos, exe)

    def stop(self) -> None:
        self._stop.set()
