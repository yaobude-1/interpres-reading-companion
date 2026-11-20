"""调试：把生成的条目 HTML 落盘、用 Edge 打开并截图。"""

from __future__ import annotations

import subprocess
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

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"


def main() -> int:
    word = sys.argv[1] if len(sys.argv) > 1 else "seek"
    cfg = Config()
    paths = (cfg.data.get("dictionaries") or {}).get("en") or {}
    dic = Dictionary(paths.get("mdx"), paths.get("mdd"))
    html = build_entry_html(dic, word)
    out = HERE / "shots" / "debug_entry.html"
    out.write_text(html, encoding="utf-8")
    print("wrote", out, len(html))
    print("has style:", "<style>" in html, "| details:", html.count("<details"))
    proc = subprocess.Popen(
        [
            EDGE,
            "--app=file:///" + str(out).replace("\\", "/"),
            "--window-size=900,860",
            "--window-position=80,60",
            "--no-first-run",
        ]
    )
    time.sleep(3.5)
    ImageGrab.grab().save(HERE / "shots" / "debug_entry.png")
    print("shot saved")
    proc.terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
