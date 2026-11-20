"""验证浮窗的两个次要状态：手动输入、术语表弹窗。"""

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


def main() -> int:
    OUT.mkdir(exist_ok=True)
    mock_openai.start(18778)
    cfg = Config(HERE / ".uidata")
    cfg.data["api"].update(
        {"base_url": "http://127.0.0.1:18778/v1", "api_key": "test-key", "model": "mock"}
    )
    cfg.save()

    from app import Application

    app = Application(cfg, enable_hotkeys=False)
    app.root.after(500, lambda: app.popup.show_input((700, 300), "Le temps est très doux aujourd'hui."))
    app.root.after(1500, lambda: ImageGrab.grab().save(OUT / "input_mode.png"))
    app.root.after(1900, lambda: app.popup.hide())
    app.root.after(2100, lambda: app.lock_term("Les Fleurs du mal", "spleen", "fr"))
    app.root.after(2900, lambda: ImageGrab.grab().save(OUT / "term_dialog.png"))
    app.root.after(3400, app.shutdown)
    app.run()
    time.sleep(0.2)
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
