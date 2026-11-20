"""截图：主面板（翻译 + 对话）。"""

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
TEXT = "Fashion is by nature ephemeral, and the desire for novelty keeps the industry moving."


def main() -> int:
    OUT.mkdir(exist_ok=True)
    data = HERE / ".uipanel"
    shutil.rmtree(data, ignore_errors=True)
    mock_openai.start(18778)
    mock_openai.CANNED["translation"] = "时尚本质上是短暂的，而对新奇事物的渴望让整个行业不断运转。"
    mock_openai.CANNED["terms"] = [
        {
            "word": "ephemeral",
            "lemma": "ephemeral",
            "reading": "/ɪˈfemərəl/",
            "pos": "形容词",
            "meaning": "短暂的；只流行一时的",
            "note": "",
        }
    ]

    cfg = Config(data)
    cfg.data["api"].update(
        {"base_url": "http://127.0.0.1:18778/v1", "api_key": "k", "model": "mock"}
    )
    cfg.save()

    from app import Application

    app = Application(cfg, enable_hotkeys=False)
    app.service.store.touch_book("Sapiens", "en")

    def open_panel() -> None:
        app.open_panel()
        app.panel.input.insert("1.0", TEXT)
        app.panel._translate()

    def ask() -> None:
        app.panel.chat_input.insert("1.0", "作者为什么反复强调“短暂”？")
        app.panel._send()

    def shot() -> None:
        ImageGrab.grab().save(OUT / "panel.png")
        print("saved")

    app.root.after(600, open_panel)
    app.root.after(2600, ask)
    app.root.after(4200, shot)
    app.root.after(4800, app.shutdown)
    app.run()
    time.sleep(0.2)
    shutil.rmtree(data, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
