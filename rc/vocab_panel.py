"""生词本页签：组合词本列表、单词表与操作。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .i18n import tr
from .theme import SCROLL_THUMB, SCROLL_TRACK
from .popup import ACCENT, BG, BORDER, DIM, FONT_FAMILY, MUTED, PANEL, PANEL_ALT, TEXT
from .vocab_actions import VocabActionsMixin
from .vocab_books import VocabBooksMixin
from .vocab_table import VocabTableMixin
from .theme import ON_ACCENT


class VocabPanel(VocabTableMixin, VocabBooksMixin, VocabActionsMixin):
    _COLS = ("word", "reading", "meaning", "book", "time", "synced")
    _COL_LABELS = {
        "word": "单词",
        "reading": "音标",
        "meaning": "释义",
        "book": "来源",
        "time": "时间",
        "synced": "同步",
    }
    _COL_DEFAULTS = {
        "word": 95,
        "reading": 72,
        "meaning": 150,
        "book": 55,
        "time": 78,
        "synced": 48,
    }
    _COL_MINS = {
        "word": 52,
        "reading": 38,
        "meaning": 68,
        "book": 34,
        "time": 68,
        "synced": 44,
    }

    def __init__(
        self,
        parent: tk.Frame,
        service,
        config,
        on_change=None,
        on_word_open=None,
    ) -> None:
        self.parent = parent
        self.service = service
        self.config = config
        self.on_change = on_change
        self.on_word_open = on_word_open
        self.books: list[dict] = []
        self.words: list[dict] = []
        self.book_id: int | None = None
        self._sync_result = None
        self._sync_ready = False
        self._dragging = False
        self._drag_left = 0
        self._drag_right = 1
        self._drag_start_x = 0
        self._drag_start: list[int] = []
        defaults = [self._COL_DEFAULTS[c] for c in self._COLS]
        mins = [self._COL_MINS[c] for c in self._COLS]
        self._col_widths = list(defaults)
        self._col_ratios = [w / sum(defaults) for w in defaults]
        saved = config.get("vocab_col_ratios")
        if isinstance(saved, list) and len(saved) == len(self._COLS):
            try:
                ratios = [float(v) for v in saved]
            except (TypeError, ValueError):
                ratios = []
            if ratios and sum(ratios) > 0 and all(v >= 0 for v in ratios):
                total = sum(ratios)
                self._col_ratios = [v / total for v in ratios]
        else:
            # 兼容上一版保存的绝对宽度，折算成比例
            old = config.get("vocab_col_widths")
            if isinstance(old, list) and len(old) == len(self._COLS):
                try:
                    values = [int(v) for v in old]
                except (TypeError, ValueError):
                    values = []
                if values and all(v >= m for v, m in zip(values, mins, strict=False)):
                    total = sum(values)
                    self._col_ratios = [v / total for v in values]
        self._sort_key = str(config.get("vocab_sort_key") or "time")
        if self._sort_key not in self._COL_LABELS:
            self._sort_key = "time"
        # 时间列默认新→旧，其余列默认正序
        self._sort_desc = bool(config.get("vocab_sort_desc", self._sort_key == "time"))
        self._build()
        self.refresh()

    def _build(self) -> None:
        actions = tk.Frame(self.parent, bg=BG)
        actions.pack(side="bottom", fill="x", padx=2, pady=(6, 0))
        # 同步按钮单独一行靠右：窄窗口下也不会被左侧按钮挤出去
        sync_row = tk.Frame(actions, bg=BG)
        sync_row.pack(fill="x")
        self._small_button(sync_row, "同步 Anki", self.sync_book, primary=True).pack(
            side="left"
        )
        tools_row = tk.Frame(actions, bg=BG)
        tools_row.pack(fill="x", pady=(4, 0))
        self._small_button(tools_row, "删除所选", self.delete_selected, danger=True).pack(side="left")
        self._small_button(tools_row, "移动到…", self.move_selected).pack(side="left", padx=(6, 0))
        self._small_button(tools_row, "导出 CSV", self.export_book).pack(side="left", padx=(6, 0))
        self._small_button(tools_row, "Anki 设置…", self.open_anki_settings).pack(
            side="left", padx=(6, 0)
        )



        outer = tk.Frame(self.parent, bg=BG)
        outer.pack(fill="both", expand=True, padx=2, pady=(4, 0))

        head = tk.Frame(outer, bg=BG)
        head.pack(fill="x")
        tk.Label(
            head, text="生词本", bg=BG, fg=TEXT, font=(FONT_FAMILY, 13, "bold")
        ).pack(side="left")
        self.book_title = tk.Label(
            head, text="", bg=BG, fg=MUTED, font=(FONT_FAMILY, 9)
        )
        self.book_title.pack(side="left", padx=(10, 0))
        self.status = tk.Label(head, text="", bg=BG, fg=MUTED, font=(FONT_FAMILY, 8))
        self.status.pack(side="right")

        body = tk.Frame(outer, bg=BG)
        body.pack(fill="both", expand=True, pady=(8, 0))

        # 左侧词本
        left = tk.Frame(body, bg=PANEL, width=190)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        tk.Label(
            left, text="词本", bg=PANEL, fg=DIM, font=(FONT_FAMILY, 8), anchor="w"
        ).pack(fill="x", padx=8, pady=(6, 2))
        self.book_tree = ttk.Treeview(left, show="tree", selectmode="browse")
        self.book_tree.pack(fill="both", expand=True, padx=4, pady=2)
        self.book_tree.bind("<<TreeviewSelect>>", lambda _e: self._on_book_selected())
        btns = tk.Frame(left, bg=PANEL)
        btns.pack(fill="x", padx=6, pady=6)
        self._small_button(btns, "新建", self.new_book).pack(side="left")
        self._small_button(btns, "改名", self.rename_book).pack(side="left", padx=(4, 0))
        self._small_button(btns, "删除", self.delete_book).pack(side="left", padx=(4, 0))

        # 右侧单词
        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(10, 0))
        bar = tk.Frame(right, bg=BG)
        bar.pack(fill="x")
        tk.Label(bar, text="搜索单词/释义", bg=BG, fg=DIM, font=(FONT_FAMILY, 8)).pack(side="left")
        self.search_var = tk.StringVar()
        entry = tk.Entry(
            bar, textvariable=self.search_var, bg=PANEL, fg=TEXT,
            insertbackground=TEXT, relief="flat", font=(FONT_FAMILY, 9), width=24,
        )
        entry.pack(side="left", padx=(6, 6), ipady=3)
        entry.bind("<KeyRelease>", lambda _e: self._debounced_load())
        entry.bind("<Escape>", lambda _e: (self.search_var.set(""), self.load_words()))
        self._small_button(bar, "刷新", self.load_words).pack(side="left")
        self.count_label = tk.Label(bar, text="", bg=BG, fg=DIM, font=(FONT_FAMILY, 8))
        self.count_label.pack(side="right")

        # 先占住底部按钮区，再让表格撑满剩余空间
        self.word_tree = ttk.Treeview(
            right, columns=self._COLS, show="headings", selectmode="extended"
        )
        for key in self._COLS:
            self.word_tree.heading(
                key, text=tr(self._COL_LABELS[key]), command=lambda c=key: self._sort_by(c)
            )
            self.word_tree.column(
                key,
                width=self._COL_DEFAULTS[key],
                minwidth=self._COL_MINS[key],
                anchor="w",
                stretch=False,
            )
        scroll = tk.Scrollbar(
            right, orient="vertical", command=self.word_tree.yview,
            bg=SCROLL_THUMB, troughcolor=SCROLL_TRACK, activebackground=ACCENT,
        )
        xscroll = tk.Scrollbar(
            right, orient="horizontal", command=self.word_tree.xview,
            bg=SCROLL_THUMB, troughcolor=SCROLL_TRACK, activebackground=ACCENT,
        )
        self.word_tree.configure(yscrollcommand=scroll.set, xscrollcommand=xscroll.set)
        xscroll.pack(side="bottom", fill="x", pady=(2, 0))
        scroll.pack(side="right", fill="y", pady=(6, 0))
        self.word_tree.pack(side="left", fill="both", expand=True, pady=(6, 0))
        self.word_tree.bind("<Delete>", lambda _e: self.delete_selected())
        self.word_tree.bind("<Double-1>", self._open_word)
        self.word_tree.bind("<Configure>", self._on_tree_configure)
        self.word_tree.bind("<Button-1>", self._on_tree_press)
        self.word_tree.bind("<B1-Motion>", self._on_tree_drag)
        self.word_tree.bind("<ButtonRelease-1>", self._on_tree_release)
        self.word_tree.bind("<Motion>", self._on_tree_motion)

        self._style_trees()

    def _style_trees(self) -> None:
        style = ttk.Style(self.parent)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "TScrollbar",
            background=SCROLL_THUMB,
            troughcolor=SCROLL_TRACK,
            bordercolor=BORDER,
            arrowcolor=MUTED,
        )
        style.map("TScrollbar", background=[("active", ACCENT)])
        for _bar in ("Vertical.TScrollbar", "Horizontal.TScrollbar"):
            style.configure(
                _bar,
                background=SCROLL_THUMB,
                troughcolor=SCROLL_TRACK,
                bordercolor=BORDER,
                arrowcolor=MUTED,
            )
            style.map(_bar, background=[("active", ACCENT)])
        style.configure(
            "Vocab.Treeview",
            background=PANEL,
            fieldbackground=PANEL,
            foreground=TEXT,
            rowheight=24,
            borderwidth=0,
            font=(FONT_FAMILY, 9),
        )
        style.configure(
            "Vocab.Treeview.Heading",
            background=PANEL_ALT,
            foreground=TEXT,
            relief="flat",
            font=(FONT_FAMILY, 8),
        )
        style.map(
            "Vocab.Treeview",
            background=[("selected", ACCENT)],
            foreground=[("selected", ON_ACCENT)],
        )
        self.word_tree.configure(style="Vocab.Treeview")
        self.book_tree.configure(style="Vocab.Treeview")

    def _small_button(self, parent, text, command, primary=False, danger=False):
        bg = ACCENT if primary else (BORDER if danger else PANEL)
        fg = ON_ACCENT if primary else (TEXT if not danger else "#ffb3b3")
        label = tk.Label(
            parent, text=text, bg=bg, fg=fg, font=(FONT_FAMILY, 8),
            padx=10, pady=4, cursor="hand2",
        )
        label.bind("<Button-1>", lambda _e: command())
        return label

    def _debounced_load(self) -> None:
        job = getattr(self, "_search_job", None)
        if job:
            try:
                self.parent.after_cancel(job)
            except Exception:
                pass
        self._search_job = self.parent.after(200, self.load_words)
