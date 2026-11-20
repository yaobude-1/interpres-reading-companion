"""对话记录管理：按书分组、查看、删除、改名、导出。"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from .popup import ACCENT, BG, DIM, FONT_FAMILY, MUTED, PANEL, TEXT


class ChatHistoryWindow:
    def __init__(self, root: tk.Tk, service, on_change=None, on_open=None) -> None:
        self.root = root
        self.service = service
        self.on_change = on_change
        self.on_open = on_open
        self.items: list[dict] = []

        self.win = tk.Toplevel(root)
        self.win.title("对话记录")
        self.win.configure(bg=BG)
        self.win.geometry("820x560")
        self.win.minsize(640, 420)
        self.win.attributes("-topmost", True)
        self.win.after(100, lambda: self.win.attributes("-topmost", False))
        self._build()
        self.refresh()
        self._center()

    def _center(self) -> None:
        self.win.update_idletasks()
        sw, sh = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
        self.win.geometry(f"820x560+{max(20, (sw - 820) // 2)}+{max(20, (sh - 560) // 3)}")

    # ------------------------------------------------------------------ 构建
    def _build(self) -> None:
        outer = tk.Frame(self.win, bg=BG)
        outer.pack(fill="both", expand=True, padx=16, pady=14)

        head = tk.Frame(outer, bg=BG)
        head.pack(fill="x")
        tk.Label(
            head, text="对话记录", bg=BG, fg=TEXT, font=(FONT_FAMILY, 14, "bold"), anchor="w"
        ).pack(side="left")
        self.count = tk.Label(head, text="", bg=BG, fg=MUTED, font=(FONT_FAMILY, 9))
        self.count.pack(side="left", padx=(12, 0))

        bar = tk.Frame(outer, bg=BG)
        bar.pack(fill="x", pady=(10, 8))
        tk.Label(bar, text="按书筛选", bg=BG, fg=DIM, font=(FONT_FAMILY, 9)).pack(side="left")
        self.var_book = tk.StringVar(value="全部")
        self.book_box = tk.OptionMenu(bar, self.var_book, "全部", command=lambda _v: self.refresh())
        self.book_box.configure(
            bg=PANEL, fg=TEXT, activebackground=PANEL, activeforeground=TEXT,
            relief="flat", highlightthickness=0, font=(FONT_FAMILY, 9), width=22, anchor="w",
        )
        self.book_box["menu"].configure(
            bg=PANEL, fg=TEXT, activebackground=ACCENT, activeforeground="#10131a"
        )
        self.book_box.pack(side="left", padx=(8, 0))

        wrap = tk.Frame(outer, bg=PANEL)
        wrap.pack(fill="both", expand=True)

        style = ttk.Style(self.win)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Chat.Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT,
            rowheight=26, borderwidth=0, font=(FONT_FAMILY, 9),
        )
        style.configure(
            "Chat.Treeview.Heading", background=BG, foreground=MUTED, relief="flat",
            font=(FONT_FAMILY, 9),
        )
        style.map(
            "Chat.Treeview", background=[("selected", ACCENT)],
            foreground=[("selected", "#10131a")],
        )

        columns = ("book", "time", "preview", "count")
        self.tree = ttk.Treeview(
            wrap, columns=columns, show="headings", style="Chat.Treeview", selectmode="extended"
        )
        for key, label, width in (
            ("book", "书", 180),
            ("time", "时间", 130),
            ("preview", "开头", 360),
            ("count", "消息", 60),
        ):
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, anchor="w", stretch=(key == "preview"))

        scroll = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", lambda _e: self.open_selected())
        self.tree.bind("<Delete>", lambda _e: self.delete_selected())

        bottom = tk.Frame(outer, bg=BG)
        bottom.pack(fill="x", pady=(10, 0))
        self._button(bottom, "在主面板继续", self.open_selected).pack(side="left")
        self._button(bottom, "查看", self.view_selected).pack(side="left", padx=(8, 0))
        self._button(bottom, "删除选中", self.delete_selected, danger=True).pack(
            side="left", padx=(8, 0)
        )
        self._button(bottom, "改书名", self.rename_book).pack(side="left", padx=(8, 0))
        self._button(bottom, "导出本书", self.export_book).pack(side="left", padx=(8, 0))
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
        books = [b["book"] or "(未命名)" for b in self.service.books_with_conversations()]
        menu = self.book_box["menu"]
        menu.delete(0, "end")
        menu.add_command(label="全部", command=lambda: (self.var_book.set("全部"), self.refresh()))
        for book in books:
            menu.add_command(
                label=book, command=lambda b=book: (self.var_book.set(b), self.refresh())
            )

        book = self.var_book.get()
        rows = self.service.conversations(None if book == "全部" else book)
        self.items = rows
        for item in self.tree.get_children():
            self.tree.delete(item)
        for conv in rows:
            preview = (conv.get("passage") or "").replace("\n", " ")[:70]
            self.tree.insert(
                "",
                "end",
                iid=str(conv["id"]),
                values=(
                    conv.get("book") or "(未命名)",
                    (conv.get("updated") or "")[:16],
                    preview,
                    conv.get("msg_count", 0),
                ),
            )
        self.count.configure(text=f"共 {len(rows)} 段对话")

    def _selected(self) -> list[int]:
        return [int(i) for i in self.tree.selection()]

    def open_selected(self) -> None:
        """把选中的对话切到主面板，接着聊。"""
        ids = self._selected()
        if not ids:
            messagebox.showinfo("对话记录", "先选中一段对话。", parent=self.win)
            return
        conv = self.service.store.conversation(ids[0])
        if not conv:
            return
        if self.on_open is not None:
            self.on_open(int(conv["id"]))
            try:
                self.win.withdraw()
            except tk.TclError:
                pass
        else:
            self.view_selected()

    def view_selected(self) -> None:
        ids = self._selected()
        if not ids:
            messagebox.showinfo("对话记录", "先选中一段对话。", parent=self.win)
            return
        conv = self.service.store.conversation(ids[0])
        if not conv:
            return
        win = tk.Toplevel(self.win)
        win.title(f"{conv.get('book') or ''} · {conv.get('created', '')[:16]}")
        win.configure(bg=BG)
        win.geometry("620x520")
        text = tk.Text(
            win, bg=PANEL, fg=TEXT, insertbackground=TEXT, relief="flat",
            font=(FONT_FAMILY, 10), wrap="word", padx=12, pady=10,
        )
        text.pack(fill="both", expand=True, padx=12, pady=12)
        lines = []
        if conv.get("passage"):
            lines.append("【原文】" + conv["passage"][:500] + "\n")
        if conv.get("translation"):
            lines.append("【译文】" + conv["translation"][:300] + "\n")
        for message in self.service.store.messages(ids[0]):
            speaker = "我" if message["role"] == "user" else "AI"
            lines.append(f"{speaker}：{message['content']}\n")
        text.insert("1.0", "\n".join(lines))
        text.configure(state="disabled")

    def delete_selected(self) -> None:
        ids = self._selected()
        if not ids:
            messagebox.showinfo("对话记录", "先选中要删除的对话。", parent=self.win)
            return
        if not messagebox.askyesno(
            "删除对话", f"确定删除选中的 {len(ids)} 段对话？此操作不可撤销。", parent=self.win
        ):
            return
        for conv_id in ids:
            self.service.delete_conversation(conv_id)
        self.refresh()
        if self.on_change:
            self.on_change()

    def rename_book(self) -> None:
        ids = self._selected()
        if not ids:
            messagebox.showinfo("改书名", "先选中一段对话。", parent=self.win)
            return
        conv = self.service.store.conversation(ids[0])
        if not conv:
            return
        old = conv.get("book") or ""
        new = simpledialog.askstring("改书名", "新的书名：", initialvalue=old, parent=self.win)
        if new and new != old:
            self.service.rename_book(old, new)
            self.refresh()

    def export_book(self) -> None:
        ids = self._selected()
        book = None
        if ids:
            conv = self.service.store.conversation(ids[0])
            book = (conv or {}).get("book")
        if not book:
            messagebox.showinfo("导出", "先选中一段对话，或先按书筛选。", parent=self.win)
            return
        result = self.service.export_conversations(book)
        messagebox.showinfo(
            "导出完成", f"已导出 {result['count']} 段对话：\n{result['path']}", parent=self.win
        )

    def show(self) -> None:
        self.win.deiconify()
        self.win.lift()
        self.refresh()
        try:
            self.win.focus_force()
        except tk.TclError:
            pass
