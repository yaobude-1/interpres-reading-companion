"""对话记录 → 主面板接管：切会话、换书名、载入消息、窗口收起。"""

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
    data = HERE / "convswitch"
    shutil.rmtree(data, ignore_errors=True)
    data.mkdir(parents=True)
    cfg = Config(data)
    cfg.data["server_port"] = 18995
    cfg.save()

    from app import Application

    app = Application(cfg, enable_hotkeys=False)
    app.root.update()
    svc = app.service

    a = svc.store.start_conversation("Book A", "原文A", "译文A", "")
    svc.store.add_message(a, "user", "A 的问题")
    svc.store.add_message(a, "assistant", "A 的回答")
    b = svc.store.start_conversation("Book B", "原文B", "译文B", "")
    svc.store.add_message(b, "user", "B 的问题一")
    svc.store.add_message(b, "assistant", "B 的回答一")

    app.open_panel()
    app.root.update()

    print("\n[直接载入]")
    app.panel.load_conversation(a)
    app.root.update()
    check("会话号切到 A", app.panel.conv_id == a, str(app.panel.conv_id))
    check("书名跟着换", "Book A" in app.panel.book_label.cget("text"), app.panel.book_label.cget("text"))

    print("\n[从记录窗口接管]")
    app.open_chat_history()
    app.root.update()
    win = app._chat_win
    check("窗口带 on_open 回调", win.on_open is not None)
    ids = [int(i) for i in win.tree.get_children()]
    check("列表里有 B", b in ids, str(ids))
    if b in ids:
        win.tree.selection_set(str(b))
        app.root.update()
        win.open_selected()
        for _ in range(10):
            app.root.update()
            time.sleep(0.05)
        check("面板切到 B", app.panel.conv_id == b, str(app.panel.conv_id))
        check("书名 B", "Book B" in app.panel.book_label.cget("text"), app.panel.book_label.cget("text"))
        check("记录窗口收起", win.win.winfo_viewable() == 0)
        texts = []

        def walk(widget):
            for child in widget.winfo_children():
                try:
                    text = child.cget("text")
                except Exception:
                    text = ""
                if text:
                    texts.append(str(text))
                walk(child)

        walk(app.panel.chat_body)
        check("气泡是 B 的", any("B 的问题一" in t for t in texts))
        check("没有 A 的残留", not any("A 的问题" in t for t in texts))

    app.shutdown()
    try:
        app.root.destroy()
    except Exception:
        pass
    shutil.rmtree(data, ignore_errors=True)
    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
