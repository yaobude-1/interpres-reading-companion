"""主面板：上面翻译、下面对话，Ctrl+Alt+S 打开。

和划词浮窗的关系：
- 划词浮窗/气泡：在阅读器里随取随用
- 主面板：一个常驻工作区，可以粘贴长文翻译，也可以继续和它聊这本书
"""

from __future__ import annotations

import json
import tkinter as tk

from . import textutil
from .popup import ACCENT, BG, DIM, FONT_FAMILY, GREEN, MUTED, PANEL, PANEL_ALT, RED, TEXT
from .panel_chat import PanelChatMixin
from .panel_dict import PanelDictMixin
from .slimscroll import SlimScrollbar


class MainPanel(PanelChatMixin, PanelDictMixin):
    def __init__(self, root: tk.Tk, service, callbacks: dict) -> None:
        self.root = root
        self.service = service
        self.cb = callbacks
        self.book = ""
        self.conv_id: int | None = None
        self._typing: tk.Frame | None = None
        self._status_job = None
        self._stream_job = None
        self._stream_target = ""
        self._stream_shown = ""
        self._stream_final: dict | None = None
        self._chat_job = None
        self._chat_target = ""
        self._chat_shown = ""
        self._chat_reply = ""
        self._chat_final = False
        self.current_tab = "translate"

        self.win = tk.Toplevel(root)
        from . import __version__ as _ver

        self.win.title(f"Interpres {_ver}")
        self.win.configure(bg=BG)
        self.win.geometry("640x880")
        self.win.minsize(520, 700)
        self.win.protocol("WM_DELETE_WINDOW", self._on_close)
        self.win.bind("<Escape>", lambda _e: self._on_close())
        self._build()

    # ------------------------------------------------------------------ 构建
    def _build(self) -> None:
        outer = tk.Frame(self.win, bg=BG)
        outer.pack(fill="both", expand=True, padx=16, pady=12)

        header = tk.Frame(outer, bg=BG)
        header.pack(fill="x")
        tk.Label(
            header, text="Interpres", bg=BG, fg=TEXT, font=(FONT_FAMILY, 14, "bold")
        ).pack(side="left")
        self.book_label = tk.Label(
            header, text="选择书籍 ▾", bg=BG, fg=MUTED, font=(FONT_FAMILY, 9), cursor="hand2"
        )
        self.book_label.pack(side="left", padx=(10, 0))
        self.book_label.bind("<Button-1>", lambda _e: self._pick_book())

        self.rec_label = tk.Label(
            header, text="翻译记录 ▾", bg=BG, fg=DIM, font=(FONT_FAMILY, 9), cursor="hand2"
        )
        self.rec_label.pack(side="left", padx=(10, 0))
        self.rec_label.bind("<Button-1>", lambda _e: self._pick_record())

        gear = tk.Label(
            header, text="⚙", bg=BG, fg=DIM, font=(FONT_FAMILY, 12), cursor="hand2", padx=6
        )
        gear.pack(side="right")
        gear.bind("<Button-1>", lambda _e: self.cb.get("settings", lambda: None)())
        gear.bind("<Enter>", lambda _e: gear.configure(fg=TEXT))
        gear.bind("<Leave>", lambda _e: gear.configure(fg=DIM))

        # ---------------------------------------------------------- 页签
        tabs = tk.Frame(outer, bg=BG)
        tabs.pack(fill="x", pady=(8, 0))
        self.tab_translate = tk.Label(
            tabs, text="翻译", bg=PANEL, fg=TEXT, font=(FONT_FAMILY, 9, "bold"),
            padx=14, pady=5, cursor="hand2",
        )
        self.tab_translate.pack(side="left")
        self.tab_dict = tk.Label(
            tabs, text="查词", bg=BG, fg=DIM, font=(FONT_FAMILY, 9, "bold"),
            padx=14, pady=5, cursor="hand2",
        )
        self.tab_dict.pack(side="left", padx=(6, 0))
        self.tab_chat = tk.Label(
            tabs, text="对话", bg=BG, fg=DIM, font=(FONT_FAMILY, 9, "bold"),
            padx=14, pady=5, cursor="hand2",
        )
        self.tab_chat.pack(side="left", padx=(6, 0))
        self.tab_translate.bind("<Button-1>", lambda _e: self._show_tab("translate"))
        self.tab_dict.bind("<Button-1>", lambda _e: self._show_tab("dict"))
        self.tab_chat.bind("<Button-1>", lambda _e: self._show_tab("chat"))
        self.tab_vocab = tk.Label(
            tabs, text="生词", bg=BG, fg=DIM, font=(FONT_FAMILY, 9, "bold"),
            padx=14, pady=5, cursor="hand2",
        )
        self.tab_vocab.pack(side="left", padx=(6, 0))
        self.tab_vocab.bind("<Button-1>", lambda _e: self._show_tab("vocab"))

        # 内容区独立滚动：词条再长也不会把下面的对话区挤掉
        self.content_wrap = tk.Frame(outer, bg=BG)
        content_wrap = self.content_wrap
        content_wrap.pack(fill="both", expand=True, pady=(6, 0))
        self.content_canvas = tk.Canvas(
            content_wrap, bg=BG, highlightthickness=0, bd=0, height=260
        )
        self.content_scroll = SlimScrollbar(
            content_wrap, command=self.content_canvas.yview, width=14
        )
        self.content_canvas.configure(
            yscrollcommand=lambda first, last: self._sync_scrollbar(
                self.content_scroll, self.content_canvas, first, last
            )
        )
        self.content_scroll.pack(side="right", fill="y")
        self.content_canvas.pack(side="left", fill="both", expand=True)
        self.content = tk.Frame(self.content_canvas, bg=BG)
        self._content_item = self.content_canvas.create_window(
            (0, 0), window=self.content, anchor="nw"
        )
        self.content.bind(
            "<Configure>",
            lambda _e: self.content_canvas.configure(
                scrollregion=self.content_canvas.bbox("all")
            ),
        )
        self.content_canvas.bind(
            "<Configure>",
            lambda e: self.content_canvas.itemconfigure(self._content_item, width=e.width),
        )
        self.content_canvas.bind(
            "<MouseWheel>",
            lambda e: self._scroll_pane(
                self.content_canvas, self.content, int(-e.delta / 120) * 2
            ),
        )

        # ---------------------------------------------------------- 翻译区
        self.trans_frame = tk.Frame(self.content, bg=BG)
        self.trans_frame.pack(fill="x")

        self.input = tk.Text(
            self.trans_frame,
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
        self.input.pack(fill="x")
        self.input.bind("<Control-Return>", lambda _e: (self._translate(), "break")[1])

        buttons = tk.Frame(self.trans_frame, bg=BG)
        buttons.pack(fill="x", pady=(6, 6))
        self._button(buttons, "翻译（Ctrl+Enter）", self._translate, primary=True).pack(side="left")
        self._button(buttons, "清空", self._clear).pack(side="left", padx=(8, 0))
        self.status = tk.Label(
            buttons, text="", bg=BG, fg=MUTED, font=(FONT_FAMILY, 8), anchor="w"
        )
        self.status.pack(side="left", padx=(10, 0))

        self.output = tk.Text(
            self.trans_frame,
            height=6,
            bg=PANEL,
            fg=TEXT,
            relief="flat",
            font=(FONT_FAMILY, 10),
            wrap="word",
            padx=10,
            pady=8,
            state="disabled",
        )
        self.output.pack(fill="x")

        # ---------------------------------------------------------- 查词区
        self.dict_frame = tk.Frame(self.content, bg=BG)
        dict_bar = tk.Frame(self.dict_frame, bg=BG)
        dict_bar.pack(fill="x")
        self.dict_input = tk.Entry(
            dict_bar,
            bg=PANEL,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            font=(FONT_FAMILY, 12),
        )
        self.dict_input.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 8))
        self._button(dict_bar, "查", self._lookup_dict, primary=True).pack(side="left")
        self.dict_input.bind("<Return>", lambda _e: (self._lookup_dict(), "break")[1])
        self.dict_input.bind("<KeyRelease>", self._on_dict_typing)

        # 输入框下方的建议列表：独立半透明浮层，跟随窗口移动、可滚轮滑动
        self.suggest_win = tk.Toplevel(self.win)
        self.suggest_win.withdraw()
        self.suggest_win.overrideredirect(True)
        self.suggest_win.configure(bg=PANEL)
        try:
            self.suggest_win.attributes("-alpha", 0.96)
        except tk.TclError:
            pass
        shell = tk.Frame(
            self.suggest_win, bg=PANEL, highlightthickness=1,
            highlightbackground="#3d4454", bd=0,
        )
        shell.pack(fill="both", expand=True)
        self.suggest_canvas = tk.Canvas(
            shell, bg=PANEL, highlightthickness=0, bd=0, takefocus=0
        )
        self.suggest_canvas.pack(fill="both", expand=True)
        self.suggest_body = tk.Frame(self.suggest_canvas, bg=PANEL)
        self._suggest_item = self.suggest_canvas.create_window(
            (0, 0), window=self.suggest_body, anchor="nw"
        )
        self.suggest_body.bind(
            "<Configure>",
            lambda _e: self.suggest_canvas.configure(
                scrollregion=self.suggest_canvas.bbox("all")
            ),
        )
        self.suggest_canvas.bind(
            "<Configure>",
            lambda e: self.suggest_canvas.itemconfigure(self._suggest_item, width=e.width),
        )
        for widget in (self.suggest_canvas, self.suggest_body):
            widget.bind("<MouseWheel>", self._suggest_wheel)
            widget.bind("<Button-1>", self._suggest_background_click)
        self.suggest_win.bind("<Button-1>", self._suggest_background_click)
        self._suggest_rows: list[tk.Frame] = []
        self._suggest_index = -1
        self._suggest_items: list[dict] = []
        self.win.bind("<Configure>", self._reposition_suggest, add="+")
        self.win.bind("<MouseWheel>", self._route_wheel, add="+")
        self.win.bind("<Button-1>", self._dismiss_on_click, add="+")
        self.win.bind("<FocusOut>", self._on_main_focus_out, add="+")
        for seq in ("<Down>", "<Up>", "<Return>", "<Escape>"):
            self.dict_input.bind(seq, self._on_suggest_key)
        self.dict_input.bind("<FocusOut>", lambda _e: self.win.after(150, self._hide_suggestions))
        self.dict_input.bind("<Button-1>", lambda _e: self.win.after(20, self._reshow_suggestions))

        self.dict_result = tk.Frame(self.dict_frame, bg=BG)
        self.dict_result.pack(fill="x", pady=(8, 0))
        self.dict_hint = tk.Label(
            self.dict_result,
            text="输入一个单词，本地词典查询，不消耗 token",
            bg=BG,
            fg=MUTED,
            font=(FONT_FAMILY, 9),
        )
        self.dict_hint.pack(fill="x", pady=(6, 10))
        self._dict_job = None

        # ---------------------------------------------------------- 对话区（独立页签）
        self.vocab_frame = None
        self.vocab_panel = None
        self.chat_frame = tk.Frame(outer, bg=BG)
        chat_head = tk.Frame(self.chat_frame, bg=BG)
        chat_head.pack(fill="x", pady=(6, 4))
        tk.Label(
            chat_head, text="与它聊聊", bg=BG, fg=ACCENT, font=(FONT_FAMILY, 9, "bold")
        ).pack(side="left")
        history = tk.Label(
            chat_head, text="对话记录", bg=BG, fg=DIM, font=(FONT_FAMILY, 8), cursor="hand2"
        )
        history.pack(side="right")
        history.bind("<Button-1>", lambda _e: self.cb.get("chat_history", lambda: None)())
        history.bind("<Enter>", lambda _e: history.configure(fg=TEXT))
        history.bind("<Leave>", lambda _e: history.configure(fg=DIM))

        chat_wrap = tk.Frame(self.chat_frame, bg=BG)
        chat_wrap.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(chat_wrap, bg=BG, highlightthickness=0, bd=0, height=220)
        self.scrollbar = SlimScrollbar(
            chat_wrap, command=self.canvas.yview, width=14
        )
        self.canvas.configure(
            yscrollcommand=lambda first, last: self._sync_scrollbar(
                self.scrollbar, self.canvas, first, last
            )
        )
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.chat_body = tk.Frame(self.canvas, bg=BG)
        self._item = self.canvas.create_window((0, 0), window=self.chat_body, anchor="nw")
        self.chat_body.bind(
            "<Configure>",
            lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.canvas.bind(
            "<Configure>", lambda e: self.canvas.itemconfigure(self._item, width=e.width)
        )
        self._bind_wheel(self.canvas)
        self._bind_wheel(self.chat_body)

        input_bar = tk.Frame(self.chat_frame, bg=BG)
        # 先占底部，聊天区再撑满剩余空间
        chat_head.pack_forget()
        chat_wrap.pack_forget()
        input_bar.pack(side="bottom", fill="x", pady=(6, 0))
        chat_head.pack(side="top", fill="x", pady=(0, 4))
        chat_wrap.pack(side="top", fill="both", expand=True)
        send = tk.Label(
            input_bar,
            text="发送",
            bg=ACCENT,
            fg="#10131a",
            font=(FONT_FAMILY, 9),
            padx=12,
            pady=8,
            cursor="hand2",
        )
        send.pack(side="right", padx=(8, 0), fill="y")
        send.bind("<Button-1>", lambda _e: self._send())
        self.chat_input = tk.Text(
            input_bar,
            height=2,
            width=20,
            bg=PANEL,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            font=(FONT_FAMILY, 10),
            wrap="word",
            padx=8,
            pady=6,
        )
        self.chat_input.pack(side="left", fill="both", expand=True)
        self.chat_input.bind("<Return>", lambda _e: (self._send(), "break")[1])
        self.chat_input.bind("<Shift-Return>", lambda _e: None)
        self._bind_wheel(self.chat_input)

    def _button(self, parent, text, command, primary=False):
        bg = ACCENT if primary else PANEL
        fg = "#10131a" if primary else TEXT
        label = tk.Label(
            parent, text=text, bg=bg, fg=fg, font=(FONT_FAMILY, 9), padx=12, pady=5, cursor="hand2"
        )
        label.bind("<Button-1>", lambda _e: command())
        return label

    def _scroll_pane(self, canvas, body, step: int) -> None:
        """内容装得下就不滚（Tk 会把内容拖出去，露出空白）。"""
        try:
            if body.winfo_height() <= canvas.winfo_height() + 1:
                canvas.yview_moveto(0.0)
                return
            canvas.yview_scroll(step, "units")
        except tk.TclError:
            pass

    def _sync_chat_scroll(self) -> None:
        try:
            content_h = self.chat_body.winfo_height()
            view_h = self.canvas.winfo_height()
            if content_h <= view_h + 1:
                self.canvas.yview_moveto(0.0)
        except tk.TclError:
            pass

    def _sync_content_scroll(self) -> None:
        """重算滚动区；内容装得下就回到顶部，杜绝滚进空白。"""
        try:
            self.content.update_idletasks()
            bbox = self.content_canvas.bbox("all")
            if bbox:
                self.content_canvas.configure(scrollregion=bbox)
            content_h = self.content.winfo_height()
            view_h = self.content_canvas.winfo_height()
            if content_h <= view_h + 1:
                self.content_canvas.yview_moveto(0.0)
        except tk.TclError:
            pass

    def _sync_scrollbar(self, bar, canvas, first, last) -> None:
        """只更新滑块位置；滚动条常驻，避免显隐导致宽度反复变化。"""
        bar.set(first, last)

    def _bind_content_wheel(self, widget) -> None:
        widget.bind(
            "<MouseWheel>",
            lambda e: self._scroll_pane(
                self.content_canvas, self.content, int(-e.delta / 120) * 2
            ),
            add="+",
        )
        for child in widget.winfo_children():
            self._bind_content_wheel(child)

    def _bind_wheel(self, widget) -> None:
        widget.bind("<MouseWheel>", self._on_wheel, add="+")
        for child in widget.winfo_children():
            self._bind_wheel(child)

    def _on_wheel(self, event) -> None:
        self.canvas.yview_scroll(int(-event.delta / 120), "units")

    # ------------------------------------------------------------------ 显示
    def show(self, book_override: str = "") -> None:
        book = (
            book_override
            or self.service.config.get("panel_book", "")
            or self.service.current_book()
        )
        if book != self.book:
            self.book = book
            self._set_book_label(book)
            self._ensure_conversation()
        elif self.conv_id is None:
            self._ensure_conversation()
        self.win.deiconify()
        self.win.lift()
        try:
            self.win.focus_force()
        except tk.TclError:
            pass
        self.input.focus_set()
        self._scroll_bottom()

    def hide(self) -> None:
        try:
            self._hide_suggestions()
        except Exception:
            pass
        self.win.withdraw()

    def _on_close(self) -> None:
        try:
            self._hide_suggestions()
        except Exception:
            pass
        """Esc / ✕：按设置决定是退出程序还是只隐藏。"""
        handler = self.cb.get("close")
        if handler is not None:
            handler()
        else:
            self.hide()

    def _set_book_label(self, book: str) -> None:
        text = f"《{textutil.display(book, 26)}》 ▾" if book else "选择书籍 ▾"
        self.book_label.configure(text=text)

    def _pick_book(self) -> None:
        menu = tk.Menu(
            self.win,
            tearoff=0,
            bg=PANEL,
            fg=TEXT,
            activebackground=ACCENT,
            activeforeground="#10131a",
            font=(FONT_FAMILY, 9),
        )
        books = self.service.store.books()
        if not books:
            menu.add_command(label="（还没有读过别的书）", state="disabled")
        for item in books:
            name = item["name"]
            mark = "✓ " if name == self.book else "   "
            menu.add_command(
                label=f"{mark}《{textutil.display(name, 28)}》",
                command=lambda n=name: self._select_book(n),
            )
        menu.add_separator()
        menu.add_command(label="管理对话记录…", command=lambda: self.cb.get("chat_history", lambda: None)())
        try:
            menu.tk_popup(self.book_label.winfo_rootx(), self.book_label.winfo_rooty() + 18)
        finally:
            menu.grab_release()

    def _pick_record(self) -> None:
        """快速回看：当前这本书最近翻译过的几段。"""
        menu = tk.Menu(
            self.win,
            tearoff=0,
            bg=PANEL,
            fg=TEXT,
            activebackground=ACCENT,
            activeforeground="#10131a",
            font=(FONT_FAMILY, 9),
        )
        rows = self.service.translations(book=self.book or None, limit=8)
        if not rows:
            menu.add_command(label="（这本书还没有翻译记录）", state="disabled")
        for row in rows:
            preview = " ".join((row.get("text") or "").split())[:38]
            stamp = (row.get("updated") or "")[5:16]
            menu.add_command(
                label=f"{stamp}  {preview}", command=lambda r=row: self._load_record(r)
            )
        menu.add_separator()
        menu.add_command(
            label="全部记录…", command=lambda: self.cb.get("translations", lambda: None)()
        )
        try:
            menu.tk_popup(self.rec_label.winfo_rootx(), self.rec_label.winfo_rooty() + 18)
        finally:
            menu.grab_release()

    def _load_record(self, row: dict) -> None:
        payload = json.loads(row.get("payload") or "{}")
        text = row.get("text") or ""
        self.input.delete("1.0", "end")
        self.input.insert("1.0", text)
        merged = dict(payload)
        merged["text"] = text
        merged["book"] = row.get("book") or self.book
        self.show_result(merged)

    def _select_book(self, book: str) -> None:
        if not book or book == self.book:
            return
        self.book = book
        self._set_book_label(book)
        self._ensure_conversation()
        try:
            self.service.config.data["panel_book"] = book
            self.service.config.save()
        except Exception:
            pass

    def on_book(self, book: str) -> None:
        """读到别的书了：只有开了「自动跟随」才切。"""
        if not book or book == self.book:
            return
        if not self.service.config.get("auto_follow_book", False):
            return
        self.book = book
        self._set_book_label(book)
        self._ensure_conversation()

    # ------------------------------------------------------------------ 对话
    def _ensure_vocab_panel(self):
        if self.vocab_panel is None:
            from .vocab_panel import VocabPanel

            outer = self.chat_frame.master
            self.vocab_frame = tk.Frame(outer, bg=BG)
            self.vocab_panel = VocabPanel(
                self.vocab_frame, self.service, self.service.config
            )
        return self.vocab_panel

    def _show_tab(self, name: str) -> None:
        self.current_tab = name
        try:
            self._hide_suggestions()
        except Exception:
            pass
        if name == "vocab":
            self.content_wrap.pack_forget()
            self.chat_frame.pack_forget()
            panel = self._ensure_vocab_panel()
            self.vocab_frame.pack(fill="both", expand=True, pady=(6, 0))
            self.tab_vocab.configure(bg=PANEL, fg=TEXT)
            self.tab_translate.configure(bg=BG, fg=DIM)
            self.tab_dict.configure(bg=BG, fg=DIM)
            self.tab_chat.configure(bg=BG, fg=DIM)
            panel.refresh()
            return
        if self.vocab_frame is not None:
            self.vocab_frame.pack_forget()
        self.tab_vocab.configure(bg=BG, fg=DIM)
        if name == "chat":
            self.content_wrap.pack_forget()
            self.chat_frame.pack(fill="both", expand=True)
            self.tab_chat.configure(bg=PANEL, fg=TEXT)
            self.tab_translate.configure(bg=BG, fg=DIM)
            self.tab_dict.configure(bg=BG, fg=DIM)
            self.input.focus_set()
            self.win.after(30, self._scroll_bottom)
            return

        self.chat_frame.pack_forget()
        if not self.content_wrap.winfo_manager():
            self.content_wrap.pack(fill="both", expand=True, pady=(6, 0))
        self.tab_chat.configure(bg=BG, fg=DIM)
        if name == "dict":
            self.trans_frame.pack_forget()
            self.dict_frame.pack(fill="x")
            self.tab_dict.configure(bg=PANEL, fg=TEXT)
            self.tab_translate.configure(bg=BG, fg=DIM)
            self.dict_input.focus_set()
            self._sync_content_scroll()
        else:
            self.dict_frame.pack_forget()
            self.trans_frame.pack(fill="x")
            self.tab_translate.configure(bg=PANEL, fg=TEXT)
            self.tab_dict.configure(bg=BG, fg=DIM)
            self.input.focus_set()
            self._sync_content_scroll()

    def _on_suggest_key(self, event) -> str:
        if not self._suggest_rows:
            if event.keysym in ("Down", "Up"):
                self._reshow_suggestions()
                return "break" if self._suggest_rows else ""
            return ""
        rows = self._suggest_rows
        if event.keysym == "Down":
            self._suggest_index = (self._suggest_index + 1) % len(rows)
        elif event.keysym == "Up":
            self._suggest_index = (self._suggest_index - 1) % len(rows)
        elif event.keysym == "Escape":
            self._hide_suggestions()
            return "break"
        elif event.keysym == "Return":
            if 0 <= self._suggest_index < len(rows):
                word = self._suggest_items[self._suggest_index]["word"]
                self._accept_suggestion(word)
                return "break"
            self._hide_suggestions()
            self._lookup_dict()
            return "break"
        self._highlight_suggestion()
        return "break"

    def _highlight_suggestion(self) -> None:
        for index, row in enumerate(self._suggest_rows):
            color = PANEL_ALT if index == self._suggest_index else PANEL
            try:
                row.configure(bg=color)
                for child in row.winfo_children():
                    child.configure(bg=color)
            except tk.TclError:
                pass

    def _route_wheel(self, event) -> str:
        """滚轮按鼠标位置分派：浮层 → 浮层，内容区 → 内容区，对话区 → 对话区。"""
        try:
            px, py = self.win.winfo_pointerxy()
        except tk.TclError:
            return "break"
        step = int(-event.delta / 120) or 0
        if step == 0:
            return "break"

        def inside(widget) -> bool:
            try:
                if not widget.winfo_ismapped():
                    return False
                x0 = widget.winfo_rootx()
                y0 = widget.winfo_rooty()
                return x0 <= px <= x0 + widget.winfo_width() and y0 <= py <= y0 + widget.winfo_height()
            except tk.TclError:
                return False

        # 建议浮层可见且鼠标在浮层（或输入框）上
        if self._suggest_rows:
            try:
                sw = self.suggest_win
                if sw.winfo_viewable() and (
                    inside(sw) or inside(self.dict_input)
                ):
                    self.suggest_canvas.yview_scroll(step, "units")
                    return "break"
            except tk.TclError:
                pass
        if inside(self.canvas):
            self._scroll_pane(self.canvas, self.chat_body, step * 2)
            return "break"
        # 内容区、输入框、顶部区域：都滚内容区
        self._scroll_pane(self.content_canvas, self.content, step * 2)
        return "break"

    def _log_click(self, event) -> None:
        try:
            import logging

            logging.getLogger("click").info(
                "panel click widget=%s class=%s xy=%s,%s",
                event.widget, event.widget.winfo_class(), event.x, event.y,
            )
        except Exception:
            pass

    def _dismiss_on_click(self, event=None) -> None:
        widget = getattr(event, "widget", None)
        if widget is self.dict_input:
            return
        if self._suggest_rows:
            self._hide_suggestions()

    def _suggest_background_click(self, event=None) -> str:
        """点在浮层空白处：收起浮层，并把这次点击透传给下面的控件。"""
        x = getattr(event, "x_root", None)
        y = getattr(event, "y_root", None)
        self._hide_suggestions()
        if x is None or y is None:
            return "break"
        self.win.after(30, lambda: self._click_through(x, y))
        return "break"

    def _click_through(self, x: int, y: int) -> None:
        try:
            import ctypes
            import time as _t

            user32 = ctypes.windll.user32
            user32.SetCursorPos(int(x), int(y))
            _t.sleep(0.02)
            user32.mouse_event(0x0002, 0, 0, 0, 0)
            _t.sleep(0.02)
            user32.mouse_event(0x0004, 0, 0, 0, 0)
        except Exception:
            pass

    def _reshow_suggestions(self) -> None:
        """不用重新输入：点输入框 / 按 ↓ 就能把建议重新唤出来。"""
        if not self._suggest_rows and self.dict_input.get().strip():
            self._update_suggestions()

    def _on_main_focus_out(self, _event=None) -> None:
        self.win.after(220, self._hide_suggest_if_unfocused)

    def _hide_suggest_if_unfocused(self) -> None:
        if not self._suggest_rows:
            return
        try:
            focused = self.win.focus_get()
        except tk.TclError:
            focused = None
        if focused is None:
            self._hide_suggestions()

    def _suggest_wheel(self, event) -> str:
        self._scroll_pane(
            self.suggest_canvas, self.suggest_body, int(-event.delta / 120)
        )
        return "break"

    def _suggest_bind_all(self, widget) -> None:
        widget.bind("<MouseWheel>", self._suggest_wheel)
        for child in widget.winfo_children():
            self._suggest_bind_all(child)

    def _hide_suggestions(self) -> None:
        for row in self._suggest_rows:
            try:
                row.destroy()
            except tk.TclError:
                pass
        self._suggest_rows = []
        self._suggest_items = []
        self._suggest_index = -1
        try:
            self.suggest_win.attributes("-topmost", False)
        except tk.TclError:
            pass
        try:
            self.suggest_win.withdraw()
        except tk.TclError:
            pass

    def _suggest_geometry(self) -> tuple[int, int, int, int]:
        self.win.update_idletasks()
        x = self.dict_input.winfo_rootx()
        y = self.dict_input.winfo_rooty() + self.dict_input.winfo_height() + 2
        width = max(200, self.dict_input.winfo_width())
        bottom = self.win.winfo_rooty() + self.win.winfo_height() - 10
        space = max(90, bottom - y)
        self.suggest_body.update_idletasks()
        content = self.suggest_body.winfo_reqheight() + 2
        height = min(content, 300, space)
        return x, y, width, height

    def _reposition_suggest(self, _event=None) -> None:
        if not self._suggest_rows:
            return
        try:
            if not self.suggest_win.winfo_viewable():
                return
        except tk.TclError:
            return
        x, y, width, height = self._suggest_geometry()
        top = self.win.winfo_rooty()
        bottom = top + self.win.winfo_height()
        # 输入框被滚出窗口：收起，别让浮层飘到窗口外面
        if y < top + 30 or y > bottom - 30:
            self._hide_suggestions()
            return
        height = min(height, bottom - y - 8)
        if height < 60:
            self._hide_suggestions()
            return
        self.suggest_win.geometry(f"{width}x{height}+{x}+{y}")

    def _accept_suggestion(self, word: str) -> None:
        self._hide_suggestions()
        self.dict_input.delete(0, "end")
        self.dict_input.insert(0, word)
        self._lookup_dict()
        try:
            self.dict_input.icursor("end")
            self.dict_input.focus_set()
            self._sync_content_scroll()
        except tk.TclError:
            pass

    def _update_suggestions(self) -> None:
        word = self.dict_input.get().strip()
        if len(word) < 1 or not self.service.has_dictionaries():
            self._hide_suggestions()
            return
        try:
            items = self.service.fuzzy_lookup(word, None, 10)
        except Exception:
            items = []
        if not items:
            self._hide_suggestions()
            return
        for row in self._suggest_rows:
            try:
                row.destroy()
            except tk.TclError:
                pass
        self._suggest_rows = []
        self._suggest_index = -1
        self._suggest_items = items
        for item in items:
            row = tk.Frame(self.suggest_body, bg=PANEL)
            row.pack(fill="x")
            name = item.get("word") or ""
            name_label = tk.Label(
                row, text=name, bg=PANEL, fg=TEXT,
                font=(FONT_FAMILY, 10, "bold"), anchor="w",
            )
            name_label.pack(side="left", padx=(10, 0), pady=3)
            pos = (item.get("pos") or "").strip()
            if pos:
                tk.Label(
                    row, text=pos, bg=PANEL, fg=ACCENT, font=(FONT_FAMILY, 8)
                ).pack(side="left", padx=(8, 0))
            gloss = (item.get("gloss") or "").strip()
            if gloss:
                tk.Label(
                    row, text=gloss[:42], bg=PANEL, fg=MUTED,
                    font=(FONT_FAMILY, 9), anchor="w",
                ).pack(side="left", padx=(10, 0))
            for widget in (row, name_label):
                widget.configure(cursor="hand2")
                widget.bind("<Button-1>", lambda _e, w=name: self._accept_suggestion(w))
            self._suggest_rows.append(row)
        self._suggest_bind_all(self.suggest_body)
        self.suggest_canvas.yview_moveto(0.0)
        x, y, width, height = self._suggest_geometry()
        self.suggest_win.geometry(f"{width}x{height}+{x}+{y}")
        self.suggest_win.deiconify()
        try:
            self.suggest_win.attributes("-topmost", True)
        except tk.TclError:
            pass
        self.suggest_win.lift()
        self.win.update_idletasks()
        self._reposition_suggest()

    def _render_fuzzy(self, word: str, lang: str | None, exclude: str = "") -> None:
        """在查词结果下面列相近的词（前缀/纠错/重音归一）。"""
        try:
            items = self.service.fuzzy_lookup(word, lang, 12)
        except Exception:
            items = []
        exclude_norm = (exclude or "").strip().lower()
        rows = [it for it in items if (it.get("word") or "").lower() != exclude_norm]
        if not rows:
            return
        box = tk.Frame(self.dict_result, bg=BG)
        box.pack(fill="x", pady=(10, 2))
        tk.Label(
            box, text="相近的词", bg=BG, fg=MUTED, font=(FONT_FAMILY, 8), anchor="w"
        ).pack(fill="x", pady=(0, 4))
        for item in rows:
            line = tk.Frame(box, bg=BG)
            line.pack(fill="x", pady=1)
            name = item.get("word") or ""
            name_label = tk.Label(
                line, text=name, bg=BG, fg=TEXT, font=(FONT_FAMILY, 10, "bold"),
                anchor="w", cursor="hand2",
            )
            name_label.pack(side="left")
            pos = (item.get("pos") or "").strip()
            if pos:
                tk.Label(
                    line, text=pos, bg=BG, fg=ACCENT, font=(FONT_FAMILY, 8)
                ).pack(side="left", padx=(8, 0))
            gloss = (item.get("gloss") or "").strip()
            if gloss:
                tk.Label(
                    line, text=gloss, bg=BG, fg=MUTED, font=(FONT_FAMILY, 9),
                    anchor="w",
                ).pack(side="left", padx=(10, 0))
            name_label.bind("<Button-1>", lambda _e, w=name: self._dict_lookup_word(w))

    def _dict_hint(self, text: str) -> None:
        tk.Label(
            self.dict_result,
            text=text,
            bg=BG,
            fg=MUTED,
            font=(FONT_FAMILY, 9),
            justify="left",
            anchor="w",
            wraplength=560,
        ).pack(fill="x", pady=(6, 10))

    def _translate(self) -> None:
        text = self.input.get("1.0", "end-1c").strip()
        if not text:
            self._set_status("先粘贴或输入要翻译的文字", RED)
            return
        self._set_status("翻译中…", MUTED)
        self.cb.get("translate", lambda *_a: None)(text, self.book)

    def show_partial(self, text: str) -> None:
        """流式：只更新目标文本，真正的显示由定时器按速度铺开。"""
        if not text:
            return
        self._stream_target = text
        if self._stream_job is None:
            self._stream_shown = ""
            try:
                self.output.configure(state="normal")
                self.output.delete("1.0", "end")
            except tk.TclError:
                return
            self._stream_tick()

    def _stream_speed(self) -> int:
        try:
            speed = int(self.service.config.get("stream_speed", 60))
        except Exception:
            speed = 60
        return max(5, min(400, speed))

    def _stream_tick(self) -> None:
        self._stream_job = None
        try:
            if not self.output.winfo_exists():
                return
        except tk.TclError:
            return
        pending = self._stream_target[len(self._stream_shown):]
        if pending:
            step = max(1, int(self._stream_speed() * 0.033))
            if len(pending) > 240:
                step *= 3  # 落后太多时自动追赶
            piece = pending[:step]
            self._stream_shown += piece
            try:
                self.output.configure(state="normal")
                self.output.insert("end", piece)
                self._fit_output_height()
            except tk.TclError:
                return
            self._stream_job = self.win.after(33, self._stream_tick)
            return
        # 追平了：如果有最终结果，收尾
        if self._stream_final is not None:
            payload = self._stream_final
            self._stream_final = None
            self._stream_target = ""
            self._stream_shown = ""
            self._finish_result(payload)

    def show_result(self, payload: dict) -> None:
        translation = payload.get("translation") or ""
        self._stream_final = payload
        if not translation:
            self._finish_result(payload)
            return
        if self._stream_job is None and not self._stream_shown:
            # 非流式路径（缓存/兼容接口）：也铺开显示
            self._stream_target = translation
            self._stream_tick()
        else:
            self._stream_target = translation

    def _finish_result(self, payload: dict) -> None:
        translation = payload.get("translation") or ""
        self._cancel_stream()
        try:
            self.output.configure(state="normal")
            self.output.delete("1.0", "end")
            self.output.insert("1.0", translation)
            self.output.configure(state="disabled")
            self._fit_output_height()
        except tk.TclError:
            pass
        self._set_status(f"完成 · {payload.get('meta', {}).get('elapsed_ms', 0)} ms", GREEN)
        self._sync_content_scroll()
        if self.conv_id is not None:
            self.service.update_conversation_context(
                self.conv_id, payload.get("text", ""), translation
            )

    def _cancel_stream(self) -> None:
        job = self._stream_job
        self._stream_job = None
        if job:
            try:
                self.win.after_cancel(job)
            except tk.TclError:
                pass
        self._stream_target = ""
        self._stream_shown = ""
        self._stream_final = None

    def _max_output_lines(self) -> int:
        import tkinter.font as tkfont

        try:
            height = self.win.winfo_height()
            linespace = tkfont.Font(font=self.output.cget("font")).metrics("linespace")
            return max(6, int(height * 0.6 / max(1, linespace)))
        except Exception:
            return 30

    def _fit_output_height(self) -> None:
        try:
            count = self.output.count("1.0", "end-1c", "displaylines")
            lines = (count[0] if isinstance(count, tuple) else count) or 1
        except Exception:
            text = self.output.get("1.0", "end-1c")
            lines = text.count("\n") + max(1, len(text) // 60)
        lines = max(4, min(int(lines) + 1, self._max_output_lines()))
        try:
            if int(self.output.cget("height")) != lines:
                self.output.configure(height=lines)
                self._sync_content_scroll()
        except tk.TclError:
            pass

    def show_progress(self, index: int, total: int) -> None:
        if index == 1:
            self._cancel_stream()
            try:
                self.output.configure(state="normal")
                self.output.delete("1.0", "end")
                self.output.configure(state="disabled")
            except tk.TclError:
                pass
        if total > 1:
            self._set_status(f"翻译中… {index}/{total}", MUTED)

    def show_error(self, message: str) -> None:
        self._set_status(message[:80], RED)

    def _set_status(self, text: str, color: str = MUTED) -> None:
        try:
            self.status.configure(text=text, fg=color)
        except tk.TclError:
            pass

    def _clear(self) -> None:
        self._cancel_stream()
        self.input.delete("1.0", "end")
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.configure(state="disabled")
        self._set_status("", MUTED)
