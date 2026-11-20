"""界面预览：启动真实界面、跑一次翻译，然后截图。

    python tests/ui_preview.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from PIL import ImageGrab  # noqa: E402

from rc.config import Config  # noqa: E402
from rc.service import Service  # noqa: E402
from tests import mock_openai  # noqa: E402

OUT = HERE / "shots"
TEXT = (
    "It was the best of times, it was the worst of times, it was the age of "
    "wisdom, it was the age of foolishness, it was the epoch of belief, it was "
    "the epoch of incredulity, it was the season of Light, it was the season of "
    "Darkness, it was the spring of hope, it was the winter of despair."
)


def main() -> int:
    OUT.mkdir(exist_ok=True)
    data_dir = HERE / ".uidata"
    mock_openai.start(18778)

    cfg = Config(data_dir)
    cfg.data["api"].update(
        {"base_url": "http://127.0.0.1:18778/v1", "api_key": "test-key", "model": "mock"}
    )
    cfg.save()

    from app import Application

    app = Application(cfg, enable_hotkeys=False)
    errors: list[str] = []

    def on_error(*args):
        import traceback

        errors.append("".join(traceback.format_exception(*args)))

    app.root.report_callback_exception = on_error

    def start() -> None:
        app.start_translation(TEXT)

    def shot_popup() -> None:
        ImageGrab.grab().save(OUT / "popup.png")
        print("saved popup.png")
        print("popup geometry:", app.popup.win.winfo_geometry(), "scale:", app.popup.scale)

    def shot_settings() -> None:
        ImageGrab.grab().save(OUT / "settings.png")
        print("saved settings.png")
        lines = []
        win = app._settings.win if app._settings else None
        if win:
            win.update_idletasks()
            lines.append(f"geometry={win.winfo_geometry()} mapped={win.winfo_ismapped()}")
            for child in win.winfo_children():
                lines.append(
                    f"  {child.winfo_class()} mapped={child.winfo_ismapped()} "
                    f"size={child.winfo_width()}x{child.winfo_height()} "
                    f"kids={len(child.winfo_children())}"
                )
                try:
                    lines.append(f"    pack={child.pack_info()}")
                except Exception as exc:  # noqa: BLE001
                    lines.append(f"    pack=<{exc}>")
        lines.append(f"root={app.root.winfo_geometry()} state={app.root.state()}")
        lines.append(f"scaling={app.root.tk.call('tk', 'scaling')} dpi={app.root.winfo_fpixels('1i')}")
        if errors:
            lines.append("ERRORS:\n" + "\n".join(errors))
        (OUT / "debug.txt").write_text("\n".join(lines), encoding="utf-8")

    def open_settings() -> None:
        app.popup.hide()
        app.open_settings()

    def done() -> None:
        app.shutdown()

    app.root.after(600, start)
    app.root.after(2200, shot_popup)
    app.root.after(2600, open_settings)
    app.root.after(3600, shot_settings)
    app.root.after(4200, done)
    app.run()
    time.sleep(0.3)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
