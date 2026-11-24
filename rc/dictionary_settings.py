"""本地词典：全局词典库 + 语言组（显示、顺序、默认）。"""

from __future__ import annotations

import copy
import logging
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, simpledialog, ttk

from . import dict_config
from .i18n import lang_display_name, tr
from .popup import ACCENT, BG, DIM, FONT_FAMILY, GREEN, MUTED, PANEL, PANEL_ALT, RED, TEXT
from .textutil import display
from .theme import BORDER_SOFT, ON_ACCENT
from .uiutil import bind_defocus

log = logging.getLogger("rc")

_FILE_TYPES = [
    (
        "MDX / StarDict / DSL / Dictd / XDXF",
        "*.mdx *.ifo *.dsl *.dsl.dz *.index *.xdxf *.xdxf.dz",
    ),
    ("所有文件", "*.*"),
]


class DictionarySettings:
    def __init__(self, root: tk.Tk, config, manager, on_saved) -> None:
        self.root = root
        self.config = config
        self.manager = manager
        self.on_saved = on_saved
        self.draft = copy.deepcopy(config.data)
        self.page = "library"
        self._canvas = None
        self.list_frame = None
        self._drag_rows: list[tuple[str, str, tk.Frame]] = []
        self._drag_active: tuple[str, str] | None = None
        self._index_queue: queue.Queue = queue.Queue()
        self._index_running = False
        self._index_total = 0
        self._index_done = 0

        self.win = tk.Toplevel(root)
        self.win.title("本地词典设置")
        self.win.configure(bg=BG)
        self.win.geometry("820x680")
        self.win.attributes("-topmost", True)
        self._build()
        bind_defocus(self.win)

    def _build(self) -> None:
        dict_config.normalize(self.draft)
        outer = tk.Frame(self.win, bg=BG)
        outer.pack(fill="both", expand=True, padx=18, pady=14)

        tk.Label(
            outer, text="本地词典", bg=BG, fg=TEXT, font=(FONT_FAMILY, 14, "bold"), anchor="w"
        ).pack(fill="x")
        tk.Label(
            outer,
            text="词典先进入词典库；再到「查词组」把它加入一个或多个语言。"
            "同一本词典可以在多个语言组里使用。",
            bg=BG,
            fg=DIM,
            font=(FONT_FAMILY, 9),
            anchor="w",
            justify="left",
            wraplength=760,
        ).pack(fill="x", pady=(2, 8))

        self.var_enabled = tk.BooleanVar(value=bool(self.draft.get("use_dictionary", True)))
        tk.Checkbutton(
            outer,
            text="翻译时自动查词典（释义/音标/例句优先用词典，模型只补上下文义）",
            variable=self.var_enabled,
            bg=BG,
            fg=TEXT,
            selectcolor=BORDER_SOFT,
            activebackground=BG,
            activeforeground=TEXT,
            font=(FONT_FAMILY, 9),
            anchor="w",
        ).pack(fill="x", pady=(0, 6))

        tabs = tk.Frame(outer, bg=BG)
        tabs.pack(fill="x", pady=(0, 6))
        self.tab_library = tk.Label(
            tabs, text="词典库", bg=PANEL, fg=TEXT, font=(FONT_FAMILY, 9),
            padx=12, pady=4, cursor="hand2",
        )
        self.tab_library.pack(side="left")
        self.tab_groups = tk.Label(
            tabs, text="查词组", bg=BG, fg=DIM, font=(FONT_FAMILY, 9),
            padx=12, pady=4, cursor="hand2",
        )
        self.tab_groups.pack(side="left", padx=(6, 0))
        self.tab_library.bind("<Button-1>", lambda _e: self._show_page("library"))
        self.tab_groups.bind("<Button-1>", lambda _e: self._show_page("groups"))

        body = tk.Frame(outer, bg=BG)
        body.pack(fill="both", expand=True)
        self._canvas = tk.Canvas(body, bg=BG, highlightthickness=0)
        scroll = tk.Scrollbar(body, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=scroll.set)
        self._canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.list_frame = tk.Frame(self._canvas, bg=BG)
        window = self._canvas.create_window((0, 0), window=self.list_frame, anchor="nw")
        self.list_frame.bind(
            "<Configure>",
            lambda _e: self._canvas.configure(scrollregion=self._canvas.bbox("all")),
        )
        self._canvas.bind(
            "<Configure>",
            lambda e: self._canvas.itemconfigure(window, width=e.width),
        )

        bar = tk.Frame(outer, bg=BG)
        bar.pack(fill="x", side="bottom", pady=(10, 0))
        self.index_status = tk.Label(
            outer,
            text="",
            bg=BG,
            fg=MUTED,
            font=(FONT_FAMILY, 8),
            anchor="w",
        )
        self.index_progress = ttk.Progressbar(
            outer,
            mode="determinate",
            length=240,
            style="TProgressbar",
        )
        self._button(bar, "保存", self.save, primary=True).pack(side="right")
        self._button(bar, "取消", self.win.destroy).pack(side="right", padx=(0, 8))
        self._button(bar, "词典映射…", self.open_profiles).pack(side="left")
        self._render()
        self.win.after(300, self._index_existing_if_missing)

    def _button(self, parent, text, command, primary=False):
        bg = ACCENT if primary else PANEL
        fg = ON_ACCENT if primary else TEXT
        label = tk.Label(
            parent, text=text, bg=bg, fg=fg, font=(FONT_FAMILY, 9), padx=10, pady=4, cursor="hand2"
        )
        label.bind("<Button-1>", lambda _e: command())
        return label

    # ------------------------------------------------------------------ pages
    def _show_page(self, page: str) -> None:
        self.page = page
        self.tab_library.configure(
            bg=PANEL if page == "library" else BG,
            fg=TEXT if page == "library" else DIM,
        )
        self.tab_groups.configure(
            bg=PANEL if page == "groups" else BG,
            fg=TEXT if page == "groups" else DIM,
        )
        self._render()

    def _render(self) -> None:
        dict_config.normalize(self.draft)
        self._drag_rows = []
        for child in self.list_frame.winfo_children():
            child.destroy()
        if self.page == "library":
            self._render_library()
        else:
            self._render_groups()

    def _render_library(self) -> None:
        head = tk.Frame(self.list_frame, bg=BG)
        head.pack(fill="x", pady=(0, 6))
        self._button(head, "+ 导入词典…", self.import_files).pack(side="left")
        self._button(head, "为已有词典建索引…", self.index_existing).pack(
            side="left", padx=(6, 0)
        )
        tk.Label(
            head, text="导入后先进入词典库；未加入任何语言组时不会参与查词。",
            bg=BG, fg=DIM, font=(FONT_FAMILY, 8),
        ).pack(side="left", padx=(10, 0))

        lib = dict_config.library(self.draft)
        if not lib:
            tk.Label(
                self.list_frame, text="词典库还是空的", bg=BG, fg=MUTED,
                font=(FONT_FAMILY, 9), anchor="w",
            ).pack(fill="x", pady=(8, 0))
            return
        for item in sorted(lib.values(), key=lambda x: x.get("name") or x.get("mdx", "")):
            self._render_library_item(item)

    def _render_library_item(self, item: dict) -> None:
        row = tk.Frame(self.list_frame, bg=PANEL)
        row.pack(fill="x", pady=(0, 5))
        path = Path(str(item.get("mdx") or ""))
        name = str(item.get("name") or "").strip() or path.stem
        info = tk.Frame(row, bg=PANEL)
        info.pack(side="left", fill="x", expand=True, padx=10, pady=5)
        tk.Label(
            info, text=display(name, 58), bg=PANEL, fg=TEXT,
            font=(FONT_FAMILY, 9), anchor="w",
        ).pack(fill="x")
        tk.Label(
            info, text=display(str(path), 76), bg=PANEL, fg=DIM,
            font=(FONT_FAMILY, 8), anchor="w",
        ).pack(fill="x")
        langs = dict_config.languages_of(self.draft, item["id"])
        assigned = ", ".join(dict_config.label(self.draft, lang) for lang in langs) or "未分配"
        state, color = self._item_state(path)
        tk.Label(
            row, text=assigned, bg=PANEL, fg=(GREEN if langs else MUTED),
            font=(FONT_FAMILY, 8), width=14, anchor="w",
        ).pack(side="left", padx=(0, 6))
        tk.Label(
            row, text=state, bg=PANEL, fg=color, font=(FONT_FAMILY, 8), width=9, anchor="w"
        ).pack(side="left")
        script_var = tk.BooleanVar(value=bool(item.get("allow_scripts", True)))
        tk.Checkbutton(
            row,
            text="允许脚本",
            variable=script_var,
            command=lambda i=item["id"], v=script_var: self._set_scripts(i, v),
            bg=PANEL,
            fg=MUTED,
            selectcolor=BORDER_SOFT,
            activebackground=PANEL,
            activeforeground=TEXT,
            font=(FONT_FAMILY, 8),
        ).pack(side="left", padx=(4, 4))
        self._button(row, "改名", lambda i=item["id"]: self._rename_library(i)).pack(
            side="left", padx=(0, 4)
        )
        self._button(row, "删除", lambda i=item["id"]: self._remove_library(i)).pack(
            side="left", padx=(0, 8)
        )

    def _set_scripts(self, item_id: str, var: tk.BooleanVar) -> None:
        allowed = bool(var.get())
        dict_config.set_scripts_allowed(self.draft, item_id, allowed)
        if allowed:
            self._toast("已允许词典脚本执行（有安全风险）")
        else:
            self._toast("已关闭词典脚本")

    def _render_groups(self) -> None:
        languages = self.draft.get("languages") or {}
        for code, lang_info in languages.items():
            self._render_group(code, lang_info)

    def _render_group(self, code: str, lang_info: dict) -> None:
        box = tk.Frame(self.list_frame, bg=PANEL)
        box.pack(fill="x", pady=(0, 8))
        head = tk.Frame(box, bg=PANEL)
        head.pack(fill="x", padx=10, pady=(7, 3))
        tk.Label(
            head, text=f"{lang_display_name(lang_info, code)}  {code}",
            bg=PANEL, fg=TEXT, font=(FONT_FAMILY, 10, "bold"), anchor="w",
        ).pack(side="left")
        group_muted = bool(dict_config.group(self.draft, code).get("group_muted"))
        muted_var = tk.BooleanVar(value=group_muted)
        tk.Checkbutton(
            head, text=tr("静音"), variable=muted_var,
            command=lambda c=code, v=muted_var: self._set_group_muted(c, v.get()),
            bg=PANEL, fg=MUTED if group_muted else DIM, selectcolor=BORDER_SOFT,
            activebackground=PANEL, activeforeground=TEXT, font=(FONT_FAMILY, 8),
        ).pack(side="left", padx=(10, 0))
        self._button(
            head, "+ 从词典库添加…", lambda c=code: self._pick_for_group(c)
        ).pack(side="right")

        items = dict_config.items(self.draft, code)
        hidden = dict_config.muted(self.draft, code)
        popup_hidden = dict_config.muted(self.draft, code, context="popup")
        default = dict_config.default_id(self.draft, code)
        if not items:
            tk.Label(
                box, text="还没有加入词典", bg=PANEL, fg=MUTED,
                font=(FONT_FAMILY, 8), anchor="w",
            ).pack(fill="x", padx=14, pady=(2, 8))
            return

        by_id = {item["id"]: item for item in items}

        def label_for(item_id: str) -> str:
            item = by_id.get(item_id) or {}
            path = Path(str(item.get("mdx") or ""))
            return str(item.get("name") or "").strip() or path.stem or item_id

        anki = dict_config.anki_id(self.draft, code)
        follow_label = tr(f"跟随查词默认（{label_for(default)}）")
        anki_label = follow_label if not anki else label_for(anki)
        anki_row = tk.Frame(box, bg=PANEL)
        anki_row.pack(fill="x", padx=14, pady=(0, 4))
        tk.Label(
            anki_row, text=tr("Anki 释义"), bg=PANEL, fg=MUTED,
            font=(FONT_FAMILY, 8), anchor="w",
        ).pack(side="left")
        choices = [follow_label] + [label_for(item["id"]) for item in items]
        choice_to_id = {follow_label: ""}
        choice_to_id.update({label_for(item["id"]): item["id"] for item in items})
        var = tk.StringVar(value=anki_label)
        menu = tk.OptionMenu(anki_row, var, *choices)
        menu.configure(
            bg=PANEL_ALT, fg=TEXT, activebackground=PANEL, activeforeground=TEXT,
            font=(FONT_FAMILY, 8), highlightthickness=0, bd=0,
        )
        menu["menu"].configure(
            bg=PANEL_ALT, fg=TEXT, activebackground=ACCENT, activeforeground=ON_ACCENT,
            font=(FONT_FAMILY, 8),
        )
        menu.pack(side="left", padx=(8, 0))

        def choose(_value=None) -> None:
            selected = var.get()
            dict_config.set_anki(self.draft, code, choice_to_id.get(selected, ""))
            self._render()

        var.trace_add("write", lambda *_a: choose())

        for index, item in enumerate(items):
            self._render_group_item(
                box,
                code,
                item,
                index,
                item["id"] not in hidden,
                item["id"] not in popup_hidden,
                default == item["id"],
            )
        tk.Frame(box, bg=PANEL, height=4).pack(fill="x")

    def _render_group_item(
        self,
        parent,
        code: str,
        item: dict,
        index: int,
        visible: bool,
        popup_visible: bool,
        is_default: bool,
    ) -> None:
        row = tk.Frame(parent, bg=PANEL)
        row.pack(fill="x", padx=10, pady=2)
        handle = tk.Label(
            row, text="⋮⋮", bg=PANEL, fg=MUTED, font=(FONT_FAMILY, 9),
            cursor="fleur",
        )
        handle.pack(side="left", padx=(0, 4))
        handle.bind(
            "<ButtonPress-1>",
            lambda e, c=code, i=item["id"]: self._drag_start(c, i, e),
        )
        handle.bind("<B1-Motion>", self._drag_motion)
        handle.bind("<ButtonRelease-1>", self._drag_end)
        self._drag_rows.append((code, item["id"], row))

        panel_var = tk.BooleanVar(value=visible)
        tk.Checkbutton(
            row, text="面板", variable=panel_var,
            command=lambda: self._set_visible(
                code, item["id"], panel_var.get(), context="panel"
            ),
            bg=PANEL, fg=TEXT if visible else MUTED, selectcolor=BORDER_SOFT,
            activebackground=PANEL, activeforeground=TEXT, font=(FONT_FAMILY, 8),
        ).pack(side="left")
        popup_var = tk.BooleanVar(value=popup_visible)
        tk.Checkbutton(
            row, text="弹窗", variable=popup_var,
            command=lambda: self._set_visible(
                code, item["id"], popup_var.get(), context="popup"
            ),
            bg=PANEL, fg=TEXT if popup_visible else MUTED, selectcolor=BORDER_SOFT,
            activebackground=PANEL, activeforeground=TEXT, font=(FONT_FAMILY, 8),
        ).pack(side="left", padx=(2, 4))
        star = tk.Label(
            row, text="★" if is_default else "☆",
            bg=PANEL, fg=ACCENT if is_default else MUTED,
            font=(FONT_FAMILY, 11), cursor="hand2",
        )
        star.pack(side="left", padx=(6, 4))
        star.bind("<Button-1>", lambda _e, i=item["id"]: self._set_default(code, i))
        path = Path(str(item.get("mdx") or ""))
        name = str(item.get("name") or "").strip() or path.stem
        info = tk.Frame(row, bg=PANEL)
        info.pack(side="left", fill="x", expand=True)
        tk.Label(
            info, text=display(name, 52), bg=PANEL, fg=TEXT if visible else MUTED,
            font=(FONT_FAMILY, 9), anchor="w",
        ).pack(fill="x")
        tk.Label(
            info, text=display(str(path), 64), bg=PANEL, fg=DIM,
            font=(FONT_FAMILY, 8), anchor="w",
        ).pack(fill="x")
        self._button(row, "↑", lambda c=code, i=index: self._move(c, i, -1)).pack(side="left")
        self._button(row, "↓", lambda c=code, i=index: self._move(c, i, 1)).pack(
            side="left", padx=(2, 2)
        )
        self._button(row, "移出组", lambda c=code, i=item["id"]: self._remove_from_group(c, i)).pack(
            side="left"
        )

    def _set_group_muted(self, code: str, muted: bool) -> None:
        dict_config.set_group_muted(self.draft, code, muted)
        self._render()

    @staticmethod
    def _item_state(path: Path) -> tuple[str, str]:
        if not str(path):
            return "未配置", MUTED
        if not path.exists():
            return "文件不存在", RED
        name = path.name.lower()
        if name.endswith(".dsl.dz") or path.suffix.lower() == ".dsl":
            return "DSL", GREEN
        if name.endswith(".xdxf.dz") or path.suffix.lower() == ".xdxf":
            return "XDXF", GREEN
        suffix = path.suffix.lower()
        if suffix in (".ifo", ".idx"):
            return "StarDict", GREEN
        if suffix == ".index":
            return "Dictd", GREEN
        return "已配置", GREEN

    # ------------------------------------------------------------------ actions
    def import_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title=tr("选择词典（可多选）"),
            filetypes=[(tr(label), pattern) for label, pattern in _FILE_TYPES],
            parent=self.win,
        )
        if not paths:
            return
        added = []
        path_by_id: dict[str, tuple[str, str]] = {}
        for path in paths:
            item = dict_config.add_library_item(self.draft, path)
            added.append(item["id"])
            path_by_id[item["id"]] = (
                str(item.get("mdx") or path),
                str(item.get("mdd") or ""),
            )
        self._render()
        if added:
            self._assign_dialog(added)
            self._start_indexing([path_by_id[item_id] for item_id in added])

    # ------------------------------------------------------------ index warming
    @staticmethod
    def _index_paths(item: dict) -> tuple[str, str]:
        return str(item.get("mdx") or ""), str(item.get("mdd") or "")

    @staticmethod
    def _needs_index(path: str, mdd: str = "") -> bool:
        source = Path(path)
        if not source.exists():
            return False
        if source.suffix.lower() == ".ifo":
            index_source = source.with_suffix("")
        else:
            index_source = source
        index = index_source.with_name(index_source.name + ".rcidx")
        fuzzy = source.with_name(source.name + ".rcfuzzy")
        if not index.exists() or not fuzzy.exists():
            return True
        if mdd:
            mdd_path = Path(mdd)
            if mdd_path.exists():
                mdd_index = mdd_path.with_name(mdd_path.name + ".rcidx")
                if not mdd_index.exists():
                    return True
        return False

    def index_existing(self) -> None:
        paths = [
            self._index_paths(item)
            for item in dict_config.library(self.draft).values()
            if self._needs_index(*self._index_paths(item))
        ]
        if not paths:
            self._toast("所有词典的索引都是最新的")
            return
        self._start_indexing(paths)

    def _index_existing_if_missing(self) -> None:
        try:
            if not self.win.winfo_exists() or getattr(self, "_index_running", False):
                return
            self.index_existing()
        except tk.TclError:
            pass

    def _start_indexing(self, paths: list[tuple[str, str]]) -> None:
        if not paths:
            return
        if getattr(self, "_index_running", False):
            return
        self._index_running = True
        self._index_total = len(paths)
        self._index_done = 0
        self.index_status.configure(text=tr("正在建立词典索引…"))
        self.index_progress.configure(maximum=max(1, self._index_total), value=0)
        self.index_status.pack(fill="x", side="bottom")
        self.index_progress.pack(fill="x", side="bottom", pady=(2, 0))
        thread = threading.Thread(
            target=self._index_worker, args=(paths,), daemon=True
        )
        thread.start()
        self.win.after(80, self._poll_index_queue)

    def _index_worker(self, paths: list[tuple[str, str]]) -> None:
        from . import fuzzy
        from .dictionary import Dictionary

        for path, mdd in paths:
            self._index_queue.put(("file", Path(path).name))
            dictionary = None
            try:
                dictionary = Dictionary(path, mdd or None)
                fuzzy.build_index(dictionary)
                self._index_queue.put(("done", Path(path).name))
            except Exception as exc:  # noqa: BLE001 - 索引失败不阻止读词
                self._index_queue.put(("error", f"{Path(path).name}: {exc}"))
            finally:
                if dictionary is not None:
                    try:
                        dictionary.close()
                    except Exception as exc:  # noqa: BLE001 - 关闭失败不阻止索引
                        log.debug("关闭索引词典失败: %s", exc)
        self._index_queue.put(("finished", None))

    def _poll_index_queue(self) -> None:
        try:
            if not self.win.winfo_exists():
                return
        except tk.TclError:
            return
        try:
            while True:
                kind, payload = self._index_queue.get_nowait()
                if kind == "file":
                    self.index_status.configure(
                        text=tr("正在建立索引：{name}").format(name=payload)
                    )
                elif kind == "done":
                    self._index_done += 1
                    self.index_progress.configure(value=self._index_done)
                elif kind == "error":
                    self.index_status.configure(text=tr("索引失败：{error}").format(error=payload))
                elif kind == "finished":
                    self._index_running = False
                    self.index_status.configure(text=tr("索引完成"))
                    self.win.after(2500, self._clear_index_status)
                    return
        except queue.Empty:
            pass
        if getattr(self, "_index_running", False):
            try:
                self.win.after(100, self._poll_index_queue)
            except tk.TclError:
                pass

    def _clear_index_status(self) -> None:
        try:
            self.index_status.pack_forget()
            self.index_progress.pack_forget()
        except tk.TclError:
            pass

    def _assign_dialog(self, item_ids: list[str]) -> None:
        dialog = tk.Toplevel(self.win)
        dialog.title("加入语言组")
        dialog.configure(bg=BG)
        dialog.geometry("440x360")
        dialog.attributes("-topmost", True)
        tk.Label(
            dialog, text="选择这些词典要加入的语言组", bg=BG, fg=TEXT,
            font=(FONT_FAMILY, 11, "bold"), anchor="w",
        ).pack(fill="x", padx=14, pady=(12, 4))
        tk.Label(
            dialog, text="可以全不选，之后在「查词组」里再添加。",
            bg=BG, fg=DIM, font=(FONT_FAMILY, 8), anchor="w",
        ).pack(fill="x", padx=14, pady=(0, 8))
        vars_map = {}
        for code, lang_info in (self.draft.get("languages") or {}).items():
            var = tk.BooleanVar(value=False)
            vars_map[code] = var
            tk.Checkbutton(
                dialog,
                text=f"{lang_display_name(lang_info, code)}  {code}",
                variable=var, bg=BG, fg=TEXT, selectcolor=BORDER_SOFT,
                activebackground=BG, activeforeground=TEXT, font=(FONT_FAMILY, 9),
                anchor="w",
            ).pack(fill="x", padx=24, pady=1)
        bar = tk.Frame(dialog, bg=BG)
        bar.pack(side="bottom", fill="x", padx=14, pady=10)
        self._button(bar, "加入", lambda: self._apply_assignment(item_ids, vars_map, dialog), primary=True).pack(side="right")
        self._button(bar, "取消", dialog.destroy).pack(side="right", padx=(0, 8))

    def _apply_assignment(self, item_ids: list[str], vars_map: dict, dialog) -> None:
        for code, var in vars_map.items():
            if var.get():
                for item_id in item_ids:
                    dict_config.add_to_group(self.draft, code, item_id, visible=True)
        dialog.destroy()
        self._render()

    def _pick_for_group(self, code: str) -> None:
        lib = dict_config.library(self.draft)
        members = set(dict_config.group_ids(self.draft, code))
        candidates = [item for item in lib.values() if item["id"] not in members]
        if not candidates:
            self._toast("词典库里的词典都已经在这个组里了")
            return
        dialog = tk.Toplevel(self.win)
        dialog.title("从词典库添加")
        dialog.configure(bg=BG)
        dialog.geometry("520x420")
        dialog.attributes("-topmost", True)
        tk.Label(
            dialog, text="勾选要加入该语言组的词典", bg=BG, fg=TEXT,
            font=(FONT_FAMILY, 10, "bold"), anchor="w",
        ).pack(fill="x", padx=14, pady=(12, 6))
        vars_map = {}
        for item in sorted(candidates, key=lambda x: x.get("name") or x["mdx"]):
            var = tk.BooleanVar(value=False)
            vars_map[item["id"]] = var
            name = item.get("name") or Path(item["mdx"]).stem
            tk.Checkbutton(
                dialog, text=display(name, 44), variable=var,
                bg=BG, fg=TEXT, selectcolor=BORDER_SOFT,
                activebackground=BG, activeforeground=TEXT, font=(FONT_FAMILY, 9),
                anchor="w",
            ).pack(fill="x", padx=24, pady=1)
        bar = tk.Frame(dialog, bg=BG)
        bar.pack(side="bottom", fill="x", padx=14, pady=10)
        self._button(
            bar, "加入", lambda: self._apply_group_pick(code, vars_map, dialog), primary=True
        ).pack(side="right")
        self._button(bar, "取消", dialog.destroy).pack(side="right", padx=(0, 8))

    def _apply_group_pick(self, code: str, vars_map: dict, dialog) -> None:
        for item_id, var in vars_map.items():
            if var.get():
                dict_config.add_to_group(self.draft, code, item_id, visible=True)
        dialog.destroy()
        self._render()

    def _set_visible(
        self, code: str, item_id: str, visible: bool, context: str = "panel"
    ) -> None:
        dict_config.set_visible(self.draft, code, item_id, visible, context)
        self._render()

    def _set_default(self, code: str, item_id: str) -> None:
        dict_config.set_default(self.draft, code, item_id)
        self._render()

    def _move(self, code: str, index: int, delta: int) -> None:
        g = dict_config.group(self.draft, code)
        refs = g.get("items") or []
        target = index + delta
        if target < 0 or target >= len(refs):
            return
        refs[index], refs[target] = refs[target], refs[index]
        for order, ref in enumerate(refs):
            ref["order"] = order
        self._render()

    # ------------------------------------------------------------- drag order
    def _drag_start(self, code: str, item_id: str, _event) -> None:
        self._drag_active = (code, item_id)

    def _drag_motion(self, _event) -> None:
        # The actual row hit-testing is done on release; this keeps Tk's
        # default drag behavior from selecting text in labels.
        return

    def _drag_end(self, event) -> None:
        active = self._drag_active
        self._drag_active = None
        if not active:
            return
        code, item_id = active
        rows = [row for c, _i, row in self._drag_rows if c == code]
        if not rows:
            return
        target = None
        for index, row in enumerate(rows):
            try:
                top = row.winfo_rooty()
                bottom = top + row.winfo_height()
            except tk.TclError:
                continue
            if top <= event.y_root <= bottom:
                target = index
                break
        if target is None:
            return
        refs = dict_config.group(self.draft, code).get("items") or []
        ids = [ref.get("id") for ref in refs]
        if item_id not in ids:
            return
        source = ids.index(item_id)
        if source == target:
            return
        ref = refs.pop(source)
        refs.insert(target, ref)
        for order, ref_item in enumerate(refs):
            ref_item["order"] = order
        self._render()

    def _remove_from_group(self, code: str, item_id: str) -> None:
        dict_config.remove_from_group(self.draft, code, item_id)
        self._render()

    def _remove_library(self, item_id: str) -> None:
        dict_config.remove_library_item(self.draft, item_id)
        self._render()

    def _rename_library(self, item_id: str) -> None:
        item = dict_config.item_by_id(self.draft, item_id)
        if not item:
            return
        current = str(item.get("name") or "").strip() or Path(str(item.get("mdx") or "")).stem
        name = simpledialog.askstring(
            "重命名词典",
            "显示名称：",
            initialvalue=current,
            parent=self.win,
        )
        if name is None:
            return
        item["name"] = name.strip()
        self._render()

    def _toast(self, text: str) -> None:
        label = tk.Label(self.win, text=text, bg=PANEL, fg=TEXT, font=(FONT_FAMILY, 9))
        label.place(relx=0.5, rely=0.95, anchor="s")
        self.win.after(1400, label.destroy)

    # ------------------------------------------------------------------ save
    def open_profiles(self) -> None:
        from .dict_profile_editor import DictProfileEditor

        DictProfileEditor(self.win, self.config, self.manager)

    def save(self) -> None:
        dict_config.normalize(self.draft)
        self.draft["use_dictionary"] = bool(self.var_enabled.get())
        self.config.data = self.draft
        self.config.save()
        self.manager.reload()
        self.on_saved()
        self.win.destroy()
