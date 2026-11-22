"""Default translation prompt: plain text, no source/grammar/terms metadata."""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from rc.llm import SYSTEM_PROMPT, Translator, _partial_translation  # noqa: E402
from rc.prompts_en import SYSTEM_PROMPT_EN  # noqa: E402

fails: list[str] = []
translator = Translator(None)


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


def main() -> int:
    print("\n[默认提示词]")
    check("中文不含 source_lang", "source_lang" not in SYSTEM_PROMPT)
    check("中文不含术语表", "术语表" not in SYSTEM_PROMPT)
    check("中文不含生词字段", '"terms"' not in SYSTEM_PROMPT)
    check("中文不含语法字段", '"grammar"' not in SYSTEM_PROMPT)
    check("英文不含 source_lang", "source_lang" not in SYSTEM_PROMPT_EN)
    check("英文不含 glossary", "glossary" not in SYSTEM_PROMPT_EN.lower())
    check("中文不限制义项数", "最多" not in SYSTEM_PROMPT)
    check("中文不要求简洁", "简洁" not in SYSTEM_PROMPT)
    check("英文不限制义项数", "at most" not in SYSTEM_PROMPT_EN.lower())
    check("英文不要求简洁", "concise" not in SYSTEM_PROMPT_EN.lower())

    print("\n[纯译文解析]")
    plain = translator._parse("Hello\nworld")
    check("译文原样保留", plain["translation"] == "Hello\nworld", repr(plain["translation"]))
    check("没有生词", plain["terms"] == [])
    check("没有语法", plain["grammar"] is None)
    check("没有原文语言", plain["source_lang"] == "")
    fenced = translator._parse("```text\n你好\n```")
    check("去掉代码围栏", fenced["translation"] == "你好", repr(fenced["translation"]))
    old_json = translator._parse('{"translation": "你好"}')
    check("兼容旧 JSON", old_json["translation"] == "你好", repr(old_json["translation"]))

    print("\n[流式纯文本]")
    check("普通文本", _partial_translation("Hello") == "Hello")
    check("未闭合 JSON 仍可用", _partial_translation('{"translation": "你') == "你")

    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
