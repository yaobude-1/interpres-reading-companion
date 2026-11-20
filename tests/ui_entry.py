"""截图：词典原版条目（Edge 内嵌渲染）。"""

from __future__ import annotations

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from PIL import ImageGrab  # noqa: E402

from rc.config import Config  # noqa: E402
from rc.dictionary import Dictionary  # noqa: E402
from rc.entryhtml import build_entry_html  # noqa: E402
from rc.htmlview import EntryViewer, wait_attached  # noqa: E402


def main() -> int:
    import tkinter as tk

    cfg = Config()
    paths = (cfg.data.get("dictionaries") or {}).get("en") or {}
    dic = Dictionary(paths.get("mdx"), paths.get("mdd"))
    word = sys.argv[1] if len(sys.argv) > 1 else "work"
    html = build_entry_html(dic, word)
    print("html length:", len(html))

    root = tk.Tk()
    root.withdraw()
    viewer = EntryViewer(root)
    viewer.show(html, word)
    attached = wait_attached(viewer, 10)
    print("attached:", attached)
    time.sleep(2.5)
    out = HERE / "shots" / "entry_view.png"
    ImageGrab.grab().save(out)
    print("saved", out)
    viewer.close()
    root.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
