"""验证翻译记录的界面与导出。"""

from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from rc.config import Config  # noqa: E402
from tests import mock_openai  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


def pump(root, predicate, timeout: float = 3.0) -> bool:
    """跑 Tk 事件循环直到条件成立：面板译文是定时器分段刷的，只 update 一次不够。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        root.update()
        if predicate():
            return True
        time.sleep(0.02)
    root.update()
    return predicate()


def main() -> int:
    data = HERE / ".transui"
    shutil.rmtree(data, ignore_errors=True)
    data.mkdir(parents=True)
    mock_openai.start(18778)

    cfg = Config(data)
    cfg.data["api"].update(
        {"base_url": "http://127.0.0.1:18778/v1", "api_key": "k", "model": "mock"}
    )
    cfg.data["server_port"] = 18805
    cfg.save()

    from app import Application

    app = Application(cfg, enable_hotkeys=False)
    service = app.service
    service.translate("The quick brown fox jumps over the lazy dog.", book="Book A")
    service.translate("Philosophy begins in wonder and ends in questions.", book="Book B")

    print("\n[记录窗口]")
    app.open_translation_history()
    app.root.update()
    win = app._trans_win
    check("窗口打开", win.win.winfo_ismapped() == 1)
    check("列出两条", len(win.tree.get_children()) == 2, str(len(win.tree.get_children())))
    check("统计文字", "2" in win.count.cget("text"), win.count.cget("text"))

    print("\n[按书筛选]")
    win.var_book.set("Book A")
    win.refresh()
    app.root.update()
    check("只剩一条", len(win.tree.get_children()) == 1, str(len(win.tree.get_children())))
    win.var_book.set("全部")
    win.refresh()

    print("\n[搜索]")
    win.var_query.set("philosophy")
    win.refresh()
    check("搜索命中", len(win.tree.get_children()) == 1, str(len(win.tree.get_children())))
    win.var_query.set("")
    win.refresh()

    print("\n[导出]")
    result = service.export_translations(fmt="md")
    path = Path(result["path"])
    check("文件已生成", path.exists(), str(path))
    body = path.read_text(encoding="utf-8")
    check("含原文", "quick brown fox" in body, body[:80])
    check("含译文", mock_openai.CANNED["translation"] in body, body[:80])
    check("按书分节", "## Book A" in body and "## Book B" in body, body[:200])

    tsv = service.export_translations(fmt="tsv")
    tsv_path = Path(tsv["path"])
    check("TSV 已生成", tsv_path.exists())
    check("TSV 有表头", "原文\t译文" in tsv_path.read_text(encoding="utf-8-sig")[:40])

    print("\n[面板快速回看]")
    app.open_panel()
    app.root.update()
    rows = service.translations(book="Book A", limit=8)
    app.panel._load_record(rows[0])
    app.root.update()
    check("原文填进面板", "quick brown" in app.panel.input.get("1.0", "end"))
    check(
        "译文显示出来",
        pump(
            app.root,
            lambda: mock_openai.CANNED["translation"] in app.panel.output.get("1.0", "end"),
        ),
    )

    app.shutdown()
    shutil.rmtree(data, ignore_errors=True)
    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
