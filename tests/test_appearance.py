"""Appearance: palette presets, import-time theme, popup opacity."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tkinter as tk
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from rc import theme  # noqa: E402
from rc.config import Config  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


def main() -> int:
    data = HERE / ".appearance"
    shutil.rmtree(data, ignore_errors=True)
    data.mkdir(parents=True)

    print("\n[调色板]")
    dark = theme.palette("dark", "blue")
    light = theme.palette("light", "blue")
    check("深色背景", dark["BG"] == "#1b1d24", dark["BG"])
    check("浅色背景", light["BG"] == "#f4f5f7", light["BG"])
    check("强调色预设", theme.palette("light", "purple")["ACCENT"] == "#7c3aed")
    check("浅色强调文字", light["ON_ACCENT"] == "#ffffff", light["ON_ACCENT"])
    check("深色强调文字", dark["ON_ACCENT"] == "#10131a", dark["ON_ACCENT"])
    check("浅色侧栏", light["SIDEBAR"] != dark["SIDEBAR"])

    print("\n[启动时读取主题]")
    cfg = Config(data)
    cfg.data["appearance"] = {
        "theme": "light",
        "accent": "purple",
        "popup_opacity": 0.8,
        "panel_opacity": 0.9,
    }
    cfg.save()
    env = os.environ.copy()
    env["RC_DATA_DIR"] = str(data)
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(
        [sys.executable, "-c",
         "import rc.theme as t; print(t.BG); print(t.ACCENT); print(t.ON_ACCENT)"],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    out = proc.stdout.splitlines()
    check("子进程读取浅色背景", out[:1] == ["#f4f5f7"], str(out[:3]))
    check("子进程读取紫色强调", out[1:2] == ["#7c3aed"], str(out[:3]))
    check("子进程强调文字为白色", out[2:3] == ["#ffffff"], str(out[:3]))

    print("\n[浮窗透明度]")
    root = tk.Tk()
    root.withdraw()
    try:
        from rc.popup import PopupWindow

        popup = PopupWindow(root, cfg, {})
        alpha = float(popup.win.attributes("-alpha"))
        check("应用 0.8 透明度", abs(alpha - 0.8) < 0.01, str(alpha))
    finally:
        root.destroy()

    print("\n[默认值]")
    fresh = Config(HERE / ".appearance-fresh")
    appearance = fresh.get("appearance") or {}
    check("默认深色", appearance.get("theme") == "dark", str(appearance))
    check("默认蓝色", appearance.get("accent") == "blue", str(appearance))
    shutil.rmtree(HERE / ".appearance-fresh", ignore_errors=True)

    shutil.rmtree(data, ignore_errors=True)
    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
