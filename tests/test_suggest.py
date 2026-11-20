"""查词建议浮层（半透明下拉）+ 滚轮路由 + 内容滚动条。"""

from __future__ import annotations

import json
import shutil
import sys
import time
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


class Key:
    def __init__(self, sym: str) -> None:
        self.keysym = sym


class Wheel:
    def __init__(self, delta: int) -> None:
        self.delta = delta


def main() -> int:
    data = HERE / "suggesttmp"
    shutil.rmtree(data, ignore_errors=True)
    data.mkdir(parents=True)
    real = Path.home() / ".reading-companion" / "config.json"
    dicts = {}
    if real.exists():
        dicts = json.loads(real.read_text(encoding="utf-8")).get("dictionaries") or {}
    cfg = Config(data)
    cfg.data["dictionaries"] = dicts
    cfg.data["server_port"] = 18930
    cfg.save()

    from app import Application

    app = Application(cfg, enable_hotkeys=False)
    app.root.update()
    app.open_panel()
    app.panel.win.geometry("620x760+80+30")
    app.root.update()
    app.panel._show_tab("dict")

    if not dicts.get("en"):
        print("没配英语词典，跳过")
        app.shutdown()
        try:
            app.root.destroy()
        except Exception:
            pass
        shutil.rmtree(data, ignore_errors=True)
        return 0

    print("\n[输入建议]")
    app.panel.dict_input.delete(0, "end")
    app.panel.dict_input.insert(0, "tset")
    app.panel._lookup_dict(_keep_suggestions=True)
    app.panel._update_suggestions()
    app.root.update()
    items = [it["word"] for it in app.panel._suggest_items]
    check("建议里有 test", "test" in items, str(items[:6]))
    check("建议浮层已显示", app.panel.suggest_win.winfo_viewable() == 1)
    check(
        "建议在输入框下方",
        app.panel.suggest_win.winfo_rooty()
        >= app.panel.dict_input.winfo_rooty() + app.panel.dict_input.winfo_height(),
    )
    check("浮层半透明", float(app.panel.suggest_win.attributes("-alpha")) < 1.0)

    print("\n[键盘选择]")
    app.panel._on_suggest_key(Key("Down"))
    app.root.update()
    check("下键有选中项", app.panel._suggest_index >= 0, str(app.panel._suggest_index))
    chosen = app.panel._suggest_items[app.panel._suggest_index]["word"]
    app.panel._on_suggest_key(Key("Return"))
    app.root.update()
    time.sleep(0.2)
    check("回车采纳建议", app.panel.dict_input.get() == chosen, app.panel.dict_input.get())
    check("采纳后收起", app.panel.suggest_win.winfo_viewable() == 0)

    print("\n[Esc 收起]")
    app.panel.dict_input.delete(0, "end")
    app.panel.dict_input.insert(0, "tset")
    app.panel._update_suggestions()
    app.root.update()
    app.panel._on_suggest_key(Key("Escape"))
    app.root.update()
    check("Esc 后收起", app.panel.suggest_win.winfo_viewable() == 0)

    print("\n[滚动条]")
    app.panel.dict_input.delete(0, "end")
    app.panel.dict_input.insert(0, "contents")
    app.panel._lookup_dict()
    app.root.update()
    time.sleep(0.3)
    app.root.update()
    bar = app.panel.content_scroll
    check("长词条显示滚动条", bar.winfo_ismapped() == 1)
    check("滚动条够宽", int(bar.cget("width")) >= 14, str(bar.cget("width")))

    print("\n[空内容不滚]")
    app.panel.dict_input.delete(0, "end")
    app.panel._lookup_dict()
    app.root.update()
    c = app.panel.content_canvas
    base_y = app.panel.dict_input.winfo_rooty() - c.winfo_rooty()
    app.panel.win.winfo_pointerxy = lambda: (
        c.winfo_rootx() + 10,
        c.winfo_rooty() + 10,
    )

    class Up:
        delta = 120

    for _ in range(4):
        app.panel._route_wheel(Up())
        app.root.update()
    moved_y = app.panel.dict_input.winfo_rooty() - c.winfo_rooty()
    check("空内容滚不动", moved_y == base_y, f"{base_y} -> {moved_y}")

    print("\n[滚轮路由]")
    app.panel.dict_input.delete(0, "end")
    app.panel.dict_input.insert(0, "go")
    app.panel._lookup_dict()
    app.panel.win.minsize(320, 360)
    app.panel.win.geometry("620x420")
    app.root.update()
    time.sleep(0.4)
    app.panel.content_canvas.yview_moveto(1.0)
    app.root.update()
    before = app.panel.content_canvas.yview()[0]
    inp = app.panel.dict_input
    app.panel.win.winfo_pointerxy = lambda: (
        inp.winfo_rootx() + 5,
        inp.winfo_rooty() + 5,
    )
    app.panel._route_wheel(Wheel(120))
    app.root.update()
    after = app.panel.content_canvas.yview()[0]
    check("指针在输入框上也能向上滚", after < before, f"{before} -> {after}")

    app.shutdown()
    try:
        app.root.destroy()
    except Exception:
        pass
    shutil.rmtree(data, ignore_errors=True)
    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
