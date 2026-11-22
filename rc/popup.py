"""划词浮窗。

一个无边框、置顶的小窗口，跟随鼠标出现，内容分四块：
原文 / 译文 / 生词 / 语法，底部是操作提示。
"""

from __future__ import annotations

import logging
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
        self._fader = anim.Fader(self.win, self._target_alpha)
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
        self.footer_bar.pack(fill="x", padx=14, pady=(2, 9), side="bottom")
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
        self.scrollbar.pack(side="right", fill="y", pady=(2, 4))
        self.canvas.pack(fill="both", expand=True, padx=(14, 4), pady=(2, 4))
        self.body = tk.Frame(self.canvas, bg=BG)
        self._canvas_item = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.body.bind(
            "<Configure>",
            lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.canvas.bind("<Configure>", self._on_canvas_resize)

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

    # ------------------------------------------------------------------ 尺寸/位置
    def _on_canvas_resize(self, event) -> None:
        self.canvas.itemconfigure(self._canvas_item, width=event.width)

    def _screen(self) -> tuple[int, int]:
        return self.win.winfo_screenwidth(), self.win.winfo_screenheight()

    def _place(self) -> None:
        self.win.update_idletasks()
        h = self.win.winfo_reqheight()
        x, y = screens.clamp(self._anchor, (self.width, h), offset=(16, 18))
        self.win.geometry(f"{self.width}x{h}+{x}+{y}")

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
        self._drag = (event.x_root, event.y_root, self.win.winfo_x(), self.win.winfo_y())

    def _do_drag(self, event) -> None:
        if not self._drag:
            return
        x0, y0, wx, wy = self._drag
        self._user_moved = True
        self.win.geometry(f"+{wx + event.x_root - x0}+{wy + event.y_root - y0}")

    # ------------------------------------------------------------------ 内容构建
    def _clear(self) -> None:
        for child in self.body.winfo_children():
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

    def _fit_height(self) -> None:
        sw, sh = self._screen()
        _, top, _, bottom = screens.work_area(self._anchor[0], self._anchor[1])
        available = max(240, bottom - top)
        max_total = int(available * self.max_ratio)
        self.win.update_idletasks()
        content_h = self.body.winfo_reqheight()
        if self._mode == "chat":
            content_h = max(content_h, 240)
        header_h = self.header.winfo_reqheight()
        footer_h = self.footer.winfo_reqheight()
        input_h = self.input_bar.winfo_reqheight() if self._mode == "chat" else 0
        chrome = header_h + footer_h + input_h + 30
        needs = content_h + chrome
        if needs <= max_total:
            self.canvas.configure(height=content_h + 2)
            self.canvas.yview_moveto(0)
            return
        self.canvas.configure(height=max(180, max_total - chrome))
        self.canvas.yview_moveto(0)

    def hide(self) -> None:
        self._visible = False
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

