"""回归：列宽按比例铺满表格，拖动后归一，不出现横向溢出。"""

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


def widths(panel) -> list[int]:
    return [int(panel.word_tree.column(c, "width")) for c in panel._COLS]


def main() -> int:
    data = HERE / ".voccoldemo"
    shutil.rmtree(data, ignore_errors=True)
    data.mkdir(parents=True)
    cfg = Config(data)
    svc = Service(cfg)
    svc.add_vocab(lang="en", word="volume", lemma="volume", meaning="音量")

    root = tk.Tk()
    root.geometry("900x620")
    frame = tk.Frame(root)
    frame.pack(fill="both", expand=True)
    panel = VocabPanel(frame, svc, cfg)
    panel.book_id = int(svc.store.default_wordbook("en")["id"])
    panel.load_words()
    root.update()

    tree_width = panel.word_tree.winfo_width()
    print("\n[铺满]")
    check("初始铺满表格宽度", abs(sum(widths(panel)) - tree_width) <= 2, f"{widths(panel)} vs {tree_width}")
    check("不出现横向滚动", panel.word_tree.xview()[1] > 0.99, str(panel.word_tree.xview()))

    print("\n[拖动后归一]")
    before = widths(panel)
    word_index = panel._COLS.index("word")
    panel.word_tree.column("word", width=before[word_index] + 150)
    check("拖动后总宽暂时溢出", sum(widths(panel)) > tree_width)
    panel._normalize_widths()
    root.update()
    after = widths(panel)
    check("归一后总宽等于表格", abs(sum(after) - tree_width) <= 2, f"{after} vs {tree_width}")
    check("被拖的列变宽", after[word_index] > before[word_index], f"{before} -> {after}")
    check(
        "每列不低于最小宽度",
        all(w >= panel._COL_MINS[c] for w, c in zip(after, panel._COLS, strict=False)),
        str(after),
    )
    check("比例已保存", isinstance(cfg.get("vocab_col_ratios"), list), str(cfg.get("vocab_col_ratios")))

    print("\n[窗口缩放]")
    root.geometry("720x620")
    root.update()
    scaled = widths(panel)
    check("缩放后仍铺满", abs(sum(scaled) - panel.word_tree.winfo_width()) <= 2, f"{scaled}")

    print("\n[重启恢复比例]")
    saved = list(cfg.get("vocab_col_ratios") or [])
    panel2 = VocabPanel(frame, svc, cfg)
    root.update()
    check("新面板沿用比例", all(abs(a - b) < 0.01 for a, b in zip(panel2._col_ratios, saved, strict=False)), f"{panel2._col_ratios} vs {saved}")

    print("\n[表头文字]")
    check("时间列简洁", panel.word_tree.heading("time", "text").startswith("时间"), panel.word_tree.heading("time", "text"))

    root.destroy()
    svc.store.close()
    shutil.rmtree(data, ignore_errors=True)
    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
