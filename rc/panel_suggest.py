"""Main panel: the dictionary suggestion popup and its keyboard handling."""

from __future__ import annotations

import tkinter as tk

from .theme import (
    ACCENT,
    BG,
    FONT_FAMILY,
    MUTED,
    PANEL,
    PANEL_ALT,
    TEXT,
)


class PanelSuggestMixin:
    def _on_suggest_key(self, event) -> str:
        if not self._suggest_rows:
            if event.keysym in ("Down", "Up"):
                self._reshow_suggestions()
                return "break" if self._suggest_rows else ""
            return ""
        rows = self._suggest_rows
        if event.keysym == "Down":
            self._suggest_index = (self._suggest_index + 1) % len(rows)
        elif event.keysym == "Up":
            self._suggest_index = (self._suggest_index - 1) % len(rows)
        elif event.keysym == "Escape":
            self._hide_suggestions()
            return "break"
        elif event.keysym == "Return":
            if 0 <= self._suggest_index < len(rows):
                word = self._suggest_items[self._suggest_index]["word"]
                self._accept_suggestion(word)
                return "break"
            self._hide_suggestions()
            self._lookup_dict()
            return "break"
        self._highlight_suggestion()
        return "break"

    def _highlight_suggestion(self) -> None:
        for index, row in enumerate(self._suggest_rows):
            color = PANEL_ALT if index == self._suggest_index else PANEL
            try:
                row.configure(bg=color)
                for child in row.winfo_children():
                    child.configure(bg=color)
            except tk.TclError:
                pass

    def _route_wheel(self, event) -> str:
        """滚轮按鼠标位置分派：浮层 → 浮层，内容区 → 内容区，对话区 → 对话区。"""
        try:
            px, py = self.win.winfo_pointerxy()
        except tk.TclError:
            return "break"
        step = int(-event.delta / 120) or 0
        if step == 0:
            return "break"

        def inside(widget) -> bool:
            try:
                if not widget.winfo_ismapped():
                    return False
                x0 = widget.winfo_rootx()
                y0 = widget.winfo_rooty()
                return x0 <= px <= x0 + widget.winfo_width() and y0 <= py <= y0 + widget.winfo_height()
            except tk.TclError:
                return False

        # 建议浮层可见且鼠标在浮层（或输入框）上
        if self._suggest_rows:
            try:
                sw = self.suggest_win
                if sw.winfo_viewable() and (
                    inside(sw) or inside(self.dict_input)
                ):
                    self.suggest_canvas.yview_scroll(step, "units")
                    return "break"
            except tk.TclError:
                pass
        if inside(self.canvas):
            self._scroll_pane(self.canvas, self.chat_body, step * 2)
            return "break"
        # 内容区、输入框、顶部区域：都滚内容区
        self._scroll_pane(self.content_canvas, self.content, step * 2)
        return "break"

    def _log_click(self, event) -> None:
        try:
            import logging

            logging.getLogger("click").info(
                "panel click widget=%s class=%s xy=%s,%s",
                event.widget, event.widget.winfo_class(), event.x, event.y,
            )
        except Exception:
            pass

    def _dismiss_on_click(self, event=None) -> None:
        widget = getattr(event, "widget", None)
        if widget is self.dict_input:
            return
        if self._suggest_rows:
            self._hide_suggestions()

    def _suggest_background_click(self, event=None) -> str:
        """点在浮层空白处：收起浮层，并把这次点击透传给下面的控件。"""
        x = getattr(event, "x_root", None)
        y = getattr(event, "y_root", None)
        self._hide_suggestions()
        if x is None or y is None:
            return "break"
        self.win.after(30, lambda: self._click_through(x, y))
        return "break"

    def _click_through(self, x: int, y: int) -> None:
        try:
            import ctypes
            import time as _t

            user32 = ctypes.windll.user32
            user32.SetCursorPos(int(x), int(y))
            _t.sleep(0.02)
            user32.mouse_event(0x0002, 0, 0, 0, 0)
            _t.sleep(0.02)
            user32.mouse_event(0x0004, 0, 0, 0, 0)
        except Exception:
            pass

    def _reshow_suggestions(self) -> None:
        """不用重新输入：点输入框 / 按 ↓ 就能把建议重新唤出来。"""
        if not self._suggest_rows and self.dict_input.get().strip():
            self._update_suggestions()

    def _on_main_focus_out(self, _event=None) -> None:
        self.win.after(220, self._hide_suggest_if_unfocused)

    def _hide_suggest_if_unfocused(self) -> None:
        if not self._suggest_rows:
            return
        try:
            focused = self.win.focus_get()
        except tk.TclError:
            focused = None
        if focused is None:
            self._hide_suggestions()

    def _suggest_wheel(self, event) -> str:
        self._scroll_pane(
            self.suggest_canvas, self.suggest_body, int(-event.delta / 120)
        )
        return "break"

    def _suggest_bind_all(self, widget) -> None:
        widget.bind("<MouseWheel>", self._suggest_wheel)
        for child in widget.winfo_children():
            self._suggest_bind_all(child)

    def _hide_suggestions(self) -> None:
        for row in self._suggest_rows:
            try:
                row.destroy()
            except tk.TclError:
                pass
        self._suggest_rows = []
        self._suggest_items = []
        self._suggest_index = -1
        try:
            self.suggest_win.attributes("-topmost", False)
        except tk.TclError:
            pass
        try:
            self.suggest_win.withdraw()
        except tk.TclError:
            pass

    def _suggest_geometry(self) -> tuple[int, int, int, int]:
        self.win.update_idletasks()
        x = self.dict_input.winfo_rootx()
        y = self.dict_input.winfo_rooty() + self.dict_input.winfo_height() + 2
        width = max(200, self.dict_input.winfo_width())
        bottom = self.win.winfo_rooty() + self.win.winfo_height() - 10
        space = max(90, bottom - y)
        self.suggest_body.update_idletasks()
        content = self.suggest_body.winfo_reqheight() + 2
        height = min(content, 300, space)
        return x, y, width, height

    def _reposition_suggest(self, _event=None) -> None:
        if not self._suggest_rows:
            return
        try:
            if not self.suggest_win.winfo_viewable():
                return
        except tk.TclError:
            return
        x, y, width, height = self._suggest_geometry()
        top = self.win.winfo_rooty()
        bottom = top + self.win.winfo_height()
        # 输入框被滚出窗口：收起，别让浮层飘到窗口外面
        if y < top + 30 or y > bottom - 30:
            self._hide_suggestions()
            return
        height = min(height, bottom - y - 8)
        if height < 60:
            self._hide_suggestions()
            return
        self.suggest_win.geometry(f"{width}x{height}+{x}+{y}")

    def _accept_suggestion(self, word: str) -> None:
        self._hide_suggestions()
        self.dict_input.delete(0, "end")
        self.dict_input.insert(0, word)
        self._lookup_dict()
        try:
            self.dict_input.icursor("end")
            self.dict_input.focus_set()
            self._sync_content_scroll()
        except tk.TclError:
            pass

    def _update_suggestions(self) -> None:
        word = self.dict_input.get().strip()
        if len(word) < 1 or not self.service.has_dictionaries():
            self._hide_suggestions()
            return
        try:
            items = self.service.fuzzy_lookup(word, None, 10)
        except Exception:
            items = []
        if not items:
            self._hide_suggestions()
            return
        for row in self._suggest_rows:
            try:
                row.destroy()
            except tk.TclError:
                pass
        self._suggest_rows = []
        self._suggest_index = -1
        self._suggest_items = items
        for item in items:
            row = tk.Frame(self.suggest_body, bg=PANEL)
            row.pack(fill="x")
            name = item.get("word") or ""
            name_label = tk.Label(
                row, text=name, bg=PANEL, fg=TEXT,
                font=(FONT_FAMILY, 10, "bold"), anchor="w",
            )
            name_label.pack(side="left", padx=(10, 0), pady=3)
            pos = (item.get("pos") or "").strip()
            if pos:
                tk.Label(
                    row, text=pos, bg=PANEL, fg=ACCENT, font=(FONT_FAMILY, 8)
                ).pack(side="left", padx=(8, 0))
            gloss = (item.get("gloss") or "").strip()
            if gloss:
                tk.Label(
                    row, text=gloss[:42], bg=PANEL, fg=MUTED,
                    font=(FONT_FAMILY, 9), anchor="w",
                ).pack(side="left", padx=(10, 0))
            for widget in (row, name_label):
                widget.configure(cursor="hand2")
                widget.bind("<Button-1>", lambda _e, w=name: self._accept_suggestion(w))
            self._suggest_rows.append(row)
        self._suggest_bind_all(self.suggest_body)
        self.suggest_canvas.yview_moveto(0.0)
        x, y, width, height = self._suggest_geometry()
        self.suggest_win.geometry(f"{width}x{height}+{x}+{y}")
        self.suggest_win.deiconify()
        try:
            self.suggest_win.attributes("-topmost", True)
        except tk.TclError:
            pass
        self.suggest_win.lift()
        self.win.update_idletasks()
        self._reposition_suggest()

    def _render_fuzzy(self, word: str, lang: str | None, exclude: str = "") -> None:
        """在查词结果下面列相近的词（前缀/纠错/重音归一）。"""
        try:
            items = self.service.fuzzy_lookup(word, lang, 12)
        except Exception:
            items = []
        exclude_norm = (exclude or "").strip().lower()
        rows = [it for it in items if (it.get("word") or "").lower() != exclude_norm]
        if not rows:
            return
        box = tk.Frame(self.dict_result, bg=BG)
        box.pack(fill="x", pady=(10, 2))
        tk.Label(
            box, text="相近的词", bg=BG, fg=MUTED, font=(FONT_FAMILY, 8), anchor="w"
        ).pack(fill="x", pady=(0, 4))
        for item in rows:
            line = tk.Frame(box, bg=BG)
            line.pack(fill="x", pady=1)
            name = item.get("word") or ""
            name_label = tk.Label(
                line, text=name, bg=BG, fg=TEXT, font=(FONT_FAMILY, 10, "bold"),
                anchor="w", cursor="hand2",
            )
            name_label.pack(side="left")
            pos = (item.get("pos") or "").strip()
            if pos:
                tk.Label(
                    line, text=pos, bg=BG, fg=ACCENT, font=(FONT_FAMILY, 8)
                ).pack(side="left", padx=(8, 0))
            gloss = (item.get("gloss") or "").strip()
            if gloss:
                tk.Label(
                    line, text=gloss, bg=BG, fg=MUTED, font=(FONT_FAMILY, 9),
                    anchor="w",
                ).pack(side="left", padx=(10, 0))
            name_label.bind("<Button-1>", lambda _e, w=name: self._dict_lookup_word(w))
