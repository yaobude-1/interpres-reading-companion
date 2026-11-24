"""原始 HTML 页面：MDX 资源/链接重写与 base 注入。"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from rc.dict_view import build_raw_page  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


def main() -> int:
    raw = (
        '<link rel="stylesheet" href="dict.css">'
        '<article class="entry"><h1>gehen</h1>'
        '<img src="pics/a.png">'
        '<audio src="sound://audio/go.mp3"></audio>'
        '<a href="entry://laufen">laufen</a>'
        "</article>"
    )
    page = build_raw_page(
        raw,
        source="Test Dictionary",
        word="gehen",
        resource_base="http://127.0.0.1:9/api/dict-res/de/tok/",
        lookup_base="interpres://lookup?word=",
    )
    print("\n[页面]")
    check("包含 base", '<base href="http://127.0.0.1:9/api/dict-res/de/tok/">' in page, page[:200])
    check("原始 HTML 保留", '<article class="entry">' in page, "")
    check("相对 CSS 保留", 'href="dict.css"' in page, "")
    check("相对图片保留", 'src="pics/a.png"' in page, "")
    check(
        "sound:// 重写",
        'http://127.0.0.1:9/api/dict-res/de/tok/audio/go.mp3' in page,
        page,
    )
    check(
        "entry:// 重写",
        'interpres://lookup?word=laufen' in page,
        page,
    )
    check("没有残留 sound://", "sound://" not in page, page)
    check("没有残留 entry://", "entry://" not in page, page)

    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
