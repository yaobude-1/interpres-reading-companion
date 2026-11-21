"""回归：单词表列头排序、排序记忆，以及和搜索叠加。"""

from __future__ import annotations

import shutil
import sys
import tkinter as tk
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from rc.config import Config  # noqa: E402
from rc.service import Service  # noqa: E402
from rc.vocab_panel import VocabPanel  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


def order(panel) -> list[str]:
    return [panel.word_tree.set(iid, "word") for iid in panel.word_tree.get_children()]


def main() -> int:
    data = HERE / ".vocabsort"
    shutil.rmtree(data, ignore_errors=True)
    data.mkdir(parents=True)
    cfg = Config(data)
    svc = Service(cfg)

    for word, meaning in (
        ("banana", "香蕉"),
        ("apple", "苹果"),
        ("cherry", "樱桃"),
    ):
        svc.add_vocab(lang="en", word=word, lemma=word, meaning=meaning)

    book = svc.store.default_wordbook("en")
    root = tk.Tk()
    root.withdraw()
    frame = tk.Frame(root)
    panel = VocabPanel(frame, svc, cfg)
    panel.book_id = int(book["id"])
    panel.load_words()
    root.update()

    print("\n[默认排序]")
    check("默认按添加时间倒序", panel._sort_key == "time" and panel._sort_desc is True)
    check("默认表头有箭头", "▼" in panel.word_tree.heading("time", "text"), panel.word_tree.heading("time", "text"))

    print("\n[按单词排序]")
    panel._sort_by("word")
    root.update()
    check("升序", order(panel) == ["apple", "banana", "cherry"], str(order(panel)))
    check("表头箭头", "▲" in panel.word_tree.heading("word", "text"), panel.word_tree.heading("word", "text"))
    panel._sort_by("word")
    root.update()
    check("再点变降序", order(panel) == ["cherry", "banana", "apple"], str(order(panel)))
    check("降序表头", "▼" in panel.word_tree.heading("word", "text"), panel.word_tree.heading("word", "text"))

    print("\n[点表头]")
    panel.word_tree.event_generate("<Button-1>", x=30, y=10)
    panel.word_tree.event_generate("<ButtonRelease-1>", x=30, y=10)
    root.update()
    check("点表头切换排序", panel._sort_key == "word", str(panel._sort_key))

    print("\n[记住选择]")
    check("配置写入 key", cfg.get("vocab_sort_key") == "word", str(cfg.get("vocab_sort_key")))
    check("配置写入方向", bool(cfg.get("vocab_sort_desc")) is True)

    panel2 = VocabPanel(frame, svc, cfg)
    panel2.book_id = int(book["id"])
    panel2.load_words()
    root.update()
    check("新面板沿用降序", order(panel2) == ["cherry", "banana", "apple"], str(order(panel2)))

    print("\n[与搜索叠加]")
    panel._sort_by("word")
    root.update()
    panel.search_var.set("an")
    panel.load_words()
    root.update()
    check("过滤后仍排序", order(panel) == ["banana"], str(order(panel)))
    panel.search_var.set("")
    panel.load_words()
    root.update()

    print("\n[选中项保持]")
    apple = next(iid for iid in panel.word_tree.get_children() if panel.word_tree.set(iid, "word") == "apple")
    panel.word_tree.selection_set(apple)
    panel._sort_by("word")
    root.update()
    check("排序后仍是同一个词选中", panel.word_tree.selection() == (apple,), str(panel.word_tree.selection()))

    root.destroy()
    svc.store.close()
    shutil.rmtree(data, ignore_errors=True)
    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
