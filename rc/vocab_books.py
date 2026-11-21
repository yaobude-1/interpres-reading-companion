"""生词本：按语言分组的词本列表与增删改。"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from .i18n import tr
from .popup import ACCENT, BG, DIM, FONT_FAMILY, PANEL, TEXT
from .theme import ON_ACCENT


class VocabBooksMixin:
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
            btns, text="保存", bg=ACCENT, fg=ON_ACCENT, font=(FONT_FAMILY, 9),
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
