"""Original dictionary entry: internal entry:// links are routed back to the app."""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from rc.entryhtml import _TOGGLE_JS, rewrite_entry_links  # noqa: E402
from rc.htmlview import parse_lookup_title  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


def main() -> int:
    print("\n[原版条目内部链接]")
    rewritten = rewrite_entry_links('<a href="entry://know">know</a>')
    check("entry:// 改成 data-entry", 'data-entry="know"' in rewritten, rewritten)
    check("脚本拦截 data-entry", "[data-entry]" in _TOGGLE_JS)
    check("脚本写窗口标题", "rc-lookup:" in _TOGGLE_JS)

    print("\n[标题解析]")
    check("普通查询", parse_lookup_title("rc-lookup:know:123456") == "know")
    check("URL 编码", parse_lookup_title("rc-lookup:ice%20cream:1") == "ice cream")
    check("非查找标题", parse_lookup_title("rc-entry-abcd 词典") == "")

    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
