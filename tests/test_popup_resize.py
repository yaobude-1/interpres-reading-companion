"""浮窗手动缩放：四边/四角、移动后不跳回、手动高度、配置写回、DPI。"""

from __future__ import annotations

import shutil
import sys
import tkinter as tk
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from rc import anim  # noqa: E402
from rc.config import Config  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


def ev(x: int, y: int) -> SimpleNamespace:
    return SimpleNamespace(x_root=x, y_root=y)


def main() -> int:
    data = HERE / ".resize"
    shutil.rmtree(data, ignore_errors=True)
    data.mkdir(parents=True)
    cfg = Config(data)
    cfg.data["popup_width"] = 480
    cfg.data["popup_max_height_ratio"] = 0.72
    cfg.data["popup_height"] = 0
    cfg.save()

    root = tk.Tk()
    root.withdraw()
    old = anim.enabled
    anim.enabled = False
    try:
        from rc.popup import PopupWindow

        popup = PopupWindow(root, cfg, {})
        scale = popup.scale
        check("100% 不透明度不启用 layered", popup._layered is False)
        filler = tk.Frame(popup.body, bg="#000000", width=100, height=2000)
        filler.pack(fill="x")
        wrap_label = tk.Label(popup.body, text="wrapped", wraplength=400)
        wrap_label.pack(fill="x")

        def reset() -> None:
            popup.width = int(480 * scale)
            popup.max_ratio = 0.5
            popup._fixed_canvas_h = None
            popup._user_moved = False
            popup._pos = None
            popup._anchor = (400, 100)
            popup.win.deiconify()
            popup.win.update_idletasks()
            popup._fit_height()
            popup._place()
            root.update()

        def end(x: int, y: int) -> None:
            popup._resize_end(ev(x, y))
            root.update()

        reset()

        print("\n[手柄与边缘]")
        for name, widget in (
            ("左边", popup._edge_left),
            ("右边", popup._edge_right),
            ("上边", popup._edge_top),
            ("下边", popup._edge_bottom),
            ("左上角", popup._corner_tl),
            ("右上角", popup._corner_tr),
            ("左下角", popup._corner_bl),
            ("右下角", popup.grip),
        ):
            check(f"{name}热区存在", widget.winfo_exists() == 1)

        print("\n[移动后再缩放不跳回]")
        ix, iy = popup.win.winfo_x(), popup.win.winfo_y()
        popup._start_drag(ev(500, 500))
        popup._do_drag(ev(540, 520))
        root.update()
        mx, my = popup.win.winfo_x(), popup.win.winfo_y()
        check("拖动改变了位置", (mx, my) != (ix, iy), f"{(mx, my)} vs {(ix, iy)}")
        popup._resize_start(ev(500, 500), "right")
        popup._resize_drag(ev(540, 500), "right")
        end(540, 500)
        check("缩放后 x 不变", popup.win.winfo_x() == mx, f"{popup.win.winfo_x()} vs {mx}")
        check("缩放后 y 不变", popup.win.winfo_y() == my, f"{popup.win.winfo_y()} vs {my}")

        print("\n[右边缘：只改宽度，左边不动]")
        reset()
        x0 = popup.win.winfo_x()
        w0 = popup.width
        wrap0 = int(str(wrap_label.cget("wraplength")))
        popup._resize_start(ev(500, 500), "right")
        popup._resize_drag(ev(540, 560), "right")
        end(540, 560)
        check("宽度变大", popup.width > w0, f"{w0} -> {popup.width}")
        check("左边不动", popup.win.winfo_x() == x0, f"{popup.win.winfo_x()} vs {x0}")
        check(
            "带 wraplength 的 Label 能重排",
            int(str(wrap_label.cget("wraplength"))) > wrap0,
            f"{wrap0} -> {wrap_label.cget('wraplength')}",
        )

        print("\n[左边缘：宽度变大，右边固定]")
        reset()
        x0 = popup.win.winfo_x()
        w0 = popup.width
        right0 = x0 + w0
        popup._resize_start(ev(500, 500), "left")
        popup._resize_drag(ev(440, 500), "left")
        end(440, 500)
        check("宽度变大", popup.width > w0, f"{w0} -> {popup.width}")
        check(
            "右边固定",
            abs((popup.win.winfo_x() + popup.width) - right0) <= 1,
            f"{popup.win.winfo_x() + popup.width} vs {right0}",
        )

        print("\n[下边缘：变高，顶边固定]")
        reset()
        y0 = popup.win.winfo_y()
        h0 = popup.win.winfo_height()
        popup._resize_start(ev(500, 500), "bottom")
        popup._resize_drag(ev(500, 540), "bottom")
        end(500, 540)
        check("高度变大", popup.win.winfo_height() >= h0 + 30, f"{h0} -> {popup.win.winfo_height()}")
        check("顶边不动", popup.win.winfo_y() == y0, f"{popup.win.winfo_y()} vs {y0}")

        print("\n[上边缘：变高，底边固定]")
        reset()
        bottom0 = popup.win.winfo_y() + popup.win.winfo_height()
        popup._resize_start(ev(500, 500), "top")
        popup._resize_drag(ev(500, 460), "top")
        end(500, 460)
        check(
            "底边固定",
            abs((popup.win.winfo_y() + popup.win.winfo_height()) - bottom0) <= 2,
            f"{popup.win.winfo_y() + popup.win.winfo_height()} vs {bottom0}",
        )

        print("\n[短内容也能手动拉高]")
        reset()
        filler.pack_forget()
        popup._fit_height()
        popup._place()
        root.update()
        h0 = popup.win.winfo_height()
        popup._resize_start(ev(500, 500), "bottom")
        popup._resize_drag(ev(500, 560), "bottom")
        end(500, 560)
        check(
            "高度按拖动增长（不受内容限制）",
            popup.win.winfo_height() >= h0 + 50,
            f"{h0} -> {popup.win.winfo_height()}",
        )

        print("\n[右下角：宽高都变]")
        reset()
        w0 = popup.width
        h0 = popup.win.winfo_height()
        popup._resize_start(ev(500, 500), "bottom-right")
        popup._resize_drag(ev(540, 540), "bottom-right")
        end(540, 540)
        check("宽度变大", popup.width > w0, f"{w0} -> {popup.width}")
        check("高度变大", popup.win.winfo_height() > h0, f"{h0} -> {popup.win.winfo_height()}")

        print("\n[上下限]")
        reset()
        popup._resize_start(ev(500, 500), "bottom-right")
        popup._resize_drag(ev(5000, 5000), "bottom-right")
        end(5000, 5000)
        check("宽度封顶 900px", abs(popup.width - int(900 * scale)) <= 1, str(popup.width))

        reset()
        popup._resize_start(ev(500, 500), "bottom-right")
        popup._resize_drag(ev(-5000, -5000), "bottom-right")
        end(-5000, -5000)
        check("宽度下限 420px", abs(popup.width - int(420 * scale)) <= 1, str(popup.width))
        check("高度下限 120px", popup._fixed_canvas_h == 120, str(popup._fixed_canvas_h))

        print("\n[配置写回]")
        saved = Config(data)
        check(
            "宽度写回配置（按 DPI 换算）",
            abs(int(saved.get("popup_width")) - int(round(popup.width / scale))) <= 1,
            f"{saved.get('popup_width')} vs {int(round(popup.width / scale))}",
        )
        check(
            "手动高度写回配置",
            int(saved.get("popup_height", 0)) > 0,
            str(saved.get("popup_height")),
        )

        print("\n[双击恢复自动高度]")
        popup._reset_height()
        root.update()
        check("清掉手动高度", popup._fixed_canvas_h is None)
        saved = Config(data)
        check("配置里高度归零", int(saved.get("popup_height", -1)) == 0, str(saved.get("popup_height")))

        print("\n[设置保存后重新套用]")
        cfg.data["popup_width"] = 600
        popup.apply_config()
        check(
            "apply_config 乘 DPI 缩放",
            popup.width == int(600 * scale),
            f"{popup.width} vs {int(600 * scale)}",
        )
    finally:
        anim.enabled = old
        try:
            root.destroy()
        except tk.TclError:
            pass
        shutil.rmtree(data, ignore_errors=True)

    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
