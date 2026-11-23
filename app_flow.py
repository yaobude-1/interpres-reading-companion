"""Application: selection -> bubble -> details -> dictionary flow."""

from __future__ import annotations

import logging
import threading
import time

from rc import capture, textutil, uia_context
from rc.dict_view_controller import view_url
from rc.selection import capture_selected_text
from rc.webview_window import WebViewEntryWindow

log = logging.getLogger("rc")


class FlowMixin:
    def _handle_selection(self, pos: tuple[int, int], exe: str) -> None:
        if not self._enable_hotkeys:
            return
        self._sel_gen += 1
        gen = self._sel_gen
        delay = int((self.config.get("selection") or {}).get("delay_ms", 150)) / 1000.0

        def worker() -> None:
            time.sleep(delay)
            with self._capture_lock:
                title = capture.foreground_title()
                hwnd = capture.foreground_hwnd()
                text = capture_selected_text()
            if not text or not text.strip():
                return
            book = capture.book_from_title(title)
            self.events.put(("sel_button", (gen, text, book, pos, hwnd)))

        threading.Thread(target=worker, daemon=True, name="selection").start()

    def _open_selection_bubble(self, anchor) -> None:
        if not self._pending_selection:
            return
        text, book, _pos, *_rest = self._pending_selection
        clean = textutil.normalize(text)
        if not clean:
            return
        # 单个词先走本地词典，不花 token
        if textutil.looks_like_word(clean):
            log.info("选词走词典")
            self.bubble.hide()
            self._open_dictionary(clean, anchor)
            return
        log.info("选段走翻译（%d 字）", len(clean))
        # 长段落直接进大浮窗：气泡放不下，也没法滚动
        if len(clean) >= 280:
            self.bubble.hide()
            self._begin(clean, book, anchor)
            return
        self._bubble_gen += 1
        gen = self._bubble_gen
        self.bubble.show_loading(anchor)

        def worker() -> None:
            try:
                payload = self._translate_sync(clean, book)
                self.events.put(("bubble_result", (gen, payload, anchor)))
            except Exception as exc:  # noqa: BLE001
                log.exception("气泡翻译失败")
                self.events.put(("bubble_error", (gen, str(exc), anchor)))

        threading.Thread(target=worker, daemon=True, name="bubble").start()

    def _dict_jump(self, word: str) -> None:
        """在查词卡片里点原形/变位形式：按新词再查一次。"""
        if not word:
            return
        anchor = getattr(self.popup, "_anchor", (300, 200)) or (300, 200)
        self._open_dictionary(word, anchor)

    def _open_dictionary(self, word: str, anchor) -> None:
        """本地词典查词：不调用模型。"""

        def worker() -> None:
            try:
                hits = self.service.lookup_all(word, context="popup")
            except Exception:  # noqa: BLE001
                log.exception("查词失败")
                hits = []
            log.info("查词命中 %d 本词典", len(hits))
            if hits:
                entry = next(
                    (h["entry"] for h in hits if (h.get("entry") or {}).get("is_default")),
                    hits[0]["entry"],
                )
                try:
                    self.service.record_lookup(entry, word, "")
                except Exception as exc:  # noqa: BLE001 - 历史失败不影响浮窗
                    log.debug("记录浮窗查词历史失败: %s", exc)
                self.events.put(("dict", (word, entry, anchor, hits)))
            else:
                self.events.put(("dict_missing", (word, anchor)))

        threading.Thread(target=worker, daemon=True, name="lookup").start()

    def show_entry_html(self, word: str, lang: str = "", dict_id: str = "") -> None:
        """打开词典原版条目（和面板同一个 WebView2 渲染器）。"""
        dict_id = (dict_id or "").strip()
        if not dict_id:
            for hit in self.service.lookup_all(word, context="popup"):
                entry = hit.get("entry") or {}
                if lang and entry.get("lang") != lang:
                    continue
                dict_id = str(hit.get("dict_id") or entry.get("dict_id") or "")
                if dict_id:
                    break
        url = self._dict_view_url(word, lang, dict_id)
        if not url:
            return
        window = getattr(self, "_entry_window", None)
        if window is None or not window.win or not window.win.winfo_exists():
            self._entry_dict_id = dict_id
            self._entry_window = WebViewEntryWindow(
                self.root,
                on_lookup=self._entry_lookup,
            )
            window = self._entry_window
        else:
            self._entry_dict_id = dict_id
        window.show(url, word)

    def _dict_view_url(self, word: str, lang: str = "", dict_id: str = "") -> str:
        port, token, running = self._dict_server_info()
        if not running or not port:
            self.toast("原版需要本地词典服务，服务未启动")
            return ""
        return view_url(port, token, word, lang=lang or "en", dict_id=dict_id)

    def _entry_lookup(self, word: str) -> None:
        window = getattr(self, "_entry_window", None)
        if window is None:
            return
        url = self._dict_view_url(word, "", getattr(self, "_entry_dict_id", ""))
        if url:
            window.load(url, word)

    def _show_details(self, payload: dict, anchor) -> None:
        self.popup.show_result(payload, anchor)

    def _open_chat_from_selection(self, anchor) -> None:
        """悬浮按钮点「聊」：不翻译，直接围绕选中的段落开聊。"""
        if not self._pending_selection:
            return
        text, book, _pos, *rest = self._pending_selection
        hwnd = rest[0] if rest else 0
        self.popup.show_chat_pending(text, book, anchor, hwnd)

    def _bubble_chat(self, payload: dict, anchor) -> None:
        """从气泡直接进入对话：先在浮窗里展示译文，再切到聊天。"""
        self.popup.show_result(payload, anchor)
        self.popup._open_chat()

    # ------------------------------------------------------------------ 对话
    def start_chat(self, payload: dict) -> dict:
        context = ""
        if bool(self.config.get("chat_auto_context", True)):
            hwnd = int(payload.get("hwnd") or 0)
            if hwnd:
                info = uia_context.read_context(hwnd)
                if info.get("ok"):
                    context = str(info.get("paragraph") or "").strip()[:6000]
        return self.service.start_conversation(
            payload.get("book") or "",
            payload.get("source_lang") or "",
            payload.get("text") or "",
            payload.get("translation") or "",
            context,
        )

    def set_chat_context(self, conv_id: int, context: str) -> None:
        self.service.set_conversation_context(int(conv_id), (context or "")[:6000])

    def ask_chat(self, conv_id, question: str) -> None:
        def worker() -> None:
            try:
                last = [0.0]

                def on_delta(partial: str) -> None:
                    import time as _t

                    now = _t.time()
                    if now - last[0] < 0.05:
                        return
                    last[0] = now
                    self.events.put(("chat_delta", (conv_id, partial)))

                result = self.service.ask(conv_id, question, on_delta=on_delta)
                self.events.put(("chat_reply", (conv_id, result["reply"])))
            except Exception as exc:  # noqa: BLE001
                log.exception("对话失败")
                self.events.put(("chat_error", (conv_id, str(exc))))

        threading.Thread(target=worker, daemon=True, name="chat").start()

    def _retry(self) -> None:
        if self.popup._pending_text:
            self.start_translation(self.popup._pending_text)

    # ------------------------------------------------------------------ 回调
