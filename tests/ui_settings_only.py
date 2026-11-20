"""单独预览设置窗口（不触发浮窗）。"""

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
    cfg.data["server_port"] = 18802
    cfg.data["api"].update(
        {"base_url": "http://127.0.0.1:18778/v1", "api_key": "test-key", "model": "mock"}
    )
    cfg.save()

    from app import Application

    app = Application(cfg, enable_hotkeys=False)

    def open_settings() -> None:
        app.open_settings()
        if app._settings:
            app._settings.win.attributes("-topmost", True)
            app._settings.win.lift()
            app.root.after(700, lambda: app._settings.win.geometry('+1300+40'))

    app.root.after(400, open_settings)
    app.root.after(2600, lambda: ImageGrab.grab().save(OUT / "settings_only.png"))
    app.root.after(3200, app.shutdown)
    app.run()
    time.sleep(0.2)
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
