"""Popup: inline chat view (streaming bubbles, input bar)."""

from __future__ import annotations

import tkinter as tk

from . import textutil
from .theme import (
    ACCENT,
    BG,
    DIM,
    FONT_FAMILY,
    MUTED,
    PANEL,
    PANEL_ALT,
    TEXT,
)
from .theme import ON_ACCENT


class ChatViewMixin:
    def _open_chat(self) -> None:
        if self._mode != "translate":
            return
        payload = self.current or self._pending_payload
        if not payload:
            return
        starter = self.cb.get("start_chat")
        if not starter:
            return
        try:
            conversation = starter(payload)
        except Exception as exc:  # noqa: BLE001
            self.cb.get("toast", lambda _m: None)(f"打开对话失败：{exc}")
            return
        if conversation:
            self.show_chat(conversation)

    def show_chat_pending(self, text: str, book: str, anchor, hwnd: int = 0) -> None:
        """不经过翻译，直接围绕一段文字开聊（悬浮按钮的「聊」走这里）。"""
        self.current = None
        self._anchor = anchor
        self._pending_payload = {
            "text": text,
            "translation": "",
            "book": book,
            "source_lang": "",
            "terms": [],
            "grammar": None,
            "meta": {},
            "hwnd": hwnd,
        }
        self._reset_to_translate(chat_button=True)
        self._open_chat()

    def show_chat(self, conversation: dict, anchor=None, payload: dict | None = None) -> None:
        self._mode = "chat"
        self._conv_id = conversation.get("id")
        if anchor is not None:
            self._anchor = anchor
        book = conversation.get("book") or (self.current or {}).get("book", "")
        self.btn_chat.configure(text="← 返回译文")
        self.btn_chat.pack(side="right")
        if book:
            self.title.configure(text=f"与《{textutil.display(book, 18)}》聊聊")
        else:
            self.title.configure(text="阅读伙伴")
        self._clear()

        if payload is None:
            payload = self.current or self._pending_payload or {}
        source = payload.get("text") or conversation.get("passage") or ""
        if source:
            quote = tk.Frame(self.body, bg=PANEL_ALT)
            quote.pack(fill="x", pady=(0, 10))
            self._label(quote, "正在读", fg=DIM, font=(FONT_FAMILY, 8), bg=PANEL_ALT).pack(
                anchor="w", padx=10, pady=(6, 0)
            )
            self._label(
                quote,
                textutil.display(source, 160),
                fg=MUTED,
                font=(FONT_FAMILY, 9),
                bg=PANEL_ALT,
                wraplength=self.width - 54,
            ).pack(fill="x", padx=10, pady=(2, 8))

        if source:
            self._chat_source = source
            self._chat_context = (conversation.get("context") or "").strip()
            ctx_bar = tk.Frame(self.body, bg=BG)
            ctx_bar.pack(fill="x", pady=(0, 8))
            self._chat_context_label = self._label(
                ctx_bar, "", fg=DIM, font=(FONT_FAMILY, 8)
            )
            self._chat_context_label.pack(side="left")
            self._chat_context_button = self._label(
                ctx_bar, "", fg=ACCENT, font=(FONT_FAMILY, 8)
            )
            self._chat_context_button.pack(side="left", padx=(8, 0))
            self._chat_context_button.configure(cursor="hand2")
            self._chat_context_button.bind(
                "<Button-1>", lambda _e: self._edit_chat_context()
            )
            self._update_chat_context()

        self.messages_frame = tk.Frame(self.body, bg=BG)
        self.messages_frame.pack(fill="both", expand=True)
        for message in conversation.get("messages") or []:
            self._bubble(message.get("role", "assistant"), message.get("content", ""))

        self.footer.configure(text="Enter 发送 · Shift+Enter 换行 · Esc 返回译文")
        self._build_input_bar()
        self.input_bar.pack(
            side="bottom", fill="x", padx=14, pady=(4, 2), before=self.scrollbar
        )
        self._reveal()
        if self.chat_input is not None:
            self.chat_input.focus_set()
        self._scroll_bottom()

    def _build_input_bar(self) -> None:
        for child in self.input_bar.winfo_children():
            child.destroy()
        # 先放发送按钮，再放输入框，否则输入框会把按钮挤没
        send = tk.Label(
            self.input_bar,
            text="发送",
            bg=ACCENT,
            fg=ON_ACCENT,
            font=(FONT_FAMILY, 9),
            padx=12,
            pady=8,
            cursor="hand2",
        )
        send.pack(side="right", padx=(8, 0), fill="y")
        send.bind("<Button-1>", lambda _e: self._send_chat())
        self.chat_input = tk.Text(
            self.input_bar,
            height=3,
            width=20,
            bg=PANEL,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            font=(FONT_FAMILY, 10),
            wrap="word",
            padx=8,
            pady=6,
        )
        self.chat_input.pack(side="left", fill="both", expand=True)
        self.chat_input.bind("<Return>", self._on_input_return)
        self.chat_input.bind("<Shift-Return>", lambda _e: None)

    def _on_input_return(self, _event=None) -> str:
        self._send_chat()
        return "break"

    def _update_chat_context(self) -> None:
        if not hasattr(self, "_chat_context_label"):
            return
        context = getattr(self, "_chat_context", "")
        source = getattr(self, "_chat_source", "")
        if context:
            text = f"已读取所在段落（{len(context)} 字）"
            action = "编辑上下文"
        elif len(source) >= 40:
            text = f"已收到选中的段落（{len(source)} 字）"
            action = "补充上下文"
        else:
            text = "只收到选中的词，可补充上下文"
            action = "补充上下文"
        self._chat_context_label.configure(text=text)
        self._chat_context_button.configure(text=action)

    def _edit_chat_context(self) -> None:
        if not self._conv_id:
            return
        win = tk.Toplevel(self.win)
        win.title("补充上下文")
        win.configure(bg=BG)
        win.transient(self.win)
        x = self.win.winfo_rootx() + 30
        y = self.win.winfo_rooty() + 30
        win.geometry(f"480x300+{x}+{y}")
        tk.Label(
            win,
            text="粘贴选中文字前后的句子或段落；AI 下次回答会参考它。",
            bg=BG, fg=MUTED, font=(FONT_FAMILY, 9), justify="left",
            wraplength=450,
        ).pack(fill="x", padx=12, pady=(10, 4))
        box = tk.Text(
            win, bg=PANEL, fg=TEXT, insertbackground=TEXT, relief="flat",
            font=(FONT_FAMILY, 10), wrap="word", padx=8, pady=6,
        )
        box.pack(fill="both", expand=True, padx=12)
        box.insert("1.0", getattr(self, "_chat_context", ""))

        def save() -> None:
            value = box.get("1.0", "end-1c").strip()
            self.cb.get("set_chat_context", lambda *_a: None)(self._conv_id, value)
            self._chat_context = value
            self._update_chat_context()
            win.destroy()

        btns = tk.Frame(win, bg=BG)
        btns.pack(fill="x", padx=12, pady=8)
        tk.Button(
            btns, text="保存", command=save, bg=ACCENT, fg=ON_ACCENT,
            relief="flat", font=(FONT_FAMILY, 9), padx=12, pady=3,
        ).pack(side="right")
        tk.Button(
            btns, text="取消", command=win.destroy, bg=PANEL, fg=TEXT,
            relief="flat", font=(FONT_FAMILY, 9), padx=12, pady=3,
        ).pack(side="right", padx=(0, 8))
        win.bind("<Escape>", lambda _e: win.destroy())
        box.focus_set()

    def _bubble(self, role: str, content: str, typing: bool = False) -> tk.Frame:
        row = tk.Frame(self.messages_frame, bg=BG)
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
            wraplength=self.width - 90,
            padx=10,
            pady=7,
        )
        label.pack()
        if typing:
            self._typing = row
            self._typing_label = label
        # 新加的气泡也要能滚轮滚动
        self._bind_wheel(row)
        return row

    def _scroll_bottom(self) -> None:
        self.root.after(10, lambda: self.canvas.yview_moveto(1.0))

    def _send_chat(self) -> None:
        if self._mode != "chat" or self.chat_input is None:
            return
        text = self.chat_input.get("1.0", "end-1c").strip()
        if not text:
            return
        self.chat_input.delete("1.0", "end")
        self._bubble("user", text)
        self._typing = None
        self._bubble("assistant", "思考中…", typing=True)
        self._scroll_bottom()
        self.cb.get("ask_chat", lambda *_a: None)(self._conv_id, text)

    def _at_bottom(self) -> bool:
        try:
            return self.canvas.yview()[1] >= 0.98
        except Exception:
            return True

    def receive_chat_delta(self, conv_id, partial: str) -> None:
        if self._mode != "chat" or conv_id != self._conv_id:
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
                speed = int(self.config.get("stream_speed", 60))
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
        if self._mode != "chat" or conv_id != self._conv_id:
            return
        self._chat_reply = reply
        self._chat_target = reply
        self._chat_final = True
        if self._chat_job is None:
            if self._chat_shown:
                self._finish_chat()
            else:
                self._typing = self._bubble("assistant", reply, typing=True)
                self._typing_label.configure(fg=TEXT)
                self._finish_chat()

    def receive_chat_error(self, conv_id, message: str) -> None:
        if self._mode != "chat" or conv_id != self._conv_id:
            return
        stick = self._at_bottom()
        if self._typing is not None:
            self._typing.destroy()
            self._typing = None
        self._bubble("assistant", f"出错了：{message}")
        if stick:
            self._scroll_bottom()

    def back_to_translation(self) -> None:
        self.input_bar.pack_forget()
        if self.current:
            self.show_result(self.current, self._anchor)
        else:
            self.hide()
