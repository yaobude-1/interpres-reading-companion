"""翻译记录：搜索、查看、删除、导出。"""

from __future__ import annotations

import json
import os
import tkinter as tk
from tkinter import messagebox, ttk

from .popup import ACCENT, BG, DIM, FONT_FAMILY, MUTED, PANEL, TEXT


class TranslationWindow:
    def __init__(self, root: tk.Tk, service) -> None:
        self.root = root
        self.service = service
        self.rows: list[dict] = []

        self.win = tk.Toplevel(root)
        self.win.title("翻译记录")
        self.win.configure(bg=BG)
        self.win.geometry("880x600")
        self.win.minsize(680, 420)
        self._build()
        self.refresh()
        self._center()

    def _center(self) -> None:
        self.win.update_idletasks()
        sw, sh = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
        self.win.geometry(f"880x600+{max(20, (sw - 880) // 2)}+{max(20, (sh - 600) // 3)}")

    # ------------------------------------------------------------------ 构建
    def _build(self) -> None:
        outer = tk.Frame(self.win, bg=BG)
        outer.pack(fill="both", expand=True, padx=16, pady=14)

        head = tk.Frame(outer, bg=BG)
        head.pack(fill="x")
        tk.Label(
            head, text="翻译记录", bg=BG, fg=TEXT, font=(FONT_FAMILY, 14, "bold")
        ).pack(side="left")
        self.count = tk.Label(head, text="", bg=BG, fg=MUTED, font=(FONT_FAMILY, 9))
        self.count.pack(side="left", padx=(12, 0))

        bar = tk.Frame(outer, bg=BG)
        bar.pack(fill="x", pady=(10, 8))
        tk.Label(bar, text="搜索", bg=BG, fg=DIM, font=(FONT_FAMILY, 9)).pack(side="left")
        self.var_query = tk.StringVar()
        entry = tk.Entry(
            bar,
            textvariable=self.var_query,
            bg=PANEL,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            font=(FONT_FAMILY, 9),
            width=30,
        )
        entry.pack(side="left", padx=(6, 12))
        entry.bind("<Return>", lambda _e: self.refresh())

        tk.Label(bar, text="书", bg=BG, fg=DIM, font=(FONT_FAMILY, 9)).pack(side="left")
        self.var_book = tk.StringVar(value="全部")
        self.book_box = tk.OptionMenu(bar, self.var_book, "全部", command=lambda _v: self.refresh())
        self.book_box.configure(
            bg=PANEL, fg=TEXT, activebackground=PANEL, activeforeground=TEXT,
            relief="flat", highlightthickness=0, font=(FONT_FAMILY, 9), width=20, anchor="w",
        )
        self.book_box["menu"].configure(
            bg=PANEL, fg=TEXT, activebackground=ACCENT, activeforeground="#10131a"
        )
        self.book_box.pack(side="left", padx=(6, 12))
        self._button(bar, "搜索", self.refresh).pack(side="left")

        wrap = tk.Frame(outer, bg=PANEL)
        wrap.pack(fill="both", expand=True)
        style = ttk.Style(self.win)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Tr.Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT,
            rowheight=26, borderwidth=0, font=(FONT_FAMILY, 9),
        )
        style.configure(
            "Tr.Treeview.Heading", background=BG, foreground=MUTED, relief="flat",
            font=(FONT_FAMILY, 9),
        )
        style.map(
            "Tr.Treeview", background=[("selected", ACCENT)],
            foreground=[("selected", "#10131a")],
        )
        self.tree = ttk.Treeview(
            wrap, columns=("time", "book", "text"), show="headings", style="Tr.Treeview"
        )
        for key, label, width in (
            ("time", "时间", 120),
            ("book", "书", 150),
            ("text", "原文", 520),
        ):
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, anchor="w", stretch=(key == "text"))
        scroll = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", lambda _e: self.view_selected())
        self.tree.bind("<Delete>", lambda _e: self.delete_selected())

        bottom = tk.Frame(outer, bg=BG)
        bottom.pack(fill="x", pady=(10, 0))
        self._button(bottom, "查看", self.view_selected).pack(side="left")
        self._button(bottom, "删除选中", self.delete_selected, danger=True).pack(
            side="left", padx=(8, 0)
        )
        self._button(bottom, "导出 Markdown", lambda: self.export("md")).pack(
            side="left", padx=(8, 0)
        )
        self._button(bottom, "导出 TSV", lambda: self.export("tsv")).pack(
            side="left", padx=(8, 0)
        )
        self._button(bottom, "关闭", self.win.destroy).pack(side="right")

    def _button(self, parent, text, command, danger=False):
        bg = "#5c2a33" if danger else PANEL
        fg = "#ff9aa8" if danger else TEXT
        label = tk.Label(
            parent, text=text, bg=bg, fg=fg, font=(FONT_FAMILY, 9), padx=12, pady=5, cursor="hand2"
        )
        label.bind("<Button-1>", lambda _e: command())
        return label

    # ------------------------------------------------------------------ 数据
    def refresh(self) -> None:
        books = [b["name"] for b in self.service.store.books()]
        menu = self.book_box["menu"]
        menu.delete(0, "end")
        menu.add_command(label="全部", command=lambda: (self.var_book.set("全部"), self.refresh()))
        for name in books:
            menu.add_command(
                label=name, command=lambda n=name: (self.var_book.set(n), self.refresh())
            )
        book = self.var_book.get()
        self.rows = self.service.translations(
            book=None if book == "全部" else book, query=self.var_query.get().strip()
        )
        for item in self.tree.get_children():
            self.tree.delete(item)
        for row in self.rows:
            self.tree.insert(
                "",
                "end",
                iid=str(row["id"]),
                values=(
                    row.get("updated", "")[:16],
                    row.get("book") or "(未标书名)",
                    " ".join((row.get("text") or "").split())[:120],
                ),
            )
        self.count.configure(text=f"共 {len(self.rows)} 条")

    def _selected(self) -> list[int]:
        return [int(i) for i in self.tree.selection()]

    def view_selected(self) -> None:
        ids = self._selected()
        if not ids:
            messagebox.showinfo("翻译记录", "先选中一条记录。", parent=self.win)
            return
        row = self.service.store.translation(ids[0])
        if not row:
            return
        payload = json.loads(row.get("payload") or "{}")
        win = tk.Toplevel(self.win)
        win.title(f"{row.get('book') or '翻译记录'} · {row.get('updated', '')[:16]}")
        win.configure(bg=BG)
        win.geometry("640x560")
        text = tk.Text(
            win, bg=PANEL, fg=TEXT, insertbackground=TEXT, relief="flat",
            font=(FONT_FAMILY, 10), wrap="word", padx=12, pady=10,
        )
        text.pack(fill="both", expand=True, padx=12, pady=12)
        lines = [
            f"【原文】\n{row.get('text', '')}\n",
            f"【译文】\n{payload.get('translation', '')}\n",
        ]
        terms = payload.get("terms") or []
        if terms:
            lines.append(
                "【生词】\n"
                + "\n".join(f"{t.get('word', '')}  {t.get('meaning', '')}" for t in terms)
            )
        text.insert("1.0", "\n".join(lines))
        text.configure(state="disabled")

    def delete_selected(self) -> None:
        ids = self._selected()
        if not ids:
            messagebox.showinfo("翻译记录", "先选中要删除的记录。", parent=self.win)
            return
        if not messagebox.askyesno(
            "删除记录", f"确定删除选中的 {len(ids)} 条记录？", parent=self.win
        ):
            return
        for rid in ids:
            self.service.store.delete_translation(rid)
        self.refresh()

    def export(self, fmt: str) -> None:
        book = self.var_book.get()
        result = self.service.export_translations(
            book=None if book == "全部" else book, query=self.var_query.get().strip(), fmt=fmt
        )
        answer = messagebox.askyesno(
            "导出完成",
            f"已导出 {result['count']} 条到：\n{result['path']}\n\n要打开文件夹吗？",
            parent=self.win,
        )
        if answer:
            try:
                os.startfile(result["dir"])  # type: ignore[attr-defined]
            except Exception:
                pass

    def show(self) -> None:
        self.win.deiconify()
        self.win.lift()
        self.refresh()
        try:
            self.win.focus_force()
        except tk.TclError:
            pass
