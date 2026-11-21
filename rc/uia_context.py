"""通过 Windows UI Automation 读取“选中文字所在段落”。

只覆盖暴露 TextPattern 的阅读器（Edge/Chrome 等 Chromium 系）；Okular 等 Qt
阅读器没有文本层，调用会返回 ok=False，由上层回退到“补充上下文”输入。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_CREATE_NO_WINDOW = 0x08000000


def script_path() -> Path:
    if getattr(sys, "_MEIPASS", None):
        return Path(sys._MEIPASS) / "rc" / "uia_context.ps1"
    return Path(__file__).resolve().parent / "uia_context.ps1"


def read_context(hwnd: int, timeout: float = 2.5) -> dict:
    """返回 {ok, reason, app, selection, paragraph}；失败时 ok=False。"""
    if os.name != "nt" or not hwnd:
        return {"ok": False, "reason": "unsupported"}
    script = script_path()
    if not script.exists():
        return {"ok": False, "reason": "script-missing"}
    command = [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-Hwnd",
        str(int(hwnd)),
    ]
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            timeout=timeout,
            creationflags=_CREATE_NO_WINDOW,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "reason": "timeout"}
    except OSError as exc:
        return {"ok": False, "reason": f"spawn: {exc}"}
    raw = (proc.stdout or b"").decode("utf-8-sig", "replace").strip()
    if not raw:
        return {"ok": False, "reason": "no-output"}
    try:
        data = json.loads(raw.splitlines()[-1])
    except json.JSONDecodeError:
        return {"ok": False, "reason": "bad-json"}
    if not isinstance(data, dict):
        return {"ok": False, "reason": "bad-json"}
    return data
