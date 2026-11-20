"""截图：查词卡片的「释义 / 时态」页签。"""

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


def main() -> int:
    word = sys.argv[1] if len(sys.argv) > 1 else "parlait"
    lang = sys.argv[2] if len(sys.argv) > 2 else "fr"
    data = HERE / ".uidict2"
    shutil.rmtree(data, ignore_errors=True)
    data.mkdir(parents=True)
    real = Path.home() / ".reading-companion" / "config.json"
    if real.exists():
        (data / "config.json").write_text(real.read_text(encoding="utf-8"), encoding="utf-8")
    cfg = Config(data)
    cfg.data["server_port"] = 18822
    cfg.data["api"].update(
        {"base_url": "http://127.0.0.1:18778/v1", "api_key": "k", "model": "mock"}
    )
    cfg.save()
    mock_openai.start(18778)

    from app import Application

    app = Application(cfg, enable_hotkeys=False)
    entry = app.service.lookup_word(word, lang)
    print("entry:", bool(entry), "| morph:", bool((entry or {}).get("morph")))

    def show() -> None:
        app.popup.show_dictionary(entry, (200, 120), word)
        app.popup.win.geometry("+200+100")

    def conj() -> None:
        app.popup._show_dict_tab("conj")

    def shot(name: str):
        def inner() -> None:
            ImageGrab.grab().save(HERE / "shots" / name)
        return inner

    app.root.after(500, show)
    app.root.after(1500, shot("dict_tab_meaning.png"))
    app.root.after(1800, conj)
    app.root.after(2800, shot("dict_tab_conj.png"))
    app.root.after(3200, app.shutdown)
    app.run()
    time.sleep(0.2)
    shutil.rmtree(data, ignore_errors=True)
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
