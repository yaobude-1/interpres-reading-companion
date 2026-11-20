"""词典探针：验证 MDX 解析与查词效果。"""

from __future__ import annotations

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from rc.mdx import MDX, html_to_text  # noqa: E402

DICT = r"D:\Downloads\Compressed\Longman Dictionary of Contemporary English 6th ed. Summer Edition (MDX)\朗文当代高级英语辞典 第6版 夏日清凉版 V3.2\朗文当代高级英语词典6th.mdx"


def main() -> int:
    started = time.time()
    d = MDX(DICT)
    print(f"加载耗时 {time.time() - started:.1f}s | 条目 {d.entry_count} | 编码 {d.encoding} | 版本 {d.version}")
    for word in ("ephemeral", "sanguine", "quixotic", "run"):
        t0 = time.time()
        html = d.lookup(word)
        cost = (time.time() - t0) * 1000
        if not html:
            print(f"\n[{word}] 没找到")
            continue
        text = html_to_text(html)
        print(f"\n[{word}] 查词 {cost:.0f}ms | HTML {len(html)} 字节 | 文本 {len(text)} 字")
        print(text[:400].replace("\n", " | "))
    d.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
