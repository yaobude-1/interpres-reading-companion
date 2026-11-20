"""截图：设置窗口的原版配色区。"""

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
    data = HERE / ".uisettings"
    shutil.rmtree(data, ignore_errors=True)
    data.mkdir(parents=True)
    real = Path.home() / ".reading-companion" / "config.json"
    if real.exists():
        (data / "config.json").write_text(real.read_text(encoding="utf-8"), encoding="utf-8")
    cfg = Config(data)
    cfg.data["server_port"] = 18826
    cfg.data["api"].update({"base_url": "http://127.0.0.1:18778/v1", "api_key": "k", "model": "mock"})
    cfg.data["entry_colors"] = {"sense": "#cc2200", "pos": "#1a66cc", "label": "#8a8f98",
                                "example": "#6b7280", "section": "#b8860b", "text": "#222222",
                                "bg": "#ffffff"}
    cfg.data["entry_font_size"] = 15
    cfg.save()
    mock_openai.start(18778)

    import tkinter as tk

    from rc.entry_settings import EntryColorSettings

    root = tk.Tk()
    root.geometry("1x1+-3000+-3000")
    win = EntryColorSettings(root, cfg, on_saved=lambda: None)

    def shot() -> None:
        w = win.win
        w.attributes("-topmost", True)
        w.lift()
        w.update()
        x, y = w.winfo_rootx(), w.winfo_rooty()
        ImageGrab.grab().crop((x, y, x + w.winfo_width(), y + w.winfo_height())).save(
            HERE / "shots" / "settings_colors.png"
        )
        try:
            win.save()
        except Exception as exc:
            print('save error:', exc)
        print("saved colors:", cfg.data.get("entry_colors", {}).get("sense"))
        print("saved font:", cfg.data.get("entry_font_size"))
        win.close()

    win.show()
    win.win.wait_visibility()
    win.win.update_idletasks()
    root.after(700, shot)
    root.after(3000, root.destroy)
    root.mainloop()
    shutil.rmtree(data, ignore_errors=True)
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
