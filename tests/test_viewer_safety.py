"""验证：关闭原版窗口不会连带关掉用户自己的 Edge 窗口。"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import time
import tkinter as tk
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from rc.config import Config  # noqa: E402
from rc.htmlview import EDGE_CANDIDATES, EntryViewer, _find_window_by_title  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


def main() -> int:
    edge = next((p for p in EDGE_CANDIDATES if Path(p).exists()), None)
    if not edge:
        print("没装 Edge，跳过")
        return 0

    real = Path.home() / ".reading-companion" / "config.json"
    data = json.loads(real.read_text(encoding="utf-8")) if real.exists() else {}
    dicts = data.get("dictionaries") or {}

    tmp = HERE / "uxtmpC"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    cfg = Config(tmp)
    cfg.data["dictionaries"] = dicts
    cfg.save()
    from rc.service import Service

    svc = Service(cfg)

    # 先开一个「用户自己的」浏览器窗口
    page = Path(tempfile.gettempdir()) / "rc-user-page.html"
    page.write_text(
        "<html><head><title>rc-user-page-MARK</title></head><body>user tab</body></html>",
        encoding="utf-8",
    )
    user_proc = subprocess.Popen(
        [edge, "--app=file:///" + str(page).replace("\\", "/"), "--window-size=500,400", "--no-first-run"]
    )
    deadline = time.time() + 8
    user_hwnd = 0
    while time.time() < deadline:
        user_hwnd = _find_window_by_title("rc-user-page-MARK")
        if user_hwnd:
            break
        time.sleep(0.2)
    check("用户窗口已打开", bool(user_hwnd), "没找到")

    root = tk.Tk()
    root.withdraw()
    html = svc.entry_html("seek", "en") if (dicts.get("en") or {}).get("mdx") else "<html><body>test</body></html>"
    viewer = EntryViewer(root)
    viewer.show(html, "seek")
    from rc.htmlview import wait_attached

    attached = wait_attached(viewer, 8.0)
    check("原版窗口已嵌入", attached, f"hwnd={viewer.hwnd}")
    viewer.close()
    root.update()
    time.sleep(1.0)

    import ctypes

    user32 = ctypes.windll.user32
    check("关闭原版后，用户的 Edge 窗口还在", bool(user32.IsWindow(user_hwnd)), "用户窗口被关掉了")

    try:
        user_proc.terminate()
    except Exception:
        pass
    root.destroy()
    shutil.rmtree(tmp, ignore_errors=True)
    try:
        page.unlink()
    except OSError:
        pass
    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
