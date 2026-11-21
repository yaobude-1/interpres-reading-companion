"""Live UI Automation test: real Edge window -> real PS helper -> paragraph.

Opt-in because it launches a visible Edge window and needs an interactive
desktop; run it locally with:

    set INTERPRES_LIVE_UIA=1
    python tests\\test_uia_live.py

CI covers the parsing/wiring path in test_chat_context.py; this test is the
evidence that the PowerShell -> UIAutomationClient -> TextPattern chain works
against a real browser.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from rc.uia_context import read_context  # noqa: E402

EDGES = [
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
]

MARKER = "quick brown fox jumps over the lazy dog"


def find_edge() -> Path | None:
    return next((path for path in EDGES if path.exists()), None)


def find_window(title: str) -> int:
    user32 = ctypes.windll.user32
    user32.FindWindowW.restype = ctypes.c_void_p
    user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
    return int(user32.FindWindowW(None, title) or 0)


def main() -> int:
    if os.name != "nt":
        print("skip: not Windows")
        return 0
    if os.environ.get("INTERPRES_LIVE_UIA") != "1":
        print("skip: set INTERPRES_LIVE_UIA=1 to run the live Edge test")
        return 0
    edge = find_edge()
    if edge is None:
        print("skip: Edge not installed")
        return 0

    work = Path(tempfile.mkdtemp(prefix="interpres-uia-live-"))
    html = work / "sample.html"
    profile = work / "profile"
    html.write_text(
        "<!doctype html><meta charset='utf-8'><title>Interpres UIA Live</title>"
        "<p>The quick brown fox jumps over the lazy dog. "
        "A second sentence keeps the paragraph long enough to be useful.</p>",
        encoding="utf-8",
    )
    proc = subprocess.Popen(
        [str(edge), f"--app={html.as_uri()}", "--no-first-run",
         "--no-default-browser-check", "--disable-sync",
         "--disable-features=msEdgeSyncPromo,msEdgeIdentityPromptForSignIn",
         f"--user-data-dir={profile}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    hwnd = 0
    try:
        deadline = time.time() + 25
        while time.time() < deadline:
            time.sleep(0.5)
            hwnd = find_window("Interpres UIA Live")
            if hwnd:
                break
        if not hwnd:
            print("FAIL: Edge window did not appear")
            return 2
        time.sleep(3)
        user32 = ctypes.windll.user32
        user32.SetWindowPos.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
            ctypes.c_int, ctypes.c_int, ctypes.c_uint,
        ]
        user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
        user32.SetWindowPos(ctypes.c_void_p(hwnd), ctypes.c_void_p(-1), 0, 0, 0, 0, 0x0003)
        user32.SetForegroundWindow(ctypes.c_void_p(hwnd))
        time.sleep(1)
        # Click the page once so the renderer owns keyboard/UIA focus.
        rect = ctypes.wintypes.RECT()
        user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.wintypes.RECT)]
        user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(rect))
        cx = (rect.left + rect.right) // 2
        cy = (rect.top + rect.bottom) // 2
        user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
        user32.SetCursorPos(cx, cy)
        user32.mouse_event.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.c_int, ctypes.c_uint, ctypes.c_void_p]
        user32.mouse_event(0x0002, 0, 0, 0, None)
        time.sleep(0.1)
        user32.mouse_event(0x0004, 0, 0, 0, None)
        time.sleep(0.8)
        selected = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(HERE / "uia_live_select.ps1"), "-Hwnd", str(hwnd)],
            capture_output=True,
            timeout=30,
            check=False,
        )
        print("select rc:", selected.returncode)
        print("select out:", selected.stdout.decode("utf-8", "replace").strip())
        print("select err:", selected.stderr.decode("utf-8", "replace").strip()[:300])
        info = read_context(hwnd, timeout=8.0)
        print("read_context:", info)
        ok = bool(info.get("ok")) and MARKER in (info.get("paragraph") or "")
        selection = (info.get("selection") or "").strip()
        print(("ok   " if ok else "FAIL ") + f"paragraph contains marker, selection={selection!r}")
        return 0 if ok else 1
    finally:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
