"""生词本：移动、删除、导出与 Anki 同步。"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox

from .popup import ACCENT, FONT_FAMILY, GREEN, PANEL, TEXT
from .theme import ON_ACCENT


class VocabActionsMixin:
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
                       activebackground=ACCENT, activeforeground=ON_ACCENT,
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
        except tk.TclError:  # 控件可能已销毁，刻意忽略
            pass
