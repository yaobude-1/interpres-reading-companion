"""划词小按钮的设置对话框。"""



from __future__ import annotations

from .uiutil import bind_defocus

import tkinter as tk
from tkinter import colorchooser

from .selection import foreground_exe
from .popup import ACCENT, BG, DIM, FONT_FAMILY, GREEN, MUTED, PANEL, TEXT
from .theme import BORDER_SOFT, ON_ACCENT


class SelectionSettings:
    def __init__(self, root: tk.Tk, config, on_saved) -> None:
        self.root = root
        self.config = config
        self.on_saved = on_saved
        self.cfg = config.get("selection") or {}
        self.button = dict(self.cfg.get("button") or {})
        self.bubble = dict(self.cfg.get("bubble") or {})

        self.win = tk.Toplevel(root)
        self.win.title("划词按钮设置")
        self.win.configure(bg=BG)
        self.win.geometry("640x720")
        self.win.attributes("-topmost", True)
        self._build()
        bind_defocus(self.win)

    # ------------------------------------------------------------------ 构建
    def _build(self) -> None:
        outer = tk.Frame(self.win, bg=BG)
        outer.pack(fill="both", expand=True, padx=18, pady=14)

        tk.Label(
            outer, text="划词按钮", bg=BG, fg=TEXT, font=(FONT_FAMILY, 14, "bold"), anchor="w"
        ).pack(fill="x")
        tk.Label(
            outer,
            text="在阅读器里拖选或双击选词后，选区旁会出现「译」按钮，点一下才翻译。",
            bg=BG,
            fg=DIM,
            font=(FONT_FAMILY, 9),
            anchor="w",
            wraplength=560,
            justify="left",
        ).pack(fill="x", pady=(2, 10))

        # 底部按钮
        bar = tk.Frame(outer, bg=BG)
        bar.pack(fill="x", side="bottom", pady=(10, 0))
        self._button(bar, "保存", self.save, primary=True).pack(side="right")
        self._button(bar, "取消", self.win.destroy).pack(side="right", padx=(0, 8))

        # 基本开关
        self.var_enabled = tk.BooleanVar(value=bool(self.cfg.get("enabled", True)))
        self.var_drag = tk.BooleanVar(value=bool(self.cfg.get("drag", True)))
        self.var_double = tk.BooleanVar(value=bool(self.cfg.get("double_click", True)))
        self._check(outer, "启用划词按钮", self.var_enabled)
        row = tk.Frame(outer, bg=BG)
        row.pack(fill="x", pady=(2, 8))
        self._check(row, "拖选触发", self.var_drag, side="left")
        self._check(row, "双击选词触发", self.var_double, side="left", padx=(16, 0))

        # 消失方式
        self._section(outer, "按钮什么时候消失")
        self.var_hide = tk.StringVar(value=self.button.get("hide_mode", "timeout"))
        self.var_seconds = tk.StringVar(
            value=str(max(1, int(self.button.get("hide_after_ms", 2500)) // 1000))
        )
        row = tk.Frame(outer, bg=PANEL)
        row.pack(fill="x", pady=(4, 10))
        for value, label in (
            ("timeout", "过几秒自动消失"),
            ("leave", "鼠标移开就消失"),
            ("always", "一直留着（点别处消失）"),
        ):
            tk.Radiobutton(
                row,
                text=label,
                value=value,
                variable=self.var_hide,
                bg=PANEL,
                fg=TEXT,
                selectcolor=BORDER_SOFT,
                activebackground=PANEL,
                activeforeground=TEXT,
                font=(FONT_FAMILY, 9),
                anchor="w",
            ).pack(side="left", padx=(10, 4), pady=6)
        tk.Spinbox(
            row,
            from_=1,
            to=20,
            width=3,
            textvariable=self.var_seconds,
            bg=PANEL,
            fg=TEXT,
            relief="flat",
            font=(FONT_FAMILY, 9),
        ).pack(side="left", padx=(6, 2))
        tk.Label(row, text="秒", bg=PANEL, fg=MUTED, font=(FONT_FAMILY, 9)).pack(side="left")

        # 外观
        self._section(outer, "外观")
        grid = tk.Frame(outer, bg=PANEL)
        grid.pack(fill="x", pady=(4, 10))
        self.var_btn_bg = tk.StringVar(value=self.button.get("bg", ACCENT))
        self.var_btn_fg = tk.StringVar(value=self.button.get("fg", "#10131a"))
        self.var_bub_bg = tk.StringVar(value=self.bubble.get("bg", BG))
        self.var_bub_fg = tk.StringVar(value=self.bubble.get("fg", TEXT))
        self._color_row(grid, 0, "按钮背景", self.var_btn_bg)
        self._color_row(grid, 1, "按钮文字", self.var_btn_fg)
        self._color_row(grid, 2, "气泡背景", self.var_bub_bg)
        self._color_row(grid, 3, "气泡文字", self.var_bub_fg)

        self.var_btn_alpha = tk.DoubleVar(value=float(self.button.get("alpha", 0.95)))
        self.var_bub_alpha = tk.DoubleVar(value=float(self.bubble.get("alpha", 0.97)))
        self._slider_row(grid, 4, "按钮透明度", self.var_btn_alpha)
        self._slider_row(grid, 5, "气泡透明度", self.var_bub_alpha)
        self.var_width = tk.StringVar(value=str(int(self.bubble.get("width", 440))))
        tk.Label(grid, text="气泡宽度", bg=PANEL, fg=DIM, font=(FONT_FAMILY, 9), anchor="w").grid(
            row=6, column=0, sticky="w", padx=(12, 4), pady=6
        )
        tk.Entry(
            grid,
            textvariable=self.var_width,
            width=6,
            bg=PANEL,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            font=(FONT_FAMILY, 9),
        ).grid(row=6, column=1, sticky="w", padx=4, pady=6)

        # 白名单
        self._section(outer, "在哪些程序里生效")
        tk.Label(
            outer,
            text="在阅读器里点「把当前窗口加进来」，程序名会自动识别。",
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

        # 按内容自适应高度，避免把白名单列表挤掉
        self.win.update_idletasks()
        need_h = self.win.winfo_reqheight()
        _sw, sh = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
        self.win.geometry(f"640x{min(need_h, sh - 80)}")

    # ------------------------------------------------------------------ 控件
    def _section(self, parent, text: str) -> None:
        tk.Label(
            parent, text=text, bg=BG, fg=ACCENT, font=(FONT_FAMILY, 9, "bold"), anchor="w"
        ).pack(fill="x", pady=(6, 0))

    def _check(self, parent, text, var, side=None, padx=None):
        box = tk.Checkbutton(
            parent,
            text=text,
            variable=var,
            bg=parent.cget("bg"),
            fg=TEXT,
            selectcolor=BORDER_SOFT,
            activebackground=parent.cget("bg"),
            activeforeground=TEXT,
            font=(FONT_FAMILY, 9),
            anchor="w",
        )
        if side:
            box.pack(side=side, pady=2, padx=padx or 0)
        else:
            box.pack(fill="x", pady=2)
        return box

    def _button(self, parent, text, command, primary=False):
        bg = ACCENT if primary else PANEL
        fg = ON_ACCENT if primary else TEXT
        label = tk.Label(
            parent, text=text, bg=bg, fg=fg, font=(FONT_FAMILY, 9), padx=12, pady=5, cursor="hand2"
        )
        label.bind("<Button-1>", lambda _e: command())
        return label

    def _color_row(self, parent, row: int, label: str, var: tk.StringVar) -> None:
        tk.Label(parent, text=label, bg=PANEL, fg=DIM, font=(FONT_FAMILY, 9), anchor="w").grid(
            row=row, column=0, sticky="w", padx=(12, 4), pady=5
        )
        swatch = tk.Label(
            parent, text="", width=6, bg=var.get(), cursor="hand2", relief="flat", height=1
        )
        swatch.grid(row=row, column=1, sticky="w", padx=4, pady=5)

        def pick() -> None:
            chosen, hex_color = colorchooser.askcolor(color=var.get(), parent=self.win)
            if hex_color:
                var.set(hex_color)
                swatch.configure(bg=hex_color)

        swatch.bind("<Button-1>", lambda _e: pick())

    def _slider_row(self, parent, row: int, label: str, var: tk.DoubleVar) -> None:
        tk.Label(parent, text=label, bg=PANEL, fg=DIM, font=(FONT_FAMILY, 9), anchor="w").grid(
            row=row, column=0, sticky="w", padx=(12, 4), pady=4
        )
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

    # ------------------------------------------------------------------ 动作
    def _add_current(self) -> None:
        exe = foreground_exe()
        if not exe:
            self.status.configure(text="没识别到前台程序，先把阅读器切到最前面再点", fg="#f7768e")
            return
        existing = [self.listbox.get(i) for i in range(self.listbox.size())]
        if exe in existing:
            self.status.configure(text=f"{exe} 已经在列表里了", fg=MUTED)
            return
        self.listbox.insert("end", exe)
        self.status.configure(text=f"已加入 {exe}", fg=GREEN)

    def _remove_selected(self) -> None:
        for index in reversed(self.listbox.curselection()):
            self.listbox.delete(index)

    def save(self) -> None:
        try:
            seconds = max(1, int(self.var_seconds.get()))
        except ValueError:
            seconds = 3
        selection = self.config.data.setdefault("selection", {})
        selection["enabled"] = bool(self.var_enabled.get())
        selection["drag"] = bool(self.var_drag.get())
        selection["double_click"] = bool(self.var_double.get())
        selection["whitelist"] = [self.listbox.get(i) for i in range(self.listbox.size())]
        selection["button"] = {
            "bg": self.var_btn_bg.get(),
            "fg": self.var_btn_fg.get(),
            "alpha": round(float(self.var_btn_alpha.get()), 2),
            "hide_mode": self.var_hide.get(),
            "hide_after_ms": seconds * 1000,
        }
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
