"""截图：翻译记录窗口。"""

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
    data = HERE / ".uitrans"
    shutil.rmtree(data, ignore_errors=True)
    mock_openai.start(18778)
    cfg = Config(data)
    cfg.data["api"].update(
        {"base_url": "http://127.0.0.1:18778/v1", "api_key": "k", "model": "mock"}
    )
    cfg.data["server_port"] = 18806
    cfg.save()

    from app import Application

    app = Application(cfg, enable_hotkeys=False)
    service = app.service
    samples = [
        ("Sapiens", "Fashion is by nature ephemeral, and the desire for novelty keeps the industry moving."),
        ("Sapiens", "The history of philosophy is a history of answers rather than of questions."),
        ("Sapiens", "Imagined orders are not lies; they are ways of cooperation."),
        ("哲学史", "La philosophie commence par l'étonnement et finit par les questions."),
    ]
    for book, text in samples:
        service.translate(text, book=book)

    def open_win() -> None:
        app.open_translation_history()
        win = app._trans_win.win
        win.attributes("-topmost", True)
        win.lift()
        win.geometry("+80+60")

    def shot() -> None:
        ImageGrab.grab().save(OUT / "translations.png")
        print("saved")

    app.root.after(500, open_win)
    app.root.after(1500, shot)
    app.root.after(2000, app.shutdown)
    app.run()
    time.sleep(0.2)
    shutil.rmtree(data, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
