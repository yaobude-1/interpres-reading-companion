"""验证划词交互的几条路径：

1. 点「译」按钮（真实 Tk 点击事件）→ 翻译 → 气泡显示
2. 在别处点一下 → 按钮和气泡都消失
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from rc.config import Config  # noqa: E402
from tests import mock_openai  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


def pump(app, seconds: float, until=None) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if until is not None and until():
            return
        app.root.update()
        time.sleep(0.02)


def main() -> int:
    data = HERE / ".bubbleflow"
    mock_openai.start(18778)
    cfg = Config(data)
    cfg.data["api"].update(
        {"base_url": "http://127.0.0.1:18778/v1", "api_key": "k", "model": "mock"}
    )
    cfg.data["server_port"] = 18792
    cfg.data["selection"]["button"]["hide_mode"] = "always"
    cfg.save()

    from app import Application

    app = Application(cfg, enable_hotkeys=False)

    print("\n[点按钮 → 翻译]")
    app._pending_selection = (
        "The quick brown fox jumps over the lazy dog.",
        "Test Book",
        (900, 360),
    )
    app.quick.show((900, 360))
    pump(app, 0.5)
    check("按钮已显示", app.quick.visible)
    app.quick.label.event_generate("<Button-1>", x=4, y=4)
    pump(app, 6, until=lambda: bool(app.bubble.payload))
    payload = app.bubble.payload or {}
    check("点一次就出译文", bool(payload.get("translation")), str(payload)[:120])
    check("按钮已收起", not app.quick.visible)

    print("\n[点别处 → 收起]")
    app.quick.show((900, 360))
    pump(app, 0.4)
    check("按钮再次显示", app.quick.visible)
    app.events.put(("press", (300, 300)))
    pump(app, 1.2, until=lambda: not app.quick.visible)
    check("别处点击后按钮消失", not app.quick.visible)
    check("气泡也消失了", not app.bubble.win.winfo_viewable())

    app.shutdown()
    import shutil

    shutil.rmtree(data, ignore_errors=True)
    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
