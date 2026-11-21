"""生词本：单词表、排序、列宽与双击词卡。"""

from __future__ import annotations

import tkinter as tk

from .i18n import tr


class VocabTableMixin:
    def _open_word(self, event) -> None:
        """双击单词行：交给上层弹一张词典/生词卡片。"""
        if not self.on_word_open:
            return
        row_id = self.word_tree.identify_row(event.y)
        if not row_id:
            return
        row = next((w for w in self.words if str(w.get("id")) == row_id), None)
        if row is None:
            return
        self.on_word_open(row, (event.x_root, event.y_root))

    def load_words(self) -> None:
        self._search_job = None
        if self.book_id is None:
            self.words = []
            self.count_label.configure(text="")
            self._render_words()
            return
        self.words = self.service.words_in_book(
            self.book_id, self.search_var.get().strip(), 3000
        )
        book = next((b for b in self.books if b["id"] == self.book_id), {})
        self.book_title.configure(
            text=f"{book.get('name', '')} · {tr('牌组')} {book.get('deck') or tr('（按语言默认）')}"
        )
        self.count_label.configure(text=f"{len(self.words)} 个")
        self._render_words()

    def _sort_by(self, column: str) -> None:
        """点列头排序：同列切换升降序，换列用该列的默认方向。"""
        if column not in self._COL_LABELS:
            return
        if column == self._sort_key:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_key = column
            self._sort_desc = column == "time"
        self.config.data["vocab_sort_key"] = self._sort_key
        self.config.data["vocab_sort_desc"] = self._sort_desc
        self.config.save()
        self._render_words()

    def _sort_value(self, word: dict):
        key = self._sort_key
        if key == "time":
            return str(word.get("updated") or "")
        if key == "synced":
            return 1 if word.get("synced") else 0
        return str(word.get(key) or "").casefold()

    def _render_words(self) -> None:
        selected = set(self.word_tree.selection())
        self.word_tree.delete(*self.word_tree.get_children())
        for word in sorted(self.words, key=self._sort_value, reverse=self._sort_desc):
            self.word_tree.insert(
                "",
                "end",
                iid=str(word["id"]),
                values=(
                    word.get("word") or "",
                    word.get("reading") or "",
                    (word.get("meaning") or "")[:80],
                    word.get("book") or "",
                    (word.get("updated") or "")[:10],
                    "已同步" if word.get("synced") else "未同步",
                ),
            )
        keep = [iid for iid in selected if self.word_tree.exists(iid)]
        if keep:
            self.word_tree.selection_set(keep)
        self._update_headings()
        self.word_tree.after_idle(self._update_scrollbars)

    def _on_tree_configure(self, event) -> None:
        if event.width > 80 and not self._dragging:
            self._fit_widths(event.width)
        self.word_tree.after_idle(self._update_scrollbars)

    def _update_scrollbars(self) -> None:
        """内容装得下时隐藏滚动条，避免横竖两条灰带。"""
        try:
            if not self.word_tree.winfo_exists():
                return
            x1, x2 = self.word_tree.xview()
            y1, y2 = self.word_tree.yview()
            mapped_x = bool(self._xscroll.winfo_ismapped())
            mapped_y = bool(self._vscroll.winfo_ismapped())
        except tk.TclError:
            return
        need_x = not (x1 <= 0.001 and x2 >= 0.999)
        need_y = not (y1 <= 0.001 and y2 >= 0.999)
        if need_x != mapped_x:
            if need_x:
                self._xscroll.pack(
                    side="bottom", fill="x", pady=(2, 0), before=self.word_tree
                )
            else:
                self._xscroll.pack_forget()
        if need_y != mapped_y:
            if need_y:
                self._vscroll.pack(
                    side="right", fill="y", pady=(6, 0), before=self.word_tree
                )
            else:
                self._vscroll.pack_forget()

    def _fit_widths(self, total: int) -> None:
        """按保存的比例铺满表格；低于最小宽度时先压释义，再从右侧列补。"""
        mins = [self._COL_MINS[c] for c in self._COLS]
        widths = [
            max(m, int(round(total * r)))
            for m, r in zip(mins, self._col_ratios, strict=False)
        ]
        flex = self._COLS.index("meaning")
        diff = total - sum(widths)
        if diff:
            widths[flex] += diff
            if widths[flex] < mins[flex]:
                deficit = mins[flex] - widths[flex]
                widths[flex] = mins[flex]
                for i in (0, 1, 3, 4, 5):
                    if deficit <= 0:
                        break
                    take = min(deficit, widths[i] - mins[i])
                    if take > 0:
                        widths[i] -= take
                        deficit -= take
        self._col_widths = widths
        self._apply_widths(widths)

    def _apply_widths(self, widths: list[int]) -> None:
        for key, width in zip(self._COLS, widths, strict=False):
            self.word_tree.column(key, width=int(width))

    def _on_tree_press(self, event) -> str | None:
        """只有落在分隔线上才接管拖拽，返回 break 阻止 ttk 自己改单列宽度。"""
        if self.word_tree.identify_region(event.x, event.y) != "separator":
            return None
        column = self.word_tree.identify_column(event.x)
        try:
            left = int(column[1:]) - 1
        except (ValueError, IndexError):
            return None
        if not (0 <= left < len(self._COLS) - 1):
            return None
        self._dragging = True
        self._drag_right = left + 1
        self._drag_start_x = event.x_root
        self._drag_start = [int(self.word_tree.column(c, "width")) for c in self._COLS]
        try:
            self.word_tree.grab_set()
        except tk.TclError:
            pass
        return "break"

    def _on_tree_drag(self, event) -> str | None:
        if not self._dragging:
            return None
        delta = event.x_root - self._drag_start_x
        widths = self._drag_widths(self._drag_start, self._drag_right, delta)
        self._col_widths = widths
        self._apply_widths(widths)
        return "break"

    def _on_tree_release(self, _event) -> str | None:
        if not self._dragging:
            return None
        self._dragging = False
        try:
            self.word_tree.grab_release()
        except tk.TclError:
            pass
        total = sum(self._col_widths) or 1
        self._col_ratios = [w / total for w in self._col_widths]
        self.config.data["vocab_col_ratios"] = [round(r, 4) for r in self._col_ratios]
        self.config.data.pop("vocab_col_widths", None)
        self.config.save()
        return "break"

    def _drag_widths(self, start: list[int], boundary: int, delta: int) -> list[int]:
        """拖动 boundary 这条交界线：压缩对侧列，某列到最小宽度后余量传给下一条交界线。"""
        widths = list(start)
        mins = [self._COL_MINS[c] for c in self._COLS]
        if delta > 0:
            capacity = sum(max(0, widths[j] - mins[j]) for j in range(boundary, len(widths)))
            move = min(delta, capacity)
            widths[boundary - 1] += move
            rest = move
            for j in range(boundary, len(widths)):
                if rest <= 0:
                    break
                take = min(rest, widths[j] - mins[j])
                widths[j] -= take
                rest -= take
        elif delta < 0:
            capacity = sum(max(0, widths[j] - mins[j]) for j in range(0, boundary))
            move = max(delta, -capacity)
            widths[boundary] += -move
            rest = -move
            for j in range(boundary - 1, -1, -1):
                if rest <= 0:
                    break
                take = min(rest, widths[j] - mins[j])
                widths[j] -= take
                rest -= take
        return widths

    def _on_tree_motion(self, event) -> None:
        if self._dragging:
            self.word_tree.configure(cursor="sb_h_double_arrow")
            return
        cursor = (
            "sb_h_double_arrow"
            if self.word_tree.identify_region(event.x, event.y) == "separator"
            else ""
        )
        if self.word_tree.cget("cursor") != cursor:
            self.word_tree.configure(cursor=cursor)

    def _update_headings(self) -> None:
        for key, label in self._COL_LABELS.items():
            arrow = ""
            if key == self._sort_key:
                arrow = " ▼" if self._sort_desc else " ▲"
            self.word_tree.heading(key, text=tr(label) + arrow)

    def _selected_words(self) -> list[int]:
        return [int(i) for i in self.word_tree.selection() if i.isdigit()]
