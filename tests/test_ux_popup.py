"""体验体检 2：弹窗/面板的交互路径和提示语。"""

from __future__ import annotations

import shutil
import sys
import tkinter as tk
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from rc.config import Config  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


def main() -> int:
    from rc.service import Service

    tmp = HERE / "uxtmp2"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)
    cfg = Config(tmp)
    cfg.data["dictionaries"] = {}
    cfg.data["api"].update({"base_url": "http://127.0.0.1:18778/v1", "api_key": "k", "model": "mock"})
    cfg.save()
    svc = Service(cfg)

    print("\n[没有词典时的提示]")
    check("has_dictionaries 为 False", svc.has_dictionaries() is False)

    root = tk.Tk()
    root.withdraw()

    from app import Application

    app = Application(cfg, enable_hotkeys=False)
    app.root.update()

    def missing_card():
        app.popup.show_dict_missing("hello", (300, 200), app.service.has_dictionaries())
        app.popup.win.update()
        return app.popup.title.cget("text")

    try:
        check("弹出未配置词典的卡片", missing_card() == "查词")
    except Exception as exc:  # noqa: BLE001
        check("弹出未配置词典的卡片", False, f"{type(exc).__name__}: {exc}")

    def press_keys():
        for seq in ("<Return>", "<space>", "<Escape>"):
            app.popup.win.event_generate(seq)
            app.popup.win.update()
        return "ok"

    try:
        check("卡片上按 Enter/空格/Esc 不报错", press_keys() == "ok")
    except Exception as exc:  # noqa: BLE001
        check("卡片上按 Enter/空格/Esc 不报错", False, f"{type(exc).__name__}: {exc}")

    print("\n[编辑查询词]")
    def edit_word():
        from rc.config import Config as _C

        fake = {"word": "seek", "senses": [], "lang": "en", "source": "测试"}
        hits = [{"lang": "en", "source": "测试", "entry": fake}]
        app.popup.show_dictionary(fake, (300, 200), "seek", hits)
        app.popup.win.update()
        widgets = []

        def walk(w):
            for c in w.winfo_children():
                widgets.append(c)
                walk(c)

        walk(app.popup.body)
        labels = [w for w in widgets if w.winfo_class() == "Label" and str(w.cget("text")) == "seek"]
        if not labels:
            return "no-label"
        labels[0].event_generate("<Button-1>")
        app.popup.win.update()
        widgets = []
        walk(app.popup.body)
        entries = [w for w in widgets if w.winfo_class() == "Entry"]
        if not entries:
            return "no-entry"
        entries[0].event_generate("<Escape>")
        app.popup.win.update()
        widgets = []
        walk(app.popup.body)
        back = [w for w in widgets if w.winfo_class() == "Label" and str(w.cget("text")) == "seek"]
        return "ok" if back else "no-restore"

    try:
        check("点词头出现输入框、Esc 恢复", edit_word() == "ok", str(edit_word()))
    except Exception as exc:  # noqa: BLE001
        check("点词头出现输入框、Esc 恢复", False, f"{type(exc).__name__}: {exc}")

    print("\n[面板查词提示]")
    def panel_lookup():
        app.open_panel()
        app.panel._show_tab("dict")
        app.panel.dict_input.delete(0, "end")
        app.panel.dict_input.insert(0, "hello")
        app.panel._lookup_dict()
        app.panel.win.update()
        texts = []

        def walk(w):
            for c in w.winfo_children():
                try:
                    t = c.cget("text")
                except Exception:
                    t = ""
                if t:
                    texts.append(str(t))
                walk(c)

        walk(app.panel.dict_result)
        return " | ".join(texts[:4])

    try:
        text = panel_lookup()
        check("面板提示未配置词典", "还没配置本地词典" in text, text[:80])
        check("面板给了 AI 兜底按钮", "用 AI 译" in text, text[:80])
    except Exception as exc:  # noqa: BLE001
        check("面板查词流程", False, f"{type(exc).__name__}: {exc}")

    app.shutdown()
    root.destroy()
    shutil.rmtree(tmp, ignore_errors=True)
    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
