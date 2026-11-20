"""按语言渲染词条原版并截图，用于对比排版。"""

from __future__ import annotations

import subprocess
import sys
import time
import uuid
from pathlib import Path

from PIL import ImageGrab

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from rc.config import Config  # noqa: E402
from rc.service import Service  # noqa: E402

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"


def main() -> int:
    word = sys.argv[1] if len(sys.argv) > 1 else "fermer"
    lang = sys.argv[2] if len(sys.argv) > 2 else "fr"
    out = sys.argv[3] if len(sys.argv) > 3 else "entry_lang.png"
    cfg = Config()
    svc = Service(cfg)
    html = svc.entry_html(word, lang)
    marker = f"rc-{uuid.uuid4().hex[:8]}"
    html = html.replace(f"<title>{word}</title>", f"<title>{marker}</title>", 1)
    path = HERE / "shots" / f"{marker}.html"
    path.write_text(html, encoding="utf-8")
    subprocess.Popen(
        [EDGE, "--app=file:///" + str(path).replace("\\", "/"),
         "--window-size=900,900", "--window-position=60,40", "--no-first-run"]
    )
    time.sleep(4.0)
    ImageGrab.grab().crop((60, 40, 960, 940)).save(HERE / "shots" / out)
    subprocess.run(["taskkill", "/F", "/IM", "msedge.exe"], capture_output=True)
    path.unlink(missing_ok=True)
    print("saved", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
