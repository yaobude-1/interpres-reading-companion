"""异常处理卫生：不允许再出现“宽泛吞错且静默”。

评审 A-2：`except Exception` / `except BaseException` / 裸 `except` 后面只跟
`pass`，会把 bug 吞成静默失效。第一批已把这些点收窄为具体异常，或改为
`log.debug/warning` 记录。此测试防止回退。

只检查 pass-only 的宽泛捕获；具体异常（`tk.TclError` / `OSError` 等）的
`pass` 是刻意为之，不在此列。
"""

from __future__ import annotations

import ast
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

BROAD = {"Exception", "BaseException"}


def _sources() -> list[Path]:
    files = sorted(ROOT.glob("app*.py")) + sorted((ROOT / "rc").glob("*.py"))
    return [p for p in files if p.is_file()]


def silent_broad_handlers(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hits: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        for handler in node.handlers:
            typ = ast.unparse(handler.type) if handler.type else "BARE"
            if typ not in BROAD and typ != "BARE":
                continue
            if len(handler.body) == 1 and isinstance(handler.body[0], ast.Pass):
                hits.append(f"{path.relative_to(ROOT)}:{handler.lineno}: {typ}")
    return hits


def main() -> int:
    hits: list[str] = []
    for path in _sources():
        hits.extend(silent_broad_handlers(path))
    if hits:
        print("发现宽泛静默吞错（应改为具体异常，或记录日志）：")
        for hit in hits:
            print("  " + hit)
        return 1
    print("  ok   没有宽泛静默吞错")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
