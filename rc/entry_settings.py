"""原版排版配色设置窗口。"""



from __future__ import annotations

from .uiutil import bind_defocus

import tkinter as tk

from .entryhtml import DEFAULT_COLORS
from .popup import ACCENT, BG, DIM, FONT_FAMILY, MUTED, PANEL, TEXT

COLOR_ROWS = [
    ("sense", "义项号"),
    ("pos", "词性"),
    ("label", "标签"),
    ("example", "例句"),
    ("section", "部分号"),
    ("text", "正文"),
    ("bg", "背景"),
]

PRESETS = {
    "默认": dict(DEFAULT_COLORS),
    "暗色正文": {
        "text": "#e6e9ef",
        "bg": "#14161a",
        "sense": "#ff6b6b",
        "pos": "#7fb0ff",
        "label": "#9aa3b0",
        "example": "#a8b0bd",
        "section": "#e0b872",
        "arrow": "#6b7280",
    },
    "柔和": {
        "text": "#2b2b2b",
        "bg": "#fbf9f4",
        "sense": "#b5563f",
        "pos": "#3f6f9f",
        "label": "#8a8578",
        "example": "#6f6a60",
        "section": "#a67c2e",
        "arrow": "#b9b2a4",
    },
    "高对比": {
        "text": "#000000",
        "bg": "#ffffff",
        "sense": "#c00000",
        "pos": "#0000c0",
        "label": "#333333",
        "example": "#000000",
        "section": "#8a5a00",
        "arrow": "#555555",
    },
}


class EntryColorSettings:
    """配色 + 字号 + 自定义 CSS。"""

    def __init__(self, root: tk.Tk, config, on_saved=None) -> None:
        self.root = root
        self.config = config
        self.on_saved = on_saved
        self.win = tk.Toplevel(root)
        bind_defocus(self.win)
        self.win.title("原版排版配色")
        self.win.configure(bg=BG)
        self.win.transient(root)
        self.win.resizable(False, False)

        self.color_vars: dict[str, tk.StringVar] = {}
        self.swatches: dict[str, tk.Label] = {}
        saved = self.config.data.get("entry_colors") or {}

        pad = tk.Frame(self.win, bg=BG)
        pad.pack(fill="both", expand=True, padx=18, pady=14)

        tk.Label(
            pad, text="原版排版配色", bg=BG, fg=TEXT, font=(FONT_FAMILY, 12, "bold"), anchor="w"
        ).pack(fill="x")
        tk.Label(
            pad,
            text="点色块改颜色，立刻反映到「原版」窗口",
            bg=BG,
            fg=DIM,
            font=(FONT_FAMILY, 9),
            anchor="w",
        ).pack(fill="x", pady=(2, 10))

        presets = tk.Frame(pad, bg=BG)
        presets.pack(fill="x", pady=(0, 8))
        tk.Label(presets, text="预设", bg=BG, fg=MUTED, font=(FONT_FAMILY, 9)).pack(side="left")
        for name in PRESETS:
            self._button(presets, name, lambda n=name: self._apply_preset(n)).pack(
                side="left", padx=(8, 0)
            )

        grid = tk.Frame(pad, bg=PANEL)
        grid.pack(fill="x", pady=(0, 10))
        for key, label in COLOR_ROWS:
            color = saved.get(key) or DEFAULT_COLORS[key]
            var = tk.StringVar(value=color)
            self.color_vars[key] = var
            row = tk.Frame(grid, bg=PANEL)
            row.pack(fill="x", padx=12, pady=3)
            tk.Label(
                row, text=label, bg=PANEL, fg=MUTED, font=(FONT_FAMILY, 9), width=6, anchor="w"
            ).pack(side="left")
            swatch = tk.Label(
                row,
                text=color,
                bg=color,
                fg=self._contrast(color),
                font=(FONT_FAMILY, 8),
                width=10,
                padx=6,
                pady=2,
                cursor="hand2",
            )
            swatch.pack(side="left")
            self.swatches[key] = swatch
            swatch.bind("<Button-1>", lambda _e, k=key: self._pick(k))

        size_row = tk.Frame(pad, bg=BG)
        size_row.pack(fill="x", pady=(0, 8))
        tk.Label(
            size_row, text="字号", bg=BG, fg=MUTED, font=(FONT_FAMILY, 9), width=6, anchor="w"
        ).pack(side="left")
        self.var_font = tk.StringVar(value=str(self.config.data.get("entry_font_size") or 15))
        tk.Spinbox(
            size_row,
            from_=10,
            to=26,
            textvariable=self.var_font,
            width=4,
            bg=PANEL,
            fg=TEXT,
            buttonbackground=PANEL,
            insertbackground=TEXT,
            relief="flat",
            font=(FONT_FAMILY, 9),
        ).pack(side="left")

        tk.Label(
            pad, text="自定义 CSS（追加到样式表末尾，可留空）", bg=BG, fg=MUTED,
            font=(FONT_FAMILY, 9), anchor="w",
        ).pack(fill="x", pady=(4, 2))
        self.css_text = tk.Text(
            pad, height=4, bg=PANEL, fg=TEXT, insertbackground=TEXT, relief="flat",
            font=("Consolas", 9), wrap="word",
        )
        self.css_text.pack(fill="x")
        self.css_text.insert("1.0", str(self.config.data.get("entry_custom_css") or ""))

        buttons = tk.Frame(pad, bg=BG)
        buttons.pack(fill="x", pady=(12, 0))
        self._button(buttons, "保存", self.save, primary=True).pack(side="right")
        self._button(buttons, "取消", self.close).pack(side="right", padx=(0, 8))
        self._button(buttons, "恢复默认", self._reset).pack(side="left")

        self.win.update_idletasks()
        width = 420
        height = self.win.winfo_reqheight()
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        self.win.geometry(f"{width}x{min(height, sh - 80)}+{max(20, (sw - width) // 2)}+60")

    # ------------------------------------------------------------------ 控件
    def _button(self, parent, text, command, primary=False) -> tk.Label:
        label = tk.Label(
            parent,
            text=text,
            bg=ACCENT if primary else PANEL,
            fg="#ffffff" if primary else TEXT,
            font=(FONT_FAMILY, 9),
            padx=12,
            pady=5,
            cursor="hand2",
        )
        label.bind("<Button-1>", lambda _e: command())
        return label

    @staticmethod
    def _contrast(color: str) -> str:
        try:
            value = color.lstrip("#")
            r, g, b = (int(value[i : i + 2], 16) for i in (0, 2, 4))
        except Exception:
            return "#ffffff"
        return "#000000" if (r * 299 + g * 587 + b * 114) / 1000 > 140 else "#ffffff"

    def _pick(self, key: str) -> None:
        from tkinter import colorchooser

        _, picked = colorchooser.askcolor(
            color=self.color_vars[key].get(), title="选择颜色", parent=self.win
        )
        if not picked:
            return
        self.color_vars[key].set(picked)
        self.swatches[key].configure(bg=picked, text=picked, fg=self._contrast(picked))

    def _apply_preset(self, name: str) -> None:
        for key, value in PRESETS[name].items():
            if key in self.color_vars:
                self.color_vars[key].set(value)
                self.swatches[key].configure(bg=value, text=value, fg=self._contrast(value))

    def _reset(self) -> None:
        self._apply_preset("默认")
        self.var_font.set("15")
        self.css_text.delete("1.0", "end")

    # ------------------------------------------------------------------ 保存
    def save(self) -> None:
        self.config.data["entry_colors"] = {
            key: var.get() for key, var in self.color_vars.items()
        }
        try:
            self.config.data["entry_font_size"] = min(
                26, max(10, int(self.var_font.get().strip() or 15))
            )
        except ValueError:
            self.config.data["entry_font_size"] = 15
        self.config.data["entry_custom_css"] = self.css_text.get("1.0", "end").strip()
        self.config.save()
        if self.on_saved:
            self.on_saved()
        self.close()

    def close(self) -> None:
        try:
            self.win.destroy()
        except tk.TclError:
            pass

    def show(self) -> None:
        self.win.deiconify()
        self.win.lift()
        self.win.focus_force()
