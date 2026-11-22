"""Main panel: the conversation tab (messages, streaming replies)."""

from __future__ import annotations

import tkinter as tk

from .theme import (
    BG,
    FONT_FAMILY,
    MUTED,
    PANEL,
    PANEL_ALT,
    TEXT,
)


class PanelChatMixin:
    def _ensure_conversation(self) -> None:
        book = self.book
        latest = self.service.latest_conversation(book) if book else None
        if latest:
            self.conv_id = latest["id"]
        else:
            conv = self.service.start_conversation(book, "", "", "")
            self.conv_id = conv["id"]
        self._render_messages()

    def load_conversation(self, conv_id: int) -> None:
        """把某段历史对话载入面板，接着聊。"""
        conv = self.service.store.conversation(int(conv_id))
        if not conv:
            return
        self.conv_id = int(conv["id"])
        book = (conv.get("book") or "").strip()
        self.book = book
        self._set_book_label(book)
        self.service.config.data["panel_book"] = book
        self._render_messages()
        self._sync_content_scroll()
        self.win.after(60, self._scroll_bottom)

    def _render_messages(self) -> None:
        for child in self.chat_body.winfo_children():
            child.destroy()
        if self.conv_id is None:
            return
        for message in self.service.chat_messages(self.conv_id):
            self._bubble(message.get("role", "assistant"), message.get("content", ""))
        self._scroll_bottom()

    def _bubble(self, role: str, content: str, typing: bool = False) -> tk.Frame:
        row = tk.Frame(self.chat_body, bg=BG)
        row.pack(fill="x", pady=(0, 8))
        mine = role == "user"
        bg = PANEL_ALT if mine else PANEL
        holder = tk.Frame(row, bg=bg)
        holder.pack(side="right" if mine else "left")
        label = tk.Label(
            holder,
            text=content,
            bg=bg,
            fg=TEXT if not typing else MUTED,
            font=(FONT_FAMILY, 10),
            justify="left",
            anchor="w",
            wraplength=520,
            padx=10,
            pady=7,
        )
        label.pack()
        self._bind_wheel(row)
        if typing:
            self._typing = row
            self._typing_label = label
        return row

    def _scroll_bottom(self) -> None:
        self.root.after(10, lambda: self.canvas.yview_moveto(1.0))

    def _at_bottom(self) -> bool:
        try:
            return self.canvas.yview()[1] >= 0.98
        except Exception:
            return True

    def _send(self) -> None:
        text = self.chat_input.get("1.0", "end-1c").strip()
        if not text:
            return
        if self.conv_id is None:
            self._ensure_conversation()
        self.chat_input.delete("1.0", "end")
        self._bubble("user", text)
        self._typing = None
        self._bubble("assistant", "思考中…", typing=True)
        self._scroll_bottom()
        self.cb.get("ask_chat", lambda *_a: None)(self.conv_id, text)

    def receive_chat_delta(self, conv_id, partial: str) -> None:
        """对话流式：只记目标文本，由定时器按速度铺开。"""
        if conv_id != self.conv_id or not self.win.winfo_exists():
            return
        self._chat_target = partial
        if self._chat_job is None:
            self._chat_shown = ""
            try:
                label = getattr(self, "_typing_label", None)
                if self._typing is not None and label is not None and label.winfo_exists():
                    label.configure(text="", fg=TEXT)
                else:
                    self._typing = self._bubble("assistant", "", typing=True)
                    self._typing_label.configure(fg=TEXT)
            except tk.TclError:
                return
            self._chat_tick()

    def _chat_tick(self) -> None:
        self._chat_job = None
        try:
            if not self.win.winfo_exists():
                return
        except tk.TclError:
            return
        pending = self._chat_target[len(self._chat_shown):]
        label = getattr(self, "_typing_label", None)
        if pending:
            try:
                speed = int(self.service.config.get("stream_speed", 60))
            except Exception:
                speed = 60
            speed = max(5, min(400, speed))
            step = max(1, int(speed * 0.033))
            if len(pending) > 240:
                step *= 3
            self._chat_shown += pending[:step]
            try:
                if label is not None and label.winfo_exists():
                    label.configure(text=self._chat_shown, fg=TEXT)
                self._scroll_bottom()
            except tk.TclError:
                return
            self._chat_job = self.win.after(33, self._chat_tick)
            return
        if self._chat_final:
            self._finish_chat()

    def _finish_chat(self) -> None:
        reply = self._chat_reply
        self._cancel_chat_stream()
        label = getattr(self, "_typing_label", None)
        try:
            if self._typing is not None and label is not None and label.winfo_exists():
                label.configure(text=reply, fg=TEXT)
                self._typing = None
                self._typing_label = None
            else:
                if self._typing is not None:
                    self._typing.destroy()
                    self._typing = None
                self._bubble("assistant", reply)
            self._scroll_bottom()
        except tk.TclError:  # 控件可能已销毁，刻意忽略
            pass

    def _cancel_chat_stream(self) -> None:
        job = self._chat_job
        self._chat_job = None
        if job:
            try:
                self.win.after_cancel(job)
            except tk.TclError:  # 控件可能已销毁，刻意忽略
                pass
        self._chat_target = ""
        self._chat_shown = ""
        self._chat_reply = ""
        self._chat_final = False

    def receive_chat(self, conv_id, reply: str) -> None:
        if conv_id != self.conv_id or not self.win.winfo_exists():
            return
        self._chat_reply = reply
        self._chat_target = reply
        self._chat_final = True
        if self._chat_job is None:
            # 已经追平（或没有增量）：直接定稿
            if self._chat_shown:
                self._finish_chat()
            else:
                self._typing = self._bubble("assistant", reply, typing=True)
                self._typing_label.configure(fg=TEXT)
                self._finish_chat()

    def receive_chat_error(self, conv_id, message: str) -> None:
        if conv_id != self.conv_id:
            return
        if self._typing is not None:
            self._typing.destroy()
            self._typing = None
        self._bubble("assistant", f"出错了：{message}")

    # ------------------------------------------------------------------ 查词
