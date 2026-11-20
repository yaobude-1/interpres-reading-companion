"""截图 + 冒烟：对话记录管理窗口。"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

import tkinter as tk  # noqa: E402

from PIL import ImageGrab  # noqa: E402

from rc.config import Config  # noqa: E402
from rc.service import Service  # noqa: E402


def main() -> int:
    OUT = HERE / "shots"
    OUT.mkdir(exist_ok=True)
    data = HERE / ".uichathist"
    shutil.rmtree(data, ignore_errors=True)
    cfg = Config(data)
    cfg.save()
    service = Service(cfg)

    conv = service.start_conversation(
        "Sapiens", "en", "Fashion is by nature ephemeral.", "时尚本质上是短暂的。"
    )
    service.store.add_message(conv["id"], "user", "作者为什么强调短暂？")
    service.store.add_message(conv["id"], "assistant", "因为时尚依赖不断更新的欲望。")
    conv2 = service.start_conversation(
        "哲学史", "en", "The history of philosophy is a history of answers.", "哲学史是一部答案史。"
    )
    service.store.add_message(conv2["id"], "user", "这里的 answers 指什么？")

    from rc.chat_ui import ChatHistoryWindow

    root = tk.Tk()
    root.withdraw()
    window = ChatHistoryWindow(root, service)
    window.win.attributes("-topmost", True)
    root.after(1200, lambda: ImageGrab.grab().save(OUT / "chat_history.png"))
    root.after(1800, root.destroy)
    root.mainloop()
    service.store.close()
    shutil.rmtree(data, ignore_errors=True)
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
