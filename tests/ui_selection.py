"""截图：划词按钮、气泡、划词设置对话框。"""

from __future__ import annotations

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from PIL import ImageGrab  # noqa: E402

from rc.config import Config  # noqa: E402

OUT = HERE / "shots"
PAYLOAD = {
    "translation": "敏捷的棕色狐狸跳过了那只懒狗。",
    "text": "The quick brown fox jumps over the lazy dog.",
    "source_lang": "en",
    "terms": [],
    "grammar": None,
    "book": "Test",
    "meta": {"cached": False, "elapsed_ms": 20},
}


def main() -> int:
    OUT.mkdir(exist_ok=True)
    cfg = Config(HERE / ".uidata")
    cfg.data["api"].update({"base_url": "http://127.0.0.1:18778/v1", "api_key": "k", "model": "mock"})
    cfg.save()

    from app import Application

    app = Application(cfg, enable_hotkeys=False)

    app.root.after(500, lambda: app.quick.show((900, 360)))
    app.root.after(900, lambda: ImageGrab.grab().save(OUT / "quick_button.png"))
    app.root.after(1100, lambda: (app.quick.hide(), app.bubble.show_result(PAYLOAD, (900, 360))))
    app.root.after(1500, lambda: ImageGrab.grab().save(OUT / "bubble.png"))

    def open_sel() -> None:
        from rc.selection_settings import SelectionSettings

        app.bubble.hide()
        SelectionSettings(app.root, app.config, lambda: None)

    app.root.after(1700, open_sel)
    app.root.after(2200, lambda: ImageGrab.grab().save(OUT / "selection_settings.png"))
    app.root.after(2700, app.shutdown)
    app.run()
    time.sleep(0.2)
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
