"""划词后的小按钮与就地气泡。

两样东西都是无边框置顶小窗：
- QuickButton：「译」按钮，鼠标松开后出现在选区旁；
- Bubble：点按钮后就地展开的小气泡，只放译文，需要更多就点「详情」。
"""

from __future__ import annotations

import tkinter as tk

from . import screens
from .popup import ACCENT, BG, BORDER, DIM, FONT_FAMILY, MUTED, TEXT


class QuickButton:
    def __init__(self, root: tk.Tk, config, on_click, on_chat=None) -> None:
        self.root = root
        self.config = config
        self.on_click = on_click
        self.on_chat = on_chat
        self._hover = False
        self._job = None
        self._anchor = (0, 0)
        self._handling = False

        self.win = tk.Toplevel(root)
        self.win.withdraw()
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)

        self.frame = tk.Frame(self.win, bg=BORDER)
        self.frame.pack()
        self.row = tk.Frame(self.frame, bg=ACCENT)
        self.row.pack(padx=1, pady=1)

        self.label = tk.Label(
            self.row,
            text="译",
            font=(FONT_FAMILY, 11, "bold"),
            padx=10,
            pady=6,
            cursor="hand2",
        )
        self.label.pack(side="left")
        self.divider = tk.Frame(self.row, bg="#2a2e39", width=1)
        self.divider.pack(side="left", fill="y")
        self.chat_label = tk.Label(
            self.row,
            text="聊",
            font=(FONT_FAMILY, 11, "bold"),
            padx=10,
            pady=6,
            cursor="hand2",
        )
        self.chat_label.pack(side="left")
        self._apply_style()

        self.label.bind("<Button-1>", self._clicked)
        self.chat_label.bind("<Button-1>", self._chat_clicked)
        for widget in (self.win, self.frame, self.row, self.label, self.chat_label):
            widget.bind("<Enter>", self._enter)
            widget.bind("<Leave>", self._leave)

    # ------------------------------------------------------------------ 样式
    def set_primary(self, text: str) -> None:
        """选到单词时按钮显示「查」，选到句子时显示「译」。"""
        try:
            self.label.configure(text=text)
        except tk.TclError:
            pass

    def _apply_style(self) -> None:
        style = (self.config.get("selection") or {}).get("button") or {}
        bg = style.get("bg", ACCENT)
        fg = style.get("fg", "#10131a")
        alpha = float(style.get("alpha", 0.95))
        self.label.configure(bg=bg, fg=fg)
        self.chat_label.configure(bg=bg, fg=fg)
        self.row.configure(bg=bg)
        self.frame.configure(bg="#ffffff")
        self.win.configure(bg=bg)
        self.win.attributes("-alpha", max(0.25, min(1.0, alpha)))

    # ------------------------------------------------------------------ 显示
    def show(self, anchor: tuple[int, int]) -> None:
        self._apply_style()
        self._anchor = anchor
        self._hover = False
        self.win.deiconify()
        self.win.update_idletasks()
        w = self.win.winfo_reqwidth()
        h = self.win.winfo_reqheight()
        x, y = screens.clamp(anchor, (w, h))
        self.win.geometry(f"+{x}+{y}")

        if self._job:
            self.root.after_cancel(self._job)
            self._job = None
        style = (self.config.get("selection") or {}).get("button") or {}
        if style.get("hide_mode", "timeout") == "timeout":
            delay = int(style.get("hide_after_ms", 2500))
            self._job = self.root.after(delay, self._maybe_hide)

    def _maybe_hide(self) -> None:
        self._job = None
        if self._hover:
            self._job = self.root.after(1200, self._maybe_hide)
            return
        self.hide()

    def _enter(self, _event=None) -> None:
        self._hover = True

    def _leave(self, _event=None) -> None:
        self._hover = False
        style = (self.config.get("selection") or {}).get("button") or {}
        if style.get("hide_mode") == "leave":
            self.hide()

    def _clicked(self, _event=None) -> None:
        # 同一次点击会依次冒泡到 label / frame / win，用一个短锁避免翻三次
        if self._handling:
            return
        self._handling = True
        self.root.after(400, lambda: setattr(self, "_handling", False))
        self.hide()
        self.on_click(self._anchor)

    def _chat_clicked(self, _event=None) -> None:
        if self._handling:
            return
        self._handling = True
        self.root.after(400, lambda: setattr(self, "_handling", False))
        self.hide()
        if self.on_chat is not None:
            self.on_chat(self._anchor)

    def hide(self) -> None:
        if self._job:
            try:
                self.root.after_cancel(self._job)
            except Exception:
                pass
            self._job = None
        self.win.withdraw()

    @property
    def visible(self) -> bool:
        return self.win.winfo_viewable() == 1


class Bubble:
    def __init__(self, root: tk.Tk, config, callbacks: dict) -> None:
        self.root = root
        self.config = config
        self.cb = callbacks
        self.payload: dict | None = None
        self._anchor = (0, 0)

        self.win = tk.Toplevel(root)
        self.win.withdraw()
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.bind("<Escape>", lambda _e: self.hide())
        self.win.bind("<FocusOut>", lambda _e: self._focus_lost())

        style = self._style()
        self.shell = tk.Frame(self.win, bg=BORDER)
        self.shell.pack(fill="both", expand=True)
        self.inner = tk.Frame(self.shell, bg=style["bg"], padx=14, pady=12)
        self.inner.pack(fill="both", expand=True, padx=1, pady=1)

        self.display = tk.Label(
            self.inner,
            text="",
            bg=style["bg"],
            fg=style["fg"],
            font=(FONT_FAMILY, 11),
            justify="left",
            anchor="w",
            wraplength=style["width"] - 32,
        )
        self.display.pack(fill="x")

        self.footer = tk.Frame(self.inner, bg=style["bg"])
        self.footer.pack(fill="x", pady=(8, 0))

        self.btn_copy = self._link("复制")
        self.btn_copy.pack(side="left")
        self.btn_details = self._link("详情")
        self.btn_details.pack(side="left", padx=(12, 0))
        self.btn_chat = self._link("聊聊")
        self.btn_chat.pack(side="left", padx=(12, 0))
        self.btn_close = self._link("✕")
        self.btn_close.pack(side="right")

        self.btn_copy.bind("<Button-1>", lambda _e: self._copy())
        self.btn_details.bind("<Button-1>", lambda _e: self._details())
        self.btn_chat.bind("<Button-1>", lambda _e: self._chat())
        self.btn_close.bind("<Button-1>", lambda _e: self.hide())

    def _style(self) -> dict:
        style = (self.config.get("selection") or {}).get("bubble") or {}
        return {
            "bg": style.get("bg", BG),
            "fg": style.get("fg", TEXT),
            "alpha": float(style.get("alpha", 0.97)),
            "width": int(style.get("width", 440)),
        }

    def _link(self, text: str) -> tk.Label:
        style = self._style()
        label = tk.Label(
            self.footer if hasattr(self, "footer") else self.inner,
            text=text,
            bg=style["bg"],
            fg=DIM,
            font=(FONT_FAMILY, 8),
            cursor="hand2",
        )
        label.bind("<Enter>", lambda _e: label.configure(fg=TEXT))
        label.bind("<Leave>", lambda _e: label.configure(fg=DIM))
        return label

    # ------------------------------------------------------------------ 状态
    def show_loading(self, anchor: tuple[int, int]) -> None:
        self.payload = None
        self._anchor = anchor
        style = self._style()
        self.inner.configure(bg=style["bg"])
        self.display.configure(text="正在翻译…", fg=MUTED, bg=style["bg"])
        self.footer.pack_forget()
        self._reveal()

    def show_result(self, payload: dict, anchor: tuple[int, int]) -> None:
        self.payload = payload
        self._anchor = anchor
        style = self._style()
        self.inner.configure(bg=style["bg"])
        text = payload.get("translation", "")
        if len(text) > 600:
            text = text[:600].rstrip() + "\n……（点「详情」看全文）"
        self.display.configure(text=text, fg=style["fg"], bg=style["bg"])
        self.footer.pack(fill="x", pady=(8, 0))
        self._reveal()

    def show_error(self, message: str, anchor: tuple[int, int]) -> None:
        self.payload = None
        self._anchor = anchor
        style = self._style()
        self.display.configure(text=message, fg="#f7768e", bg=style["bg"])
        self.footer.pack_forget()
        self._reveal()

    def _reveal(self) -> None:
        style = self._style()
        self.win.configure(bg=BORDER)
        self.win.attributes("-alpha", max(0.3, min(1.0, style["alpha"])))
        self.win.deiconify()
        self.win.update_idletasks()
        w = self.win.winfo_reqwidth()
        h = self.win.winfo_reqheight()
        x, y = screens.clamp(self._anchor, (w, h))
        self.win.geometry(f"+{x}+{y}")
        try:
            self.win.focus_force()
        except tk.TclError:
            pass

    def _focus_lost(self, event=None) -> None:
        # 点到别处就收起；焦点转到自己的子控件时忽略
        if event is not None and event.widget is not self.win:
            return
        if self.payload is not None:
            self.root.after(120, self._hide_if_unfocused)

    def _hide_if_unfocused(self) -> None:
        try:
            if self.win.focus_get() is None:
                self.hide()
        except tk.TclError:
            pass

    def _copy(self) -> None:
        if not self.payload:
            return
        self.win.clipboard_clear()
        self.win.clipboard_append(self.payload.get("translation", ""))
        self.cb.get("toast", lambda _m: None)("译文已复制")

    def _details(self) -> None:
        if not self.payload:
            return
        payload = self.payload
        self.hide()
        self.cb.get("details", lambda *_a: None)(payload, self._anchor)

    def _chat(self) -> None:
        if not self.payload:
            return
        payload = self.payload
        self.hide()
        self.cb.get("chat", lambda *_a: None)(payload, self._anchor)

    def hide(self) -> None:
        self.win.withdraw()
