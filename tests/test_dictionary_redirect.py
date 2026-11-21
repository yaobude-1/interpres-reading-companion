"""MDX redirects: inflections are labelled, lexical redirects are disclosed."""

from __future__ import annotations

import shutil
import sys
import tkinter as tk
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from rc.config import Config  # noqa: E402
from rc.popup import PopupWindow  # noqa: E402
from rc.service import Service  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


def find_text(widget, wanted: str) -> bool:
    for child in widget.winfo_children():
        try:
            if isinstance(child, tk.Label) and wanted in child.cget("text"):
                return True
        except tk.TclError:
            pass
        if find_text(child, wanted):
            return True
    return False


def main() -> int:
    data = HERE / ".redirect"
    shutil.rmtree(data, ignore_errors=True)
    data.mkdir(parents=True)
    cfg = Config(data)
    svc = Service(cfg)

    print("\n[分类]")
    lexical = {"word": "composition"}
    kind = svc._annotate_redirect(lexical, "decomposition", "en")
    check("词义重定向", kind == "lexical", kind)
    check("记录目标", lexical.get("redirect") == "composition", str(lexical))
    inflection = {"word": "decompose"}
    kind = svc._annotate_redirect(inflection, "decomposed", "en")
    check("屈折重定向", kind == "inflection", kind)
    check("按原形标注", inflection.get("matched") == "decompose", str(inflection))
    check("不标 redirect", "redirect" not in inflection, str(inflection))
    same = {"word": "Composition"}
    check("同词不是重定向", svc._annotate_redirect(same, "composition", "en") == "")
    svc.store.close()

    print("\n[弹窗提示]")
    root = tk.Tk()
    root.withdraw()
    try:
        popup = PopupWindow(root, cfg, {})
        popup.show_dictionary(
            {
                "word": "composition",
                "lang": "en",
                "source": "Test Dictionary",
                "phonetic": "ˌkɒmpəˈzɪʃən",
                "senses": [{"pos": "noun", "definition": "the parts something is made of"}],
                "matched": "decomposition",
                "query": "decomposition",
                "redirect": "composition",
            },
            (300, 300),
            "decomposition",
        )
        root.update()
        check("显示重定向提示", find_text(popup.win, "重定向到"))
        check("显示目标词条入口", find_text(popup.win, "查看 composition"))
        check("保留 AI 入口", find_text(popup.win, "用 AI 译"))
        check("显示目标词条释义", find_text(popup.win, "the parts something is made of"))
    finally:
        root.destroy()

    shutil.rmtree(data, ignore_errors=True)
    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
