"""验证对话功能：开启 → 提问 → 记忆 → 管理。"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from rc.config import Config  # noqa: E402
from rc.service import Service  # noqa: E402
from tests import mock_openai  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


def main() -> int:
    data = HERE / ".chat"
    shutil.rmtree(data, ignore_errors=True)
    data.mkdir(parents=True)
    mock_openai.start(18778)

    cfg = Config(data)
    cfg.data["api"].update(
        {"base_url": "http://127.0.0.1:18778/v1", "api_key": "k", "model": "mock"}
    )
    cfg.save()
    service = Service(cfg)

    print("\n[开启对话]")
    conv = service.start_conversation(
        "Sapiens", "en", "Fashion is by nature ephemeral.", "时尚本质上是短暂的。"
    )
    check("对话已创建", conv["id"] > 0, str(conv))
    check("初始没有消息", len(conv["messages"]) == 0, str(conv["messages"]))

    print("\n[提问与记忆]")
    result = service.ask(conv["id"], "作者为什么这样说？")
    check("拿到了回复", bool(result.get("reply")), str(result)[:80])
    check("消息已保存（2 条）", len(result["messages"]) == 2, str(result["messages"]))

    again = service.ask(conv["id"], "那和前文有什么关系？")
    check("第二轮也有回复", bool(again.get("reply")), str(again)[:80])
    check("累计 4 条消息", len(again["messages"]) == 4, str(len(again["messages"])))

    print("\n[长段落完整进上下文]")
    service.config.data["chat_passage_chars"] = 0  # 这一段专门验证 0 = 不限制
    long_passage = "This is a long paragraph. " * 800 + "TAILMARKER_END"
    long_conv = service.start_conversation("Long Book", "en", long_passage, "很长的一段译文。")
    service.ask(long_conv["id"], "这段讲了什么？")
    system = mock_openai._Handler.last_body["messages"][0]["content"]
    check("上限 0 时两万字也能完整进上下文", "TAILMARKER_END" in system, f"{len(long_passage)} 字")
    check("标注了全文长度", "共" in system and "字" in system, system[system.find("用户正在读"):][:60])

    print("\n[超上限时明确告知]")
    service.config.data["chat_passage_chars"] = 100
    service.ask(long_conv["id"], "再看一次？")
    system = mock_openai._Handler.last_body["messages"][0]["content"]
    check("说明只给了前 100 字", "只给出前 100 字" in system, system[system.find("用户正在读"):][:80])
    check("说明还有多少没给", "没给你" in system, system[system.find("用户正在读"):][:120])
    service.config.data["chat_passage_chars"] = 40000
    service.delete_conversation(long_conv["id"])

    print("\n[按书管理]")
    service.start_conversation("A History of Philosophy", "en", "The history of philosophy...", "哲学史…")
    books = service.books_with_conversations()
    names = [b["book"] for b in books]
    check("两本书都有记录", set(names) == {"Sapiens", "A History of Philosophy"}, str(names))
    sapiens = service.conversations("Sapiens")
    check("Sapiens 下有 1 段对话", len(sapiens) == 1, str(len(sapiens)))

    service.rename_book("A History of Philosophy", "哲学史")
    names = [b["book"] for b in service.books_with_conversations()]
    check("改名生效", "哲学史" in names, str(names))

    exported = service.export_conversations("Sapiens")
    path = Path(exported["path"])
    check("导出 Markdown", path.exists() and "作者为什么" in path.read_text(encoding="utf-8"), str(path))

    service.delete_conversation(conv["id"])
    check("删除单段对话", len(service.conversations("Sapiens")) == 0)
    removed = service.delete_book_conversations("哲学史")
    check("删除整本书", removed == 1, str(removed))
    check("已经清空", len(service.books_with_conversations()) == 0)

    service.store.close()
    mock_openai.start  # noqa: B018
    shutil.rmtree(data, ignore_errors=True)
    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
