"""截图：面板查词页签的「释义 / 时态」。"""

from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageGrab  # noqa: E402

from rc.config import Config  # noqa: E402
from tests import mock_openai  # noqa: E402


def main() -> int:
    word = sys.argv[1] if len(sys.argv) > 1 else "avoir"
    lang = sys.argv[2] if len(sys.argv) > 2 else "fr"
    data = HERE / ".uipaneldict"
    shutil.rmtree(data, ignore_errors=True)
    data.mkdir(parents=True)
    real = Path.home() / ".reading-companion" / "config.json"
    if real.exists():
        (data / "config.json").write_text(real.read_text(encoding="utf-8"), encoding="utf-8")
    cfg = Config(data)
    cfg.data["server_port"] = 18823
    cfg.data["api"].update(
        {"base_url": "http://127.0.0.1:18778/v1", "api_key": "k", "model": "mock"}
    )
    cfg.save()
    mock_openai.start(18778)

    from app import Application

    app = Application(cfg, enable_hotkeys=False)
    entry = app.service.lookup_word(word, lang)
    print("entry:", bool(entry), "| morph:", bool((entry or {}).get("morph")))

    def open_panel() -> None:
        app.open_panel()
        app.panel._show_tab("dict")
        app.panel.dict_input.insert(0, word)
        app.panel._lookup_dict()
        app.panel.win.geometry("+60+60")
        app.panel.win.attributes("-topmost", True)
        app.panel.win.lift()

    def conj() -> None:
        if hasattr(app.panel, "_panel_tab_conj"):
            app.panel._panel_show_tab("conj")

    def shot(name: str):
        def inner() -> None:
            win = app.panel.win
            x, y = win.winfo_rootx(), win.winfo_rooty()
            w, h = win.winfo_width(), win.winfo_height()
            ImageGrab.grab().crop((x, y, x + w, y + h)).save(HERE / "shots" / name)
        return inner

    def lookup_later() -> None:
        app.panel._show_tab("dict")
        app.panel.dict_input.delete(0, "end")
        app.panel.dict_input.insert(0, word)
        app.panel._lookup_dict()

    app.root.after(600, open_panel)
    app.root.after(1100, lookup_later)
    app.root.after(1800, shot("panel_dict_meaning.png"))
    app.root.after(2100, conj)
    app.root.after(3100, shot("panel_dict_conj.png"))
    app.root.after(3500, app.shutdown)
    app.run()
    time.sleep(0.2)
    shutil.rmtree(data, ignore_errors=True)
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
