"""打印词条 HTML 的结构轮廓，用来定位 DOM 重排的容器。"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from lxml import html as lxml_html  # noqa: E402

from rc.config import Config  # noqa: E402
from rc.dictionary import Dictionary  # noqa: E402


def outline(node, depth: int = 0, max_depth: int = 3, limit: int = 14) -> None:
    children = [c for c in node if isinstance(c.tag, str)]
    for index, child in enumerate(children[:limit]):
        classes = (child.get("class") or "").strip()
        text = " ".join((child.text_content() or "").split())[:36]
        print("  " * depth + f"[{index}] <{child.tag}> .{classes}  «{text}»")
        if depth + 1 < max_depth:
            outline(child, depth + 1, max_depth, limit)
    if len(children) > limit:
        print("  " * depth + f"... (+{len(children) - limit} more)")


def main() -> int:
    word = sys.argv[1] if len(sys.argv) > 1 else "seek"
    cfg = Config()
    paths = (cfg.data.get("dictionaries") or {}).get("en") or {}
    dic = Dictionary(paths.get("mdx"), paths.get("mdd"))
    raw = dic._mdx.lookup(word)
    html = raw[1] if isinstance(raw, tuple) else raw
    if isinstance(html, bytes):
        html = html.decode("utf-8", "replace")
    tree = lxml_html.fromstring(html)
    print("root:", tree.tag, ".", tree.get("class"))
    outline(tree, 0, 2, 18)
    print("\nsensenum nodes:", len(tree.xpath('.//*[contains(@class,"sensenum")]')))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
