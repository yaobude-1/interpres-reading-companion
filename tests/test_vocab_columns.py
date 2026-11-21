"""回归：拖动分隔线时只移动那条交界线，列到最小宽度后把余量传给下一条。"""

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

    print("\n[初始铺满]")
    tree_width = panel.word_tree.winfo_width()
    check("列宽填满表格", abs(sum(widths(panel)) - tree_width) <= 2, f"{widths(panel)} vs {tree_width}")

    mins = [panel._COL_MINS[c] for c in panel._COLS]
    start = [100, 100, 100, 100, 100, 100]
    total = sum(start)

    print("\n[只动一条交界线]")
    result = panel._drag_widths(start, 3, 30)
    check("左列加宽、右列变窄", result[2] == 130 and result[3] == 70, str(result))
    check("总宽不变", sum(result) == total, str(sum(result)))
    check("其他列不动", result[:2] == start[:2] and result[4:] == start[4:], str(result))

    print("\n[右列到最小宽度后传给下一条]")
    room = start[3] - panel._COL_MINS[panel._COLS[3]]
    result = panel._drag_widths(start, 3, room + 20)
    check("第三条列到最小", result[3] == panel._COL_MINS[panel._COLS[3]], str(result))
    check("下一条列接着让位", result[4] == 100 - 20, str(result))
    check("总宽还是不变", sum(result) == total, str(sum(result)))

    print("\n[拖到边界就停]")
    result = panel._drag_widths(start, 3, 9999)
    check("右侧列全部到最小", result[3:] == mins[3:], str(result))
    check("总量守恒", sum(result) == total, str(sum(result)))
    check("没有小于最小宽度", all(w >= m for w, m in zip(result, mins, strict=False)), str(result))

    print("\n[向左拖是对称的]")
    result = panel._drag_widths(start, 3, -30)
    check("右列加宽、左列变窄", result[3] == 130 and result[2] == 70, str(result))
    result = panel._drag_widths(start, 3, -9999)
    check("左侧列全部到最小", result[:3] == mins[:3], str(result))
    check("左侧拖动的总量守恒", sum(result) == total, str(sum(result)))

    print("\n[拖动保存比例]")
    panel._dragging = True
    panel._drag_right = 3
    panel._drag_start_x = 500
    panel._drag_start = widths(panel)

    class Event:
        x_root = 0

    event = Event()
    event.x_root = 540
    panel._on_tree_drag(event)
    panel._on_tree_release(event)
    root.update()
    saved = cfg.get("vocab_col_ratios")
    check("写入 vocab_col_ratios", isinstance(saved, list) and len(saved) == 6, str(saved))
    check("比例和为 1", bool(saved) and abs(sum(saved) - 1) < 0.01, str(saved))
    total_now = sum(widths(panel))
    expected = [round(w / total_now, 4) for w in widths(panel)]
    check(
        "比例对应当前宽度",
        all(abs(a - b) < 0.002 for a, b in zip(saved, expected, strict=False)),
        f"{saved} vs {expected}",
    )
    check("旧的绝对宽度键已清理", cfg.get("vocab_col_widths") is None)

    print("\n[真实事件绑定]")
    boundary = sum(widths(panel)[:3])
    before = widths(panel)
    panel.word_tree.event_generate("<Button-1>", x=boundary, y=10)
    root.update()
    check("按下分隔线进入拖拽", panel._dragging)
    panel.word_tree.event_generate("<B1-Motion>", x=boundary - 30, y=10)
    root.update()
    check("拖动改变列宽", widths(panel) != before, f"{before} -> {widths(panel)}")
    panel.word_tree.event_generate("<ButtonRelease-1>", x=boundary - 30, y=10)
    root.update()
    check("松手结束拖拽", not panel._dragging)
    check("松手后总宽仍铺满", abs(sum(widths(panel)) - panel.word_tree.winfo_width()) <= 2, str(widths(panel)))

    print("\n[窗口缩放保持比例]")
    before_widths = widths(panel)
    before_ratios = [w / sum(before_widths) for w in before_widths]
    root.geometry("980x620")
    root.update()
    after = widths(panel)
    after_ratios = [w / sum(after) for w in after]
    check("变宽后仍铺满", abs(sum(after) - panel.word_tree.winfo_width()) <= 2, str(after))
    check(
        "比例基本保持",
        all(abs(a - b) < 0.03 for a, b in zip(after_ratios, before_ratios, strict=False)),
        f"{before_ratios} -> {after_ratios}",
    )
    check("列确实变宽", after[0] > before_widths[0], f"{before_widths} -> {after}")
    root.geometry("740x620")
    root.update()
    check("变窄后仍铺满", abs(sum(widths(panel)) - panel.word_tree.winfo_width()) <= 2, str(widths(panel)))

    print("\n[重启恢复比例]")
    saved = list(cfg.get("vocab_col_ratios") or [])
    panel2 = VocabPanel(frame, svc, cfg)
    root.update()
    check(
        "新面板沿用保存的比例",
        all(abs(a - b) < 0.01 for a, b in zip(panel2._col_ratios, saved, strict=False)),
        f"{panel2._col_ratios} vs {saved}",
    )
    check(
        "按当前窗口宽度铺满",
        abs(sum(panel2._col_widths) - panel2.word_tree.winfo_width()) <= 2,
        f"{panel2._col_widths} vs {panel2.word_tree.winfo_width()}",
    )

    root.destroy()
    svc.store.close()
    shutil.rmtree(data, ignore_errors=True)
    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
