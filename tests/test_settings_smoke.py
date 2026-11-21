"""设置窗口冒烟：每个页面都能构建出来，切换不报错。"""

from __future__ import annotations

import shutil
import sys
import tkinter as tk
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from rc.config import Config  # noqa: E402
from rc.service import Service  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


def main() -> int:
    data = HERE / ".settings-smoke"
    shutil.rmtree(data, ignore_errors=True)
    data.mkdir(parents=True)

    cfg = Config(data)
    svc = Service(cfg)

    from rc.settings_ui import SettingsWindow

    root = tk.Tk()
    root.withdraw()
    win = SettingsWindow(root, svc, on_saved=lambda: None, on_quit=lambda: None, on_restart=None)
    root.update()

    print("\n[页面构建]")
    for key in ("ai", "general", "langdict", "anki", "about"):
        child_count = 0
        error = ""
        try:
            win._show_page(key)
            root.update()
            body = win._page_bodies.get(key)
            child_count = len(body.winfo_children()) if body is not None else -1
        except Exception as exc:  # noqa: BLE001
            error = f"{type(exc).__name__}: {exc}"
        check(f"{key} 页可切换且有内容", child_count > 0, error or f"children={child_count}")

    print("\n[关闭]")
    try:
        win.close()
        root.update()
        check("关闭不报错", True)
    except Exception as exc:  # noqa: BLE001
        check("关闭不报错", False, f"{type(exc).__name__}: {exc}")

    try:
        root.destroy()
    except Exception:  # noqa: BLE001
        pass
    shutil.rmtree(data, ignore_errors=True)
    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
