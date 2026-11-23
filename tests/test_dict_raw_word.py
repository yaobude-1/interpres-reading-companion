"""原版页面词头选择：输入变形不能直接拿去查 MDX。"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from rc.panel_dict import _dict_raw_candidates  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


def main() -> int:
    print("\n[原版词头]")
    check(
        "优先 matched",
        _dict_raw_candidates(
            {"matched": "vendre", "word": "vendre"}, "vends"
        )[:2]
        == ["vendre", "vends"],
        str(_dict_raw_candidates({"matched": "vendre", "word": "vendre"}, "vends")),
    )
    check(
        "没有 matched 时用 word",
        _dict_raw_candidates({"word": "vend"}, "vends")[:2] == ["vend", "vends"],
        str(_dict_raw_candidates({"word": "vend"}, "vends")),
    )
    check(
        "morph lemma 兜底",
        _dict_raw_candidates({"morph": {"lemma": "vendre"}}, "vends")[:2]
        == ["vendre", "vends"],
        str(_dict_raw_candidates({"morph": {"lemma": "vendre"}}, "vends")),
    )
    check(
        "输入词保留为最后兜底",
        _dict_raw_candidates({}, "vends") == ["vends"],
        str(_dict_raw_candidates({}, "vends")),
    )
    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
