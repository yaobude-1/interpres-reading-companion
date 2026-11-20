"""截图：浮窗就地变成对话面板。"""

from __future__ import annotations

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
TEXT = "Fashion is by nature ephemeral, and the desire for novelty keeps the industry moving."


def main() -> int:
    OUT.mkdir(exist_ok=True)
    data = HERE / ".uichat"
    mock_openai.CANNED["translation"] = "时尚本质上是短暂的，而对新奇事物的渴望让整个行业不断运转。"
    mock_openai.start(18778)

    cfg = Config(data)
    cfg.data["api"].update(
        {"base_url": "http://127.0.0.1:18778/v1", "api_key": "k", "model": "mock"}
    )
    cfg.save()

    from app import Application

    app = Application(cfg, enable_hotkeys=False)

    def start() -> None:
        app.start_translation(TEXT)

    def open_chat() -> None:
        app.popup._open_chat()

    def ask() -> None:
        if app.popup.chat_input is not None:
            app.popup.chat_input.insert("1.0", "作者为什么强调“短暂”？")
            app.popup._send_chat()

    def shot() -> None:
        ImageGrab.grab().save(OUT / "chat_panel.png")
        print("saved")

    app.root.after(600, start)
    app.root.after(2600, open_chat)
    app.root.after(3000, ask)
    app.root.after(4400, shot)
    app.root.after(5000, app.shutdown)
    app.run()
    time.sleep(0.2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
