"""浮窗/气泡/按钮的淡入淡出：到达配置透明度，隐藏后真正收起。"""

from __future__ import annotations

import shutil
import sys
import time
import tkinter as tk
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from rc import anim  # noqa: E402
from rc.config import Config  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


def pump(root, predicate, timeout: float = 3.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        root.update()
        if predicate():
            return True
        time.sleep(0.01)
    root.update()
    return predicate()


def main() -> int:
    data = HERE / ".animwin"
    shutil.rmtree(data, ignore_errors=True)
    data.mkdir(parents=True)

    cfg = Config(data)
    cfg.data["appearance"] = {
        "theme": "dark",
        "accent": "blue",
        "popup_opacity": 0.8,
        "panel_opacity": 1.0,
        "animations": True,
    }
    cfg.save()

    root = tk.Tk()
    root.withdraw()
    old = anim.enabled
    anim.enabled = True
    try:
        from rc.popup import PopupWindow

        print("\n[浮窗]")
        popup = PopupWindow(root, cfg, {})
        popup.win.deiconify()
        popup.win.update_idletasks()
        popup._fade_to_visible(restart=True)
        check(
            "淡入到配置透明度",
            pump(root, lambda: abs(float(popup.win.attributes("-alpha")) - 0.8) < 0.02),
            str(popup.win.attributes("-alpha")),
        )
        popup.hide()
        check("淡出后收起", pump(root, lambda: popup.win.winfo_viewable() != 1))
        check(
            "最终 alpha=0",
            abs(float(popup.win.attributes("-alpha"))) < 0.02,
            str(popup.win.attributes("-alpha")),
        )

        from rc.bubble import Bubble, QuickButton

        print("\n[气泡]")
        bubble = Bubble(root, cfg, {})
        bubble.show_result({"translation": "hello"}, (200, 200))
        check(
            "淡入到气泡透明度",
            pump(root, lambda: abs(float(bubble.win.attributes("-alpha")) - 0.97) < 0.02),
            str(bubble.win.attributes("-alpha")),
        )
        bubble.hide()
        check("淡出后收起", pump(root, lambda: bubble.win.winfo_viewable() != 1))

        print("\n[划词按钮]")
        quick = QuickButton(root, cfg, on_click=lambda _a: None)
        quick.show((300, 300))
        check(
            "淡入到按钮透明度",
            pump(root, lambda: abs(float(quick.win.attributes("-alpha")) - 0.95) < 0.02),
            str(quick.win.attributes("-alpha")),
        )
        quick.hide()
        check("淡出后收起", pump(root, lambda: quick.win.winfo_viewable() != 1))
    finally:
        anim.enabled = old
        try:
            root.destroy()
        except tk.TclError:
            pass
        shutil.rmtree(data, ignore_errors=True)

    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
