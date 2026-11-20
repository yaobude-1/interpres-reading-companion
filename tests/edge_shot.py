"""工具：用 Edge app 模式打开 HTML，找到窗口、置前、按窗口范围截图。"""

from __future__ import annotations

import ctypes
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

from PIL import ImageGrab

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
user32 = ctypes.windll.user32


def find_by_title(needle: str) -> int:
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            if needle in buf.value:
                found.append(hwnd)
        return True

    user32.EnumWindows(cb, 0)
    return found[0] if found else 0


def main() -> int:
    html_path = Path(sys.argv[1])
    title = sys.argv[2]
    out = Path(sys.argv[3])
    width = int(sys.argv[4]) if len(sys.argv) > 4 else 900
    height = int(sys.argv[5]) if len(sys.argv) > 5 else 600

    proc = subprocess.Popen(
        [
            EDGE,
            "--app=file:///" + str(html_path).replace("\\", "/"),
            f"--window-size={width},{height}",
            "--window-position=60,40",
            "--no-first-run",
        ]
    )
    hwnd = 0
    for _ in range(60):
        time.sleep(0.25)
        hwnd = find_by_title(title)
        if hwnd:
            break
    if not hwnd:
        print("window not found")
        proc.terminate()
        return 1
    user32.SetForegroundWindow(hwnd)
    user32.SetWindowPos(hwnd, -1, 60, 40, width, height, 0x0040)
    time.sleep(2.5)
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    ImageGrab.grab().crop((rect.left, rect.top, rect.right, rect.bottom)).save(out)
    print("saved", out, (rect.left, rect.top, rect.right, rect.bottom))
    proc.terminate()
    time.sleep(0.5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
