"""Application: main-panel wiring (translate, ask, history windows)."""

from __future__ import annotations

import logging
import threading

from rc import capture, textutil

log = logging.getLogger("rc")


class PanelMixin:
    def panel_translate(self, text: str, book: str) -> None:
        lang = self._book_lang(book)
        if lang and not self._ask_lang_consent(lang):
            self.panel.show_error("该语言还没有配置词典，已取消翻译")
            return

        def worker() -> None:
            try:
                payload = self.service.translate(
                    text,
                    book=book,
                    on_progress=lambda i, n: self.events.put(("panel_progress", (i, n))),
                    on_partial=lambda partial: self.events.put(
                        ("panel_partial", partial)
                    ),
                )
                self.events.put(("panel_result", payload))
            except Exception as exc:  # noqa: BLE001
                log.exception("面板翻译失败")
                self.events.put(("panel_error", str(exc)))

        threading.Thread(target=worker, daemon=True, name="panel-translate").start()

    def panel_ask(self, conv_id, question: str) -> None:
        def worker() -> None:
            try:
                last = [0.0]

                def on_delta(partial: str) -> None:
                    import time as _t

                    now = _t.time()
                    if now - last[0] < 0.05:
                        return
                    last[0] = now
                    self.events.put(("panel_chat_delta", (conv_id, partial)))

                result = self.service.ask(conv_id, question, on_delta=on_delta)
                self.events.put(("panel_chat", (conv_id, result["reply"])))
            except Exception as exc:  # noqa: BLE001
                log.exception("面板对话失败")
                self.events.put(("panel_chat_error", (conv_id, str(exc))))

        threading.Thread(target=worker, daemon=True, name="panel-chat").start()

    def _close_panel(self) -> None:
        """主界面的 Esc / ✕：有托盘就隐藏，没有则按设置退出/隐藏。"""
        if self.config.get("quit_on_panel_close", True):
            log.info("关闭主界面 → 退出程序")
            self.shutdown()
        else:
            log.info("关闭主界面 → 隐藏")
            self.panel.hide()
            tray = getattr(self, "tray", None)
            if tray is not None and tray.active:
                self.root.after(
                    100, lambda: self.toast("已隐藏到托盘，双击托盘图标可打开")
                )

    def open_chat_history(self) -> None:
        from rc.chat_ui import ChatHistoryWindow

        if self._chat_win is None or not self._chat_win.win.winfo_exists():
            self._chat_win = ChatHistoryWindow(
                self.root, self.service, on_open=self._switch_conversation
            )
        self._chat_win.show()

    def _switch_conversation(self, conv_id: int) -> None:
        """从对话记录里挑一段，接管到主面板继续聊。"""
        try:
            self.open_panel()
            self.panel.load_conversation(int(conv_id))
            self.panel.win.lift()
            self.panel.win.focus_force()
        except Exception as exc:  # noqa: BLE001
            self.toast(f"切换对话失败：{exc}")

    def open_translation_history(self) -> None:
        from rc.translation_ui import TranslationWindow

        if self._trans_win is None or not self._trans_win.win.winfo_exists():
            self._trans_win = TranslationWindow(self.root, self.service)
        self._trans_win.show()

    # ------------------------------------------------------------------ 翻译流程
    def start_translation(self, text: str | None = None) -> None:
        if self._busy.locked():
            return
        self.quick.hide()
        self.bubble.hide()
        anchor = capture.cursor_pos()
        if text is not None:
            self._begin(text, "", anchor)
            return
        # 先给反馈，再慢慢抓取
        self.events.put(("busy", anchor))

        def worker() -> None:
            with self._busy:
                selected, title = capture.grab_selection()
                if not selected or not selected.strip():
                    self.events.put(("input", (anchor, capture.read_clipboard() or "")))
                    return
                if textutil.looks_like_word(selected):
                    self._open_dictionary(selected.strip(), anchor)
                    return
                book = capture.book_from_title(title)
                # 交给主线程处理：_begin 可能弹语言确认框，不能在后台线程碰 Tk
                self.events.put(("begin", (selected, book, anchor)))

        threading.Thread(target=worker, daemon=True, name="capture").start()

    def manual_translate(self, text: str) -> None:
        self.start_translation(text)

    def _begin(self, text: str, book: str, anchor) -> None:
        clean = textutil.normalize(text)
        if not clean:
            self.events.put(("error", ("选中的内容为空。", anchor)))
            return
        lang = self._book_lang(book)
        if lang and not self._ask_lang_consent(lang):
            self.events.put(("error", ("该语言还没有配置词典，已取消翻译。", anchor)))
            return
        self.events.put(("loading", (clean, book, anchor)))

        def worker() -> None:
            try:
                payload = self._translate_sync(
                    clean,
                    book,
                    on_progress=lambda i, n: self.events.put(("progress", (i, n))),
                )
                self.events.put(("result", (payload, anchor)))
            except Exception as exc:  # noqa: BLE001
                log.exception("翻译失败")
                self.events.put(("error", (str(exc), anchor)))

        threading.Thread(target=worker, daemon=True, name="translate").start()

    def _translate_sync(self, clean: str, book: str, on_progress=None) -> dict:
        """带上下文缓冲的翻译，浮窗和气泡共用。"""
        context_before = ""
        context_after = ""
        recent_key = book or "_"
        if textutil.looks_like_word(clean):
            context_before, context_after = self.service.recent_context(
                recent_key, int(self.config.get("context_chars", 1800))
            )
        payload = self.service.translate(
            clean,
            book=book,
            context_before=context_before,
            context_after=context_after,
            on_progress=on_progress,
        )
        self.service.remember(recent_key, clean)
        return payload

    # -------------------------------------------------------------- 划词小按钮
