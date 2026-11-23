"""Recent lookup history window (separate from the vocabulary list)."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from .i18n import lang_display_name, tr
from .theme import ACCENT, BG, FONT_FAMILY, MUTED, PANEL, PANEL_ALT, TEXT


def lookup_time(value: str) -> str:
    """Compact, locale-neutral timestamp for the history lists."""
    text = (value or "").strip()
    if len(text) >= 16:
        return text[5:16]
    return text


class LookupHistoryWindow:
    def __init__(self, root: tk.Tk, service, on_open) -> None:
        self.service = service
        self.on_open = on_open
        self.rows: dict[str, dict] = {}
        self.lang_codes: dict[str, str] = {tr("全部语言"): ""}
        self.win = tk.Toplevel(root)
        self.win.title("查词历史")
        self.win.geometry("740x640")
        self.win.configure(bg=BG)
        self.win.transient(root)
        self.win.bind("<Escape>", lambda _e: self.close())

        head = tk.Frame(self.win, bg=BG)
        head.pack(fill="x", padx=16, pady=(14, 6))
        tk.Label(
            head, text="查词历史", bg=BG, fg=TEXT,
            font=(FONT_FAMILY, 14, "bold"), anchor="w",
        ).pack(side="left")
        tk.Label(
            head, text="最近查过的词，点击可重新查词", bg=BG, fg=MUTED,
            font=(FONT_FAMILY, 8), anchor="w",
        ).pack(side="left", padx=(12, 0), pady=(4, 0))

        languages = self.service.languages()
        lang_values = [tr("全部语言")]
        for code, info in languages.items():
            label = lang_display_name(info, code)
            self.lang_codes[label] = code
            lang_values.append(label)
        self.lang_var = tk.StringVar(value=tr("全部语言"))
        self.book_var = tk.StringVar(value=tr("全部书籍"))
        self._book_values = [tr("全部书籍")]
        self._book_codes = {tr("全部书籍"): ""}

        filters = tk.Frame(self.win, bg=BG)
        filters.pack(fill="x", padx=16, pady=(0, 6))
        tk.Label(
            filters, text=tr("语言"), bg=BG, fg=MUTED,
            font=(FONT_FAMILY, 8),
        ).pack(side="left")
        lang_box = ttk.Combobox(
            filters, textvariable=self.lang_var, values=lang_values,
            state="readonly", width=12, font=(FONT_FAMILY, 8),
        )
        lang_box.pack(side="left", padx=(5, 12))
        lang_box.bind("<<ComboboxSelected>>", lambda _e: self.refresh())
        tk.Label(
            filters, text=tr("书籍"), bg=BG, fg=MUTED,
            font=(FONT_FAMILY, 8),
        ).pack(side="left")
        self.book_box = ttk.Combobox(
            filters, textvariable=self.book_var, values=self._book_values,
            state="readonly", width=22, font=(FONT_FAMILY, 8),
        )
        self.book_box.pack(side="left", padx=(5, 12))
        self.book_box.bind("<<ComboboxSelected>>", lambda _e: self.refresh())

        self.limit_var = tk.StringVar(value=str(self.service.lookup_history_limit()))
        tk.Label(
            filters, text=tr("条"), bg=BG, fg=MUTED,
            font=(FONT_FAMILY, 8),
        ).pack(side="right", padx=(5, 0))
        limit_box = ttk.Spinbox(
            filters, from_=50, to=5000, increment=50, width=6,
            textvariable=self.limit_var, font=(FONT_FAMILY, 8),
            command=self._apply_limit,
        )
        limit_box.pack(side="right", padx=(5, 0))
        limit_box.bind("<Return>", lambda _e: self._apply_limit())
        limit_box.bind("<FocusOut>", lambda _e: self._apply_limit())
        tk.Label(
            filters, text=tr("保留"), bg=BG, fg=MUTED,
            font=(FONT_FAMILY, 8),
        ).pack(side="right", padx=(5, 0))

        self.stats_label = tk.Label(
            self.win, text="", bg=BG, fg=MUTED, font=(FONT_FAMILY, 8), anchor="w"
        )
        self.stats_label.pack(fill="x", padx=16, pady=(0, 6))

        body = tk.Frame(self.win, bg=BG)
        body.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        style = ttk.Style(self.win)
        style.configure(
            "Lookup.Treeview",
            background=PANEL,
            fieldbackground=PANEL,
            foreground=TEXT,
            rowheight=27,
            font=(FONT_FAMILY, 9),
            borderwidth=0,
        )
        style.configure(
            "Lookup.Treeview.Heading",
            background=PANEL_ALT,
            foreground=TEXT,
            relief="flat",
            font=(FONT_FAMILY, 9, "bold"),
        )
        style.map(
            "Lookup.Treeview",
            background=[("selected", ACCENT)],
            foreground=[("selected", BG)],
        )
        columns = ("star", "word", "source", "book", "time", "count")
        self.tree = ttk.Treeview(
            body,
            columns=columns,
            show="headings",
            selectmode="browse",
            style="Lookup.Treeview",
        )
        headings = {
            "star": "★",
            "word": "单词",
            "source": "来源",
            "book": "书籍",
            "time": "时间",
            "count": "次数",
        }
        widths = {"star": 36, "word": 145, "source": 180, "book": 110, "time": 85, "count": 45}
        for name in columns:
            self.tree.heading(name, text=headings[name])
            self.tree.column(
                name,
                width=widths[name],
                anchor="center" if name in ("star", "count") else "w",
                stretch=name in ("source", "book"),
            )
        scroll = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<Double-Button-1>", lambda _e: self._open_selected())
        self.tree.bind("<Button-1>", self._on_tree_click)
        self.tree.bind("<Return>", lambda _e: self._open_selected())
        self.tree.tag_configure("odd", background=PANEL_ALT)
        self.tree.tag_configure("even", background=PANEL)

        bar = tk.Frame(self.win, bg=BG)
        bar.pack(fill="x", padx=16, pady=(0, 14))
        self._button(bar, "打开", self._open_selected).pack(side="left")
        self._button(bar, "收藏", self._toggle_selected).pack(side="left", padx=(6, 0))
        self._button(bar, "删除", self._delete_selected).pack(side="left", padx=(6, 0))
        self._button(bar, "清空", self._clear).pack(side="left", padx=(6, 0))
        self._button(bar, "关闭", self.close).pack(side="right")

        self.refresh()

    def _button(self, parent, text: str, command):
        label = tk.Label(
            parent,
            text=tr(text),
            bg=PANEL,
            fg=TEXT,
            font=(FONT_FAMILY, 9),
            padx=12,
            pady=5,
            cursor="hand2",
        )
        label.bind("<Button-1>", lambda _e: command())
        return label

    def _apply_limit(self) -> None:
        try:
            value = int(self.limit_var.get())
        except ValueError:
            return
        self.service.set_lookup_history_limit(value)
        self.limit_var.set(str(self.service.lookup_history_limit()))
        self.refresh()

    def _saved(self, entry: dict) -> bool:
        try:
            return bool(
                self.service.find_vocab(
                    str(entry.get("lang") or ""),
                    str(entry.get("word") or entry.get("lemma") or ""),
                )
            )
        except Exception:
            return False

    def refresh(self) -> None:
        self._refresh_books()
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.rows.clear()
        lang = self.lang_codes.get(self.lang_var.get(), "")
        book = self._book_codes.get(self.book_var.get(), "")
        entries = self.service.lookup_history(500, lang, book)
        for index, entry in enumerate(entries):
            iid = str(entry["id"])
            self.rows[iid] = entry
            self.tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    "★" if self._saved(entry) else "☆",
                    entry.get("word") or entry.get("lemma") or "",
                    entry.get("source") or "",
                    entry.get("book") or "",
                    lookup_time(entry.get("last_used") or ""),
                    entry.get("count") or 1,
                ),
                tags=("odd" if index % 2 else "even",),
            )
        if entries:
            first = self.tree.get_children()[0]
            self.tree.selection_set(first)
            self.tree.focus(first)
        stats = self.service.lookup_stats()
        top = stats.get("top") or []
        top_text = ""
        if top:
            top_text = " · " + tr("最常查：") + "、".join(
                f"{item['word']} ({item['count']})" for item in top[:3]
            )
        self.stats_label.configure(
            text=tr("共 {} 次 · {} 个词").format(stats.get("total", 0), stats.get("words", 0))
            + top_text
        )

    def _refresh_books(self) -> None:
        books = [tr("全部书籍")] + self.service.lookup_books()
        self._book_values = books
        self._book_codes = {tr("全部书籍"): ""}
        self._book_codes.update({book: book for book in books[1:]})
        self.book_box.configure(values=books)
        if self.book_var.get() not in books:
            self.book_var.set(tr("全部书籍"))

    def _selected(self) -> dict | None:
        selection = self.tree.selection()
        if not selection:
            return None
        return self.rows.get(selection[0])

    def _on_tree_click(self, event) -> None:
        if self.tree.identify("region", event.x, event.y) != "cell":
            return
        if self.tree.identify_column(event.x) != "#1":
            return
        iid = self.tree.identify_row(event.y)
        entry = self.rows.get(iid)
        if entry:
            self._toggle_star(entry)

    def _toggle_selected(self) -> None:
        entry = self._selected()
        if entry:
            self._toggle_star(entry)

    def _toggle_star(self, entry: dict) -> None:
        lang = str(entry.get("lang") or "")
        word = str(entry.get("word") or entry.get("lemma") or "")
        if not word:
            return
        try:
            if self._saved(entry):
                self.service.remove_vocab(lang, word)
            else:
                preview = str(entry.get("preview") or "")
                self.service.add_vocab(
                    lang=lang or "??",
                    word=word,
                    lemma=str(entry.get("lemma") or word),
                    meaning=preview,
                    book=str(entry.get("book") or ""),
                    dict_source=str(entry.get("source") or ""),
                    dict_meaning=preview,
                    dict_id=str(entry.get("dict_id") or ""),
                )
        except Exception as exc:
            messagebox.showerror(tr("收藏失败"), str(exc))
            return
        self.refresh()

    def _open_selected(self) -> None:
        entry = self._selected()
        if not entry:
            return
        word = entry.get("word") or entry.get("lemma") or ""
        if word:
            self.on_open(word, entry)

    def _delete_selected(self) -> None:
        entry = self._selected()
        if not entry:
            return
        self.service.remove_lookup(int(entry["id"]))
        self.refresh()

    def _clear(self) -> None:
        if not messagebox.askyesno(tr("清空查词历史"), tr("确定清空全部查词历史吗？")):
            return
        self.service.clear_lookup_history()
        self.refresh()

    def close(self) -> None:
        try:
            self.win.destroy()
        except tk.TclError:
            pass

    def alive(self) -> bool:
        try:
            return bool(self.win.winfo_exists())
        except tk.TclError:
            return False
