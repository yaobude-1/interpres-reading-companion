"""自绘竖向滚动条。

Windows 原生主题下 tk.Scrollbar / ttk 滚动条会画成浅色，深色界面上很扎眼，
而且宽度不好调。这里用 Canvas 自己画：14px 宽、深色、可拖动、可点轨道翻页。
"""

from __future__ import annotations

import tkinter as tk

from .theme import ACCENT, SCROLL_THUMB, SCROLL_TRACK

THUMB = SCROLL_THUMB
THUMB_ACTIVE = ACCENT
TRACK = SCROLL_TRACK


class SlimScrollbar(tk.Canvas):
    def __init__(
        self,
        master,
        command,
        width: int = 14,
        bg: str = TRACK,
        thumb: str = THUMB,
        **kwargs,
    ) -> None:
        super().__init__(
            master,
            width=width,
            bg=bg,
            highlightthickness=0,
            bd=0,
            takefocus=0,
            **kwargs,
        )
        self._command = command
        self._first = 0.0
        self._last = 1.0
        self._thumb_color = thumb
        self._drag_start = None
        self._drag_from = 0.0
        self._thumb = self.create_rectangle(3, 0, 3, 0, fill=thumb, outline="")
        self.bind("<Configure>", lambda _e: self._draw())
        self.bind("<Button-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Enter>", lambda _e: self.itemconfigure(self._thumb, fill=THUMB_ACTIVE))
        self.bind("<Leave>", lambda _e: self.itemconfigure(self._thumb, fill=self._thumb_color))

    # ------------------------------------------------------------------ 外部接口
    def set(self, first, last) -> None:
        try:
            self._first = max(0.0, float(first))
            self._last = min(1.0, float(last))
        except (TypeError, ValueError):
            return
        self._draw()

    # ------------------------------------------------------------------ 绘制
    def _geometry(self) -> tuple[int, int, int]:
        height = max(1, self.winfo_height())
        width = max(1, self.winfo_width())
        top = int(self._first * height)
        bottom = int(self._last * height)
        if bottom - top < 24:
            bottom = min(height, top + 24)
            top = max(0, bottom - 24)
        return top, bottom, width

    def _draw(self) -> None:
        # 内容装得下：把滑块藏起来（滚动条本身仍占位，避免宽度抖动）
        needed = self._first > 0.001 or self._last < 0.999
        state = "normal" if needed else "hidden"
        if self.itemcget(self._thumb, "state") != state:
            self.itemconfigure(self._thumb, state=state)
        if not needed:
            return
        top, bottom, width = self._geometry()
        self.coords(self._thumb, 3, top, max(4, width - 3), bottom)

    # ------------------------------------------------------------------ 拖动
    def _thumb_range(self) -> tuple[float, float]:
        height = max(1, self.winfo_height())
        top, bottom, _w = self._geometry()
        return top / height, bottom / height

    def _on_press(self, event) -> None:
        start, end = self._thumb_range()
        fraction = event.y / max(1, self.winfo_height())
        if fraction < start or fraction > end:
            # 点轨道：翻页
            if self._command:
                self._command("moveto", max(0.0, min(1.0, fraction - (end - start) / 2)))
            self._drag_start = None
            return
        self._drag_start = (event.y, start, end)
        self._drag_from = self._first

    def _on_drag(self, event) -> None:
        if not self._drag_start:
            return
        start_y, start_f, end_f = self._drag_start
        height = max(1, self.winfo_height())
        span = max(0.0, end_f - start_f)
        delta = (event.y - start_y) / height
        target = max(0.0, min(1.0 - span, start_f + delta))
        if self._command:
            self._command("moveto", target)

    def _on_release(self, _event) -> None:
        self._drag_start = None
