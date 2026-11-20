"""生词本管理窗口：查看、搜索、删除、导出、同步。"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from .popup import ACCENT, BG, DIM, FONT_FAMILY, MUTED, PANEL, TEXT


class VocabWindow:
    def __init__(self, root: tk.Tk, service, config, on_change=None) -> None:
        self.root = root
        self.service = service
        self.config = config
        self.on_change = on_change
        self.words: list[dict] = []

        self.win = tk.Toplevel(root)
        self.win.title("生词本")
        self.win.configure(bg=BG)
        self.win.geometry("880x620")
        self.win.minsize(680, 440)
        self.win.attributes("-topmost", True)
        self.win.after(100, lambda: self.win.attributes("-topmost", False))
        self._build()
        self.refresh()
        self._center()

    def _center(self) -> None:
        self.win.update_idletasks()
        w = self.win.winfo_width() or 880
        h = self.win.winfo_height() or 620
        sw, sh = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
        self.win.geometry(f"{w}x{h}+{(sw - w) // 2}+{max(20, (sh - h) // 3)}")

    # ------------------------------------------------------------------ 构建
    def _build(self) -> None:
        outer = tk.Frame(self.win, bg=BG)
        outer.pack(fill="both", expand=True, padx=16, pady=14)

        head = tk.Frame(outer, bg=BG)
        head.pack(fill="x")
        tk.Label(
            head, text="生词本", bg=BG, fg=TEXT, font=(FONT_FAMILY, 14, "bold"), anchor="w"
        ).pack(side="left")
        self.count_label = tk.Label(
            head, text="", bg=BG, fg=MUTED, font=(FONT_FAMILY, 9), anchor="w"
        )
        self.count_label.pack(side="left", padx=(12, 0))

        # 工具条
        bar = tk.Frame(outer, bg=BG)
        bar.pack(fill="x", pady=(10, 8))

        languages = ["全部"] + [
            code for code in (self.config.data.get("languages") or {})
        ]
        self.var_lang = tk.StringVar(value="全部")
        self.lang_box = tk.OptionMenu(bar, self.var_lang, *languages,
                                      command=lambda _v: self.refresh())
        self.lang_box.configure(
            bg=PANEL, fg=TEXT, activebackground=PANEL, activeforeground=TEXT,
            relief="flat", highlightthickness=0, font=(FONT_FAMILY, 9), width=8, anchor="w",
        )
        self.lang_box["menu"].configure(bg=PANEL, fg=TEXT, activebackground=ACCENT,
                                        activeforeground="#10131a")
        self.lang_box.pack(side="left")

        tk.Label(bar, text="搜索", bg=BG, fg=DIM, font=(FONT_FAMILY, 9)).pack(
            side="left", padx=(12, 4)
        )
        self.var_search = tk.StringVar()
        entry = tk.Entry(
            bar, textvariable=self.var_search, width=24, bg=PANEL, fg=TEXT,
            insertbackground=TEXT, relief="flat", font=(FONT_FAMILY, 9),
        )
        entry.pack(side="left")
        entry.bind("<KeyRelease>", lambda _e: self.refresh())

        self._button(bar, "刷新", self.refresh).pack(side="right")

        # 表格
        wrap = tk.Frame(outer, bg=PANEL)
        wrap.pack(fill="both", expand=True)

        style = ttk.Style(self.win)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "RC.Treeview",
            background=PANEL,
            fieldbackground=PANEL,
            foreground=TEXT,
            rowheight=26,
            borderwidth=0,
            font=(FONT_FAMILY, 9),
        )
        style.configure(
            "RC.Treeview.Heading",
            background=BG,
            foreground=MUTED,
            relief="flat",
            font=(FONT_FAMILY, 9),
        )
        style.map(
            "RC.Treeview",
            background=[("selected", ACCENT)],
            foreground=[("selected", "#10131a")],
        )
        style.configure(
            "RC.Vertical.TScrollbar", background=PANEL, troughcolor=BG, borderwidth=0,
            arrowcolor=MUTED,
        )

        columns = ("word", "reading", "meaning", "book", "created")
        self.tree = ttk.Treeview(
            wrap, columns=columns, show="headings", style="RC.Treeview",
            selectmode="extended",
        )
        headings = {
            "word": ("单词", 150),
            "reading": ("音标", 120),
            "meaning": ("释义", 300),
            "book": ("书名", 150),
            "created": ("添加时间", 120),
        }
        for key, (label, width) in headings.items():
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, anchor="w", stretch=(key == "meaning"))

        scroll = ttk.Scrollbar(
            wrap, orient="vertical", command=self.tree.yview, style="RC.Vertical.TScrollbar"
        )
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(0, 0))
        scroll.pack(side="right", fill="y")

        self.tree.bind("<Delete>", lambda _e: self.delete_selected())
        self.tree.bind("<Double-1>", lambda _e: self._detail())

        # 底部
        bottom = tk.Frame(outer, bg=BG)
        bottom.pack(fill="x", pady=(10, 0))
        self._button(bottom, "删除选中", self.delete_selected, danger=True).pack(side="left")
        tk.Label(
            bottom, text="（可按住 Ctrl / Shift 多选，或按 Delete 键）",
            bg=BG, fg=DIM, font=(FONT_FAMILY, 8),
        ).pack(side="left", padx=(8, 0))
        self._button(bottom, "关闭", self.win.destroy).pack(side="right")
        self._button(bottom, "同步 Anki", self._push).pack(side="right", padx=(0, 8))
        self._button(bottom, "导出 CSV", self._export).pack(side="right", padx=(0, 8))

    def _button(self, parent, text, command, danger: bool = False) -> tk.Label:
        bg = "#5c2a33" if danger else PANEL
        fg = "#ff9aa8" if danger else TEXT
        label = tk.Label(
            parent, text=text, bg=bg, fg=fg, font=(FONT_FAMILY, 9), padx=12, pady=5,
            cursor="hand2",
        )
        label.bind("<Button-1>", lambda _e: command())
        return label

    # ------------------------------------------------------------------ 数据
    def refresh(self) -> None:
        lang = self.var_lang.get()
        code = None if lang == "全部" else lang
        words = self.service.vocab(code, limit=5000)
        needle = self.var_search.get().strip().lower()
        if needle:
            words = [
                w
                for w in words
                if needle in (w.get("word") or "").lower()
                or needle in (w.get("lemma") or "").lower()
                or needle in (w.get("meaning") or "").lower()
            ]
        self.words = words

        for item in self.tree.get_children():
            self.tree.delete(item)
        for word in words:
            self.tree.insert(
                "",
                "end",
                iid=str(word["id"]),
                values=(
                    word.get("word") or word.get("lemma") or "",
                    word.get("reading") or "",
                    word.get("meaning") or "",
                    word.get("book") or "",
                    (word.get("created") or "")[:16],
                ),
            )
        total = self.service.store.word_count()
        self.count_label.configure(text=f"显示 {len(words)} 个 · 库内共 {total} 个")

    def _selected_ids(self) -> list[int]:
        return [int(i) for i in self.tree.selection()]

    def delete_selected(self) -> None:
        ids = self._selected_ids()
        if not ids:
            messagebox.showinfo("生词本", "先在列表里选中要删除的单词。", parent=self.win)
            return
        if not messagebox.askyesno(
            "删除生词", f"确定删除选中的 {len(ids)} 个生词？\n（只删本地的，Anki 里已有的卡片不受影响）",
            parent=self.win,
        ):
            return
        removed = self.service.store.delete_words(ids)
        self.refresh()
        if self.on_change:
            self.on_change()
        messagebox.showinfo("生词本", f"已删除 {removed} 个。", parent=self.win)

    def _detail(self) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        word = next((w for w in self.words if str(w["id"]) == selection[0]), None)
        if not word:
            return
        messagebox.showinfo(
            word.get("word") or "",
            f"原形：{word.get('lemma') or '-'}\n"
            f"音标：{word.get('reading') or '-'}\n"
            f"词性：{word.get('pos') or '-'}\n"
            f"释义：{word.get('meaning') or '-'}\n"
            f"书名：{word.get('book') or '-'}\n"
            f"原句：{word.get('sentence') or '-'}",
            parent=self.win,
        )

    def _export(self) -> None:
        result = self.service.export_vocab(None if self.var_lang.get() == "全部" else self.var_lang.get())
        messagebox.showinfo("导出完成", f"已导出 {result['count']} 条：\n{result['path']}", parent=self.win)

    def _push(self) -> None:
        import threading

        langs = [c for c in (self.config.data.get("languages") or {}) if self.service.store.word_count(c)]
        if not langs:
            messagebox.showinfo("同步 Anki", "没有可同步的生词。", parent=self.win)
            return

        def run() -> None:
            lines = []
            for lang in langs:
                try:
                    result = self.service.push_anki(lang)
                    line = f"{lang}: 新增 {result.get('added', 0)}，重复 {result.get('duplicated', 0)}"
                    if result.get("skipped"):
                        line += f"，已存在 {result['skipped']}"
                    lines.append(line)
                except Exception as exc:  # noqa: BLE001
                    lines.append(f"{lang}: {exc}")
            self.win.after(
                0, lambda: messagebox.showinfo("同步 Anki", "\n".join(lines), parent=self.win)
            )

        threading.Thread(target=run, daemon=True).start()

    def show(self) -> None:
        self.win.deiconify()
        self.win.lift()
        self.refresh()
        try:
            self.win.focus_force()
        except tk.TclError:
            pass
