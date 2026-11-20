"""划词浮窗。

一个无边框、置顶的小窗口，跟随鼠标出现，内容分四块：
原文 / 译文 / 生词 / 语法，底部是操作提示。
"""

from __future__ import annotations

import tkinter as tk

from . import screens, textutil

BG = "#1b1d24"
PANEL = "#23262f"
PANEL_ALT = "#2a2e39"
TEXT = "#e6e9ef"
MUTED = "#9aa5b1"
DIM = "#6b7280"
ACCENT = "#7aa2f7"
GREEN = "#9ece6a"
RED = "#f7768e"
BORDER = "#3b414f"

FONT_FAMILY = "Microsoft YaHei UI"


class PopupWindow:
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
            bg="#4b5263",
            troughcolor=PANEL,
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
        except Exception:
            pass

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
        line = tk.Frame(self.body, bg="#2f3440", height=1)
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
        except tk.TclError:
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
            fg="#10131a",
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
    def _dict_action(self, parent, text: str, command) -> tk.Label:
        label = tk.Label(
            parent,
            text=text,
            bg=PANEL,
            fg=TEXT,
            font=(FONT_FAMILY, 9),
            padx=10,
            pady=5,
            cursor="hand2",
        )
        label.bind("<Button-1>", lambda _e: command())
        label.bind("<Enter>", lambda _e: label.configure(bg=PANEL_ALT))
        label.bind("<Leave>", lambda _e: label.configure(bg=PANEL))
        return label

    def show_dictionary(self, entry: dict, anchor, word: str = "", alternatives=None) -> None:
        """本地词典查词结果（不花 token）；有变位/变格时提供「时态」页签。"""
        self._reset_to_translate(chat_button=False)
        self._mode = "dict"
        self._dict = entry
        if anchor != self._anchor:
            self._user_moved = False
        self._anchor = anchor
        self._dict_word = word or entry.get("word") or entry.get("query") or ""
        self.current = None
        self._clear()
        self._dict_editing = False
        self._dict_entry = None
        self.title.configure(text="查词")

        head = tk.Frame(self.body, bg=BG)
        head.pack(fill="x", pady=(2, 6))
        self._dict_word_label = self._label(
            head, self._dict_word, fg=TEXT, font=(FONT_FAMILY, 17, "bold")
        )
        self._dict_word_label.pack(side="left")
        self._dict_word_label.configure(cursor="hand2")
        self._dict_word_label.bind("<Button-1>", lambda _e: self._edit_dict_word())
        self._dict_word_label.bind(
            "<Enter>",
            lambda _e: self._dict_word_label.configure(
                font=(FONT_FAMILY, 17, "bold", "underline")
            ),
        )
        self._dict_word_label.bind(
            "<Leave>",
            lambda _e: self._dict_word_label.configure(font=(FONT_FAMILY, 17, "bold")),
        )
        edit = self._label(head, "✎", fg=DIM, font=(FONT_FAMILY, 11))
        edit.pack(side="left", padx=(8, 0))
        edit.configure(cursor="hand2")
        edit.bind("<Button-1>", lambda _e: self._edit_dict_word())
        edit.bind("<Enter>", lambda _e: edit.configure(fg=ACCENT))
        edit.bind("<Leave>", lambda _e: edit.configure(fg=DIM))
        phonetic = (entry.get("phonetic") or "").strip()
        if phonetic:
            self._label(head, f"/{phonetic}/", fg=MUTED, font=(FONT_FAMILY, 9)).pack(
                side="left", padx=(8, 0)
            )
        if entry.get("audio_key") or entry.get("lang") or self._lang:
            speak = self._label(head, "🔊", fg=ACCENT, font=(FONT_FAMILY, 12))
            speak.pack(side="left", padx=(8, 0))
            speak.configure(cursor="hand2")
            speak.bind("<Button-1>", lambda _e: self._speak())
            speak.bind("<Enter>", lambda _e: speak.configure(fg=TEXT))
            speak.bind("<Leave>", lambda _e: speak.configure(fg=ACCENT))
        finder = self.cb.get("find_word")
        saved = finder(entry.get("lang") or self._lang or "", self._dict_word) if finder else None
        star = self._label(
            head, "★" if saved else "☆",
            fg="#f5c542" if saved else ACCENT, font=(FONT_FAMILY, 13),
        )
        star.pack(side="left", padx=(8, 0))
        star.configure(cursor="hand2")
        star.bind("<Button-1>", lambda _e, st=star: self._save_dict_word(st))
        star.bind("<Enter>", lambda _e: star.configure(fg=TEXT))
        star.bind("<Leave>", lambda _e, st=star: st.configure(fg=st.cget("fg")))
        original = self._label(head, "原版", fg=TEXT, font=(FONT_FAMILY, 8))
        original.pack(side="left", padx=(10, 0))
        original.configure(cursor="hand2")
        original.bind(
            "<Button-1>",
            lambda _e: self.cb.get("show_entry", lambda *_a: None)(
                self._dict_word, entry.get("lang") or ""
            ),
        )
        original.bind("<Enter>", lambda _e: original.configure(fg=ACCENT))
        original.bind("<Leave>", lambda _e: original.configure(fg=TEXT))
        source = entry.get("source") or ""
        if source:
            self._label(head, _short_source(source), fg=GREEN, font=(FONT_FAMILY, 8)).pack(
                side="left", padx=(8, 0)
            )

        alternatives = alternatives or []
        if len(alternatives) > 1:
            bar = tk.Frame(self.body, bg=BG)
            bar.pack(fill="x", pady=(0, 6))
            current = (entry.get("source") or "", entry.get("lang") or "")
            for hit in alternatives:
                active = (hit.get("source") or "", hit.get("lang") or "") == current
                label = tk.Label(
                    bar,
                    text=f"{self.cb.get('lang_label', lambda c: c)(hit.get('lang', ''))}·{_short_source(hit.get('source', ''))}",
                    bg=PANEL if active else BG,
                    fg=TEXT if active else DIM,
                    font=(FONT_FAMILY, 8),
                    padx=8,
                    pady=3,
                    cursor="hand2",
                )
                label.pack(side="left", padx=(0, 6))
                label.bind(
                    "<Button-1>",
                    lambda _e, h=hit: self.show_dictionary(
                        h["entry"], self._anchor, self._dict_word, alternatives
                    ),
                )

        morph = entry.get("morph") or {}
        if morph:
            lemma_text = morph.get("lemma") or ""
            lemma_label = self._label(
                self.body,
                f"原形 {lemma_text}（{morph.get('label', '')}）",
                fg=ACCENT,
                font=(FONT_FAMILY, 9),
            )
            lemma_label.pack(fill="x", pady=(0, 6))
            if lemma_text:
                lemma_label.configure(cursor="hand2")
                lemma_label.bind("<Button-1>", lambda _e, w=lemma_text: self._dict_jump(w))
            tabs = tk.Frame(self.body, bg=BG)
            tabs.pack(fill="x", pady=(0, 4))
            self._dict_tab_meaning = tk.Label(
                tabs, text="释义", bg=PANEL, fg=TEXT, font=(FONT_FAMILY, 9, "bold"),
                padx=12, pady=4, cursor="hand2",
            )
            self._dict_tab_meaning.pack(side="left")
            has_cases = any((t or {}).get("cases") for t in (morph.get("tables") or []))
            self._dict_tab_conj = tk.Label(
                tabs, text="变格" if has_cases else "时态", bg=BG, fg=DIM, font=(FONT_FAMILY, 9, "bold"),
                padx=12, pady=4, cursor="hand2",
            )
            self._dict_tab_conj.pack(side="left", padx=(6, 0))
            self._dict_tab_meaning.bind("<Button-1>", lambda _e: self._show_dict_tab("meaning"))
            self._dict_tab_conj.bind("<Button-1>", lambda _e: self._show_dict_tab("conj"))

        container = tk.Frame(self.body, bg=BG)
        container.pack(fill="x", pady=(4, 0))
        self._dict_meaning = tk.Frame(container, bg=BG)
        self._dict_meaning.pack(fill="x")
        self._dict_conj = tk.Frame(container, bg=BG)
        self._render_dict_senses(self._dict_meaning, entry)
        if morph:
            self._render_morph_tables(self._dict_conj, morph)

        actions = tk.Frame(self.body, bg=BG)
        actions.pack(fill="x", pady=(10, 4))
        self._dict_action(actions, "用 AI 译", self._translate_dict_word).pack(side="right")

        self.footer.configure(text="Enter 收藏 · 空格 发音 · Esc 关闭")
        self._reveal()

    def _show_dict_tab(self, name: str) -> None:
        if name == "conj":
            self._dict_meaning.pack_forget()
            self._dict_conj.pack(fill="x")
            self._dict_tab_conj.configure(bg=PANEL, fg=TEXT)
            self._dict_tab_meaning.configure(bg=BG, fg=DIM)
        else:
            self._dict_conj.pack_forget()
            self._dict_meaning.pack(fill="x")
            self._dict_tab_meaning.configure(bg=PANEL, fg=TEXT)
            self._dict_tab_conj.configure(bg=BG, fg=DIM)

    def _render_dict_senses(self, parent, entry: dict) -> None:
        matched = entry.get("matched") or ""
        if matched and matched.lower() != self._dict_word.lower():
            self._label(
                parent, f"按原形 {matched} 查到", fg=DIM, font=(FONT_FAMILY, 8)
            ).pack(fill="x", pady=(0, 6))
        senses = entry.get("senses") or []
        groups: dict[str, list[dict]] = {}
        order: list[str] = []
        for sense in senses:
            pos = (sense.get("pos") or "").strip()
            if pos not in groups:
                groups[pos] = []
                order.append(pos)
            groups[pos].append(sense)
        suggestions = entry.get("lemma_suggestions") or []
        if suggestions:
            hint = tk.Frame(parent, bg=BG)
            hint.pack(fill="x", pady=(2, 4))
            self._label(hint, "您是否要查找：", fg=MUTED, font=(FONT_FAMILY, 9)).pack(side="left")
            for idx, cand in enumerate(suggestions):
                if idx:
                    self._label(hint, " / ", fg=MUTED, font=(FONT_FAMILY, 9)).pack(side="left")
                link = self._label(
                    hint, cand, fg=ACCENT, font=(FONT_FAMILY, 9, "underline")
                )
                link.pack(side="left")
                link.configure(cursor="hand2")
                link.bind("<Button-1>", lambda _e, w=cand: self._dict_jump(w))
        for pos in order:
            if pos:
                self._label(
                    parent, pos, fg=ACCENT, font=(FONT_FAMILY, 9, "bold")
                ).pack(fill="x", pady=(6, 2))
            for index, sense in enumerate(groups[pos], start=1):
                row = tk.Frame(parent, bg=BG)
                row.pack(fill="x", pady=(0, 2))
                self._label(
                    row, f"{index}.", fg=ACCENT, font=(FONT_FAMILY, 9)
                ).pack(side="left", anchor="n", padx=(0, 4))
                definition = sense.get("definition_cn") or sense.get("definition") or ""
                self._label(
                    row, definition, fg=TEXT, font=(FONT_FAMILY, 10),
                    wraplength=self.width - 110,
                ).pack(side="left", anchor="w")
                example = (sense.get("example") or "").strip()
                if example:
                    self._label(
                        parent, example, fg=MUTED, font=(FONT_FAMILY, 9),
                        wraplength=self.width - 80,
                    ).pack(fill="x", padx=(26, 0), pady=(0, 2))
                example_cn = (sense.get("example_cn") or "").strip()
                if example_cn:
                    self._label(
                        parent, example_cn, fg=DIM, font=(FONT_FAMILY, 9),
                        wraplength=self.width - 80,
                    ).pack(fill="x", padx=(26, 0), pady=(0, 2))
        if not (entry.get("senses") or []):
            self._label(
                parent, "（词典里这个词没有释义）", fg=MUTED, font=(FONT_FAMILY, 9)
            ).pack(fill="x", pady=(0, 6))

    def _render_morph_tables(self, parent, morph: dict) -> None:
        target = (morph.get("form") or "").lower()
        tables = morph.get("tables") or []
        # 含查询形式的时态组排到最前面
        def has_target(group) -> bool:
            for row in group.get("rows") or []:
                if isinstance(row, dict):
                    if target and target in (
                        (row.get("sing") or "").lower(),
                        (row.get("plur") or "").lower(),
                    ):
                        return True
                elif isinstance(row, (tuple, list)) and len(row) == 2:
                    if (row[1] or "").lower() == target:
                        return True
            return False
        tables = sorted(tables, key=lambda g: 0 if has_target(g) else 1)
        for group in tables:
            card = tk.Frame(parent, bg=PANEL)
            card.pack(fill="x", pady=(0, 8))
            header = tk.Frame(card, bg=PANEL_ALT)
            header.pack(fill="x")
            self._label(
                header,
                f"{group.get('zh', '')}  {group.get('fr', '')}",
                fg=ACCENT,
                font=(FONT_FAMILY, 9, "bold"),
                bg=PANEL_ALT,
            ).pack(anchor="w", padx=10, pady=(6, 4))
            body = tk.Frame(card, bg=PANEL)
            body.pack(fill="x", padx=10, pady=(4, 8))
            if group.get("cases"):
                for row in group.get("rows") or []:
                    line = tk.Frame(body, bg=PANEL)
                    line.pack(fill="x")
                    self._label(
                        line, row.get("case", ""), fg=DIM, font=(FONT_FAMILY, 9), bg=PANEL
                    ).pack(side="left", pady=1)
                    for key, _fallback in (("sing", ""), ("plur", "")):
                        value = (row.get(key) or "").strip()
                        if not value:
                            continue
                        mine = value.lower() == target
                        value_label = self._label(
                            line,
                            value,
                            fg=ACCENT if mine else TEXT,
                            font=(FONT_FAMILY, 10, "bold" if mine else "normal"),
                            bg=PANEL,
                        )
                        value_label.pack(side="left", padx=(14, 0), pady=1)
                        value_label.configure(cursor="hand2")
                        value_label.bind(
                            "<Button-1>", lambda _e, w=value: self._dict_jump(w)
                        )
            else:
                for person, form in group.get("rows") or []:
                    line = tk.Frame(body, bg=PANEL)
                    line.pack(fill="x")
                    self._label(
                        line, person, fg=DIM, font=(FONT_FAMILY, 9), bg=PANEL
                    ).pack(side="left", pady=1)
                    mine = (form or "").lower() == target
                    form_label = self._label(
                        line,
                        form,
                        fg=ACCENT if mine else TEXT,
                        font=(FONT_FAMILY, 10, "bold" if mine else "normal"),
                        bg=PANEL,
                    )
                    form_label.pack(side="left", padx=(14, 0), pady=1)
                    if form and " " not in form.strip():
                        form_label.configure(cursor="hand2")
                        form_label.bind(
                            "<Button-1>", lambda _e, w=form: self._dict_jump(w)
                        )

    def show_dict_missing(self, word: str, anchor, configured: bool = True) -> None:
        """词典里没有：提示 + 给「用 AI 译」按钮。"""
        self._reset_to_translate(chat_button=False)
        self._mode = "dict"
        if anchor != self._anchor:
            self._user_moved = False
        self._anchor = anchor
        self._dict = None
        self._dict_word = word
        if anchor != self._anchor:
            self._user_moved = False
        self._anchor = anchor
        self.current = None
        self._clear()
        self._dict_editing = False
        self._dict_entry = None
        self.title.configure(text="查词")
        self._label(self.body, word, fg=TEXT, font=(FONT_FAMILY, 16, "bold")).pack(
            fill="x", pady=(2, 4)
        )
        message = (
            "本地词典里没有这个词。"
            if configured
            else "还没配置本地词典：设置 →「词典设置…」添加 MDX。"
        )
        self._label(
            self.body, message, fg=MUTED, font=(FONT_FAMILY, 10)
        ).pack(fill="x", pady=(0, 10))
        self._render_similar(self.body, word, "", anchor)
        actions = tk.Frame(self.body, bg=BG)
        actions.pack(fill="x", pady=(4, 4))
        self._dict_action(actions, "用 AI 译", self._translate_dict_word).pack(side="left")
        self.footer.configure(text="Esc 关闭")
        self._reveal()

    def _edit_dict_word(self) -> None:
        """把词头原地变成输入框，改完回车重新查。"""
        existing = getattr(self, "_dict_entry", None)
        if existing is not None:
            try:
                if existing.winfo_exists():
                    existing.focus_set()
                    return
            except tk.TclError:
                pass
            self._dict_entry = None
            self._dict_editing = False
        label = getattr(self, "_dict_word_label", None)
        if label is None:
            return
        head = label.master
        self._dict_editing = True
        siblings = [
            w for w in head.winfo_children()
            if w is not label and w.winfo_manager() == "pack"
        ]
        first = siblings[0] if siblings else None
        try:
            entry = tk.Entry(
                head,
                bg=PANEL,
                fg=TEXT,
                insertbackground=TEXT,
                relief="flat",
                font=(FONT_FAMILY, 15),
                width=max(8, min(24, len(self._dict_word) + 2)),
            )
            entry.insert(0, self._dict_word)
            if first is not None:
                entry.pack(side="left", padx=(0, 6), before=first)
            else:
                entry.pack(side="left", padx=(0, 6))
            self._dict_entry = entry
            label.pack_forget()
            entry.focus_set()
            entry.select_range(0, "end")
            entry.icursor("end")

            def restore() -> None:
                self._dict_editing = False
                self._dict_entry = None
                try:
                    entry.destroy()
                except tk.TclError:
                    pass
                try:
                    remaining = [
                        w for w in head.winfo_children()
                        if w is not label and w.winfo_manager() == "pack"
                    ]
                    if remaining:
                        label.pack(side="left", before=remaining[0])
                    else:
                        label.pack(side="left")
                except tk.TclError:
                    pass

            def commit(_event=None) -> None:
                text = entry.get().strip()
                restore()
                if text and text != self._dict_word:
                    self._dict_jump(text)

            def cancel(_event=None) -> None:
                restore()

            entry.bind("<Return>", commit)
            entry.bind("<Escape>", cancel)
            entry.bind("<FocusOut>", cancel)
        except Exception:
            self._dict_editing = False

    def _render_similar(self, parent, word: str, lang: str, anchor) -> None:
        """没查到词时列相近的词。"""
        cb = self.cb.get("fuzzy")
        if cb is None:
            return
        try:
            items = cb(word, lang)
        except Exception:
            items = []
        rows = [it for it in (items or []) if (it.get("word") or "").lower() != word.lower()]
        if not rows:
            return
        self._label(
            parent, "相近的词", fg=MUTED, font=(FONT_FAMILY, 8)
        ).pack(fill="x", pady=(4, 4))
        for item in rows[:8]:
            line = tk.Frame(parent, bg=BG)
            line.pack(fill="x", pady=1)
            name = item.get("word") or ""
            name_label = self._label(
                line, name, fg=TEXT, font=(FONT_FAMILY, 10, "bold")
            )
            name_label.pack(side="left")
            name_label.configure(cursor="hand2")
            name_label.bind("<Button-1>", lambda _e, w=name: self._dict_jump(w))
            pos = (item.get("pos") or "").strip()
            if pos:
                self._label(line, pos, fg=ACCENT, font=(FONT_FAMILY, 8)).pack(
                    side="left", padx=(8, 0)
                )
            gloss = (item.get("gloss") or "").strip()
            if gloss:
                self._label(line, gloss, fg=MUTED, font=(FONT_FAMILY, 9)).pack(
                    side="left", padx=(10, 0)
                )

    def _dict_jump(self, word: str) -> None:
        """点原形/变位形式：让宿主再查一次这个词。"""
        word = (word or "").strip()
        if not word:
            return
        cb = self.cb.get("dict_lookup")
        if cb is not None:
            cb(word)

    def _save_dict_word(self, star=None) -> None:
        entry = self._dict or {}
        senses = entry.get("senses") or []
        first = senses[0] if senses else {}
        lang = entry.get("lang") or self._lang or ""
        finder = self.cb.get("find_word")
        remover = self.cb.get("remove_word")
        existing = finder(lang, self._dict_word) if finder else None
        if existing and remover:
            remover(lang, self._dict_word)
            if star is not None:
                try:
                    star.configure(text="☆", fg=ACCENT)
                except tk.TclError:
                    pass
            self.footer.configure(text=f"已从生词本移除：{self._dict_word}")
            self.cb.get("toast", lambda _m: None)(f"已取消收藏 {self._dict_word}")
            return
        saver = self.cb.get("save_word")
        if not saver:
            return
        result = saver(
            {
                "lang": entry.get("lang") or self._lang or "",
                "word": self._dict_word,
                "lemma": entry.get("matched") or self._dict_word,
                "reading": entry.get("phonetic") or "",
                "pos": first.get("pos") or "",
                "meaning": first.get("definition_cn") or first.get("definition") or "",
                "sentence": "",
                "book": "",
                "dict_source": entry.get("source") or "",
                "dict_meaning": first.get("definition_cn") or first.get("definition") or "",
                "dict_example": first.get("example") or "",
                "dict_example_cn": first.get("example_cn") or "",
                "audio_key": entry.get("audio_key") or "",
            }
        )
        if star is not None:
            try:
                star.configure(text="★", fg="#f5c542")
            except tk.TclError:
                pass
        self.footer.configure(text=f"★ 已加入生词本：{self._dict_word}")
        self.cb.get("toast", lambda _m: None)(
            f"已收藏 {self._dict_word}（{result.get('total', 0)} 个）"
        )

    def _translate_dict_word(self) -> None:
        word = self._dict_word
        if not word:
            return
        self.hide()
        self.cb.get("manual_translate", lambda _t: None)(word)

    def _open_chat(self) -> None:
        if self._mode != "translate":
            return
        payload = self.current or self._pending_payload
        if not payload:
            return
        starter = self.cb.get("start_chat")
        if not starter:
            return
        try:
            conversation = starter(payload)
        except Exception as exc:  # noqa: BLE001
            self.cb.get("toast", lambda _m: None)(f"打开对话失败：{exc}")
            return
        if conversation:
            self.show_chat(conversation)

    def show_chat_pending(self, text: str, book: str, anchor) -> None:
        """不经过翻译，直接围绕一段文字开聊（悬浮按钮的「聊」走这里）。"""
        self.current = None
        self._anchor = anchor
        self._pending_payload = {
            "text": text,
            "translation": "",
            "book": book,
            "source_lang": "",
            "terms": [],
            "grammar": None,
            "meta": {},
        }
        self._reset_to_translate(chat_button=True)
        self._open_chat()

    def show_chat(self, conversation: dict, anchor=None, payload: dict | None = None) -> None:
        self._mode = "chat"
        self._conv_id = conversation.get("id")
        if anchor is not None:
            self._anchor = anchor
        book = conversation.get("book") or (self.current or {}).get("book", "")
        self.btn_chat.configure(text="← 返回译文")
        self.btn_chat.pack(side="right")
        if book:
            self.title.configure(text=f"与《{textutil.display(book, 18)}》聊聊")
        else:
            self.title.configure(text="阅读伙伴")
        self._clear()

        if payload is None:
            payload = self.current or self._pending_payload or {}
        source = payload.get("text") or ""
        if source:
            quote = tk.Frame(self.body, bg=PANEL_ALT)
            quote.pack(fill="x", pady=(0, 10))
            self._label(quote, "正在读", fg=DIM, font=(FONT_FAMILY, 8), bg=PANEL_ALT).pack(
                anchor="w", padx=10, pady=(6, 0)
            )
            self._label(
                quote,
                textutil.display(source, 160),
                fg=MUTED,
                font=(FONT_FAMILY, 9),
                bg=PANEL_ALT,
                wraplength=self.width - 54,
            ).pack(fill="x", padx=10, pady=(2, 8))

        self.messages_frame = tk.Frame(self.body, bg=BG)
        self.messages_frame.pack(fill="both", expand=True)
        for message in conversation.get("messages") or []:
            self._bubble(message.get("role", "assistant"), message.get("content", ""))

        self.footer.configure(text="Enter 发送 · Shift+Enter 换行 · Esc 返回译文")
        self._build_input_bar()
        self.input_bar.pack(
            side="bottom", fill="x", padx=14, pady=(4, 2), before=self.scrollbar
        )
        self._reveal()
        if self.chat_input is not None:
            self.chat_input.focus_set()
        self._scroll_bottom()

    def _build_input_bar(self) -> None:
        for child in self.input_bar.winfo_children():
            child.destroy()
        # 先放发送按钮，再放输入框，否则输入框会把按钮挤没
        send = tk.Label(
            self.input_bar,
            text="发送",
            bg=ACCENT,
            fg="#10131a",
            font=(FONT_FAMILY, 9),
            padx=12,
            pady=8,
            cursor="hand2",
        )
        send.pack(side="right", padx=(8, 0), fill="y")
        send.bind("<Button-1>", lambda _e: self._send_chat())
        self.chat_input = tk.Text(
            self.input_bar,
            height=3,
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
        self.chat_input.bind("<Return>", self._on_input_return)
        self.chat_input.bind("<Shift-Return>", lambda _e: None)

    def _on_input_return(self, _event=None) -> str:
        self._send_chat()
        return "break"

    def _bubble(self, role: str, content: str, typing: bool = False) -> tk.Frame:
        row = tk.Frame(self.messages_frame, bg=BG)
        row.pack(fill="x", pady=(0, 8))
        mine = role == "user"
        bg = PANEL_ALT if mine else PANEL
        holder = tk.Frame(row, bg=bg)
        holder.pack(side="right" if mine else "left")
        label = tk.Label(
            holder,
            text=content,
            bg=bg,
            fg=TEXT if not typing else MUTED,
            font=(FONT_FAMILY, 10),
            justify="left",
            anchor="w",
            wraplength=self.width - 90,
            padx=10,
            pady=7,
        )
        label.pack()
        if typing:
            self._typing = row
            self._typing_label = label
        # 新加的气泡也要能滚轮滚动
        self._bind_wheel(row)
        return row

    def _scroll_bottom(self) -> None:
        self.root.after(10, lambda: self.canvas.yview_moveto(1.0))

    def _send_chat(self) -> None:
        if self._mode != "chat" or self.chat_input is None:
            return
        text = self.chat_input.get("1.0", "end-1c").strip()
        if not text:
            return
        self.chat_input.delete("1.0", "end")
        self._bubble("user", text)
        self._typing = None
        self._bubble("assistant", "思考中…", typing=True)
        self._scroll_bottom()
        self.cb.get("ask_chat", lambda *_a: None)(self._conv_id, text)

    def _at_bottom(self) -> bool:
        try:
            return self.canvas.yview()[1] >= 0.98
        except Exception:
            return True

    def receive_chat_delta(self, conv_id, partial: str) -> None:
        if self._mode != "chat" or conv_id != self._conv_id:
            return
        self._chat_target = partial
        if self._chat_job is None:
            self._chat_shown = ""
            try:
                label = getattr(self, "_typing_label", None)
                if self._typing is not None and label is not None and label.winfo_exists():
                    label.configure(text="", fg=TEXT)
                else:
                    self._typing = self._bubble("assistant", "", typing=True)
                    self._typing_label.configure(fg=TEXT)
            except tk.TclError:
                return
            self._chat_tick()

    def _chat_tick(self) -> None:
        self._chat_job = None
        try:
            if not self.win.winfo_exists():
                return
        except tk.TclError:
            return
        pending = self._chat_target[len(self._chat_shown):]
        label = getattr(self, "_typing_label", None)
        if pending:
            try:
                speed = int(self.config.get("stream_speed", 60))
            except Exception:
                speed = 60
            speed = max(5, min(400, speed))
            step = max(1, int(speed * 0.033))
            if len(pending) > 240:
                step *= 3
            self._chat_shown += pending[:step]
            try:
                if label is not None and label.winfo_exists():
                    label.configure(text=self._chat_shown, fg=TEXT)
                self._scroll_bottom()
            except tk.TclError:
                return
            self._chat_job = self.win.after(33, self._chat_tick)
            return
        if self._chat_final:
            self._finish_chat()

    def _finish_chat(self) -> None:
        reply = self._chat_reply
        self._cancel_chat_stream()
        label = getattr(self, "_typing_label", None)
        try:
            if self._typing is not None and label is not None and label.winfo_exists():
                label.configure(text=reply, fg=TEXT)
                self._typing = None
                self._typing_label = None
            else:
                if self._typing is not None:
                    self._typing.destroy()
                    self._typing = None
                self._bubble("assistant", reply)
            self._scroll_bottom()
        except tk.TclError:
            pass

    def _cancel_chat_stream(self) -> None:
        job = self._chat_job
        self._chat_job = None
        if job:
            try:
                self.win.after_cancel(job)
            except tk.TclError:
                pass
        self._chat_target = ""
        self._chat_shown = ""
        self._chat_reply = ""
        self._chat_final = False

    def receive_chat(self, conv_id, reply: str) -> None:
        if self._mode != "chat" or conv_id != self._conv_id:
            return
        self._chat_reply = reply
        self._chat_target = reply
        self._chat_final = True
        if self._chat_job is None:
            if self._chat_shown:
                self._finish_chat()
            else:
                self._typing = self._bubble("assistant", reply, typing=True)
                self._typing_label.configure(fg=TEXT)
                self._finish_chat()

    def receive_chat_error(self, conv_id, message: str) -> None:
        if self._mode != "chat" or conv_id != self._conv_id:
            return
        stick = self._at_bottom()
        if self._typing is not None:
            self._typing.destroy()
            self._typing = None
        self._bubble("assistant", f"出错了：{message}")
        if stick:
            self._scroll_bottom()

    def back_to_translation(self) -> None:
        self.input_bar.pack_forget()
        if self.current:
            self.show_result(self.current, self._anchor)
        else:
            self.hide()

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
        self.footer.configure(text="Ctrl+Alt+S 打开设置 · Esc 关闭")
        self._reveal()

    def show_result(self, payload: dict, anchor: tuple[int, int]) -> None:
        # 正在聊天时翻译结果回来了：静默更新，不要打断对话
        if self._mode == "chat":
            self.current = payload
            self._pending_payload = payload
            return
        self.current = payload
        self._pending_payload = payload
        if anchor != self._anchor:
            self._user_moved = False
        self._anchor = anchor
        self._expanded = False
        self.saved = set()
        self._input_mode = False
        self._reset_to_translate(chat_button=True)
        self._lang = payload.get("source_lang") or "en"
        book = payload.get("book") or ""

        self.title.configure(text=self._title_text(book, self._lang, payload.get("meta")))
        self._clear()

        # 原文（可折叠）
        source = payload.get("text") or ""
        src_frame = tk.Frame(self.body, bg=BG)
        src_frame.pack(fill="x", pady=(0, 2))
        self._label(
            src_frame,
            source if self._expanded or len(source) <= 180 else source[:180] + " …",
            fg=MUTED,
            font=(FONT_FAMILY, 9),
            wraplength=self.width - 40,
        ).pack(fill="x")
        if len(source) > 180:
            toggle = self._label(
                src_frame, "展开原文" if not self._expanded else "收起", fg=DIM,
                font=(FONT_FAMILY, 8), cursor="hand2",
            )
            toggle.pack(anchor="w", pady=(2, 0))
            toggle.bind("<Button-1>", lambda _e: self._toggle_source())

        self._divider(9)

        # 译文
        translation = tk.Frame(self.body, bg=PANEL)
        translation.pack(fill="x")
        self._label(
            translation,
            payload.get("translation", ""),
            fg=TEXT,
            font=(FONT_FAMILY, 12),
            bg=PANEL,
            wraplength=self.width - 62,
        ).pack(fill="x", padx=14, pady=12)

        # 生词
        terms = payload.get("terms") or []
        if terms:
            self._divider(10)
            head = tk.Frame(self.body, bg=BG)
            head.pack(fill="x")
            self._label(head, "生词", fg=DIM, font=(FONT_FAMILY, 8)).pack(side="left")
            self._label(
                head,
                "数字键收藏 · 点击也可",
                fg=DIM,
                font=(FONT_FAMILY, 8),
            ).pack(side="right")
            for idx, term in enumerate(terms[:9]):
                self._term_row(idx, term, source, book)

        # 语法
        grammar = payload.get("grammar")
        if grammar:
            self._divider(10)
            row = tk.Frame(self.body, bg=PANEL_ALT)
            row.pack(fill="x")
            self._label(
                row,
                "语法",
                fg=ACCENT,
                font=(FONT_FAMILY, 8, "bold"),
                bg=PANEL_ALT,
            ).pack(anchor="w", padx=12, pady=(8, 0))
            self._label(
                row,
                grammar,
                fg=MUTED,
                font=(FONT_FAMILY, 9),
                bg=PANEL_ALT,
                wraplength=self.width - 56,
            ).pack(anchor="w", padx=12, pady=(2, 8))

        # 术语命中
        hits = payload.get("glossary_hits") or []
        if hits:
            self._divider(8)
            text = " · ".join(f"{h['term']} → {h['rendering']}" for h in hits)
            self._label(self.body, f"术语表命中：{text}", fg=DIM, font=(FONT_FAMILY, 8)).pack(
                fill="x"
            )

        meta = payload.get("meta") or {}
        cached = "缓存" if meta.get("cached") else f"{meta.get('elapsed_ms', 0)} ms"
        self.footer.configure(
            text=f"1-9 收藏 · Ctrl+Enter 同步 Anki · 空格朗读 · Enter 复制 · {cached}"
        )
        self._reveal()

    def _title_text(self, book: str, src: str, meta: dict | None) -> str:
        lang_label = self.cb.get("lang_label", lambda c: c)(src) if src else ""
        parts = [f"{lang_label} → 中文"] if lang_label else ["翻译"]
        if book:
            parts.append(textutil.display(book, 28))
        if meta and meta.get("cached"):
            parts.append("缓存")
        return "   ·   ".join(parts)

    def _toggle_source(self) -> None:
        if not self.current:
            return
        saved = set(self.saved)
        self._expanded = not self._expanded
        self.show_result(self.current, self._anchor)
        self.saved = saved
        for idx, term in enumerate(self.current.get("terms") or []):
            if (term.get("lemma") or term.get("word")) in saved:
                self._mark_saved(idx)

    def _term_row(self, idx: int, term: dict, sentence: str, book: str) -> None:
        row = tk.Frame(self.body, bg=PANEL)
        row.pack(fill="x", pady=(6, 0))

        badge = tk.Label(
            row,
            text=str(idx + 1),
            bg=PANEL_ALT,
            fg=MUTED,
            font=(FONT_FAMILY, 8),
            width=2,
        )
        badge.pack(side="left", padx=(10, 8), pady=8)

        text_frame = tk.Frame(row, bg=PANEL)
        text_frame.pack(side="left", fill="x", expand=True, pady=6)

        top = tk.Frame(text_frame, bg=PANEL)
        top.pack(fill="x")
        word = tk.Label(
            top,
            text=term.get("word", ""),
            bg=PANEL,
            fg=TEXT,
            font=(FONT_FAMILY, 11, "bold"),
        )
        word.pack(side="left")
        if term.get("reading"):
            tk.Label(
                top,
                text="  " + term["reading"],
                bg=PANEL,
                fg=DIM,
                font=(FONT_FAMILY, 8),
            ).pack(side="left")
        if term.get("pos"):
            tk.Label(
                top,
                text="  " + term["pos"],
                bg=PANEL,
                fg=ACCENT,
                font=(FONT_FAMILY, 8),
            ).pack(side="left")

        dict_info = term.get("dict") or {}
        if dict_info.get("source"):
            tk.Label(
                top,
                text="  " + _short_source(dict_info["source"]),
                bg=PANEL,
                fg=GREEN,
                font=(FONT_FAMILY, 7),
            ).pack(side="left")

        dict_def = (dict_info.get("definition") or "").strip()
        llm_def = (term.get("meaning") or "").strip()
        primary = dict_def or llm_def
        meaning = tk.Label(
            text_frame,
            text=primary,
            bg=PANEL,
            fg=TEXT,
            font=(FONT_FAMILY, 9),
            justify="left",
            anchor="w",
            wraplength=self.width - 110,
        )
        meaning.pack(fill="x", pady=(2, 0))
        if dict_def and llm_def and llm_def != dict_def:
            tk.Label(
                text_frame,
                text=f"文中义：{llm_def}",
                bg=PANEL,
                fg=ACCENT,
                font=(FONT_FAMILY, 8),
                justify="left",
                anchor="w",
                wraplength=self.width - 110,
            ).pack(fill="x", pady=(1, 0))
        note_text = term.get("note") or (dict_info.get("example") or "")
        if note_text:
            tk.Label(
                text_frame,
                text=note_text,
                bg=PANEL,
                fg=DIM,
                font=(FONT_FAMILY, 8),
                justify="left",
                anchor="w",
                wraplength=self.width - 110,
            ).pack(fill="x", pady=(1, 0))

        star = tk.Label(
            row,
            text="☆",
            bg=PANEL,
            fg=DIM,
            font=(FONT_FAMILY, 12),
            cursor="hand2",
            padx=10,
        )
        star.pack(side="right")

        def save(_event=None):
            self._save_word(idx)

        for widget in (row, badge, text_frame, top, word, meaning, star):
            widget.bind("<Button-1>", save)
        for widget in (row, badge, text_frame, top, word, meaning, star):
            widget.bind("<Enter>", lambda _e, r=row, s=star: (r.configure(bg=PANEL_ALT), s.configure(bg=PANEL_ALT)))
            widget.bind("<Leave>", lambda _e, r=row, s=star: (r.configure(bg=PANEL), s.configure(bg=PANEL)))

        self._bind_wheel(row)

    # ------------------------------------------------------------------ 动作
    def _save_word(self, idx: int) -> None:
        if self._input_mode or self._mode == "chat" or not self.current:
            return
        terms = self.current.get("terms") or []
        if idx >= len(terms):
            return
        term = terms[idx]
        key = term.get("lemma") or term.get("word")
        if key in self.saved:
            self.cb.get("toast", lambda _m: None)("已经收藏过了")
            return
        result = self.cb.get("save_word")(
            {
                "lang": self._lang,
                "word": term.get("word", ""),
                "lemma": term.get("lemma", ""),
                "reading": term.get("reading", ""),
                "pos": term.get("pos", ""),
                "meaning": term.get("meaning", ""),
                "sentence": self.current.get("text", ""),
                "book": self.current.get("book", ""),
                "dict_source": (term.get("dict") or {}).get("source", ""),
                "dict_meaning": (term.get("dict") or {}).get("definition", ""),
                "dict_example": (term.get("dict") or {}).get("example", ""),
                "dict_example_cn": (term.get("dict") or {}).get("example_cn", ""),
                "audio_key": (term.get("dict") or {}).get("audio_key", ""),
            }
        )
        self.saved.add(key)
        self.cb.get("toast", lambda _m: None)(
            f"已收藏 {term.get('word', '')}（{result.get('total', 0)} 个）"
        )
        # 行内的星星换成实心
        self._mark_saved(idx)

    def _mark_saved(self, idx: int) -> None:
        rows = [w for w in self.body.winfo_children() if isinstance(w, tk.Frame)]
        counter = -1
        for frame in rows:
            for child in frame.winfo_children():
                if isinstance(child, tk.Label) and child.cget("text") == "☆":
                    counter += 1
                    if counter == idx:
                        child.configure(text="★", fg=GREEN)

    def _toggle(self, idx: int) -> None:
        self._save_word(idx)

    def _make_toggle(self, idx: int):
        return lambda _e: self._save_word(idx)

    def _copy(self) -> None:
        if self._input_mode:
            self._manual()
            return
        if self._mode == "chat" or not self.current:
            return
        self.win.clipboard_clear()
        self.win.clipboard_append(self.current.get("translation", ""))
        self.cb.get("toast", lambda _m: None)("译文已复制")

    def _push_anki(self) -> None:
        if self._input_mode:
            self._manual()
            return
        if self._mode == "chat":
            return
        self.cb.get("push_anki", lambda: None)(self._lang)

    def _speak(self) -> None:
        if self._input_mode or self._mode == "chat" or not self.current:
            if self._mode == "dict" and self._dict_word:
                entry = self._dict or {}
                self.cb.get("speak", lambda *_a: None)(
                    self._dict_word,
                    entry.get("lang") or self._lang,
                    entry.get("audio_key") or "",
                )
            return
        text = self.current.get("text", "")
        self.cb.get("speak", lambda *_a: None)(text, self._lang)

    def _lock_term(self) -> None:
        if not self.current:
            return
        terms = self.current.get("terms") or []
        if not terms:
            return
        self.cb.get("lock_term", lambda *_a: None)(
            self.current.get("book", ""), terms[0].get("word", ""), self._lang
        )

    # ------------------------------------------------------------------ 显示
    def _reveal(self) -> None:
        self._bind_wheel(self.shell)
        self.win.deiconify()
        self.win.update_idletasks()
        self._fit_height()
        if not getattr(self, "_user_moved", False):
            self._place()
        self._visible = True
        try:
            self.win.focus_force()
        except tk.TclError:
            pass

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
        self.win.withdraw()
        self._visible = False
        tts = self.cb.get("stop_speak")
        if tts:
            tts()

    @property
    def visible(self) -> bool:
        return self._visible


def _short_source(name: str) -> str:
    """把词典名缩成卡片/浮窗上的小标签。"""
    text = (name or "").lower()
    for key, label in (
        ("朗文", "朗文"),
        ("longman", "朗文"),
        ("牛津", "牛津"),
        ("oxford", "牛津"),
        ("collins", "Collins"),
        ("vocabulary", "Vocabulary"),
        ("larousse", "Larousse"),
        ("robert", "Robert"),
    ):
        if key in text:
            return label
    return (name or "")[:8]
