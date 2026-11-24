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

    head = page.split("<body", 1)[0]
    check("样式提到 head", 'href="dict.css"' in head, head[-300:])
    check("只有一个 head", page.count("<head") == 1 and page.count("</head>") == 1, page[:300])
    check("词典脚本不执行", "zngq_evil()" not in page, page)
    check("内联事件清理", "onclick=" not in page, page)
    check("javascript 链接清理", "javascript:" not in page, page)

    styled = build_raw_page(
        '<head><link rel="stylesheet" href="zngq.css">'
        '<style>.x:before{content:"N"}</style>'
        "<script>zngq_evil()</script></head>"
        '<zngq><span tab="Noun1" onclick="zngq_evil()">Noun</span></zngq>',
        source="OED",
        word="test",
        resource_base="http://127.0.0.1:9/api/dict-res/en/tok/",
        lookup_base="interpres://lookup?word=",
    )
    head = styled.split("<body", 1)[0]
    check("OED CSS 提到 head", 'href="zngq.css"' in head and ".x:before" in head, head)
    check("OED tab 属性保留", 'tab="Noun1"' in styled, styled)
    check("OED 脚本清理", "zngq_evil" not in styled, styled)
    check("OED 无嵌套 head", styled.count("<head") == 1, styled[:300])

    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
