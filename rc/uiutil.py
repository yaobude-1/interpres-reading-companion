"""窗口小工具：点击空白/标签时移走输入焦点。

Tk 的默认行为：点 Label、Frame、按钮这类控件不会改变键盘焦点，
所以从输入框点出去以后，键盘仍然在往原输入框里打字，容易误填。
"""

from __future__ import annotations

import tkinter as tk

INPUT_CLASSES = {
    "Entry",
    "Text",
    "TEntry",
    "TCombobox",
    "Spinbox",
    "TSpinbox",
}


def bind_defocus(win) -> None:
    """点非输入控件时，把焦点从输入框移走（焦点交给窗口本身）。"""

    def handler(event) -> None:
        try:
            widget = event.widget
            if widget is None:
                return
            if widget.winfo_class() in INPUT_CLASSES:
                return
        except Exception:
            return
        try:
            win.focus_set()
        except tk.TclError:  # 控件可能已销毁，刻意忽略
            pass

    try:
        win.bind("<Button-1>", handler, add="+")
    except tk.TclError:  # 控件可能已销毁，刻意忽略
        pass
