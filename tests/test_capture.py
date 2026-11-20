"""验证「模拟 Ctrl+C 取选中文字」这条路。

会弹出一个临时窗口，选中一段文字后触发抓取，检查读到的内容是否正确。
"""

from __future__ import annotations

import sys
import threading
import tkinter as tk
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from rc import capture  # noqa: E402

SAMPLE = "The quick brown fox jumps over the lazy dog."
result = {"text": None, "title": None}


def main() -> int:
    root = tk.Tk()
    root.title("RC Capture Test")
    root.geometry("620x160+200+200")

    text = tk.Text(root, font=("Consolas", 12))
    text.pack(fill="both", expand=True, padx=10, pady=10)
    text.insert("1.0", SAMPLE)

    state = {"skipped": False}

    def worker() -> None:
        got, title = capture.grab_selection()
        result["text"] = got
        result["title"] = title

    def trigger() -> None:
        root.focus_force()
        text.focus_set()
        text.tag_add("sel", "1.0", "end-1c")
        # 后台进程可能抢不到前台焦点，那就说明这个用例在本环境不适用
        if "RC Capture Test" not in capture.foreground_title():
            state["skipped"] = True
            print("SKIP: 测试窗口没有拿到前台焦点（沙箱限制），跳过真实 Ctrl+C 用例")
            root.destroy()
            return
        root.after(300, lambda: threading.Thread(target=worker, daemon=True).start())

    def report() -> None:
        text_read = (result["text"] or "").strip()
        ok = SAMPLE in text_read
        print(f"title: {result['title']!r}")
        print(f"read : {text_read[:80]!r}")
        print("RESULT:", "PASS" if ok else "FAIL")
        root.destroy()

    root.after(400, trigger)
    root.after(2200, report)
    root.mainloop()
    if state["skipped"]:
        return 0
    return 0 if (result["text"] and SAMPLE in result["text"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
