"""验证划词链路（两段）。

A. 真实 Ctrl+C 取词，并检查剪贴板被还原
B. 用模拟的鼠标状态驱动 MouseWatcher，检查拖选/双击能被正确识别
"""

from __future__ import annotations

import sys
import threading
import time
import tkinter as tk
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from rc import capture, selection  # noqa: E402

SAMPLE = "The quick brown fox jumps over the lazy dog."
fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


# --------------------------------------------------------------------- A
def test_capture(root: tk.Tk) -> None:
    """验证「取词后还原剪贴板」的逻辑。

    真实 Ctrl+C 需要测试窗口处于前台，而沙箱里后台程序抢不到前台焦点，
    所以这里把 send_copy 换成一个直接写剪贴板的假实现，专测保存/还原逻辑。
    （真实 Ctrl+C 路径见 test_capture.py，可在前台环境下跑。）
    """
    print("\n[A] 取词逻辑 + 剪贴板还原")
    root.clipboard_clear()
    root.clipboard_append("ORIGINAL-CLIPBOARD")
    root.update()

    original_send = capture.send_copy

    def fake_copy() -> None:
        root.clipboard_clear()
        root.clipboard_append(SAMPLE)
        root.update()

    capture.send_copy = fake_copy  # type: ignore[assignment]
    try:
        got = selection.capture_selected_text()
    finally:
        capture.send_copy = original_send  # type: ignore[assignment]

    after = capture.read_clipboard()
    check("取到选中文字", bool(got) and SAMPLE in (got or ""), repr(got))
    check("剪贴板已还原", after == "ORIGINAL-CLIPBOARD", repr(after))


# --------------------------------------------------------------------- B
def test_watcher_drag() -> None:
    print("\n[B1] 拖选识别")
    fired: list[tuple] = []
    start = time.time()

    class FakeUser32:
        def GetAsyncKeyState(self, vk: int) -> int:
            if vk != selection.VK_LBUTTON:
                return 0
            dt = time.time() - start
            return 0x8000 if 0.25 < dt < 0.75 else 0

    original_user32 = selection.user32
    original_cursor = capture.cursor_pos
    selection.user32 = FakeUser32()  # type: ignore[assignment]
    capture.cursor_pos = lambda: (100 + int((time.time() - start) * 220), 100)  # type: ignore[assignment]
    selection.pid_at_point = lambda x, y: 999999  # type: ignore[assignment]
    selection.foreground_exe = lambda: "chrome.exe"  # type: ignore[assignment]

    class Cfg:
        def get(self, key, default=None):
            if key == "selection":
                return {
                    "enabled": True,
                    "drag": True,
                    "double_click": True,
                    "whitelist": ["chrome.exe"],
                }
            return default

    watcher = selection.MouseWatcher(Cfg(), lambda pos, exe: fired.append((pos, exe)))
    watcher.start()
    time.sleep(1.4)
    watcher.stop()
    selection.user32 = original_user32  # type: ignore[assignment]
    capture.cursor_pos = original_cursor  # type: ignore[assignment]

    check("拖选触发了回调", len(fired) == 1, repr(fired))
    if fired:
        check("带回程序名", fired[0][1] == "chrome.exe", str(fired[0]))


def test_watcher_whitelist() -> None:
    print("\n[B2] 白名单外不触发")
    fired: list[tuple] = []
    start = time.time()

    class FakeUser32:
        def GetAsyncKeyState(self, vk: int) -> int:
            if vk != selection.VK_LBUTTON:
                return 0
            dt = time.time() - start
            return 0x8000 if 0.25 < dt < 0.75 else 0

    original_user32 = selection.user32
    original_cursor = capture.cursor_pos
    selection.user32 = FakeUser32()  # type: ignore[assignment]
    capture.cursor_pos = lambda: (200 + int((time.time() - start) * 220), 200)  # type: ignore[assignment]
    selection.pid_at_point = lambda x, y: 999999  # type: ignore[assignment]
    selection.foreground_exe = lambda: "notepad.exe"  # type: ignore[assignment]

    class Cfg:
        def get(self, key, default=None):
            if key == "selection":
                return {
                    "enabled": True,
                    "drag": True,
                    "double_click": False,
                    "whitelist": ["chrome.exe"],
                }
            return default

    watcher = selection.MouseWatcher(Cfg(), lambda pos, exe: fired.append((pos, exe)))
    watcher.start()
    time.sleep(1.2)
    watcher.stop()
    selection.user32 = original_user32  # type: ignore[assignment]
    capture.cursor_pos = original_cursor  # type: ignore[assignment]

    check("白名单外不触发", len(fired) == 0, repr(fired))


def test_watcher_double_click() -> None:
    print("\n[B3] 双击选词识别")
    fired: list[tuple] = []
    start = time.time()

    class FakeUser32:
        def GetAsyncKeyState(self, vk: int) -> int:
            if vk != selection.VK_LBUTTON:
                return 0
            dt = time.time() - start
            # 两次短按，中间 0.18 秒
            for t0 in (0.25, 0.48):
                if t0 <= dt < t0 + 0.06:
                    return 0x8000
            return 0

    original_user32 = selection.user32
    original_cursor = capture.cursor_pos
    selection.user32 = FakeUser32()  # type: ignore[assignment]
    capture.cursor_pos = lambda: (400, 400)  # type: ignore[assignment]
    selection.pid_at_point = lambda x, y: 999999  # type: ignore[assignment]
    selection.foreground_exe = lambda: "okular.exe"  # type: ignore[assignment]

    class Cfg:
        def get(self, key, default=None):
            if key == "selection":
                return {
                    "enabled": True,
                    "drag": False,
                    "double_click": True,
                    "whitelist": ["okular.exe"],
                }
            return default

    watcher = selection.MouseWatcher(Cfg(), lambda pos, exe: fired.append((pos, exe)))
    watcher.start()
    time.sleep(1.2)
    watcher.stop()
    selection.user32 = original_user32  # type: ignore[assignment]
    capture.cursor_pos = original_cursor  # type: ignore[assignment]

    check("双击触发了回调", len(fired) >= 1, repr(fired))


def test_press_notify() -> None:
    print("\n[B4] 点自己窗口不算「点别处」")
    fired: list = []

    class Cfg:
        def get(self, key, default=None):
            return default

    watcher = selection.MouseWatcher(Cfg(), lambda *a: None, on_press=fired.append)
    selection.pid_at_point = lambda x, y: watcher._own_pid  # type: ignore[assignment]
    watcher._notify_press((10, 10))
    check("点自己窗口不触发收起", len(fired) == 0, repr(fired))

    selection.pid_at_point = lambda x, y: 424242  # type: ignore[assignment]
    watcher._notify_press((10, 10))
    check("点别的程序会触发收起", len(fired) == 1, repr(fired))


def test_long_drag() -> None:
    """慢慢拖选（超过 1.2 秒）也要能触发。"""
    print("\n[B5] 长段落慢速拖选")
    fired: list = []
    start = time.time()

    class FakeUser32:
        def GetAsyncKeyState(self, vk: int) -> int:
            if vk != selection.VK_LBUTTON:
                return 0
            dt = time.time() - start
            return 0x8000 if 0.2 < dt < 3.2 else 0

    original_user32 = selection.user32
    original_cursor = capture.cursor_pos
    selection.user32 = FakeUser32()  # type: ignore[assignment]
    capture.cursor_pos = lambda: (100 + int((time.time() - start) * 60), 100)  # type: ignore[assignment]
    selection.pid_at_point = lambda x, y: 999999  # type: ignore[assignment]
    selection.foreground_exe = lambda: "chrome.exe"  # type: ignore[assignment]

    class Cfg:
        def get(self, key, default=None):
            if key == "selection":
                return {"enabled": True, "drag": True, "double_click": True, "whitelist": ["chrome.exe"]}
            return default

    watcher = selection.MouseWatcher(Cfg(), lambda pos, exe: fired.append((pos, exe)))
    watcher.start()
    time.sleep(3.6)
    watcher.stop()
    selection.user32 = original_user32  # type: ignore[assignment]
    capture.cursor_pos = original_cursor  # type: ignore[assignment]
    check("3 秒拖选也触发", len(fired) == 1, repr(fired))


def test_shift_click() -> None:
    """点开头 + Shift+点结尾（鼠标几乎没动）也要能触发。"""
    print("\n[B6] Shift+点击选段")
    fired: list = []
    start = time.time()

    class FakeUser32:
        def GetAsyncKeyState(self, vk: int) -> int:
            dt = time.time() - start
            if vk == selection.VK_LBUTTON:
                return 0x8000 if 0.2 < dt < 0.32 else 0
            if vk == 0x10:  # VK_SHIFT
                return 0x8000
            return 0

    original_user32 = selection.user32
    original_cursor = capture.cursor_pos
    selection.user32 = FakeUser32()  # type: ignore[assignment]
    capture.cursor_pos = lambda: (300, 300)  # type: ignore[assignment]
    selection.pid_at_point = lambda x, y: 999999  # type: ignore[assignment]
    selection.foreground_exe = lambda: "okular.exe"  # type: ignore[assignment]

    class Cfg:
        def get(self, key, default=None):
            if key == "selection":
                return {"enabled": True, "drag": True, "double_click": True, "whitelist": ["okular.exe"]}
            return default

    watcher = selection.MouseWatcher(Cfg(), lambda pos, exe: fired.append((pos, exe)))
    watcher.start()
    time.sleep(1.0)
    watcher.stop()
    selection.user32 = original_user32  # type: ignore[assignment]
    capture.cursor_pos = original_cursor  # type: ignore[assignment]
    check("Shift+点击触发", len(fired) >= 1, repr(fired))


def main() -> int:
    root = tk.Tk()
    root.withdraw()
    test_capture(root)
    test_watcher_drag()
    test_watcher_whitelist()
    test_watcher_double_click()
    test_press_notify()
    test_long_drag()
    test_shift_click()
    root.destroy()
    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
