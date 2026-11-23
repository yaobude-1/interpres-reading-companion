"""复制查词设置：白名单、气泡外观和开关。"""

from __future__ import annotations

import tkinter as tk
from tkinter import colorchooser

from .i18n import tr
from .selection import foreground_exe
from .theme import (
    ACCENT,
    BG,
    DIM,
    FONT_FAMILY,
    GREEN,
    MUTED,
    PANEL,
    TEXT,
    BORDER_SOFT,
    ON_ACCENT,
)
from .uiutil import bind_defocus


class SelectionSettings:
    def __init__(self, root: tk.Tk, config, on_saved) -> None:
        self.root = root
        self.config = config
        self.on_saved = on_saved
        self.cfg = config.get("selection") or {}
        self.bubble = dict(self.cfg.get("bubble") or {})

        self.win = tk.Toplevel(root)
        self.win.title(tr("复制查词设置"))
        self.win.configure(bg=BG)
        self.win.geometry("640x560")
        self.win.attributes("-topmost", True)
        self._build()
        bind_defocus(self.win)

    def _build(self) -> None:
        outer = tk.Frame(self.win, bg=BG)
        outer.pack(fill="both", expand=True, padx=18, pady=14)

        tk.Label(
            outer, text=tr("复制查词"), bg=BG, fg=TEXT,
            font=(FONT_FAMILY, 14, "bold"), anchor="w",
        ).pack(fill="x")
        tk.Label(
            outer,
            text=tr(
                "在阅读器里 Ctrl+C 或右键复制文本后，程序自动判断查词还是翻译，"
                "不再出现划词小按钮。"
            ),
            bg=BG,
            fg=DIM,
            font=(FONT_FAMILY, 9),
            anchor="w",
            wraplength=580,
            justify="left",
        ).pack(fill="x", pady=(2, 10))

        bar = tk.Frame(outer, bg=BG)
        bar.pack(fill="x", side="bottom", pady=(10, 0))
        self._button(bar, "保存", self.save, primary=True).pack(side="right")
        self._button(bar, "取消", self.win.destroy).pack(side="right", padx=(0, 8))

        self.var_enabled = tk.BooleanVar(
            value=bool(self.cfg.get("clipboard_enabled", True))
        )
        self._check(outer, "启用复制后自动查词 / 翻译", self.var_enabled)

        self._section(outer, "气泡外观")
        grid = tk.Frame(outer, bg=PANEL)
        grid.pack(fill="x", pady=(4, 10))
        self.var_bub_bg = tk.StringVar(value=self.bubble.get("bg", BG))
        self.var_bub_fg = tk.StringVar(value=self.bubble.get("fg", TEXT))
        self._color_row(grid, 0, "气泡背景", self.var_bub_bg)
        self._color_row(grid, 1, "气泡文字", self.var_bub_fg)
        self.var_bub_alpha = tk.DoubleVar(value=float(self.bubble.get("alpha", 0.97)))
        self._slider_row(grid, 2, "气泡透明度", self.var_bub_alpha)
        self.var_width = tk.StringVar(value=str(int(self.bubble.get("width", 440))))
        tk.Label(
            grid, text="气泡宽度", bg=PANEL, fg=DIM, font=(FONT_FAMILY, 9), anchor="w"
        ).grid(row=3, column=0, sticky="w", padx=(12, 4), pady=6)
        tk.Entry(
            grid,
            textvariable=self.var_width,
            width=6,
            bg=PANEL,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            font=(FONT_FAMILY, 9),
        ).grid(row=3, column=1, sticky="w", padx=4, pady=6)

        self._section(outer, "在哪些程序里生效")
        tk.Label(
            outer,
            text=tr("在阅读器里点「把当前窗口加进来」，程序名会自动识别。"),
            bg=BG,
            fg=DIM,
            font=(FONT_FAMILY, 8),
            anchor="w",
        ).pack(fill="x")
        list_frame = tk.Frame(outer, bg=PANEL)
        list_frame.pack(fill="x", pady=(4, 6))
        self.listbox = tk.Listbox(
            list_frame,
            height=5,
            bg=PANEL,
            fg=TEXT,
            selectbackground=ACCENT,
            selectforeground=ON_ACCENT,
            font=(FONT_FAMILY, 9),
            relief="flat",
            highlightthickness=0,
        )
        self.listbox.pack(fill="x", padx=8, pady=8)
        for name in self.cfg.get("whitelist") or []:
            self.listbox.insert("end", name)

        row = tk.Frame(outer, bg=BG)
        row.pack(fill="x")
        self._button(row, "把当前窗口加进来", self._add_current).pack(side="left")
        self._button(row, "删除选中", self._remove_selected).pack(side="left", padx=(8, 0))
        self.status = tk.Label(row, text="", bg=BG, fg=GREEN, font=(FONT_FAMILY, 9), anchor="w")
        self.status.pack(side="left", padx=(10, 0))

        self.win.update_idletasks()
        need_h = self.win.winfo_reqheight()
        _sw, sh = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
        self.win.geometry(f"640x{min(need_h, sh - 80)}")

    def _section(self, parent, text: str) -> None:
        tk.Label(
            parent, text=tr(text), bg=BG, fg=ACCENT,
            font=(FONT_FAMILY, 9, "bold"), anchor="w",
        ).pack(fill="x", pady=(6, 0))

    def _check(self, parent, text, var):
        box = tk.Checkbutton(
            parent,
            text=tr(text),
            variable=var,
            bg=parent.cget("bg"),
            fg=TEXT,
            selectcolor=BORDER_SOFT,
            activebackground=parent.cget("bg"),
            activeforeground=TEXT,
            font=(FONT_FAMILY, 9),
            anchor="w",
        )
        box.pack(fill="x", pady=2)
        return box

    def _button(self, parent, text, command, primary=False):
        bg = ACCENT if primary else PANEL
        fg = ON_ACCENT if primary else TEXT
        label = tk.Label(
            parent, text=tr(text), bg=bg, fg=fg,
            font=(FONT_FAMILY, 9), padx=12, pady=5, cursor="hand2",
        )
        label.bind("<Button-1>", lambda _e: command())
        return label

    def _color_row(self, parent, row: int, label: str, var: tk.StringVar) -> None:
        tk.Label(
            parent, text=tr(label), bg=PANEL, fg=DIM,
            font=(FONT_FAMILY, 9), anchor="w",
        ).grid(row=row, column=0, sticky="w", padx=(12, 4), pady=5)
        swatch = tk.Label(
            parent, text="", width=6, bg=var.get(),
            cursor="hand2", relief="flat", height=1,
        )
        swatch.grid(row=row, column=1, sticky="w", padx=4, pady=5)

        def pick() -> None:
            chosen, hex_color = colorchooser.askcolor(color=var.get(), parent=self.win)
            if hex_color:
                var.set(hex_color)
                swatch.configure(bg=hex_color)

        swatch.bind("<Button-1>", lambda _e: pick())

    def _slider_row(self, parent, row: int, label: str, var: tk.DoubleVar) -> None:
        tk.Label(
            parent, text=tr(label), bg=PANEL, fg=DIM,
            font=(FONT_FAMILY, 9), anchor="w",
        ).grid(row=row, column=0, sticky="w", padx=(12, 4), pady=4)
        tk.Scale(
            parent,
            from_=0.3,
            to=1.0,
            resolution=0.05,
            orient="horizontal",
            variable=var,
            bg=PANEL,
            fg=MUTED,
            troughcolor=BORDER_SOFT,
            highlightthickness=0,
            length=180,
            showvalue=True,
        ).grid(row=row, column=1, sticky="w", padx=4, pady=4)

    def _add_current(self) -> None:
        exe = foreground_exe()
        if not exe:
            self.status.configure(
                text=tr("没识别到前台程序，先把阅读器切到最前面再点"), fg="#f7768e"
            )
            return
        existing = [self.listbox.get(i) for i in range(self.listbox.size())]
        if exe in existing:
            self.status.configure(text=f"{exe} " + tr("已经在列表里了"), fg=MUTED)
            return
        self.listbox.insert("end", exe)
        self.status.configure(text=tr("已加入 ") + exe, fg=GREEN)

    def _remove_selected(self) -> None:
        for index in reversed(self.listbox.curselection()):
            self.listbox.delete(index)

    def save(self) -> None:
        selection = self.config.data.setdefault("selection", {})
        selection["clipboard_enabled"] = bool(self.var_enabled.get())
        selection["whitelist"] = [
            self.listbox.get(i) for i in range(self.listbox.size())
        ]
        try:
            width = max(260, min(900, int(self.var_width.get())))
        except ValueError:
            width = 440
        selection["bubble"] = {
            "bg": self.var_bub_bg.get(),
            "fg": self.var_bub_fg.get(),
            "alpha": round(float(self.var_bub_alpha.get()), 2),
            "width": width,
        }
        self.config.save()
        self.on_saved()
        self.win.destroy()
