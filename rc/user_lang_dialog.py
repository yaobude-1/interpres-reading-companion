"""词形与变位表：用户给任意语言补充“变形 → 原形”和可显示的变位表。"""

from __future__ import annotations

import csv
import json
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .i18n import lang_display_name
from .popup import ACCENT, BG, DIM, FONT_FAMILY, GREEN, MUTED, PANEL, PANEL_ALT, RED, TEXT
from .theme import BORDER_SOFT, ON_ACCENT
from .uiutil import bind_defocus


class UserLangDialog:
    def __init__(self, root: tk.Tk, config, data, dicts=None) -> None:
        self.root = root
        self.config = config
        self.data = data
        self.dicts = dicts
        self.lang = ""
        self._display_to_code: dict[str, str] = {}
        self._extract_cancel = threading.Event()
        self._extract_queue: queue.Queue = queue.Queue()
        self._extract_progress: tk.Toplevel | None = None

        self.win = tk.Toplevel(root)
        self.win.title("词形与变位表")
        self.win.configure(bg=BG)
        self.win.geometry("800x700")
        self.win.attributes("-topmost", True)
        self._build()
        self._set_initial_lang()
        bind_defocus(self.win)

    # ------------------------------------------------------------------ 构建
    def _build(self) -> None:
        outer = tk.Frame(self.win, bg=BG)
        outer.pack(fill="both", expand=True, padx=18, pady=14)

        tk.Label(
            outer, text="词形与变位表", bg=BG, fg=TEXT,
            font=(FONT_FAMILY, 14, "bold"), anchor="w",
        ).pack(fill="x")
        tk.Label(
            outer,
            text="给词典没收录的变形补一条“变形 → 原形”，或者导入一张变位表；"
            "表里的每个形式都会自动变成反查项。只保存 JSON，不执行代码。",
            bg=BG, fg=DIM, font=(FONT_FAMILY, 9), anchor="w",
            justify="left", wraplength=730,
        ).pack(fill="x", pady=(2, 10))

        lang_row = tk.Frame(outer, bg=BG)
        lang_row.pack(fill="x", pady=(0, 10))
        tk.Label(lang_row, text="语言", bg=BG, fg=DIM, font=(FONT_FAMILY, 9)).pack(side="left")
        self.var_lang = tk.StringVar(value="")
        self.lang_menu = tk.OptionMenu(lang_row, self.var_lang, "")
        self.lang_menu.configure(
            bg=PANEL, fg=TEXT, activebackground=ACCENT, activeforeground=ON_ACCENT,
            highlightthickness=0, font=(FONT_FAMILY, 9),
        )
        self.lang_menu["menu"].configure(
            bg=PANEL, fg=TEXT, activebackground=ACCENT, activeforeground=ON_ACCENT,
        )
        self.lang_menu.pack(side="left", padx=(8, 0))

        # ---------------------------------------------------------- 用户词形
        self._section(outer, "用户词形（变形 → 原形）")
        form_box = tk.Frame(outer, bg=PANEL)
        form_box.pack(fill="x")
        style = ttk.Style(self.win)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "UL.Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT,
            rowheight=22, borderwidth=0,
        )
        style.map(
            "UL.Treeview",
            background=[("selected", ACCENT)],
            foreground=[("selected", ON_ACCENT)],
        )
        style.configure(
            "UL.Treeview.Heading", background=PANEL_ALT, foreground=TEXT,
            borderwidth=0, relief="flat",
        )
        self.form_tree = ttk.Treeview(
            form_box, columns=("form", "lemma"), show="headings", height=6,
            style="UL.Treeview",
        )
        self.form_tree.heading("form", text="变形")
        self.form_tree.heading("lemma", text="原形")
        self.form_tree.column("form", width=220, anchor="w")
        self.form_tree.column("lemma", width=220, anchor="w")
        self.form_tree.pack(side="left", fill="x", expand=True, padx=(8, 0), pady=8)

        add_row = tk.Frame(outer, bg=BG)
        add_row.pack(fill="x", pady=(8, 2))
        self.var_form = tk.StringVar()
        self.var_lemma = tk.StringVar()
        tk.Label(add_row, text="变形", bg=BG, fg=DIM, font=(FONT_FAMILY, 9)).pack(side="left")
        self._entry(add_row, self.var_form).pack(side="left", padx=(6, 8))
        tk.Label(add_row, text="→", bg=BG, fg=DIM, font=(FONT_FAMILY, 9)).pack(side="left")
        tk.Label(add_row, text="原形", bg=BG, fg=DIM, font=(FONT_FAMILY, 9)).pack(side="left", padx=(8, 0))
        self._entry(add_row, self.var_lemma).pack(side="left", padx=(6, 8))
        self._button(add_row, "添加", self.add_form, primary=True).pack(side="left")
        self._button(add_row, "删除选中", self.delete_form).pack(side="left", padx=(6, 0))
        self._button(add_row, "从词典提取…", self.extract_forms).pack(side="left", padx=(6, 0))
        self._button(add_row, "导入 JSON/CSV", self.import_forms).pack(side="right")
        self._button(add_row, "导出", self.export_lang).pack(side="right", padx=(0, 6))

        bulk_row = tk.Frame(outer, bg=BG)
        bulk_row.pack(fill="x", pady=(4, 0))
        self._button(bulk_row, "批量提取整本词典…", self.bulk_extract).pack(side="left")
        tk.Label(
            bulk_row,
            text="扫描一次，按相似度批量加入；可先预览",
            bg=BG, fg=DIM, font=(FONT_FAMILY, 8),
        ).pack(side="left", padx=(8, 0))

        # ---------------------------------------------------------- 用户变位表
        self._section(outer, "用户变位表（显示 + 自动反查）")
        table_box = tk.Frame(outer, bg=PANEL)
        table_box.pack(fill="x")
        self.table_tree = ttk.Treeview(
            table_box, columns=("lemma", "groups"), show="headings", height=4,
            style="UL.Treeview",
        )
        self.table_tree.heading("lemma", text="原形")
        self.table_tree.heading("groups", text="时态组")
        self.table_tree.column("lemma", width=220, anchor="w")
        self.table_tree.column("groups", width=120, anchor="w")
        self.table_tree.pack(side="left", fill="x", expand=True, padx=(8, 0), pady=8)

        table_row = tk.Frame(outer, bg=BG)
        table_row.pack(fill="x", pady=(8, 2))
        self._button(table_row, "导入变位表（JSON）…", self.import_tables, primary=True).pack(side="left")
        self._button(table_row, "删除选中", self.delete_table).pack(side="left", padx=(6, 0))
        self._button(table_row, "预览", self.preview_table).pack(side="left", padx=(6, 0))

        self.status = tk.Label(
            outer, text="", bg=BG, fg=GREEN, font=(FONT_FAMILY, 9), anchor="w",
        )
        self.status.pack(fill="x", pady=(8, 0))

        bar = tk.Frame(outer, bg=BG)
        bar.pack(fill="x", side="bottom", pady=(10, 0))
        self._button(bar, "关闭", self.win.destroy).pack(side="right")

    def _section(self, parent, text: str) -> None:
        tk.Label(
            parent, text=text, bg=BG, fg=TEXT,
            font=(FONT_FAMILY, 10, "bold"), anchor="w",
        ).pack(fill="x", pady=(10, 6))

    def _entry(self, parent, variable: tk.StringVar) -> tk.Entry:
        return tk.Entry(
            parent,
            textvariable=variable,
            width=16,
            bg=BG,
            fg=TEXT,
            insertbackground=TEXT,
            relief="solid",
            bd=1,
            highlightthickness=0,
            font=(FONT_FAMILY, 9),
        )

    def _button(self, parent, text: str, command, primary: bool = False) -> tk.Button:        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=ACCENT if primary else PANEL,
            fg=ON_ACCENT if primary else TEXT,
            activebackground=ACCENT if primary else BORDER_SOFT,
            activeforeground=ON_ACCENT if primary else TEXT,
            relief="flat",
            font=(FONT_FAMILY, 9),
            padx=10,
            pady=3,
            cursor="hand2",
        )

    # ------------------------------------------------------------------ 语言
    def _set_initial_lang(self) -> None:
        codes = sorted(set(self.config.data.get("languages") or {}) | set(self.data.languages()))
        if not codes:
            codes = ["en"]
        menu = self.lang_menu["menu"]
        menu.delete(0, "end")
        self._display_to_code = {}
        for code in codes:
            try:
                name = lang_display_name(self.config.language(code), code)
            except Exception:  # noqa: BLE001 - 语言配置不完整时只显示代码
                name = code
            display = f"{name} ({code})"
            self._display_to_code[display] = code
            menu.add_command(label=display, command=lambda d=display: self._set_lang(d))
        first = next(iter(self._display_to_code))
        self.var_lang.set(first)
        self._set_lang(first)

    def _set_lang(self, display: str) -> None:
        self.lang = self._display_to_code.get(display, "")
        self.var_lang.set(display)
        self.refresh()

    # ------------------------------------------------------------------ 刷新
    def refresh(self) -> None:
        for row in self.form_tree.get_children():
            self.form_tree.delete(row)
        for row in self.table_tree.get_children():
            self.table_tree.delete(row)
        if not self.lang:
            return
        forms = self.data.forms(self.lang)
        for form in sorted(forms):
            self.form_tree.insert("", "end", values=(form, forms[form]))
        for lemma in sorted(self.data.tables(self.lang)):
            groups = self.data.tables(self.lang)[lemma]
            self.table_tree.insert("", "end", values=(lemma, f"{len(groups)} 组"))
        self.status.configure(text=f"{self.lang}：{len(forms)} 条词形，{len(self.data.tables(self.lang))} 张表")

    # ------------------------------------------------------------------ 词形
    def add_form(self) -> None:
        form = self.var_form.get().strip()
        lemma = self.var_lemma.get().strip()
        if not form or not lemma:
            self._error("变形和原形都要填")
            return
        self.data.add_form(self.lang, form, lemma)
        self.var_form.set("")
        self.var_lemma.set("")
        self.refresh()
        self.status.configure(text=f"已添加：{form} → {lemma}", fg=GREEN)

    def delete_form(self) -> None:
        selected = self.form_tree.selection()
        if not selected:
            self._error("先选中一条词形")
            return
        values = self.form_tree.item(selected[0], "values")
        if not values:
            return
        self.data.remove_form(self.lang, values[0])
        self.refresh()
        self.status.configure(text=f"已删除：{values[0]}", fg=MUTED)

    def import_forms(self) -> None:
        path = filedialog.askopenfilename(
            parent=self.win,
            title="导入词形（JSON/CSV）",
            filetypes=[("JSON / CSV", "*.json *.csv"), ("JSON", "*.json"), ("CSV", "*.csv"), ("全部文件", "*.*")],
        )
        if not path:
            return
        try:
            if path.lower().endswith(".csv"):
                forms = {}
                with open(path, encoding="utf-8-sig", newline="") as handle:
                    for row in csv.reader(handle):
                        if len(row) < 2:
                            continue
                        form = row[0].strip()
                        lemma = row[1].strip()
                        if not form or not lemma:
                            continue
                        if form.lower() in ("form", "变形") and lemma.lower() in ("lemma", "原形"):
                            continue
                        forms[form] = lemma
                count = self.data.merge({"forms": forms}, self.lang)
            else:
                payload = json.loads(open(path, encoding="utf-8").read())
                count = self.data.merge(payload, self.lang)
        except (OSError, ValueError, csv.Error) as exc:
            self._error(f"导入失败：{exc}")
            return
        self.refresh()
        self.status.configure(text=f"已导入 {count} 条", fg=GREEN)

    def export_lang(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self.win,
            title="导出词形与变位表",
            defaultextension=".json",
            initialfile=f"{self.lang or 'lang'}.json",
            filetypes=[("JSON", "*.json")],
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(self.data.export(self.lang), handle, ensure_ascii=False, indent=2)
        except OSError as exc:
            self._error(f"导出失败：{exc}")
            return
        self.status.configure(text=f"已导出：{path}", fg=GREEN)

    # ------------------------------------------------------------------ 变位表
    def import_tables(self) -> None:
        path = filedialog.askopenfilename(
            parent=self.win,
            title="导入变位表（JSON）",
            filetypes=[("JSON", "*.json"), ("全部文件", "*.*")],
        )
        if not path:
            return
        try:
            payload = json.loads(open(path, encoding="utf-8").read())
            count = self.data.merge(payload, self.lang)
        except (OSError, ValueError) as exc:
            self._error(f"导入失败：{exc}")
            return
        self.refresh()
        self.status.configure(text=f"已导入 {count} 条表/词形", fg=GREEN)

    def delete_table(self) -> None:
        selected = self.table_tree.selection()
        if not selected:
            self._error("先选中一张表")
            return
        values = self.table_tree.item(selected[0], "values")
        if not values:
            return
        self.data.remove_table(self.lang, values[0])
        self.refresh()
        self.status.configure(text=f"已删除表：{values[0]}", fg=MUTED)

    def preview_table(self) -> None:
        selected = self.table_tree.selection()
        if not selected:
            self._error("先选中一张表")
            return
        values = self.table_tree.item(selected[0], "values")
        if not values:
            return
        groups = self.data.table(self.lang, values[0]) or []
        lines = [f"{values[0]}", ""]
        for group in groups:
            lines.append(f"[{group.get('zh') or group.get('key') or ''}]")
            for person, form in group.get("rows") or []:
                lines.append(f"  {person or '':12s} {form}")
            lines.append("")
        messagebox.showinfo("变位表预览", "\n".join(lines), parent=self.win)

    # ------------------------------------------------------------ 词典提取
    def extract_forms(self) -> None:
        lemma = self.var_lemma.get().strip()
        if not lemma:
            self._error("先在「原形」输入框里填一个词")
            return
        if self.dicts is None:
            self._error("词典管理器不可用")
            return
        dictionary = self.dicts.dictionary(self.lang)
        if dictionary is None:
            self._error(f"{self.lang} 还没有配置词典")
            return
        from .dict_forms import redirect_forms

        def on_done(forms) -> None:
            if not forms:
                self.status.configure(
                    text="词典里没有指向这个词的 @@@LINK 变形（这本词典可能没收录）",
                    fg=MUTED,
                )
                return
            ExtractFormsDialog(
                self,
                lemma,
                forms,
                lambda selected: self._apply_extracted(self.lang, lemma, selected),
            )

        self._start_scan(
            "从词典提取变形",
            f"正在扫描词典：{lemma}",
            lambda cancel, progress: redirect_forms(
                dictionary,
                lemma,
                data_dir=self.config.data_dir,
                progress=progress,
                cancel=cancel,
            ),
            on_done,
        )

    def bulk_extract(self) -> None:
        if self.dicts is None:
            self._error("词典管理器不可用")
            return
        dictionary = self.dicts.dictionary(self.lang)
        if dictionary is None:
            self._error(f"{self.lang} 还没有配置词典")
            return
        from .dict_forms import bulk_candidates

        def on_done(candidates) -> None:
            if not candidates:
                self.status.configure(
                    text="词典里没有可提取的 @@@LINK 变形（这本词典可能没收录）",
                    fg=MUTED,
                )
                return
            BulkExtractDialog(self, candidates, self._apply_bulk)

        self._start_scan(
            "批量提取词典变形",
            "正在扫描整本词典（首次可能 30–60 秒）",
            lambda cancel, progress: bulk_candidates(
                dictionary,
                data_dir=self.config.data_dir,
                progress=progress,
                cancel=cancel,
            ),
            on_done,
        )

    def _start_scan(self, title: str, label_text: str, worker, on_done) -> None:
        if self._extract_progress is not None:
            return
        self._extract_cancel.clear()
        self._extract_queue = queue.Queue()
        self._extract_text = label_text
        self._extract_on_done = on_done
        progress = tk.Toplevel(self.win)
        progress.title(title)
        progress.configure(bg=BG)
        progress.geometry("460x140")
        progress.transient(self.win)
        progress.attributes("-topmost", True)
        progress.grab_set()
        progress.protocol(
            "WM_DELETE_WINDOW",
            lambda: (self._extract_cancel.set(), self._close_extract_progress()),
        )
        label = tk.Label(
            progress,
            text=f"{label_text}\n首次扫描大词典可能需要 30–60 秒…",
            bg=BG, fg=TEXT, font=(FONT_FAMILY, 9), justify="left", anchor="w",
            wraplength=420,
        )
        label.pack(fill="x", padx=14, pady=(12, 8))
        self._button(progress, "取消", self._extract_cancel.set).pack(side="right", padx=14)
        self._extract_progress = progress
        self._extract_label = label

        queue_ = self._extract_queue

        def thread_worker() -> None:
            try:
                result = worker(
                    self._extract_cancel.is_set,
                    lambda done, total: queue_.put(("progress", done, total)),
                )
                queue_.put(("done", result))
            except Exception as exc:  # noqa: BLE001 - 后台线程异常回报给界面
                queue_.put(("error", str(exc)))

        threading.Thread(target=thread_worker, daemon=True).start()
        self.win.after(100, self._poll_scan)

    def _poll_scan(self) -> None:
        progress = self._extract_progress
        if progress is None or not progress.winfo_exists():
            self._extract_progress = None
            return
        try:
            kind, *payload = self._extract_queue.get_nowait()
        except queue.Empty:
            self.win.after(100, self._poll_scan)
            return
        if kind == "progress":
            done, total = payload
            percent = int(done * 100 / total) if total else 0
            self._extract_label.configure(
                text=f"{self._extract_text}\n{percent}%（{done}/{total}）"
            )
            self.win.after(100, self._poll_scan)
            return
        self._close_extract_progress()
        if kind == "error":
            self._error(f"提取失败：{payload[0]}")
            return
        result = payload[0]
        if result is None:
            self.status.configure(text="已取消提取", fg=MUTED)
            return
        callback = self._extract_on_done
        self._extract_on_done = None
        if callback is not None:
            callback(result)

    def _close_extract_progress(self) -> None:
        progress = self._extract_progress
        self._extract_progress = None
        if progress is not None:
            try:
                progress.destroy()
            except tk.TclError:
                pass

    def _apply_extracted(self, lang: str, lemma: str, forms: list[str]) -> None:
        for form in forms:
            self.data.add_form(lang, form, lemma)
        self.refresh()
        self.status.configure(text=f"从词典添加 {len(forms)} 条：{lemma}", fg=GREEN)

    def _apply_bulk(self, mapping: dict[str, str]) -> None:
        added = self.data.add_forms(self.lang, mapping)
        self.refresh()
        self.status.configure(
            text=f"批量提取：新增 {added} 条（已存在的不覆盖）", fg=GREEN
        )

    # ------------------------------------------------------------------ 错误
    def _error(self, message: str) -> None:
        self.status.configure(text=message, fg=RED)


class ExtractFormsDialog:
    """展示词典里指向某个原形的 @@@LINK，让用户确认哪些是真正的变形。"""

    def __init__(self, parent: UserLangDialog, lemma: str, candidates, on_apply) -> None:
        self.parent = parent
        self.lemma = lemma
        self.candidates = candidates
        self.on_apply = on_apply

        self.win = tk.Toplevel(parent.win)
        self.win.title("从词典提取变形")
        self.win.configure(bg=BG)
        self.win.geometry("580x520")
        self.win.transient(parent.win)
        self.win.attributes("-topmost", True)
        self.win.grab_set()

        outer = tk.Frame(self.win, bg=BG)
        outer.pack(fill="both", expand=True, padx=16, pady=14)
        tk.Label(
            outer, text=f"词典里指向「{lemma}」的重定向",
            bg=BG, fg=TEXT, font=(FONT_FAMILY, 12, "bold"), anchor="w",
        ).pack(fill="x")
        tk.Label(
            outer,
            text="这些是词典自己的 @@@LINK；不一定都是变形，请只保留真正的屈折形式。",
            bg=BG, fg=DIM, font=(FONT_FAMILY, 9), anchor="w",
            justify="left", wraplength=540,
        ).pack(fill="x", pady=(2, 8))

        box = tk.Frame(outer, bg=PANEL)
        box.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(
            box,
            columns=("form", "similarity"),
            show="headings",
            selectmode="extended",
            height=13,
            style="UL.Treeview",
        )
        self.tree.heading("form", text="变形")
        self.tree.heading("similarity", text="相似度")
        self.tree.column("form", width=360, anchor="w")
        self.tree.column("similarity", width=100, anchor="e")
        scroll = tk.Scrollbar(box, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        scroll.pack(side="right", fill="y", pady=8)

        selected = []
        for form, ratio in candidates:
            item = self.tree.insert("", "end", values=(form, f"{round(ratio * 100)}%"))
            if ratio >= 0.5:
                selected.append(item)
        if selected:
            self.tree.selection_set(*selected)

        bar = tk.Frame(outer, bg=BG)
        bar.pack(fill="x", pady=(10, 0))
        self.parent._button(bar, "采用选中", self.apply, primary=True).pack(side="right")
        self.parent._button(bar, "取消", self.win.destroy).pack(side="right", padx=(0, 8))
        tk.Label(
            bar, text=f"共 {len(candidates)} 个", bg=BG, fg=DIM,
            font=(FONT_FAMILY, 9),
        ).pack(side="left")

    def apply(self) -> None:
        selected = self.tree.selection()
        forms = []
        for item in selected:
            values = self.tree.item(item, "values")
            if values:
                forms.append(values[0])
        if not forms:
            messagebox.showinfo("从词典提取", "先选中至少一个变形。", parent=self.win)
            return
        self.on_apply(forms)
        self.win.destroy()


class BulkExtractDialog:
    """整本词典的批量提取：一个相似度阈值，预览数量后全部导入。"""

    def __init__(self, parent: UserLangDialog, candidates, on_apply) -> None:
        self.parent = parent
        self.candidates = candidates
        self.on_apply = on_apply

        self.win = tk.Toplevel(parent.win)
        self.win.title("批量提取整本词典")
        self.win.configure(bg=BG)
        self.win.geometry("620x380")
        self.win.transient(parent.win)
        self.win.attributes("-topmost", True)
        self.win.grab_set()

        outer = tk.Frame(self.win, bg=BG)
        outer.pack(fill="both", expand=True, padx=16, pady=14)
        tk.Label(
            outer, text="批量提取整本词典", bg=BG, fg=TEXT,
            font=(FONT_FAMILY, 12, "bold"), anchor="w",
        ).pack(fill="x")
        tk.Label(
            outer,
            text="0% = 全部词典链接（可能混入近义词/拼写变体）；越高越严格；"
            "已存在的用户词形不会被覆盖。",
            bg=BG, fg=DIM, font=(FONT_FAMILY, 9), anchor="w",
            justify="left", wraplength=560,
        ).pack(fill="x", pady=(2, 10))

        self.var_threshold = tk.DoubleVar(value=0.0)
        row = tk.Frame(outer, bg=BG)
        row.pack(fill="x")
        tk.Label(row, text="相似度 ≥", bg=BG, fg=DIM, font=(FONT_FAMILY, 9)).pack(side="left")
        tk.Scale(
            row,
            from_=0.0,
            to=0.9,
            resolution=0.05,
            orient="horizontal",
            variable=self.var_threshold,
            command=lambda _v: self._update(),
            bg=BG,
            fg=TEXT,
            troughcolor=PANEL,
            activebackground=ACCENT,
            highlightthickness=0,
            length=360,
        ).pack(side="left", padx=(8, 8))

        self.info = tk.Label(
            outer, text="", bg=BG, fg=TEXT, font=(FONT_FAMILY, 10, "bold"), anchor="w",
        )
        self.info.pack(fill="x", pady=(8, 4))
        self.samples = tk.Label(
            outer, text="", bg=BG, fg=MUTED, font=(FONT_FAMILY, 9), anchor="w",
            justify="left", wraplength=560,
        )
        self.samples.pack(fill="x")

        bar = tk.Frame(outer, bg=BG)
        bar.pack(fill="x", side="bottom", pady=(10, 0))
        self.apply_btn = self.parent._button(bar, "全部导入", self.apply, primary=True)
        self.apply_btn.pack(side="right")
        self.parent._button(bar, "取消", self.win.destroy).pack(side="right", padx=(0, 8))
        self._update()

    def _filtered(self):
        threshold = float(self.var_threshold.get())
        return [item for item in self.candidates if item[2] >= threshold]

    def _update(self) -> None:
        if not hasattr(self, "apply_btn"):
            return
        selected = self._filtered()
        targets = len({item[0] for item in selected})
        threshold = int(round(float(self.var_threshold.get()) * 100))
        self.info.configure(
            text=f"相似度 ≥ {threshold}%：{len(selected)} 条变形，{targets} 个原形"
        )
        self.apply_btn.configure(text=f"全部导入 {len(selected)} 条")
        sample = "\n".join(
            f"{target} ← {form}" for target, form, _ratio in selected[:6]
        )
        self.samples.configure(text=sample)

    def apply(self) -> None:
        selected = self._filtered()
        mapping: dict[str, str] = {}
        for target, form, _ratio in selected:
            mapping.setdefault(form, target)
        if not mapping:
            messagebox.showinfo("批量提取", "当前阈值下没有可导入的变形。", parent=self.win)
            return
        self.on_apply(mapping)
        self.win.destroy()

