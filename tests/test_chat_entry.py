"""验证「选完字就能聊」：翻译还没出来时也能开对话；气泡上也能进对话。"""

from __future__ import annotations

import shutil
import sys
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
    data = HERE / ".chatentry"
    shutil.rmtree(data, ignore_errors=True)
    data.mkdir(parents=True)
    mock_openai.start(18778)

    cfg = Config(data)
    cfg.data["api"].update(
        {"base_url": "http://127.0.0.1:18778/v1", "api_key": "k", "model": "mock"}
    )
    cfg.data["server_port"] = 18799
    cfg.save()

    from app import Application

    app = Application(cfg, enable_hotkeys=False)

    print("\n[翻译中就能聊]")
    app.popup.show_loading("Fashion is by nature ephemeral.", "Sapiens", "en", (400, 300))
    app.root.update()
    check("加载状态显示聊天按钮", app.popup.btn_chat.winfo_ismapped() == 1)
    app.popup._open_chat()
    app.root.update()
    check("进入了对话模式", app.popup._mode == "chat")
    convs = app.service.conversations("Sapiens")
    check("对话已创建", len(convs) == 1, str(len(convs)))
    check("对话记下了原文", "ephemeral" in (convs[0].get("passage") or ""), str(convs[0])[:120])
    check("翻译字段允许为空", convs[0].get("translation") == "", str(convs[0].get("translation")))

    print("\n[聊天时翻译结果回来不打断]")
    app.popup.show_result(
        {
            "text": "Fashion is by nature ephemeral.",
            "translation": "时尚本质上是短暂的。",
            "source_lang": "en",
            "book": "Sapiens",
            "terms": [],
            "grammar": None,
            "meta": {},
        },
        (400, 300),
    )
    app.root.update()
    check("仍在对话模式", app.popup._mode == "chat")

    print("\n[气泡上直接聊]")
    app.popup._reset_to_translate(chat_button=True)
    payload = {
        "text": "The quick brown fox.",
        "translation": "敏捷的棕色狐狸。",
        "source_lang": "en",
        "book": "Test",
        "terms": [],
        "grammar": None,
        "meta": {},
    }
    app._bubble_chat(payload, (500, 400))
    app.root.update()
    check("气泡进入对话模式", app.popup._mode == "chat")
    convs = app.service.conversations("Test")
    check("气泡对话也建了记录", len(convs) == 1, str(len(convs)))

    print("\n[悬浮按钮「聊」不翻译直接开]")
    app.popup._reset_to_translate(chat_button=True)
    app.popup.show_chat_pending("Another passage to discuss.", "Third Book", (300, 300))
    app.root.update()
    check("进入对话模式", app.popup._mode == "chat")
    convs = app.service.conversations("Third Book")
    check("对话已创建", len(convs) == 1, str(len(convs)))
    check("没有译文", convs[0].get("translation") == "", str(convs[0].get("translation")))

    app.shutdown()
    mock_openai.start  # noqa: B018
    shutil.rmtree(data, ignore_errors=True)
    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
