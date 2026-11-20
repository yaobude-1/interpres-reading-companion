"""Regression: popup chat must be usable before the first streaming delta."""

from __future__ import annotations

import shutil
import sys
import time
import tkinter as tk
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from rc.config import Config  # noqa: E402
from rc.popup import PopupWindow  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


def main() -> int:
    data = HERE / ".chat-popup"
    shutil.rmtree(data, ignore_errors=True)
    data.mkdir(parents=True)
    cfg = Config(data)
    root = tk.Tk()
    root.withdraw()
    try:
        popup = PopupWindow(root, cfg, {})
        popup.show_chat({"id": 1, "book": "", "messages": []})
        check("聊天字段已初始化", popup._chat_job is None and popup._chat_target == "")
        popup.receive_chat_delta(1, "hello")
        popup.receive_chat(1, "hello world")
        for _ in range(20):
            root.update()
            time.sleep(0.03)

        def find_text(widget, wanted: str) -> bool:
            for child in widget.winfo_children():
                try:
                    if isinstance(child, tk.Label) and wanted in child.cget("text"):
                        return True
                except tk.TclError:
                    pass
                if find_text(child, wanted):
                    return True
            return False

        check("回复已显示", find_text(popup.win, "hello world"))
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass
        shutil.rmtree(data, ignore_errors=True)
    print("\n" + "=" * 50)
    print(f"失败 {len(fails)} 项")
    for name in fails:
        print("  ✗", name)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
