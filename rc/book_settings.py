"""书名过滤设置：用户自己指定哪些窗口标题不算书。"""



from __future__ import annotations

from .uiutil import bind_defocus

import tkinter as tk

from .popup import ACCENT, BG, DIM, FONT_FAMILY, MUTED, PANEL, TEXT
from .theme import ON_ACCENT


class BookFilterSettings:
    def __init__(self, root: tk.Tk, config, on_saved=None) -> None:
        self.root = root
        self.config = config
        self.on_saved = on_saved

        self.win = tk.Toplevel(root)
        bind_defocus(self.win)
        self.win.title("书名过滤")
        self.win.configure(bg=BG)
        self.win.transient(root)
        self.win.resizable(False, False)

        pad = tk.Frame(self.win, bg=BG)
        pad.pack(fill="both", expand=True, padx=18, pady=14)

        tk.Label(
            pad, text="书名过滤", bg=BG, fg=TEXT, font=(FONT_FAMILY, 12, "bold"), anchor="w"
        ).pack(fill="x")
        tk.Label(
            pad,
            text="自动跟随当前书籍时，窗口标题里含下面任意一条就忽略。每行一条，不分大小写。\n"
            "浏览器内部页（新建标签页、New Tab、设置…）已经默认过滤，不用重复加。",
            bg=BG,
            fg=DIM,
            font=(FONT_FAMILY, 9),
            anchor="w",
            justify="left",
        ).pack(fill="x", pady=(2, 8))

        self.text = tk.Text(
            pad,
            height=8,
            width=40,
            bg=PANEL,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            font=("Consolas", 9),
            wrap="word",
        )
        self.text.pack(fill="x")
        current = self.config.data.get("book_ignore_keywords") or []
        self.text.insert("1.0", "\n".join(str(x) for x in current))

        hint = tk.Label(
            pad,
            text="例：知乎、Bilibili、豆瓣、微信、Netflix",
            bg=BG,
            fg=MUTED,
            font=(FONT_FAMILY, 8),
            anchor="w",
        )
        hint.pack(fill="x", pady=(4, 10))

        buttons = tk.Frame(pad, bg=BG)
        buttons.pack(fill="x")
        self._button(buttons, "保存", self.save, primary=True).pack(side="right")
        self._button(buttons, "取消", self.close).pack(side="right", padx=(0, 8))
        self._button(buttons, "清空", self._clear).pack(side="left")

        self.win.update_idletasks()
        width = max(self.win.winfo_reqwidth(), 460)
        height = max(self.win.winfo_reqheight(), 320)
        self.win.geometry(
            f"{width}x{height}+{max(20, (self.win.winfo_screenwidth() - width) // 2)}+120"
        )

    def _button(self, parent, text, command, primary=False) -> tk.Label:
        label = tk.Label(
            parent,
            text=text,
            bg=ACCENT if primary else PANEL,
            fg=ON_ACCENT if primary else TEXT,
            font=(FONT_FAMILY, 9),
            padx=12,
            pady=5,
            cursor="hand2",
        )
        label.bind("<Button-1>", lambda _e: command())
        return label

    def _keywords(self) -> list[str]:
        raw = self.text.get("1.0", "end")
        return [line.strip() for line in raw.splitlines() if line.strip()]

    def _clear(self) -> None:
        self.text.delete("1.0", "end")

    def save(self) -> None:
        from .capture import set_user_blocklist

        keywords = self._keywords()
        self.config.data["book_ignore_keywords"] = keywords
        self.config.save()
        set_user_blocklist(keywords)
        if self.on_saved:
            self.on_saved()
        self.close()

    def close(self) -> None:
        try:
            self.win.destroy()
        except tk.TclError:  # 控件可能已销毁，刻意忽略
            pass

    def show(self) -> None:
        self.win.deiconify()
        self.win.lift()
        self.win.focus_force()
