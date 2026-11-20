"""验证长对话能滚动、能看全。"""

from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from rc.config import Config  # noqa: E402
from tests import mock_openai  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


def main() -> int:
    data = HERE / ".chatscroll"
    shutil.rmtree(data, ignore_errors=True)
    data.mkdir(parents=True)
    mock_openai.start(18778)

    cfg = Config(data)
    cfg.data["api"].update(
        {"base_url": "http://127.0.0.1:18778/v1", "api_key": "k", "model": "mock"}
    )
    cfg.data["server_port"] = 18800
    cfg.save()

    from app import Application

    app = Application(cfg, enable_hotkeys=False)
    service = app.service

    conv = service.start_conversation("Sapiens", "en", "Fashion is by nature ephemeral.", "时尚…")
    for i in range(14):
        service.store.add_message(conv["id"], "user", f"第 {i} 个问题：这段话里的意思是什么？")
        service.store.add_message(
            conv["id"],
            "assistant",
            f"第 {i} 个回答：作者想说的是，时尚依赖于不断更新的欲望，"
            "一旦停止更新，它就不再具有吸引力。这个问题还可以从社会学角度继续展开。",
        )

    conversation = {
        "id": conv["id"],
        "book": "Sapiens",
        "messages": service.chat_messages(conv["id"]),
    }
    app.popup.show_chat_pending("Fashion is by nature ephemeral.", "Sapiens", (400, 300))
    app.root.update()
    app.popup.show_chat(conversation)
    app.root.update()
    app.root.update_idletasks()
    time.sleep(0.2)
    app.root.update()

    canvas = app.popup.canvas
    content = canvas.bbox("all")
    view = canvas.yview()
    print(f"画布高 {canvas.winfo_height()}，内容高 {content[3] - content[1]}，视图 {view}")

    check("内容比窗口长", (content[3] - content[1]) > canvas.winfo_height(), str(content))
    check("打开时滚到底部", view[1] >= 0.98, str(view))

    canvas.yview_moveto(0)
    app.root.update()
    check("能滚回顶部", canvas.yview()[0] <= 0.02, str(canvas.yview()))

    first_bubble = app.popup.messages_frame.winfo_children()[0]
    has_wheel = bool(first_bubble.bind("<MouseWheel>"))
    check("气泡绑定了滚轮", has_wheel, str(first_bubble.bind("<MouseWheel>")))

    app.shutdown()
    shutil.rmtree(data, ignore_errors=True)
    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
