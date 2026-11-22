"""词典设置：给每个语种指定本地 MDX/MDD。"""



from __future__ import annotations

from .uiutil import bind_defocus

import tkinter as tk
from pathlib import Path
from tkinter import filedialog

from .popup import ACCENT, BG, DIM, FONT_FAMILY, GREEN, MUTED, PANEL, RED, TEXT
from .i18n import lang_display_name, tr
from .theme import BORDER_SOFT, ON_ACCENT


class DictionarySettings:
    def __init__(self, root: tk.Tk, config, manager, on_saved) -> None:
        self.root = root
        self.config = config
        self.manager = manager
        self.on_saved = on_saved
        self.vars: dict[str, tk.StringVar] = {}
        self.status: dict[str, tk.Label] = {}

        self.win = tk.Toplevel(root)
        self.win.title("本地词典设置")
        self.win.configure(bg=BG)
        self.win.geometry("720x520")
        self.win.attributes("-topmost", True)
        self._build()
        bind_defocus(self.win)

    def _build(self) -> None:
        outer = tk.Frame(self.win, bg=BG)
        outer.pack(fill="both", expand=True, padx=18, pady=14)

        tk.Label(
            outer, text="本地词典", bg=BG, fg=TEXT, font=(FONT_FAMILY, 14, "bold"), anchor="w"
        ).pack(fill="x")
        tk.Label(
            outer,
            text="选择 MDX 文件即可，同目录的 MDD（发音/图片）会自动识别。"
            "支持 MDX 2.0；带加密锁或 1.2 老格式的词典暂时读不了。",
            bg=BG,
            fg=DIM,
            font=(FONT_FAMILY, 9),
            anchor="w",
            justify="left",
            wraplength=660,
        ).pack(fill="x", pady=(2, 10))

        bar = tk.Frame(outer, bg=BG)
        bar.pack(fill="x", side="bottom", pady=(10, 0))
        self._button(bar, "保存", self.save, primary=True).pack(side="right")
        self._button(bar, "取消", self.win.destroy).pack(side="right", padx=(0, 8))
        self._button(bar, "重新检测", self.refresh).pack(side="left")
        self._button(bar, "词典映射…", self.open_profiles).pack(side="left", padx=(8, 0))

        self.var_enabled = tk.BooleanVar(value=bool(self.config.get("use_dictionary", True)))
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
            justify="left",
            wraplength=660,
        ).pack(fill="x", pady=(0, 8))

        table = tk.Frame(outer, bg=PANEL)
        table.pack(fill="both", expand=True)
        table.columnconfigure(1, weight=1)

        tk.Label(
            table, text="语种", bg=PANEL, fg=DIM, font=(FONT_FAMILY, 8), anchor="w"
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(8, 2))
        tk.Label(
            table, text="词典文件", bg=PANEL, fg=DIM, font=(FONT_FAMILY, 8), anchor="w"
        ).grid(row=0, column=1, sticky="w", padx=6, pady=(8, 2))

        languages = self.config.data.get("languages") or {}
        dictionaries = self.config.data.get("dictionaries") or {}
        row = 1
        for code, entry in languages.items():
            label = f"{lang_display_name(entry, code)}  {code}"
            tk.Label(
                table, text=label, bg=PANEL, fg=TEXT, font=(FONT_FAMILY, 9), anchor="w"
            ).grid(row=row, column=0, sticky="w", padx=12, pady=6)

            cell = tk.Frame(table, bg=PANEL)
            cell.grid(row=row, column=1, sticky="ew", padx=6, pady=6)
            var = tk.StringVar(value=str((dictionaries.get(code) or {}).get("mdx", "")))
            self.vars[code] = var
            tk.Entry(
                cell,
                textvariable=var,
                bg=PANEL,
                fg=TEXT,
                insertbackground=TEXT,
                relief="flat",
                font=(FONT_FAMILY, 9),
            ).pack(side="left", fill="x", expand=True)
            self._button(cell, "选择…", lambda c=code: self.pick(c)).pack(side="left", padx=(6, 0))

            status = tk.Label(
                table, text="", bg=PANEL, fg=MUTED, font=(FONT_FAMILY, 8), anchor="w"
            )
            status.grid(row=row, column=2, sticky="w", padx=(6, 12), pady=6)
            self.status[code] = status
            row += 1

        self.refresh()

    def open_profiles(self) -> None:
        from .dict_profile_editor import DictProfileEditor

        DictProfileEditor(self.win, self.config, self.manager)

    def _button(self, parent, text, command, primary=False):
        bg = ACCENT if primary else PANEL
        fg = ON_ACCENT if primary else TEXT
        label = tk.Label(
            parent, text=text, bg=bg, fg=fg, font=(FONT_FAMILY, 9), padx=12, pady=5, cursor="hand2"
        )
        label.bind("<Button-1>", lambda _e: command())
        return label

    # ------------------------------------------------------------------ 动作
    def pick(self, code: str) -> None:
        path = filedialog.askopenfilename(
            title=tr(f"选择 {code} 的 MDX 词典"),
            filetypes=[(tr("MDX 词典"), "*.mdx"), (tr("所有文件"), "*.*")],
            parent=self.win,
        )
        if not path:
            return
        self.vars[code].set(path)
        self.manager.reload()
        self.refresh()

    def refresh(self) -> None:
        for code, var in self.vars.items():
            path = var.get().strip()
            label = self.status.get(code)
            if not label:
                continue
            if not path:
                label.configure(text="未配置", fg=MUTED)
                continue
            if not Path(path).exists():
                label.configure(text="文件不存在", fg=RED)
                continue
            describe = self.manager.describe(code)
            label.configure(
                text=describe, fg=(GREEN if "读取失败" not in describe else RED)
            )

    def save(self) -> None:
        table = self.config.data.setdefault("dictionaries", {})
        for code, var in self.vars.items():
            path = var.get().strip()
            entry = table.setdefault(code, {"mdx": "", "mdd": ""})
            entry["mdx"] = path
            if path:
                mdx = Path(path)
                candidates = [
                    mdx.with_suffix(".mdd"),
                    mdx.with_name(mdx.stem + ".1.mdd"),
                    mdx.parent / (mdx.stem + ".mdd"),
                ]
                found = next((str(c) for c in candidates if c.exists()), "")
                entry["mdd"] = found
            else:
                entry["mdd"] = ""
        self.config.data["use_dictionary"] = bool(self.var_enabled.get())
        self.config.save()
        self.manager.reload()
        self.on_saved()
        self.win.destroy()
