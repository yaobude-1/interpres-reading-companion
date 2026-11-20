"""截图：长对话滚动效果。"""

from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from PIL import ImageGrab  # noqa: E402

from rc.config import Config  # noqa: E402
from tests import mock_openai  # noqa: E402

OUT = HERE / "shots"


def main() -> int:
    OUT.mkdir(exist_ok=True)
    data = HERE / ".uichatlong"
    shutil.rmtree(data, ignore_errors=True)
    mock_openai.start(18778)
    cfg = Config(data)
    cfg.data["api"].update(
        {"base_url": "http://127.0.0.1:18778/v1", "api_key": "k", "model": "mock"}
    )
    cfg.save()

    from app import Application

    app = Application(cfg, enable_hotkeys=False)
    service = app.service
    conv = service.start_conversation("Sapiens", "en", "Fashion is by nature ephemeral.", "时尚…")
    for i in range(6):
        service.store.add_message(conv["id"], "user", f"第 {i} 个问题：这里的 ephemeral 怎么理解？")
        service.store.add_message(
            conv["id"],
            "assistant",
            f"第 {i} 个回答：它强调的是一时的、易逝的，与后半句“对新颖的渴望”形成对照。",
        )

    conversation = {"id": conv["id"], "book": "Sapiens", "messages": service.chat_messages(conv["id"])}

    def open_chat() -> None:
        app.popup.show_chat_pending("Fashion is by nature ephemeral.", "Sapiens", (400, 300))
        app.popup.show_chat(conversation)

    def shot() -> None:
        ImageGrab.grab().save(OUT / "chat_long.png")
        print("saved")

    app.root.after(700, open_chat)
    app.root.after(2000, shot)
    app.root.after(2600, app.shutdown)
    app.run()
    time.sleep(0.2)
    shutil.rmtree(data, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
