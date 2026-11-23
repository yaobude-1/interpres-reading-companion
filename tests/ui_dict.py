"""截图：面板查词页签 + 浮窗查词卡片。"""

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

OUT = HERE / "shots"
REAL = Path.home() / ".reading-companion" / "config.json"


def main() -> int:
    OUT.mkdir(exist_ok=True)
    data = HERE / ".uidict"
    shutil.rmtree(data, ignore_errors=True)
    data.mkdir(parents=True)
    if REAL.exists():
        (data / "config.json").write_text(REAL.read_text(encoding="utf-8"), encoding="utf-8")

    cfg = Config(data)
    cfg.data["server_port"] = 18807
    cfg.data["api"].update({"base_url": "http://127.0.0.1:18778/v1", "api_key": "k", "model": "mock"})
    cfg.save()

    from tests import mock_openai

    mock_openai.start(18778)

    from app import Application

    app = Application(cfg, enable_hotkeys=False)

    def open_dict() -> None:
        app.open_panel()
        app.panel._show_tab("dict")
        app.panel.dict_input.insert(0, "ephemeral")
        app.panel._lookup_dict(sync=True)
        app.panel.win.geometry("+40+40")

    def shot_panel() -> None:
        ImageGrab.grab().save(OUT / "panel_dict.png")

    def show_popup() -> None:
        entry = app.service.lookup_word("ephemeral")
        app.popup.show_dictionary(entry, (760, 120), "ephemeral")

    def shot_popup() -> None:
        img = ImageGrab.grab()
        img.save(OUT / "popup_dict.png")
        img.crop((730, 90, 1330, 720)).save(OUT / "crop_popup_dict.png")

    app.root.after(700, open_dict)
    app.root.after(2600, shot_panel)
    app.root.after(3000, show_popup)
    app.root.after(4200, shot_popup)
    app.root.after(4800, app.shutdown)
    app.run()
    time.sleep(0.2)
    shutil.rmtree(data, ignore_errors=True)
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
