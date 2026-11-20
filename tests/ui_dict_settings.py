"""截图：词典设置对话框。"""

from __future__ import annotations

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

import tkinter as tk  # noqa: E402

from PIL import ImageGrab  # noqa: E402

from rc.config import Config  # noqa: E402
from rc.service import Service  # noqa: E402

OUT = HERE / "shots"
BASE = (
    r"D:\Downloads\Compressed\Longman Dictionary of Contemporary English 6th ed. "
    r"Summer Edition (MDX)\朗文当代高级英语辞典 第6版 夏日清凉版 V3.2"
)


def main() -> int:
    OUT.mkdir(exist_ok=True)
    data = HERE / ".uidictset"
    cfg = Config(data)
    cfg.data["dictionaries"]["en"] = {
        "mdx": BASE + r"\朗文当代高级英语词典6th.mdx",
        "mdd": BASE + r"\朗文当代高级英语词典6th.mdd",
    }
    cfg.save()
    service = Service(cfg)

    root = tk.Tk()
    root.withdraw()
    from rc.dictionary_settings import DictionarySettings

    win = DictionarySettings(root, cfg, service.dicts, lambda: None)
    win.win.attributes("-topmost", True)
    root.after(1500, lambda: ImageGrab.grab().save(OUT / "dict_settings.png"))
    root.after(2100, root.destroy)
    root.mainloop()
    service.store.close()
    import shutil

    shutil.rmtree(data, ignore_errors=True)
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
