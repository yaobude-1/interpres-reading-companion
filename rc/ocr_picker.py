"""Full-screen drag rectangle used for screenshot OCR."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from PIL import ImageGrab

from .i18n import tr
from .theme import ACCENT, BG, FONT_FAMILY, TEXT


class OCRPicker:
    def __init__(self, root: tk.Tk, on_done) -> None:
        self.root = root
        self.on_done = on_done
        self.start: tuple[int, int] | None = None
        self.rect_id = None
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.32)
        self.win.configure(bg=BG)
        width = self.win.winfo_screenwidth()
        height = self.win.winfo_screenheight()
        self.win.geometry(f"{width}x{height}+0+0")
        self.canvas = tk.Canvas(
            self.win, bg=BG, highlightthickness=0, cursor="crosshair"
        )
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_text(
            width // 2,
            42,
            text=tr("拖动框选要识别的文字 · Esc 取消"),
            fill=TEXT,
            font=(FONT_FAMILY, 13, "bold"),
        )
        self.canvas.bind("<ButtonPress-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.win.bind("<Escape>", lambda _e: self.cancel())
        self.win.focus_force()
        self.canvas.focus_set()

    def _press(self, event) -> None:
        self.start = (event.x, event.y)
        if self.rect_id is not None:
            self.canvas.delete(self.rect_id)
        self.rect_id = self.canvas.create_rectangle(
            event.x, event.y, event.x, event.y,
            outline=ACCENT, width=2, fill="",
        )

    def _drag(self, event) -> None:
        if self.start is None or self.rect_id is None:
            return
        x0, y0 = self.start
        self.canvas.coords(self.rect_id, x0, y0, event.x, event.y)

    def _release(self, event) -> None:
        if self.start is None:
            return
        x0, y0 = self.start
        x1, y1 = event.x, event.y
        left, right = sorted((x0, x1))
        top, bottom = sorted((y0, y1))
        if right - left < 8 or bottom - top < 8:
            self.cancel()
            return
        self.start = None
        self.win.withdraw()
        self.win.update_idletasks()
        # Let the overlay disappear before grabbing pixels, otherwise the dark
        # overlay itself would be part of the OCR image.
        self.root.after(120, lambda: self._capture((left, top, right, bottom)))

    def _capture(self, bbox: tuple[int, int, int, int]) -> None:
        try:
            image = ImageGrab.grab(bbox=bbox, all_screens=True)
        except Exception as exc:  # noqa: BLE001 - capture failure is reported in UI
            messagebox.showerror(tr("截图 OCR 失败"), str(exc))
            self.close()
            return
        callback = self.on_done
        self.close()
        try:
            callback(image, bbox)
        except Exception as exc:  # noqa: BLE001 - callback must not leak picker
            messagebox.showerror(tr("OCR 失败"), str(exc))

    def cancel(self) -> None:
        self.close()

    def close(self) -> None:
        try:
            self.win.destroy()
        except tk.TclError:
            pass
