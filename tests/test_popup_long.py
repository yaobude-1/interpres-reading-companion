"""验证：长译文浮窗能滚动；长段落走大浮窗；热键先给反馈。"""

from __future__ import annotations

import shutil
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


def main() -> int:
    data = HERE / ".popuplong"
    shutil.rmtree(data, ignore_errors=True)
    data.mkdir(parents=True)
    mock_openai.start(18778)

    cfg = Config(data)
    cfg.data["api"].update(
        {"base_url": "http://127.0.0.1:18778/v1", "api_key": "k", "model": "mock"}
    )
    cfg.data["server_port"] = 18804
    cfg.save()

    from app import Application

    app = Application(cfg, enable_hotkeys=False)

    print("\n[长译文可滚动]")
    long_text = "这是一段很长的译文，用来测试滚动。" * 120
    app.popup.show_result(
        {
            "translation": long_text,
            "text": "Source " * 80,
            "source_lang": "en",
            "book": "",
            "terms": [],
            "grammar": None,
            "meta": {},
        },
        (300, 200),
    )
    app.root.update()
    canvas = app.popup.canvas
    content_h = app.popup.body.winfo_reqheight()
    check("内容比视口高", content_h > canvas.winfo_height(), f"{content_h} vs {canvas.winfo_height()}")
    view = canvas.yview()
    check("打开时在顶部", view[0] <= 0.02, str(view))
    canvas.yview_scroll(5, "units")
    app.root.update()
    check("能往下滚", canvas.yview()[0] > 0.05, str(canvas.yview()))

    print("\n[热键先给反馈]")
    app.popup.show_busy((300, 200))
    app.root.update()
    check("浮窗立即出现", app.popup.visible, "")
    texts = [w.cget("text") for w in app.popup.body.winfo_children() if hasattr(w, "cget")]
    check("显示读取提示", any("读取" in str(t) for t in texts), str(texts)[:80])

    print("\n[长段落走大浮窗，不走气泡]")
    app._pending_selection = ("A long paragraph. " * 40, "Sapiens", (0, 0))
    app.popup.hide()
    app._open_selection_bubble((400, 300))
    deadline = time.time() + 3
    while time.time() < deadline and not app.popup.visible:
        app.root.update()
        time.sleep(0.03)
    app.root.update()
    check("气泡没出现", app.bubble.win.winfo_ismapped() == 0)
    check("浮窗出现了", app.popup.visible)
    check("处于翻译模式", app.popup._mode == "translate", app.popup._mode)
    time.sleep(0.3)

    print("\n[气泡里的超长译文截断]")
    app.bubble.show_result(
        {"translation": "很长的译文" * 300, "text": "x", "source_lang": "en",
         "book": "", "terms": [], "grammar": None, "meta": {}},
        (500, 300),
    )
    app.root.update()
    shown = app.bubble.display.cget("text")
    check("气泡截断显示", len(shown) < 700, str(len(shown)))
    check("提示看详情", "详情" in shown, shown[-30:])
    check("完整译文仍在", len(app.bubble.payload["translation"]) > 1000)

    app.shutdown()
    shutil.rmtree(data, ignore_errors=True)
    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
