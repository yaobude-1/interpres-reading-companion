"""Regression: a new selection must not close the open translation popup."""

from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from rc.config import Config  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


def main() -> int:
    data = HERE / ".selection-popup"
    shutil.rmtree(data, ignore_errors=True)
    data.mkdir(parents=True)
    cfg = Config(data)
    cfg.data["server_port"] = 18799
    cfg.save()

    from app import Application

    app = Application(cfg, enable_hotkeys=False)
    try:
        entry = {
            "word": "volume",
            "lang": "en",
            "source": "Test",
            "senses": [{"pos": "noun", "definition": "sound level"}],
        }
        app.popup.show_dictionary(entry, (300, 300), "volume")
        for _ in range(20):
            app.root.update()
            time.sleep(0.02)
        check("浮窗先显示", app.popup.visible)

        app._sel_gen = 7
        app.events.put(("sel_button", (7, "another word", "Book", (420, 420), 0)))
        app._pump_events()
        for _ in range(20):
            app.root.update()
            time.sleep(0.02)

        check("新选区后浮窗仍显示", app.popup.visible)
        check("快捷按钮出现", bool(app.quick.win.winfo_viewable()))
        check("待处理选区已更新", (app._pending_selection or ("",))[0] == "another word")
    finally:
        app.shutdown()
        shutil.rmtree(data, ignore_errors=True)

    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
