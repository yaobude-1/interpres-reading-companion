"""验证书籍解析、导入、定位、检索。"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from rc.book import parse_book  # noqa: E402
from rc.store import Store  # noqa: E402

EPUB = (
    r"D:\Downloads\Quest-ce que la philosophie  (Gilles Deleuze, "
    r"Félix Guattari) (z-library.sk, 1lib.sk, z-lib.sk).epub"
)

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


def main() -> int:
    data = HERE / ".book"
    shutil.rmtree(data, ignore_errors=True)
    data.mkdir(parents=True)

    print("\n[解析 EPUB]")
    info = parse_book(EPUB)
    print(f"  标题: {info['title']} | 章节: {len(info['sections'])}")
    check("有标题", bool(info["title"]), info["title"])
    check("解析出章节", len(info["sections"]) >= 3, str(len(info["sections"])))
    total = sum(len(s["paragraphs"]) for s in info["sections"])
    print(f"  段落总数: {total}")
    check("解析出段落", total > 100, str(total))
    print("  前三个章节:",
          [s["title"][:20] for s in info["sections"][:3]])

    print("\n[入库]")
    store = Store(data / "test.db")
    book_id = store.import_book(EPUB, info["title"], "epub", info["sections"])
    book = store.book(book_id)
    check("书目已存", book is not None and book["para_count"] == total, str(book))
    check("可重复导入", store.import_book(EPUB, info["title"], "epub", info["sections"]) == book_id)

    print("\n[定位：拿一段文字找位置]")
    sample_section = info["sections"][2]
    sample_para = sample_section["paragraphs"][3]
    found = store.find_paragraph(book_id, sample_para[:120])
    check("定位到段落", found is not None, str(found))
    if found:
        check("章节对得上", int(found["section_idx"]) == 2, str(found["section_idx"]))
    store.set_book_position(book_id, 2, 0)
    book = store.book(book_id)
    check("位置已保存", book["position_section"] == 2, str(book["position_section"]))

    print("\n[检索：只在读过的范围]")
    hits = store.search_book(book_id, ["philosophie", "concept"], max_section=2, limit=5)
    check("检索到内容", len(hits) > 0, str(len(hits)))
    check("没有越过位置", all(int(h["section_idx"]) <= 2 for h in hits), str(hits))
    far = store.search_book(book_id, ["philosophie"], max_section=0, limit=20)
    check("范围收紧有效", all(int(h["section_idx"]) <= 0 for h in far), str(len(far)))

    store.close()
    shutil.rmtree(data, ignore_errors=True)
    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
