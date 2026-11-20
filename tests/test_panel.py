"""验证主面板：翻译 + 对话 + 隐藏后保留内容。"""

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


def pump(app, seconds: float, until=None) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if until is not None and until():
            return
        app.root.update()
        time.sleep(0.02)


def main() -> int:
    data = HERE / ".panel"
    shutil.rmtree(data, ignore_errors=True)
    data.mkdir(parents=True)
    mock_openai.start(18778)
    mock_openai.CANNED["translation"] = "时尚本质上是短暂的。"
    mock_openai.CANNED["terms"] = [
        {
            "word": "ephemeral",
            "lemma": "ephemeral",
            "reading": "/ɪˈfemərəl/",
            "pos": "形容词",
            "meaning": "短暂的",
            "note": "",
        }
    ]

    cfg = Config(data)
    cfg.data["api"].update(
        {"base_url": "http://127.0.0.1:18778/v1", "api_key": "k", "model": "mock"}
    )
    cfg.data["server_port"] = 18801
    cfg.save()

    from app import Application

    app = Application(cfg, enable_hotkeys=False)
    app.service.store.touch_book("Sapiens", "en")

    print("\n[打开面板]")
    app.open_panel()
    app.root.update()
    check("面板显示", app.panel.win.winfo_ismapped() == 1)
    check("书名显示", "Sapiens" in app.panel.book_label.cget("text"), app.panel.book_label.cget("text"))
    check("建了对话", app.panel.conv_id is not None, str(app.panel.conv_id))

    print("\n[翻译]")
    app.panel.input.insert("1.0", "Fashion is by nature ephemeral.")
    app.panel._translate()
    pump(app, 8, until=lambda: "完成" in app.panel.status.cget("text"))
    output = app.panel.output.get("1.0", "end")
    check("译文进了面板", "时尚本质上是短暂的" in output, output[:80])
    check("译文不再夹带生词", "生词" not in output, output[:120])
    conv = app.service.store.conversation(app.panel.conv_id)
    check("对话上下文更新", "ephemeral" in (conv.get("passage") or ""), str(conv.get("passage"))[:60])

    print("\n[对话]")
    app.panel.chat_input.insert("1.0", "作者为什么这样说？")
    app.panel._send()
    pump(
        app,
        5,
        until=lambda: len(app.service.store.messages(app.panel.conv_id)) == 2,
    )
    messages = app.service.store.messages(app.panel.conv_id)
    check("消息已存储", len(messages) == 2, str(len(messages)))

    print("\n[隐藏后保留]")
    app.panel.hide()
    app.root.update()
    check("面板已隐藏", app.panel.win.winfo_ismapped() == 0)
    app.open_panel()
    app.root.update()
    check("再次打开还在", app.panel.win.winfo_ismapped() == 1)
    check("译文还在", "时尚" in app.panel.output.get("1.0", "end"))
    check("对话还在", len(app.service.store.messages(app.panel.conv_id)) == 2)

    print("\n[手动切书]")
    before = app.panel.conv_id
    app.panel._select_book("Manual Book")
    app.root.update()
    check("书名切过去", "Manual Book" in app.panel.book_label.cget("text"),
          app.panel.book_label.cget("text"))
    check("对话切过去", app.panel.conv_id != before, "对话没切")
    check("记住选择", app.service.config.get("panel_book") == "Manual Book",
          str(app.service.config.get("panel_book")))

    print("\n[自动跟随开关]")
    # 面板隐藏时后台不会跟随前台窗口，避免被真实窗口抢走书名
    app.panel.hide()
    app.root.update()
    app.service.config.data["auto_follow_book"] = False
    app.panel.on_book("Auto Book")
    app.root.update()
    check("关闭时不跟", "Auto Book" not in app.panel.book_label.cget("text"),
          app.panel.book_label.cget("text"))
    app.service.config.data["auto_follow_book"] = True
    app.panel.on_book("Auto Book")
    app.root.update()
    check("开启时跟随", "Auto Book" in app.panel.book_label.cget("text"),
          app.panel.book_label.cget("text"))
    # 恢复可见，后面要测「跟着前台换书」
    app.panel.win.deiconify()
    app.root.update()

    print("\n[主界面跟着前台换书]")
    import app as app_module
    from rc import capture as cap

    orig_exe, orig_title = app_module.foreground_exe, cap.foreground_title
    app_module.foreground_exe = lambda: "okular.exe"
    cap.foreground_title = lambda: "A Third Book - Okular"
    app._book_check_at = 0.0
    app._follow_active_book()
    app.root.update()
    check("跟着换成新书", "A Third Book" in app.panel.book_label.cget("text"),
          app.panel.book_label.cget("text"))
    app_module.foreground_exe = orig_exe
    cap.foreground_title = orig_title

    print("\n[关闭行为]")
    app.service.config.data["quit_on_panel_close"] = False
    app.panel._on_close()
    app.root.update()
    check("关掉设置时只是隐藏", app.panel.win.winfo_ismapped() == 0)
    app.open_panel()
    app.root.update()
    check("还能再打开", app.panel.win.winfo_ismapped() == 1)
    app.service.config.data["quit_on_panel_close"] = True

    app.shutdown()
    shutil.rmtree(data, ignore_errors=True)
    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
