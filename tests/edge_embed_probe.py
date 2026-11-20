"""探针：把 Edge 的 app 模式窗口用 SetParent 嵌进 Tk 窗口。"""

from __future__ import annotations

import ctypes
import subprocess
import tempfile
import time
from ctypes import wintypes
from pathlib import Path

user32 = ctypes.windll.user32
user32.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
user32.SetWindowLongW.restype = wintypes.LONG
user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
user32.MoveWindow.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.BOOL]

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
GWL_STYLE = -16
WS_CHILD = 0x40000000
WS_POPUP = 0x80000000


def find_window_by_title(needle: str) -> int:
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length:
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            if needle.lower() in buf.value.lower():
                found.append(hwnd)
        return True

    user32.EnumWindows(callback, 0)
    return found[0] if found else 0


def find_window_for_pid(pid: int) -> int:
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _):
        proc_id = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(proc_id))
        if proc_id.value == pid and user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length:
                found.append(hwnd)
        return True

    user32.EnumWindows(callback, 0)
    return found[0] if found else 0


def main() -> int:
    import tkinter as tk

    html = Path(tempfile.gettempdir()) / "rc_edge_probe.html"
    html.write_text(
        "<html><head><title>rcprobe</title></head><body style='background:#111;color:#eee;font:18px sans-serif'>"
        "<h1>Edge 内嵌 OK</h1><p>这是嵌进 Tk 的 Chromium 渲染</p></body></html>",
        encoding="utf-8",
    )

    root = tk.Tk()
    root.geometry("900x600+120+120")
    frame = tk.Frame(root, bg="#222")
    frame.pack(fill="both", expand=True)
    root.update()
    frame_hwnd = int(frame.winfo_id())

    proc = subprocess.Popen(
        [
            EDGE,
            "--app=file:///" + str(html).replace("\\", "/"),
            "--window-size=880,560",
            "--window-position=160,160",
            "--no-first-run",
            "--disable-features=msEdgeSidebarV2",
        ]
    )
    handle = 0
    for _ in range(40):
        time.sleep(0.25)
        handle = find_window_by_title("rcprobe")
        if handle:
            break
    print("edge pid:", proc.pid, "hwnd:", handle, "frame:", frame_hwnd)
    if not handle:
        root.destroy()
        return 1

    user32.SetParent(handle, frame_hwnd)
    style = user32.GetWindowLongW(handle, GWL_STYLE)
    style = (style & ~WS_POPUP) | WS_CHILD
    user32.SetWindowLongW(handle, GWL_STYLE, style)
    user32.MoveWindow(handle, 0, 0, 880, 560, True)
    root.update()

    def resize(_event=None):
        user32.MoveWindow(handle, 0, 0, frame.winfo_width(), frame.winfo_height(), True)

    frame.bind("<Configure>", resize)
    root.update()

    def shot():
        from PIL import ImageGrab

        out = Path(__file__).resolve().parent / "shots" / "edge_embed.png"
        ImageGrab.grab().save(out)
        print("shot saved", out)

    root.after(2500, shot)
    root.after(4000, lambda: (proc.terminate(), root.destroy()))
    root.mainloop()
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
