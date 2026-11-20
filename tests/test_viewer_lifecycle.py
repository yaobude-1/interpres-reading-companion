"""验证：原版窗口生命周期 + 气泡/弹窗在屏幕边缘的定位。"""

from __future__ import annotations

import json
import shutil
import sys
import tkinter as tk
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from rc import screens  # noqa: E402
from rc.config import Config  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


def main() -> int:
    real = Path.home() / ".reading-companion" / "config.json"
    data = json.loads(real.read_text(encoding="utf-8")) if real.exists() else {}
    dicts = data.get("dictionaries") or {}

    tmp = HERE / "uxtmpB"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    cfg = Config(tmp)
    cfg.data["dictionaries"] = dicts
    cfg.save()

    from rc.service import Service

    svc = Service(cfg)

    print("\n[屏幕边缘定位]")
    left, top, right, bottom = screens.work_area(0, 0)
    check("工作区有效", right > left and bottom > top, f"{left},{top},{right},{bottom}")

    for anchor, size in (
        ((right - 5, top + 50), (440, 200)),      # 右边贴边
        ((left + 5, bottom - 5), (440, 200)),     # 右下角
        ((-900, 200), (440, 200)),                # 左屏（不存在时回退主屏）
        ((0, 0), (440, 200)),
    ):
        x, y = screens.clamp(anchor, size)
        inside = left <= x <= right - size[0] and top <= y <= bottom - size[1]
        check(f"锚点{anchor}夹取在屏内", inside, f"→({x},{y}) 工作区({left},{top},{right},{bottom})")

    root = tk.Tk()
    root.withdraw()

    print("\n[原版窗口]")
    if not (dicts.get("en") or {}).get("mdx"):
        print("  没配英语词典，跳过")
    else:
        from rc.htmlview import EntryViewer, find_edge, wait_attached

        if not find_edge():
            print("  没装 Edge，跳过")
        else:
            html = svc.entry_html("seek", "en")
            viewer = EntryViewer(root)

            def show_and_wait():
                viewer.show(html, "seek")
                from rc.htmlview import wait_attached

                return wait_attached(viewer, 8.0)

            try:
                attached = show_and_wait()
                check("Edge 窗口嵌进来了", attached, f"hwnd={viewer.hwnd}")
                hwnd = viewer.hwnd
                path = viewer._html_path
                viewer.close()
                root.update()
                import ctypes

                user32 = ctypes.windll.user32
                check("嵌入的窗口已关闭", not user32.IsWindow(hwnd), "窗口还在")
                # 再开一次：用户关掉原版窗口后再点「原版」必须还能用
                again = viewer.show(html, "seek")
                reopened = wait_attached(viewer, 8.0)
                check("关闭后还能再次打开", again and reopened, f"again={again} hwnd={viewer.hwnd}")
                viewer.close()
                check("临时文件已清理", not (path and path.exists()), str(path))
            except Exception as exc:  # noqa: BLE001
                check("原版窗口流程", False, f"{type(exc).__name__}: {exc}")

            # 超时保护：伪造一个不存在的标记，3.6 秒内应放弃并给出兜底
            try:
                viewer2 = EntryViewer(root)
                viewer2._marker = "rc-entry-does-not-exist-xyz"
                viewer2._attach_tries = 0
                viewer2._attach_job = root.after(0, viewer2._attach)
                import time

                deadline = time.time() + 8
                while time.time() < deadline and viewer2._attach_tries < 12:
                    root.update()
                    time.sleep(0.05)
                check("找不到窗口会超时放弃", viewer2._attach_tries >= 12, str(viewer2._attach_tries))
                viewer2.close()
            except Exception as exc:  # noqa: BLE001
                check("超时保护", False, f"{type(exc).__name__}: {exc}")

    root.destroy()
    shutil.rmtree(tmp, ignore_errors=True)
    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
