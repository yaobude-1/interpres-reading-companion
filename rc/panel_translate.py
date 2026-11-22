"""Main panel: the translate tab (streaming output, progress, errors)."""

from __future__ import annotations

import tkinter as tk

from .theme import (
    GREEN,
    MUTED,
    RED,
)


class PanelTranslateMixin:
    def _translate(self) -> None:
        text = self.input.get("1.0", "end-1c").strip()
        if not text:
            self._set_status("先粘贴或输入要翻译的文字", RED)
            return
        self._set_status("翻译中…", MUTED)
        self.cb.get("translate", lambda *_a: None)(text, self.book)

    def show_partial(self, text: str) -> None:
        """流式：只更新目标文本，真正的显示由定时器按速度铺开。"""
        if not text:
            return
        self._stream_target = text
        if self._stream_job is None:
            self._stream_shown = ""
            try:
                self.output.configure(state="normal")
                self.output.delete("1.0", "end")
            except tk.TclError:
                return
            self._stream_tick()

    def _stream_speed(self) -> int:
        try:
            speed = int(self.service.config.get("stream_speed", 60))
        except Exception:
            speed = 60
        return max(5, min(400, speed))

    def _stream_tick(self) -> None:
        self._stream_job = None
        try:
            if not self.output.winfo_exists():
                return
        except tk.TclError:
            return
        pending = self._stream_target[len(self._stream_shown):]
        if pending:
            step = max(1, int(self._stream_speed() * 0.033))
            if len(pending) > 240:
                step *= 3  # 落后太多时自动追赶
            piece = pending[:step]
            self._stream_shown += piece
            try:
                self.output.configure(state="normal")
                self.output.insert("end", piece)
                self._fit_output_height()
            except tk.TclError:
                return
            self._stream_job = self.win.after(33, self._stream_tick)
            return
        # 追平了：如果有最终结果，收尾
        if self._stream_final is not None:
            payload = self._stream_final
            self._stream_final = None
            self._stream_target = ""
            self._stream_shown = ""
            self._finish_result(payload)

    def show_result(self, payload: dict) -> None:
        translation = payload.get("translation") or ""
        self._stream_final = payload
        if not translation:
            self._finish_result(payload)
            return
        if self._stream_job is None and not self._stream_shown:
            # 非流式路径（缓存/兼容接口）：也铺开显示
            self._stream_target = translation
            self._stream_tick()
        else:
            self._stream_target = translation

    def _finish_result(self, payload: dict) -> None:
        translation = payload.get("translation") or ""
        self._cancel_stream()
        try:
            self.output.configure(state="normal")
            self.output.delete("1.0", "end")
            self.output.insert("1.0", translation)
            self.output.configure(state="disabled")
            self._fit_output_height()
        except tk.TclError:  # 控件可能已销毁，刻意忽略
            pass
        self._set_status(f"完成 · {payload.get('meta', {}).get('elapsed_ms', 0)} ms", GREEN)
        self._sync_content_scroll()
        if self.conv_id is not None:
            self.service.update_conversation_context(
                self.conv_id, payload.get("text", ""), translation
            )

    def _cancel_stream(self) -> None:
        job = self._stream_job
        self._stream_job = None
        if job:
            try:
                self.win.after_cancel(job)
            except tk.TclError:  # 控件可能已销毁，刻意忽略
                pass
        self._stream_target = ""
        self._stream_shown = ""
        self._stream_final = None

    def _max_output_lines(self) -> int:
        import tkinter.font as tkfont

        try:
            height = self.win.winfo_height()
            linespace = tkfont.Font(font=self.output.cget("font")).metrics("linespace")
            return max(6, int(height * 0.6 / max(1, linespace)))
        except Exception:
            return 30

    def _fit_output_height(self) -> None:
        try:
            count = self.output.count("1.0", "end-1c", "displaylines")
            lines = (count[0] if isinstance(count, tuple) else count) or 1
        except Exception:
            text = self.output.get("1.0", "end-1c")
            lines = text.count("\n") + max(1, len(text) // 60)
        lines = max(4, min(int(lines) + 1, self._max_output_lines()))
        try:
            if int(self.output.cget("height")) != lines:
                self.output.configure(height=lines)
                self._sync_content_scroll()
        except tk.TclError:  # 控件可能已销毁，刻意忽略
            pass

    def show_progress(self, index: int, total: int) -> None:
        if index == 1:
            self._cancel_stream()
            try:
                self.output.configure(state="normal")
                self.output.delete("1.0", "end")
                self.output.configure(state="disabled")
            except tk.TclError:  # 控件可能已销毁，刻意忽略
                pass
        if total > 1:
            self._set_status(f"翻译中… {index}/{total}", MUTED)

    def show_error(self, message: str) -> None:
        self._set_status(message[:80], RED)

    def _set_status(self, text: str, color: str = MUTED) -> None:
        try:
            self.status.configure(text=text, fg=color)
        except tk.TclError:  # 控件可能已销毁，刻意忽略
            pass

    def _clear(self) -> None:
        self._cancel_stream()
        self.input.delete("1.0", "end")
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.configure(state="disabled")
        self._set_status("", MUTED)
