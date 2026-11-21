"""对话上下文：保存、注入提示词、手动补充。"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from rc.config import Config  # noqa: E402
from rc.service import Service  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


def main() -> int:
    data = HERE / ".chatcontext"
    shutil.rmtree(data, ignore_errors=True)
    data.mkdir(parents=True)
    cfg = Config(data)
    svc = Service(cfg)

    paragraph = "The quick brown fox jumps over the lazy dog. Vacuola means vacuole here."

    print("\n[保存与注入]")
    conv = svc.start_conversation("Interrogating the Real", "en", "vacuola", "", paragraph)
    conv_id = int(conv["id"])
    row = svc.store.conversation(conv_id)
    check("conversation 存了 context", row.get("context") == paragraph, str(row.get("context")))
    system = svc._chat_system(row)
    check("提示词包含段落", paragraph in system, system[:200])
    check("提示词标注自动读取", "自动读取" in system, system[:300])
    check("单词场景规则", "选中的单词" in system, system[-260:])

    print("\n[没有上下文]")
    conv2 = svc.start_conversation("Some Book", "en", "vacuola", "")
    row2 = svc.store.conversation(int(conv2["id"]))
    system2 = svc._chat_system(row2)
    check("不注入段落", "自动读取" not in system2, system2[:200])
    check("start_chat 返回 context 字段", conv2.get("context") == "")

    print("\n[手动补充]")
    svc.set_conversation_context(conv2["id"], "A sentence with vacuola in it.")
    row2 = svc.store.conversation(int(conv2["id"]))
    check("补充后写入数据库", row2.get("context") == "A sentence with vacuola in it.", str(row2.get("context")))
    check("补充后进入提示词", "A sentence with vacuola" in svc._chat_system(row2))

    print("\n[默认值]")
    check("自动读取默认开启", bool(cfg.get("chat_auto_context", True)) is True)
    check("原文上限默认 4000", int(cfg.get("chat_passage_chars", 0)) == 4000)

    svc.store.close()
    shutil.rmtree(data, ignore_errors=True)

    print("\n[Application 接入]")
    data2 = HERE / ".chatcontext-app"
    shutil.rmtree(data2, ignore_errors=True)
    data2.mkdir(parents=True)
    cfg2 = Config(data2)
    cfg2.data["server_port"] = 18793
    cfg2.save()

    import rc.uia_context as uia
    from app import Application

    original = uia.read_context
    uia.read_context = lambda hwnd, timeout=2.5: {
        "ok": True,
        "paragraph": f"paragraph for {int(hwnd)}",
    }
    try:
        app = Application(cfg2, enable_hotkeys=False)
        try:
            result = app.start_chat(
                {"book": "B", "text": "vacuola", "source_lang": "en", "hwnd": 123}
            )
            row = app.service.store.conversation(int(result["id"]))
            check("自动读取写进会话", row.get("context") == "paragraph for 123", str(row.get("context")))
            cfg2.data["chat_auto_context"] = False
            cfg2.save()
            result2 = app.start_chat(
                {"book": "B", "text": "vacuola", "source_lang": "en", "hwnd": 456}
            )
            row2 = app.service.store.conversation(int(result2["id"]))
            check("关闭开关后不读取", row2.get("context") == "", str(row2.get("context")))
        finally:
            app.shutdown()
    finally:
        uia.read_context = original
        shutil.rmtree(data2, ignore_errors=True)

    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
