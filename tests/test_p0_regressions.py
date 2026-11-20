"""Regression checks for the P0 issues found in the project review."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from rc.anki import Anki  # noqa: E402
from rc.config import Config  # noqa: E402
from rc.mdx import MDXError, _inflate_block  # noqa: E402
from rc.service import Service  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


def main() -> int:
    data = HERE / ".p0-regressions"
    shutil.rmtree(data, ignore_errors=True)
    data.mkdir(parents=True)
    cfg = Config(data)
    service = Service(cfg)

    print("\n[重复收藏不丢字段]")
    service.add_vocab(
        lang="en", word="alpha", lemma="alpha", meaning="first",
        book="Book A", dict_meaning="dict A", dict_example="example A",
    )
    service.add_vocab(
        lang="en", word="alpha", lemma="alpha", meaning="second",
        book="", dict_meaning="", dict_example="",
    )
    word = service.find_vocab("en", "alpha") or {}
    check("book 保留", word.get("book") == "Book A", str(word))
    check("dict_meaning 保留", word.get("dict_meaning") == "dict A", str(word))
    check("dict_example 保留", word.get("dict_example") == "example A", str(word))
    check("meaning 仍更新", word.get("meaning") == "second", str(word))

    print("\n[长对话取最新消息]")
    conv_id = service.store.start_conversation("T", "en", "", "")
    for index in range(205):
        service.store.add_message(conv_id, "user", f"m{index}")
    messages = service.store.messages(conv_id, 200)
    check("保留 200 条", len(messages) == 200, str(len(messages)))
    check("取最新范围", messages[0]["content"] == "m5" and messages[-1]["content"] == "m204",
          f'{messages[0]["content"]}..{messages[-1]["content"]}')

    print("\n[缓存键随配置变化]")
    key1 = service._cache_key("text", "book", "en", "zh", "", "", [("a", "甲")])
    key2 = service._cache_key("text", "book", "en", "zh", "", "", [("a", "乙")])
    check("glossary 影响缓存键", key1 != key2)
    old_model = service.config.api.get("model")
    service.config.api["model"] = "another-model"
    key3 = service._cache_key("text", "book", "en", "zh", "", "", [("a", "甲")])
    service.config.api["model"] = old_model
    check("model 影响缓存键", key1 != key3)

    print("\n[Anki 只更新第一个模板]")
    anki = object.__new__(Anki)
    calls = []

    def fake_names(model):
        return ["Card 1", "Recall"]

    def fake_invoke(action, **params):
        calls.append((action, params))
        return None

    anki.model_template_names = fake_names  # type: ignore[method-assign]
    anki._invoke = fake_invoke  # type: ignore[method-assign]
    anki.update_custom_templates("Custom", "F", "B", "C")
    templates = calls[0][1]["model"]["templates"]
    check("只包含 Card 1", list(templates) == ["Card 1"], str(templates))
    check("未改 Recall", "Recall" not in templates, str(templates))

    print("\n[MDX 解压上限]")
    import zlib

    bomb = zlib.compress(b"x" * (64 * 1024 * 1024 + 1))
    try:
        _inflate_block((2).to_bytes(4, "little") + b"\0" * 4 + bomb)
        check("拒绝超大记录", False, "没有抛错")
    except MDXError:
        check("拒绝超大记录", True)

    shutil.rmtree(data, ignore_errors=True)
    print("\n" + "=" * 50)
    print(f"通过 {len(fails) == 0 and '全部' or '部分'}；失败 {len(fails)} 项")
    for name in fails:
        print("  ✗", name)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
