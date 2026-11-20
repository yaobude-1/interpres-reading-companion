"""生词本页签：按语言分组的词本 + 单词表 + 移动/导出/同步。"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, ttk

from .i18n import tr
from .popup import ACCENT, BG, BORDER, DIM, FONT_FAMILY, GREEN, MUTED, PANEL, PANEL_ALT, TEXT


class VocabPanel:
    def __init__(self, parent: tk.Frame, service, config, on_change=None) -> None:
        self.parent = parent
        self.service = service
        self.config = config
        self.on_change = on_change
        self.books: list[dict] = []
        self.words: list[dict] = []
        self.book_id: int | None = None
        self._sync_result = None
        self._sync_ready = False
        self._build()
        self.refresh()

    # ------------------------------------------------------------------ 构建
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
        tk.Label(bar, text="搜索", bg=BG, fg=DIM, font=(FONT_FAMILY, 8)).pack(side="left")
        self.search_var = tk.StringVar()
        entry = tk.Entry(
            bar, textvariable=self.search_var, bg=PANEL, fg=TEXT,
            insertbackground=TEXT, relief="flat", font=(FONT_FAMILY, 9), width=24,
        )
        entry.pack(side="left", padx=(6, 6), ipady=3)
        entry.bind("<KeyRelease>", lambda _e: self._debounced_load())
        self._small_button(bar, "刷新", self.load_words).pack(side="left")
        self.count_label = tk.Label(bar, text="", bg=BG, fg=DIM, font=(FONT_FAMILY, 8))
        self.count_label.pack(side="right")

        # 先占住底部按钮区，再让表格撑满剩余空间
        cols = ("word", "reading", "meaning", "book", "time", "synced")
        self.word_tree = ttk.Treeview(right, columns=cols, show="headings", selectmode="extended")
        for key, label, width in (
            ("word", "单词", 85),
            ("reading", "音标", 60),
            ("meaning", "释义", 110),
            ("book", "来源", 65),
            ("time", "添加时间", 65),
            ("synced", "同步", 40),
        ):
            self.word_tree.heading(key, text=tr(label))
            self.word_tree.column(key, width=width, anchor="w", stretch=(key == "meaning"))
        scroll = tk.Scrollbar(right, orient="vertical", command=self.word_tree.yview)
        xscroll = tk.Scrollbar(right, orient="horizontal", command=self.word_tree.xview)
        self.word_tree.configure(yscrollcommand=scroll.set, xscrollcommand=xscroll.set)
        xscroll.pack(side="bottom", fill="x", pady=(2, 0))
        scroll.pack(side="right", fill="y", pady=(6, 0))
        self.word_tree.pack(side="left", fill="both", expand=True, pady=(6, 0))
        self.word_tree.bind("<Delete>", lambda _e: self.delete_selected())

        self._style_trees()

    def _style_trees(self) -> None:
        style = ttk.Style(self.parent)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
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
            foreground=[("selected", "#10131a")],
        )
        self.word_tree.configure(style="Vocab.Treeview")
        self.book_tree.configure(style="Vocab.Treeview")

    def _small_button(self, parent, text, command, primary=False, danger=False):
        bg = ACCENT if primary else (BORDER if danger else PANEL)
        fg = "#10131a" if primary else (TEXT if not danger else "#ffb3b3")
        label = tk.Label(
            parent, text=text, bg=bg, fg=fg, font=(FONT_FAMILY, 8),
            padx=10, pady=4, cursor="hand2",
        )
        label.bind("<Button-1>", lambda _e: command())
        return label

    # ------------------------------------------------------------------ 数据
    def refresh(self) -> None:
        self.books = self.service.wordbooks()
        self._fill_books()
        if self.books:
            first = next((b for b in self.books if b["is_default"]), self.books[0])
            target = self.book_id or first["id"]
            if not any(b["id"] == target for b in self.books):
                target = first["id"]
            self._select_book(target)

    def _fill_books(self) -> None:
        self.book_tree.delete(*self.book_tree.get_children())
        groups: dict[str, list[dict]] = {}
        for book in self.books:
            groups.setdefault(book.get("lang") or "??", []).append(book)
        for lang, books in sorted(groups.items(), key=lambda kv: kv[0]):
            label = self.service.lang_label(lang) if hasattr(self.service, "lang_label") else lang
            parent = self.book_tree.insert(
                "", "end", iid=f"lang:{lang}", text=f"{label} ({sum(b['count'] for b in books)})",
                open=True,
            )
            for book in books:
                suffix = f" · {tr('默认')}" if book.get("is_default") else ""
                self.book_tree.insert(
                    parent, "end", iid=str(book["id"]),
                    text=f"{book['name']}{suffix} ({book['count']})",
                )

    def _select_book(self, book_id: int) -> None:
        self.book_tree.selection_set(str(book_id))
        self.book_tree.see(str(book_id))
        self.book_id = int(book_id)
        self.load_words()

    def _on_book_selected(self) -> None:
        selection = self.book_tree.selection()
        if not selection:
            return
        iid = selection[0]
        if iid.startswith("lang:"):
            return
        try:
            book_id = int(iid)
        except ValueError:
            return
        if book_id != self.book_id:
            self.book_id = book_id
            self.load_words()

    def _debounced_load(self) -> None:
        job = getattr(self, "_search_job", None)
        if job:
            try:
                self.parent.after_cancel(job)
            except Exception:
                pass
        self._search_job = self.parent.after(200, self.load_words)

    def load_words(self) -> None:
        self._search_job = None
        self.word_tree.delete(*self.word_tree.get_children())
        if self.book_id is None:
            self.words = []
            self.count_label.configure(text="")
            return
        self.words = self.service.words_in_book(
            self.book_id, self.search_var.get().strip(), 3000
        )
        book = next((b for b in self.books if b["id"] == self.book_id), {})
        self.book_title.configure(
            text=f"{book.get('name', '')} · {tr('牌组')} {book.get('deck') or tr('（按语言默认）')}"
        )
        for word in self.words:
            self.word_tree.insert(
                "",
                "end",
                iid=str(word["id"]),
                values=(
                    word.get("word") or "",
                    word.get("reading") or "",
                    (word.get("meaning") or "")[:80],
                    word.get("book") or "",
                    (word.get("updated") or "")[:16],
                    "已同步" if word.get("synced") else "未同步",
                ),
            )
        self.count_label.configure(text=f"{len(self.words)} 个")

    def _selected_words(self) -> list[int]:
        return [int(i) for i in self.word_tree.selection() if i.isdigit()]

    # ------------------------------------------------------------------ 操作
    def new_book(self) -> None:
        langs = sorted(
            {b.get("lang") or "en" for b in self.books}
            or {
                code
                for code in (self.config.get("languages") or {}).keys()
                if code
            }
            or {"en"}
        )
        dialog = BookDialog(self.parent, "新建词本", langs=langs)
        self.parent.wait_window(dialog.win)
        if dialog.result:
            name, lang, deck = dialog.result
            book_id = self.service.create_wordbook(lang, name, deck)
            self.refresh()
            self._select_book(book_id)
            self._set_status(f"已新建词本：{name}")

    def rename_book(self) -> None:
        if not self.book_id:
            return
        book = next((b for b in self.books if b["id"] == self.book_id), None)
        if not book:
            return
        dialog = BookDialog(
            self.parent, "编辑词本", langs=[book["lang"]], lang=book["lang"],
            name=book["name"], deck=book.get("deck") or "", locked_lang=True,
        )
        self.parent.wait_window(dialog.win)
        if dialog.result:
            name, _lang, deck = dialog.result
            self.service.rename_wordbook(self.book_id, name, deck)
            self.refresh()
            self._set_status(f"已保存词本：{name}")

    def delete_book(self) -> None:
        if not self.book_id:
            return
        book = next((b for b in self.books if b["id"] == self.book_id), None)
        if not book:
            return
        if book.get("is_default"):
            messagebox.showinfo("生词本", "默认词本不能删除。", parent=self.parent)
            return
        if not messagebox.askyesno(
            "删除词本",
            f"删除「{book['name']}」？里面的词会移回该语言的默认词本，不会被删除。",
            parent=self.parent,
        ):
            return
        moved = self.service.delete_wordbook(self.book_id)
        self.book_id = None
        self.refresh()
        self._set_status(f"已删除词本，{moved} 个词移回默认词本")

    def move_selected(self) -> None:
        ids = self._selected_words()
        if not ids or not self.book_id:
            return
        current = next((b for b in self.books if b["id"] == self.book_id), {})
        targets = [
            b
            for b in self.books
            if b.get("lang") == current.get("lang") and b["id"] != self.book_id
        ]
        if not targets:
            messagebox.showinfo(
                "移动到词本", "这个语言下没有别的词本，先新建一个。", parent=self.parent
            )
            return
        menu = tk.Menu(self.parent, tearoff=0, bg=PANEL, fg=TEXT,
                       activebackground=ACCENT, activeforeground="#10131a",
                       font=(FONT_FAMILY, 9))
        for book in targets:
            menu.add_command(
                label=book["name"],
                command=lambda b=book: self._do_move(ids, b),
            )
        try:
            menu.tk_popup(
                self.parent.winfo_pointerx(), self.parent.winfo_pointery()
            )
        finally:
            menu.grab_release()

    def _do_move(self, ids: list[int], book: dict) -> None:
        moved = self.service.move_words(ids, book["id"])
        self.refresh()
        self._set_status(f"已移动 {moved} 个词到「{book['name']}」")

    def delete_selected(self) -> None:
        ids = self._selected_words()
        if not ids:
            return
        if not messagebox.askyesno(
            "删除生词", f"删除选中的 {len(ids)} 个生词？", parent=self.parent
        ):
            return
        count = self.service.store.delete_words(ids)
        self.refresh()
        self._set_status(f"已删除 {count} 个生词")

    def export_book(self) -> None:
        if not self.book_id:
            return
        try:
            result = self.service.export_vocab(wordbook_id=self.book_id)
            self._set_status(f"已导出 {result.get('count', 0)} 个到 {result.get('path')}")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("导出失败", str(exc), parent=self.parent)

    def open_anki_settings(self) -> None:
        if not self.book_id:
            return
        book = next((b for b in self.books if b["id"] == self.book_id), None)
        if not book:
            return
        from .wordbook_anki_settings import WordbookAnkiSettings

        WordbookAnkiSettings(self.parent, self.service, book)

    def sync_book(self) -> None:
        if not self.book_id:
            return
        if getattr(self, "_syncing", False):
            return
        book = next((b for b in self.books if b["id"] == self.book_id), {})
        self._syncing = True
        self._sync_ready = False
        self._sync_result = None
        self._set_status(f"正在同步「{book.get('name', '')}」…")

        def run() -> None:
            try:
                self._sync_result = ("ok", self.service.push_anki(wordbook_id=self.book_id))
            except Exception as exc:  # noqa: BLE001
                self._sync_result = ("err", str(exc))
            self._sync_ready = True

        threading.Thread(target=run, daemon=True).start()
        self.parent.after(120, self._poll_sync)

    def _poll_sync(self) -> None:
        try:
            if not self.parent.winfo_exists():
                return
        except tk.TclError:
            return
        if not self._sync_ready:
            self.parent.after(120, self._poll_sync)
            return
        self._syncing = False
        kind, data = self._sync_result or ("err", "未知错误")
        if kind == "ok":
            message = (
                f"新增 {data.get('added', 0)}，重复 {data.get('duplicated', 0)}，"
                f"已存在 {data.get('skipped', 0)}"
            )
            if data.get("failed"):
                message += f"，失败 {len(data['failed'])}"
            self._set_status(f"Anki 同步完成：{message}")
        else:
            self._set_status("同步失败", error=True)
            messagebox.showerror("Anki 同步失败", str(data), parent=self.parent)
        self.refresh()

    def _set_status(self, text: str, error: bool = False) -> None:
        try:
            self.status.configure(text=text[:90], fg="#ff8080" if error else GREEN)
        except tk.TclError:
            pass


class BookDialog:
    """新建/编辑词本的小对话框。"""

    def __init__(
        self,
        parent,
        title: str,
        langs: list[str],
        lang: str = "",
        name: str = "",
        deck: str = "",
        locked_lang: bool = False,
    ) -> None:
        self.result = None
        self.win = tk.Toplevel(parent)
        self.win.title(title)
        self.win.configure(bg=BG)
        self.win.resizable(False, False)
        self.win.transient(parent.winfo_toplevel())
        self.win.grab_set()
        outer = tk.Frame(self.win, bg=BG)
        outer.pack(fill="both", expand=True, padx=16, pady=14)

        def row(label, width=26):
            frame = tk.Frame(outer, bg=BG)
            frame.pack(fill="x", pady=4)
            tk.Label(frame, text=label, bg=BG, fg=DIM, font=(FONT_FAMILY, 9), width=6,
                     anchor="w").pack(side="left")
            entry = tk.Entry(
                frame, bg=PANEL, fg=TEXT, insertbackground=TEXT, relief="flat",
                font=(FONT_FAMILY, 9), width=width,
            )
            entry.pack(side="left", fill="x", expand=True, ipady=4)
            return entry

        if not lang:
            lang = langs[0] if langs else "en"
        entry_lang = row("语言")
        entry_lang.insert(0, lang)
        if locked_lang or len(langs) <= 1:
            entry_lang.configure(state="disabled")
        entry_name = row("名称")
        entry_name.insert(0, name)
        entry_deck = row("牌组")
        entry_deck.insert(0, deck)
        tk.Label(
            outer, text="牌组留空 = 使用该语言的默认牌组", bg=BG, fg=DIM,
            font=(FONT_FAMILY, 8),
        ).pack(fill="x", pady=(0, 6))

        btns = tk.Frame(outer, bg=BG)
        btns.pack(fill="x", pady=(4, 0))

        def save() -> None:
            name_value = entry_name.get().strip()
            lang_value = entry_lang.get().strip().lower() or lang
            deck_value = entry_deck.get().strip()
            if not name_value:
                messagebox.showinfo(title, "词本名称不能为空。", parent=self.win)
                return
            self.result = (name_value, lang_value, deck_value)
            self.win.destroy()

        tk.Label(
            btns, text="保存", bg=ACCENT, fg="#10131a", font=(FONT_FAMILY, 9),
            padx=14, pady=5, cursor="hand2",
        ).pack(side="right")
        btns.winfo_children()[-1].bind("<Button-1>", lambda _e: save())
        tk.Label(
            btns, text="取消", bg=PANEL, fg=TEXT, font=(FONT_FAMILY, 9),
            padx=14, pady=5, cursor="hand2",
        ).pack(side="right", padx=(0, 8))
        btns.winfo_children()[-1].bind("<Button-1>", lambda _e: self.win.destroy())
        self.win.bind("<Escape>", lambda _e: self.win.destroy())
        entry_name.focus_set()
        self.win.update_idletasks()
        parent_x = parent.winfo_rootx()
        parent_y = parent.winfo_rooty()
        width = max(self.win.winfo_reqwidth(), 400)
        height = max(self.win.winfo_reqheight(), 300)
        self.win.geometry(
            f"{width}x{height}+{parent_x + 80}+{parent_y + 80}"
        )
