"""划词浮窗。

一个无边框、置顶的小窗口，跟随鼠标出现，内容分四块：
原文 / 译文 / 生词 / 语法，底部是操作提示。
"""

from __future__ import annotations

import logging
import time
import tkinter as tk

from . import anim, screens, textutil
from .popup_chat import ChatViewMixin
from .popup_dict import DictViewMixin
from .popup_result import ResultViewMixin
from .theme import (
    ACCENT as ACCENT,
    BG as BG,
    BORDER as BORDER,
    DIM as DIM,
    FONT_FAMILY as FONT_FAMILY,
    GREEN as GREEN,
    MUTED as MUTED,
    PANEL as PANEL,
    PANEL_ALT as PANEL_ALT,
    RED as RED,
    TEXT as TEXT,
)
from .theme import BORDER_SOFT, ON_ACCENT, SCROLL_THUMB, SCROLL_TRACK

log = logging.getLogger("rc")


class PopupWindow(DictViewMixin, ChatViewMixin, ResultViewMixin):
    def __init__(self, root: tk.Tk, config, callbacks: dict) -> None:
        self.root = root
        self.config = config
        self.cb = callbacks
        self.current: dict | None = None
        self.saved: set = set()
        self._visible = False
        self._user_moved = False
        self._drag = None
        self._expanded = False
        self._lang = "en"
        self._anchor = (200, 200)
        self._pending_text: str | None = None
        self._pending_payload: dict | None = None
        self._input_mode = False
        self._mode = "translate"
        self._conv_id: int | None = None
        self._dict: dict | None = None
        self._dict_word = ""
        self._typing: tk.Frame | None = None
        self._chat_job = None
        self._chat_target = ""
        self._chat_shown = ""
        self._chat_reply = ""
        self._chat_final = False
        self.chat_input: tk.Text | None = None

        try:
            self.scale = max(1.0, float(root.winfo_fpixels("1i")) / 96.0)
        except Exception:
            self.scale = 1.0
        self.width = int(int(config.get("popup_width", 560)) * self.scale)
        self.max_ratio = float(config.get("popup_max_height_ratio", 0.72))
        fixed_h = int(config.get("popup_height", 0) or 0)
        self._fixed_canvas_h: int | None = int(fixed_h * self.scale) if fixed_h > 0 else None
        self._resize_from: dict | None = None
        self._resize_available = 0
        self._pos: tuple[int, int] | None = None

        self.win = tk.Toplevel(root)
        self.win.withdraw()
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg=BORDER)
        appearance = config.get("appearance") or {}
        try:
            opacity = float(appearance.get("popup_opacity", 1.0))
        except (TypeError, ValueError):
            opacity = 1.0
        self._target_alpha = max(0.3, min(1.0, opacity))
        # alpha < 1 才会让 Windows 把窗口标成 layered window；layered 窗口
        # 在“移动 + 改尺寸”时容易留下半透明/空白表面，所以 100% 时不启用。
        self._layered = self._target_alpha < 0.999
        self._fader = anim.Fader(self.win, self._target_alpha)
        log.debug(
            "浮窗初始化：alpha=%.2f layered=%s scale=%.2f",
            self._target_alpha,
            self._layered,
            self.scale,
        )
        try:
            self.win.attributes("-alpha", self._target_alpha)
        except tk.TclError:  # 控件可能已销毁，刻意忽略
            pass

        self.shell = tk.Frame(self.win, bg=BG)
        self.shell.pack(fill="both", expand=True, padx=1, pady=1)

        self.header = tk.Frame(self.shell, bg=BG, height=34)
        self.header.pack(fill="x", padx=14, pady=(10, 0))
        self.header.pack_propagate(False)

        self.title = tk.Label(
            self.header, text="", bg=BG, fg=MUTED, font=(FONT_FAMILY, 9), anchor="w"
        )
        self.title.pack(side="left", fill="y")

        self.btn_close = tk.Label(
            self.header,
            text="✕",
            bg=BG,
            fg=DIM,
            font=(FONT_FAMILY, 11),
            cursor="hand2",
            padx=6,
        )
        self.btn_close.pack(side="right")
        self.btn_close.bind("<Button-1>", lambda _e: self.hide())
        self.btn_close.bind("<Enter>", lambda _e: self.btn_close.configure(fg=TEXT))
        self.btn_close.bind("<Leave>", lambda _e: self.btn_close.configure(fg=DIM))

        self.btn_settings = tk.Label(
            self.header,
            text="⚙",
            bg=BG,
            fg=DIM,
            font=(FONT_FAMILY, 11),
            cursor="hand2",
            padx=6,
        )
        self.btn_settings.pack(side="right")
        self.btn_settings.bind("<Button-1>", lambda _e: self.cb.get("settings", lambda: None)())
        self.btn_settings.bind("<Enter>", lambda _e: self.btn_settings.configure(fg=TEXT))
        self.btn_settings.bind("<Leave>", lambda _e: self.btn_settings.configure(fg=DIM))

        # 底部操作条（先占住底部，避免被 canvas 挤掉）
        self.footer_bar = tk.Frame(self.shell, bg=BG)
        self.footer_bar.pack(fill="x", padx=(14, 20), pady=(2, 9), side="bottom")
        self.footer = tk.Label(
            self.footer_bar, text="", bg=BG, fg=DIM, font=(FONT_FAMILY, 8), anchor="w"
        )
        self.footer.pack(side="left")
        self.btn_chat = tk.Label(
            self.footer_bar,
            text="和它聊聊",
            bg=BG,
            fg=ACCENT,
            font=(FONT_FAMILY, 8),
            cursor="hand2",
            padx=6,
        )
        self.btn_chat.pack(side="right")
        self.btn_chat.bind("<Button-1>", lambda _e: self._chat_button())
        self.btn_chat.bind("<Enter>", lambda _e: self.btn_chat.configure(fg=TEXT))
        self.btn_chat.bind("<Leave>", lambda _e: self.btn_chat.configure(fg=ACCENT))

        # 对话输入条（聊天模式才显示）
        self.input_bar = tk.Frame(self.shell, bg=BG)

        self.canvas = tk.Canvas(self.shell, bg=BG, highlightthickness=0, bd=0)
        self.scrollbar = tk.Scrollbar(
            self.shell,
            orient="vertical",
            command=self.canvas.yview,
            bg=SCROLL_THUMB,
            troughcolor=SCROLL_TRACK,
            activebackground=ACCENT,
            width=9,
            relief="flat",
            bd=0,
        )
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.scrollbar.pack(side="right", fill="y", padx=(0, 4), pady=(2, 4))
        self.canvas.pack(fill="both", expand=True, padx=(14, 4), pady=(2, 4))
        self.body = tk.Frame(self.canvas, bg=BG)
        self._canvas_item = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.body.bind(
            "<Configure>",
            lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.canvas.bind("<Configure>", self._on_canvas_resize)

        # 四边 + 四角缩放热区：悬停变光标，拖动像普通窗口一样改尺寸
        self._edge_left = tk.Frame(self.shell, bg=BG)
        self._edge_left.place(relx=0.0, rely=0.0, anchor="nw", width=5, relheight=1.0)
        self._edge_top = tk.Frame(self.shell, bg=BG)
        self._edge_top.place(relx=0.0, rely=0.0, anchor="nw", relwidth=1.0, height=5)
        self._edge_right = tk.Frame(self.shell, bg=BG)
        self._edge_right.place(relx=1.0, rely=0.0, anchor="ne", width=4, relheight=1.0)
        self._edge_bottom = tk.Frame(self.shell, bg=BG)
        self._edge_bottom.place(relx=0.0, rely=1.0, anchor="sw", relwidth=1.0, height=5)
        self._corner_tl = tk.Frame(self.shell, bg=BG)
        self._corner_tl.place(relx=0.0, rely=0.0, anchor="nw", width=9, height=9)
        self._corner_tr = tk.Frame(self.shell, bg=BG)
        self._corner_tr.place(relx=1.0, rely=0.0, anchor="ne", width=9, height=9)
        self._corner_bl = tk.Frame(self.shell, bg=BG)
        self._corner_bl.place(relx=0.0, rely=1.0, anchor="sw", width=9, height=9)

        # 右下角手柄：既能拖宽也能拖高
        self.grip = tk.Label(
            self.shell,
            text="◢",
            bg=BG,
            fg=DIM,
            font=(FONT_FAMILY, 9),
            padx=1,
        )
        self.grip.place(relx=1.0, rely=1.0, anchor="se", x=-4, y=-3)
        self.grip.lift()

        self._bind_resize(self._edge_left, "left", "size_we")
        self._bind_resize(self._edge_right, "right", "size_we")
        self._bind_resize(self._edge_top, "top", "size_ns")
        self._bind_resize(self._edge_bottom, "bottom", "size_ns")
        self._bind_resize(self._corner_tl, "top-left", "size_nw_se")
        self._bind_resize(self._corner_tr, "top-right", "size_ne_sw")
        self._bind_resize(self._corner_bl, "bottom-left", "size_ne_sw")
        self._bind_resize(self.grip, "bottom-right", "size_nw_se")
        self.grip.bind("<Double-Button-1>", self._reset_height)
        self._edge_bottom.bind("<Double-Button-1>", self._reset_height)
        self.grip.bind("<Enter>", lambda _e: self.grip.configure(fg=TEXT))
        self.grip.bind("<Leave>", lambda _e: self.grip.configure(fg=DIM))

        self.win.bind("<Escape>", lambda _e: self._on_escape())
        self.win.bind("<Return>", lambda _e: self._on_enter())
        self.win.bind("<Control-Return>", lambda _e: self._push_anki())
        self.win.bind("<space>", lambda _e: self._speak())
        self.win.bind("<Control-g>", lambda _e: self._lock_term())
        for i in range(1, 10):
            self.win.bind(str(i), self._make_toggle(i - 1))

        for widget in (self.header, self.title):
            widget.bind("<Button-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._do_drag)
            widget.bind("<ButtonRelease-1>", self._end_drag)

    # ------------------------------------------------------------------ 尺寸/位置
    def _on_canvas_resize(self, event) -> None:
        host = getattr(self, "_dict_inline_host", None)
        if host is not None:
            host.pause(0.2)
        self.canvas.itemconfigure(self._canvas_item, width=event.width)
        resize = getattr(self, "_resize_inline_dict", None)
        if resize is not None:
            resize()

    def _screen(self) -> tuple[int, int]:
        return self.win.winfo_screenwidth(), self.win.winfo_screenheight()

    def _place(self) -> None:
        self.win.update_idletasks()
        h = self.win.winfo_reqheight()
        if self._user_moved and self._pos is not None:
            x, y = screens.clamp_point(self._pos, (self.width, h))
            self._pos = (x, y)
        else:
            x, y = screens.clamp(self._anchor, (self.width, h), offset=(16, 18))
        self.win.geometry(f"{self.width}x{h}+{x}+{y}")
        # layered 窗口在移动/改尺寸后需要重新应用 alpha，否则表面可能不刷新
        if self._layered:
            try:
                self.win.attributes("-alpha", self._target_alpha)
            except tk.TclError:  # 控件可能已销毁，刻意忽略
                pass
        # 让 <Configure> 立刻处理：否则刚变宽/变高时内层 body 还没跟上，
        # 会短暂露出窗口底色。
        self.win.update_idletasks()
        # 快速拖动时 Tk 会先处理大量 motion 事件，重绘可能被饿死，
        # 导致拖动过程中窗口一片空白；这里在布局完成后强制立即重画一次。
        if self._resize_from is not None or self._drag is not None:
            self._repaint_self()

    def _log_click(self, event) -> None:
        try:
            import logging

            logging.getLogger("click").info(
                "popup click widget=%s class=%s xy=%s,%s text=%r",
                event.widget, event.widget.winfo_class(), event.x, event.y,
                event.widget.cget("text") if event.widget.winfo_class() == "Label" else "",
            )
        except (tk.TclError, ValueError) as exc:  # noqa: BLE001 - 调试日志失败不处理
            log.debug("记录浮窗点击失败: %s", exc)

    def _start_drag(self, event) -> None:
        self._suspend_layering()
        self._drag = (event.x_root, event.y_root, self.win.winfo_x(), self.win.winfo_y())
        self._drag_rect = (
            self.win.winfo_x(),
            self.win.winfo_y(),
            self.win.winfo_width(),
            self.win.winfo_height(),
        )

    def _do_drag(self, event) -> None:
        if not self._drag:
            return
        x0, y0, wx, wy = self._drag
        x = wx + event.x_root - x0
        y = wy + event.y_root - y0
        before = (
            self.win.winfo_x(),
            self.win.winfo_y(),
            self.win.winfo_width(),
            self.win.winfo_height(),
        )
        self._user_moved = True
        self._pos = (x, y)
        self.win.geometry(f"+{x}+{y}")
        self.win.update_idletasks()
        now = time.monotonic()
        if now - getattr(self, "_last_ghost_ts", 0.0) > 0.02:
            self._last_ghost_ts = now
            self._repaint_with(before)

    def _end_drag(self, _event=None) -> None:
        rect = getattr(self, "_drag_rect", None)
        self._drag = None
        self._drag_rect = None
        self._restore_layering()
        if rect is not None:
            self._repaint_with(rect)
        self._force_recompose()

    # ------------------------------------------------------------------ 重绘兜底
    def _force_recompose(self) -> None:
        """让 DWM 重新合成一次：临时取消/恢复 topmost，清掉 GPU 表面的残影。"""
        try:
            import ctypes

            user32 = ctypes.windll.user32
            hwnd = user32.GetAncestor(self.win.winfo_id(), 2)  # GA_ROOT
            flags = 0x0001 | 0x0002 | 0x0010  # NOSIZE | NOMOVE | NOACTIVATE
            user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, flags)  # HWND_NOTOPMOST
            user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, flags)  # HWND_TOPMOST
        except (OSError, AttributeError):
            pass

    def _repaint_self(self) -> None:
        """强制浮窗自身立即重绘（不等 Tk 的事件队列）。"""
        try:
            import ctypes

            user32 = ctypes.windll.user32
            hwnd = user32.GetAncestor(self.win.winfo_id(), 2)  # GA_ROOT
            flags = 0x0001 | 0x0100 | 0x0080  # INVALIDATE | UPDATENOW | ALLCHILDREN
            user32.RedrawWindow(hwnd, None, None, flags)
        except (OSError, AttributeError):
            pass

    def _repaint_with(self, before: tuple[int, int, int, int]) -> None:
        """窗口移动/缩放后，让下层窗口重画被它盖过的那块区域。

        Windows + Chromium 有时会把被置顶窗口盖过的像素留在屏幕上（浮窗底色），
        这里对“旧位置 ∪ 新位置”调用 RedrawWindow 兜底。
        """
        try:
            import ctypes
            from ctypes import wintypes

            x1, y1 = self.win.winfo_x(), self.win.winfo_y()
            w1, h1 = self.win.winfo_width(), self.win.winfo_height()
            left = min(before[0], x1)
            top = min(before[1], y1)
            right = max(before[0] + before[2], x1 + w1)
            bottom = max(before[1] + before[3], y1 + h1)
            rect = wintypes.RECT(int(left), int(top), int(right), int(bottom))
            ctypes.windll.user32.RedrawWindow(
                None,
                ctypes.byref(rect),
                None,
                0x0001 | 0x0080,  # RDW_INVALIDATE | RDW_ALLCHILDREN
            )
        except (OSError, AttributeError):
            pass

    # ------------------------------------------------------------------ 手动缩放
    def _bind_resize(self, widget, mode: str, cursor: str) -> None:
        widget.configure(cursor=cursor)
        widget.bind("<Button-1>", lambda e, m=mode: self._resize_start(e, m))
        widget.bind("<B1-Motion>", lambda e, m=mode: self._resize_drag(e, m))
        widget.bind("<ButtonRelease-1>", self._resize_end)

    def _suspend_layering(self) -> None:
        """拖动期间临时关掉 layered：否则移动+改尺寸时表面会空白/透明。"""
        self._drag_was_layered = self._layered
        if not self._layered:
            self._clear_layered_style()
            return
        self._fader.cancel()
        try:
            self.win.attributes("-alpha", 1.0)
        except tk.TclError:  # 控件可能已销毁，刻意忽略
            pass
        self._clear_layered_style()

    def _restore_layering(self) -> None:
        if getattr(self, "_drag_was_layered", False):
            self.set_opacity(self._target_alpha)
        self._drag_was_layered = False

    def _resize_start(self, event, edge: str = "bottom-right") -> None:
        self._suspend_layering()
        _, top, _, bottom = screens.work_area(event.x_root, event.y_root)
        self._resize_available = max(240, bottom - top)
        self.win.update_idletasks()
        x, y = self.win.winfo_x(), self.win.winfo_y()
        self._pos = (x, y)
        self._user_moved = True
        self._resize_from = {
            "edge": edge,
            "x": x,
            "y": y,
            "w": self.width,
            "h": max(200, self.win.winfo_height()),
            "canvas": max(120, self.canvas.winfo_height()),
            "max_canvas": max(
                120, int(self._resize_available * 0.95) - self._chrome_height()
            ),
            "mx": event.x_root,
            "my": event.y_root,
        }

    def _resize_drag(self, event, edge: str = "bottom-right") -> None:
        if self._resize_from is None:
            return
        f = self._resize_from
        dx = event.x_root - f["mx"]
        dy = event.y_root - f["my"]
        before = (
            self.win.winfo_x(),
            self.win.winfo_y(),
            self.win.winfo_width(),
            self.win.winfo_height(),
        )
        min_w, max_w = int(420 * self.scale), int(900 * self.scale)
        width = f["w"]
        x = f["x"]
        if "left" in edge:
            new_w = max(min_w, min(max_w, width - dx))
            x = f["x"] + (width - new_w)  # 右边缘固定
            width = new_w
        elif "right" in edge:
            width = max(min_w, min(max_w, width + dx))
        if "top" in edge:
            self._fixed_canvas_h = max(120, min(f["max_canvas"], f["canvas"] - dy))
        elif "bottom" in edge:
            self._fixed_canvas_h = max(120, min(f["max_canvas"], f["canvas"] + dy))
        self.width = width
        self._fit_height()
        if "top" in edge:
            # 底边固定：先算出最终高度，再一次性设置 geometry，避免中间帧跳动
            self.win.update_idletasks()
            new_h = self.win.winfo_reqheight()
            self._pos = (x, f["y"] + (f["h"] - new_h))
        else:
            self._pos = (x, f["y"])
        self._place()
        # 缩小/移动时旧位置会露出下层窗口，及时让它重画，避免重影
        nx, ny = self.win.winfo_x(), self.win.winfo_y()
        nw, nh = self.win.winfo_width(), self.win.winfo_height()
        vacated = not (
            nx <= before[0]
            and ny <= before[1]
            and nx + nw >= before[0] + before[2]
            and ny + nh >= before[1] + before[3]
        )
        now = time.monotonic()
        if vacated and now - getattr(self, "_last_ghost_ts", 0.0) > 0.02:
            self._last_ghost_ts = now
            self._repaint_with(before)

    def _resize_end(self, _event=None) -> None:
        if self._resize_from is None:
            return
        f = self._resize_from
        old_width = f["w"]
        self._resize_from = None
        self._reflow_wraplengths(old_width)
        self._fit_height()
        self._place()
        self._restore_layering()
        # 整窗强制重绘一次，清掉拖动过程中可能残留的半截文字
        self.win.update()
        self._repaint_with((f["x"], f["y"], f["w"], f["h"]))
        self._force_recompose()
        logical = int(round(self.width / self.scale))
        self.config.data["popup_width"] = max(420, min(900, logical))
        if self._fixed_canvas_h is not None:
            self.config.data["popup_height"] = max(
                120, int(round(self._fixed_canvas_h / self.scale))
            )
        try:
            self.config.save()
        except OSError as exc:  # noqa: BLE001 - 保存失败不影响本次调整
            log.warning("保存浮窗尺寸失败: %s", exc)

    def _reset_height(self, _event=None) -> None:
        """双击上/下边缘：恢复“高度随内容自适应”。"""
        self._fixed_canvas_h = None
        self.config.data["popup_height"] = 0
        try:
            self.config.save()
        except OSError as exc:  # noqa: BLE001 - 保存失败不影响本次调整
            log.warning("保存浮窗高度失败: %s", exc)
        self._fit_height()
        self._place()
        self.win.update()

    def _reflow_wraplengths(self, old_width: int) -> None:
        """窗口变宽/变窄后，把已有文本按比例重新换行。"""
        if old_width <= 0 or self.width <= 0 or self.width == old_width:
            return
        ratio = self.width / old_width

        def walk(widget) -> None:
            for child in widget.winfo_children():
                try:
                    wrap = int(str(child.cget("wraplength")))
                except (tk.TclError, TypeError, ValueError):
                    wrap = 0
                if wrap > 0:
                    child.configure(wraplength=max(80, int(wrap * ratio)))
                walk(child)

        walk(self.body)

    def apply_config(self) -> None:
        """设置页保存后重新套用尺寸（必须乘 DPI 缩放）。"""
        self.width = int(int(self.config.get("popup_width", 560)) * self.scale)
        self.max_ratio = float(self.config.get("popup_max_height_ratio", 0.72))
        fixed_h = int(self.config.get("popup_height", 0) or 0)
        self._fixed_canvas_h = int(fixed_h * self.scale) if fixed_h > 0 else None

    def set_opacity(self, opacity: float) -> None:
        """设置页保存后更新浮窗不透明度；100% 时回到非 layered 窗口。"""
        try:
            value = float(opacity)
        except (TypeError, ValueError):
            value = 1.0
        self._target_alpha = max(0.3, min(1.0, value))
        self._layered = self._target_alpha < 0.999
        self._fader.cancel()
        try:
            self.win.attributes("-alpha", self._target_alpha)
        except tk.TclError:  # 控件可能已销毁，刻意忽略
            pass
        if not self._layered:
            self._clear_layered_style()

    def _clear_layered_style(self) -> None:
        """把 WS_EX_LAYERED 去掉：Tk 把 alpha 设回 1.0 时不会自动清掉。"""
        try:
            import ctypes

            user32 = ctypes.windll.user32
            hwnd = user32.GetAncestor(self.win.winfo_id(), 2)  # GA_ROOT
            gwl_exstyle = -20
            ws_ex_layered = 0x00080000
            style = user32.GetWindowLongW(hwnd, gwl_exstyle)
            if style & ws_ex_layered:
                user32.SetWindowLongW(hwnd, gwl_exstyle, style & ~ws_ex_layered)
                flags = 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020
                user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, flags)
        except (OSError, AttributeError):
            pass

    # ------------------------------------------------------------------ 内容构建
    def _clear(self, keep_web: bool = False) -> None:
        if not keep_web:
            dispose = getattr(self, "_dispose_inline_dict", None)
            if dispose is not None:
                dispose()
        else:
            host = getattr(self, "_dict_inline_host", None)
            if host is not None:
                host.hide()
        for child in self.body.winfo_children():
            if keep_web and child is getattr(self, "_dict_inline_frame", None):
                try:
                    child.pack_forget()
                except tk.TclError:
                    pass
                continue
            child.destroy()

    def _label(self, parent, text: str, **kw) -> tk.Label:
        label = tk.Label(
            parent,
            text=text,
            bg=kw.pop("bg", BG),
            fg=kw.pop("fg", TEXT),
            font=kw.pop("font", (FONT_FAMILY, 10)),
            justify=kw.pop("justify", "left"),
            anchor=kw.pop("anchor", "w"),
            wraplength=kw.pop("wraplength", self.width - 32),
            **kw,
        )
        return label

    def _divider(self, pady: int = 8) -> None:
        line = tk.Frame(self.body, bg=BORDER_SOFT, height=1)
        line.pack(fill="x", pady=(pady, pady))

    def _bind_wheel(self, widget) -> None:
        widget.bind("<MouseWheel>", self._on_wheel, add="+")
        for child in widget.winfo_children():
            self._bind_wheel(child)

    def _on_wheel(self, event) -> None:
        self.canvas.yview_scroll(int(-event.delta / 120), "units")

    # ------------------------------------------------------------------ 状态展示
    def _reset_to_translate(self, *, chat_button: bool) -> None:
        self._mode = "translate"
        self._conv_id = None
        self.input_bar.pack_forget()
        self.btn_chat.configure(text="和它聊聊")
        if chat_button:
            self.btn_chat.pack(side="right")
        else:
            self.btn_chat.pack_forget()

    def _chat_button(self) -> None:
        if self._mode == "chat":
            self.back_to_translation()
        else:
            self._open_chat()

    def show_busy(self, anchor, label: str = "正在读取选中文字…") -> None:
        """按下热键的瞬间先给个反馈，抓取文字可能要等一下。"""
        self._anchor = anchor
        self._input_mode = False
        self.current = None
        self._reset_to_translate(chat_button=False)
        self._clear()
        self.title.configure(text="翻译")
        self._label(self.body, label, fg=ACCENT, font=(FONT_FAMILY, 11)).pack(
            fill="x", pady=(6, 8)
        )
        self._label(
            self.body,
            "如果没有反应，说明当前程序没有提供可复制的选中文字。",
            fg=DIM,
            font=(FONT_FAMILY, 8),
        ).pack(fill="x", pady=(0, 6))
        self.footer.configure(text="Esc 关闭")
        self._reveal()

    def show_loading(self, text: str, book: str, src_hint: str, anchor: tuple[int, int]) -> None:
        if anchor != self._anchor:
            self._user_moved = False
        self._anchor = anchor
        self._lang = src_hint or "en"
        self._expanded = False
        self.saved = set()
        self._input_mode = False
        # 翻译还没出来也能直接聊：先拿原文开一段对话
        self._pending_payload = {
            "text": text,
            "translation": "",
            "book": book,
            "source_lang": src_hint or "",
            "terms": [],
            "grammar": None,
            "meta": {},
        }
        self._reset_to_translate(chat_button=True)
        self._clear()
        self.title.configure(text=self._title_text(book, src_hint, None))
        self._pending_text = text

        preview = self._label(
            self.body,
            textutil.display(text, 220),
            fg=MUTED,
            font=(FONT_FAMILY, 9),
            bg=BG,
        )
        preview.pack(fill="x", pady=(2, 10))

        loading = self._label(self.body, "正在翻译…", fg=ACCENT, font=(FONT_FAMILY, 11))
        loading.pack(fill="x", pady=(4, 14))
        self._loading_label = loading
        self.footer.configure(text="Esc 关闭")

        self._reveal()

    def set_progress(self, text: str) -> None:
        """长文本分段翻译时更新进度文字。"""
        label = getattr(self, "_loading_label", None)
        try:
            if label is not None and label.winfo_exists() and self._mode == "translate":
                label.configure(text=text)
        except tk.TclError:  # 控件可能已销毁，刻意忽略
            pass

    def show_input(self, anchor: tuple[int, int], clipboard_text: str = "") -> None:
        """没读到选中文字时，给一个输入框手动翻译。"""
        self._anchor = anchor
        self._input_mode = True
        self.current = None
        self._reset_to_translate(chat_button=False)
        self._clear()
        self.title.configure(text="手动翻译")

        self._label(
            self.body,
            "没有读到选中的文字。可以直接粘贴或输入要翻译的内容：",
            fg=MUTED,
            font=(FONT_FAMILY, 9),
            wraplength=self.width - 40,
        ).pack(fill="x", pady=(2, 8))

        self.input_text = tk.Text(
            self.body,
            height=4,
            bg=PANEL,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            font=(FONT_FAMILY, 10),
            wrap="word",
            padx=10,
            pady=8,
        )
        self.input_text.pack(fill="x")
        if clipboard_text:
            self.input_text.insert("1.0", clipboard_text.strip()[:2000])

        row = tk.Frame(self.body, bg=BG)
        row.pack(fill="x", pady=(8, 4))
        btn = tk.Label(
            row,
            text="翻译（Ctrl+Enter）",
            bg=ACCENT,
            fg=ON_ACCENT,
            font=(FONT_FAMILY, 9),
            padx=12,
            pady=5,
            cursor="hand2",
        )
        btn.pack(side="right")
        btn.bind("<Button-1>", lambda _e: self._manual())

        self.footer.configure(text="Ctrl+Enter 翻译 · Esc 关闭")
        self._reveal()
        self.input_text.focus_set()

    def _manual(self) -> None:
        if not self._input_mode:
            return
        text = self.input_text.get("1.0", "end-1c").strip()
        if text:
            self.cb.get("manual_translate", lambda _t: None)(text)

    # ------------------------------------------------------------------ 对话
    # ------------------------------------------------------------------ 查词
    def _on_escape(self) -> None:
        if self._mode == "chat":
            self.back_to_translation()
        else:
            self.hide()

    def _on_enter(self) -> None:
        if self._mode == "chat":
            self._send_chat()
        elif self._mode == "dict":
            if self._dict:
                self._save_dict_word()
        else:
            self._copy()

    def show_error(self, message: str, retry=None) -> None:
        self._input_mode = False
        self._reset_to_translate(chat_button=False)
        self._clear()
        box = tk.Frame(self.body, bg=PANEL)
        box.pack(fill="x", pady=(4, 8))
        self._label(box, "出了点问题", fg=RED, font=(FONT_FAMILY, 11, "bold"), bg=PANEL).pack(
            fill="x", padx=12, pady=(10, 2)
        )
        self._label(box, message, fg=TEXT, font=(FONT_FAMILY, 9), bg=PANEL,
                    wraplength=self.width - 60).pack(fill="x", padx=12, pady=(0, 10))
        if retry:
            btn = self._label(box, "↻ 重试", fg=ACCENT, font=(FONT_FAMILY, 9), bg=PANEL)
            btn.pack(anchor="w", padx=12, pady=(0, 10))
            btn.configure(cursor="hand2")
            btn.bind("<Button-1>", lambda _e: retry())
        self.footer.configure(text="Ctrl+Alt+S 打开面板 · Esc 关闭")
        self._reveal()

    def _chrome_height(self) -> int:
        header_h = self.header.winfo_reqheight()
        footer_h = self.footer.winfo_reqheight()
        input_h = self.input_bar.winfo_reqheight() if self._mode == "chat" else 0
        return header_h + footer_h + input_h + 30

    def _fit_height(self) -> None:
        sw, sh = self._screen()
        _, top, _, bottom = screens.work_area(self._anchor[0], self._anchor[1])
        available = max(240, bottom - top)
        max_total = int(available * self.max_ratio)
        self.win.update_idletasks()
        content_h = self.body.winfo_reqheight()
        if self._mode == "chat":
            content_h = max(content_h, 240)
        chrome = self._chrome_height()
        if self._fixed_canvas_h is not None:
            # 用户手动拖过高度：按像素精确显示，上限是屏幕 95%，不受自动上限约束
            hard = max(120, int(available * 0.95))
            cap = max(120, hard - chrome)
            self.canvas.configure(height=max(120, min(self._fixed_canvas_h, cap)))
            self.canvas.yview_moveto(0)
            return
        needs = content_h + chrome
        if needs <= max_total:
            self.canvas.configure(height=content_h + 2)
            self.canvas.yview_moveto(0)
            return
        self.canvas.configure(height=max(180, max_total - chrome))
        self.canvas.yview_moveto(0)

    def hide(self) -> None:
        self._visible = False
        host = getattr(self, "_dict_inline_host", None)
        if host is not None:
            host.hide()
        tts = self.cb.get("stop_speak")
        if tts:
            tts()
        self._fader.fade_out(on_done=self._withdraw)

    def _withdraw(self) -> None:
        try:
            self.win.withdraw()
        except tk.TclError:
            pass

    def _fade_to_visible(self, restart: bool) -> None:
        self._fader.target = self._target_alpha
        self._fader.fade_in(restart=restart)

    @property
    def visible(self) -> bool:
        return self._visible

