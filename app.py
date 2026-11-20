"""Interpres —— 入口。

单独运行：
    pythonw app.py                # 正常后台运行（无控制台）
    python  app.py --debug        # 带控制台，看日志
    python  app.py --translate "text"   # 命令行翻译一次（调试用）
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import logging
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

from rc import __version__
from rc import capture, textutil
from rc.bubble import Bubble, QuickButton
from rc.config import Config
from rc.hotkey import HotkeyWatcher
from rc.htmlview import EntryViewer
from rc.instance import SingleInstance
from rc.panel import MainPanel
from rc.popup import PopupWindow
from rc.selection import MouseWatcher, capture_selected_text, foreground_exe
from rc.server import ApiServer
from rc.service import Service
from rc.settings_ui import SettingsWindow

log = logging.getLogger("rc")


class Application:
    def __init__(self, config: Config, *, enable_hotkeys: bool = True, silent: bool = False) -> None:
        self.config = config
        self.silent = silent
        self.service = Service(config)
        try:
            from .capture import set_user_blocklist as _set_blocklist
        except ImportError:
            from rc.capture import set_user_blocklist as _set_blocklist
        _set_blocklist(config.get("book_ignore_keywords") or [])
        try:
            removed = self.service.store.purge_empty_conversations()
            if removed:
                log.info("清理空白对话 %d 条", removed)
        except Exception:
            log.exception("清理空白对话失败")
        self.events: queue.Queue = queue.Queue()
        self.quitting = False
        self._settings: SettingsWindow | None = None
        self._entry_viewer = None
        self._chat_win = None
        self._trans_win = None
        self._toast_win: tk.Toplevel | None = None
        self._toast_job = None
        self._busy = threading.Lock()
        self._capture_lock = threading.Lock()

        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title("Interpres")
        try:
            base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
            icon = base_dir / "assets" / "reading-companion.ico"
            if icon.exists():
                self.root.iconbitmap(default=str(icon))
        except Exception:
            pass
        self._setup_dpi()

        self.popup = PopupWindow(
            self.root,
            config,
            {
                "save_word": self.save_word,
                "find_word": self.service.find_vocab,
                "remove_word": self.service.remove_vocab,
                "push_anki": self.push_anki,
                "speak": self.speak,
                "stop_speak": self.service.tts.stop,
                "settings": self.open_settings,
                "toast": self.toast,
                "lang_label": self.service.lang_label,
                "lock_term": self.lock_term,
                "manual_translate": self.manual_translate,
                "start_chat": self.start_chat,
                "ask_chat": self.ask_chat,
                "dict_lookup": self._dict_jump,
                "show_entry": self.show_entry_html,
                "fuzzy": lambda w, lang="": self.service.fuzzy_lookup(w, lang or None, 12),
            },
        )

        self.bubble = Bubble(
            self.root,
            config,
            {
                "toast": self.toast,
                "details": self._show_details,
                "chat": self._bubble_chat,
            },
        )
        self.quick = QuickButton(
            self.root, config, self._open_selection_bubble, self._open_chat_from_selection
        )
        try:
            geometry = str(self.config.get("panel_geometry") or "")
            if geometry:
                self.panel.win.geometry(geometry)
        except Exception:
            pass
        self._pending_selection: tuple[str, str, tuple[int, int]] | None = None
        self._sel_gen = 0
        self._bubble_gen = 0
        self._sel_watcher: MouseWatcher | None = None

        self.panel = MainPanel(
            self.root,
            self.service,
            {
                "translate": self.panel_translate,
                "ask_chat": self.panel_ask,
                "settings": self.open_settings,
                "chat_history": self.open_chat_history,
                "translations": self.open_translation_history,
                "save_word": self.save_word,
                "find_word": self.service.find_vocab,
                "remove_word": self.service.remove_vocab,
                "speak": self.speak,
                "show_entry": self.show_entry_html,
                "close": self._close_panel,
            },
        )

        self.api = ApiServer(
            self.service,
            port=int(config.get("server_port", 18777)),
            token=str(config.get("server_token", "")),
            on_show_settings=self._on_show_settings_request,
            on_show_panel=lambda: self.events.put(("show_panel", None)),
        )
        self._api_error: str | None = None
        self._enable_hotkeys = enable_hotkeys
        if enable_hotkeys:
            try:
                self.api.start()
                log.info("API 已启动：http://127.0.0.1:%s", config.get("server_port"))
            except OSError as exc:
                self._api_error = str(exc)
                log.warning("API 启动失败：%s", exc)

        self.watcher: HotkeyWatcher | None = None
        if enable_hotkeys:
            self._start_hotkeys()
            self._start_selection_watch()

        self.tray = None
        if enable_hotkeys:
            try:
                from rc.tray import TrayIcon

                icon_path = Path(
                    getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)
                ) / "assets" / "reading-companion.ico"
                self.tray = TrayIcon(
                    icon_path,
                    on_open_panel=lambda: self.events.put(("show_panel", None)),
                    on_open_settings=lambda: self.events.put(("open_settings", None)),
                    on_quit=lambda: self.events.put(("quit", None)),
                )
                if self.tray.start():
                    log.info("托盘图标已启动")
                else:
                    log.warning("托盘图标启动失败：%s", self.tray.error)
                    self.tray = None
            except Exception:
                log.exception("托盘初始化失败")
                self.tray = None

        self.root.after(30, self._pump)

    # ------------------------------------------------------------------ 初始化
    def _setup_dpi(self) -> None:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass
        try:
            dpi = float(self.root.winfo_fpixels("1i"))
            if dpi > 0:
                self.root.tk.call("tk", "scaling", dpi / 72.0)
        except Exception:
            pass

    def _start_hotkeys(self) -> None:
        combos = {
            "translate": str(self.config.get("hotkey", "ctrl+alt+t")),
            "settings": str(self.config.get("settings_hotkey", "ctrl+alt+s")),
        }
        try:
            self.watcher = HotkeyWatcher(combos, lambda name: self.events.put(("hotkey", name)))
            self.watcher.start()
            log.info("热键已注册：%s", combos)
        except Exception as exc:  # noqa: BLE001
            log.error("热键注册失败：%s", exc)
            self.toast(f"热键注册失败：{exc}")

    def restart_hotkeys(self) -> None:
        if self.watcher:
            self.watcher.stop()
        self._start_hotkeys()

    def _start_selection_watch(self) -> None:
        if self._sel_watcher is not None:
            self._sel_watcher.stop()
            self._sel_watcher = None
        cfg = self.config.get("selection") or {}
        if not cfg.get("enabled", True):
            log.info("划词监听已关闭")
            return
        try:
            self._sel_watcher = MouseWatcher(
                self.config,
                lambda pos, exe: self.events.put(("selection", (pos, exe))),
                on_press=lambda pos: self.events.put(("press", pos)),
            )
            self._sel_watcher.start()
            log.info("划词监听已启动，白名单：%s", cfg.get("whitelist"))
        except Exception as exc:  # noqa: BLE001
            log.error("划词监听启动失败：%s", exc)

    # ------------------------------------------------------------------ 事件循环
    def _pump(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "hotkey":
                    self._on_hotkey(payload)
                elif kind == "loading":
                    text, book, anchor = payload
                    self.popup.show_loading(text, book, "", anchor)
                elif kind == "busy":
                    self.popup.show_busy(payload)
                elif kind == "dict":
                    if len(payload) == 4:
                        word, entry, anchor, hits = payload
                        self.popup.show_dictionary(entry, anchor, word, hits)
                    else:
                        word, entry, anchor = payload
                        self.popup.show_dictionary(entry, anchor, word)
                elif kind == "dict_missing":
                    word, anchor = payload
                    self.popup.show_dict_missing(word, anchor, self.service.has_dictionaries())
                elif kind == "result":
                    payload_data, anchor = payload
                    detected = (payload_data.get("source_lang") or "").lower()
                    if detected and not self._ask_lang_consent(detected):
                        self.popup.show_error("该语言还没有配置词典，已取消翻译。", retry=self._retry)
                        break
                    self.popup.show_result(payload_data, anchor)
                    if payload_data.get("book"):
                        self.panel.on_book(payload_data["book"])
                elif kind == "input":
                    anchor, clipboard_text = payload
                    self.popup.show_input(anchor, clipboard_text)
                elif kind == "error":
                    message, anchor = payload
                    self.popup.show_error(message, retry=self._retry)
                elif kind == "press":
                    # 任何点在别处的鼠标按下，都收起残留的按钮和气泡
                    self.quick.hide()
                    self.bubble.hide()
                elif kind == "selection":
                    pos, exe = payload
                    self._handle_selection(pos, exe)
                elif kind == "sel_button":
                    gen, text, book, pos = payload
                    if gen == self._sel_gen:
                        self._pending_selection = (text, book, pos)
                        self.popup.hide()
                        self.bubble.hide()
                        self.quick.show(pos)
                elif kind == "bubble_result":
                    gen, payload_data, anchor = payload
                    if gen == self._bubble_gen:
                        detected = (payload_data.get("source_lang") or "").lower()
                        if detected and not self._ask_lang_consent(detected):
                            self.bubble.show_error("该语言还没有配置词典。", anchor)
                            break
                        self.bubble.show_result(payload_data, anchor)
                        if payload_data.get("book"):
                            self.panel.on_book(payload_data["book"])
                elif kind == "bubble_error":
                    gen, message, anchor = payload
                    if gen == self._bubble_gen:
                        self.bubble.show_error(message, anchor)
                elif kind == "progress":
                    index, total = payload
                    if total > 1:
                        self.popup.set_progress(f"正在翻译… {index}/{total}")
                elif kind == "panel_progress":
                    index, total = payload
                    self.panel.show_progress(index, total)
                elif kind == "panel_partial":
                    self.panel.show_partial(payload)
                elif kind == "panel_result":
                    detected = (payload.get("source_lang") or "").lower()
                    if detected and not self._ask_lang_consent(detected):
                        self.panel.show_error("该语言还没有配置词典，已取消翻译")
                        break
                    self.panel.show_result(payload)
                elif kind == "panel_error":
                    self.panel.show_error(payload)
                elif kind == "panel_chat_delta":
                    conv_id, partial = payload
                    self.panel.receive_chat_delta(conv_id, partial)
                elif kind == "panel_chat":
                    conv_id, reply = payload
                    self.panel.receive_chat(conv_id, reply)
                elif kind == "panel_chat_error":
                    conv_id, message = payload
                    self.panel.receive_chat_error(conv_id, message)
                elif kind == "chat_delta":
                    conv_id, partial = payload
                    self.popup.receive_chat_delta(conv_id, partial)
                elif kind == "chat_reply":
                    conv_id, reply = payload
                    self.popup.receive_chat(conv_id, reply)
                elif kind == "chat_error":
                    conv_id, message = payload
                    self.popup.receive_chat_error(conv_id, message)
                elif kind == "toast":
                    self.toast(payload)
                elif kind == "show_panel":
                    self.open_panel()
                elif kind == "open_settings":
                    self.open_settings()
                elif kind == "settings":
                    self.open_panel()
                elif kind == "quit":
                    self.shutdown()
                    return
        except queue.Empty:
            pass
        self._follow_active_book()
        if not self.quitting:
            self.root.after(25, self._pump)

    def _follow_active_book(self) -> None:
        """主界面开着时盯着前台阅读器：开了「自动跟随」才换书。"""
        if not self.config.get("auto_follow_book", False):
            return
        now = time.time()
        if now - getattr(self, "_book_check_at", 0.0) < 1.0:
            return
        self._book_check_at = now
        try:
            if not self.panel.win.winfo_viewable():
                return
            exe = foreground_exe() or ""
            allowed = [
                str(x).lower() for x in (self.config.get("selection", {}).get("whitelist") or [])
            ]
            if not exe or exe not in allowed:
                return
            title = capture.foreground_title()
            if not title or "Interpres" in title:
                return
            book = capture.book_from_title(title)
            if book and book != self.panel.book:
                log.info("前台换书：%s → %s", self.panel.book, book)
                self.panel.on_book(book)
        except Exception:
            pass

    def _on_show_settings_request(self) -> None:
        """另一个实例（用户又点了图标）请求把主面板打开。"""
        log.info("收到「打开主面板」请求")
        self.events.put(("settings", None))

    def _on_hotkey(self, name: str) -> None:
        if name == "settings":
            # 热键现在打开主面板，设置从面板右上角的齿轮进
            self.open_panel()
        elif name == "translate":
            self.start_translation()

    def open_panel(self) -> None:
        # 「自动跟随当前书籍」打开时，按前台阅读器的标题识别书名；否则用上次手动选的
        book = ""
        if self.config.get("auto_follow_book", False):
            try:
                exe = foreground_exe() or ""
                allowed = [
                    str(x).lower()
                    for x in (self.config.get("selection", {}).get("whitelist") or [])
                ]
                if exe and (not allowed or exe in allowed):
                    title = capture.foreground_title()
                    if title and "Interpres" not in title:
                        book = capture.book_from_title(title)
            except Exception:
                pass
        self.panel.show(book)
        # 只有语言切换触发的自动重启才恢复上次标签页；普通启动默认翻译页
        if bool(self.config.get("restore_panel_tab", False)):
            tab = str(self.config.get("panel_tab") or "")
            self.config.data["restore_panel_tab"] = False
            self.config.save()
            if tab:
                try:
                    self.panel._show_tab(tab)
                except Exception:
                    pass

    def restart(self) -> None:
        """保存窗口状态，释放单实例并启动一个新进程。"""
        try:
            if getattr(self, "panel", None) is not None:
                self.config.data["panel_geometry"] = self.panel.win.geometry()
                self.config.data["panel_tab"] = getattr(self.panel, "current_tab", "translate")
                self.config.data["restore_panel_tab"] = True
            self.config.save()
        except Exception:
            pass
        global _MUTEX_HANDLE
        try:
            if _MUTEX_HANDLE:
                ctypes.windll.kernel32.CloseHandle(_MUTEX_HANDLE)
                _MUTEX_HANDLE = None
        except Exception:
            pass
        self.shutdown()
        try:
            if getattr(sys, "frozen", False):
                cmd = [sys.executable]
                cwd = Path(sys.executable).resolve().parent
            else:
                script = Path(__file__).resolve()
                cmd = [sys.executable, str(script)]
                cwd = script.parent
            cmd += ["--data-dir", str(self.config.data_dir)]
            flags = 0
            if os.name == "nt":
                flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            subprocess.Popen(
                cmd,
                cwd=str(cwd),
                close_fds=True,
                creationflags=flags,
            )
        except Exception:
            pass

    def _book_lang(self, book: str) -> str:
        if not book:
            return ""
        try:
            for row in self.service.store.books():
                if (row.get("name") or "") == book:
                    return (row.get("lang") or "").lower()
        except Exception:
            pass
        return ""

    def _ask_lang_consent(self, lang: str) -> bool:
        """没有词典的语言：先问是否允许只用 AI。"""
        if not getattr(self, "_enable_hotkeys", True):
            return True
        if not lang or self.service.language_allowed(lang):
            return True
        name = self.service.lang_label(lang)
        parent = self.root
        try:
            if self.panel.win.winfo_exists():
                parent = self.panel.win
        except Exception:
            pass
        allowed = messagebox.askyesno(
            "没有词典",
            f"「{name}」还没有配置本地词典。\n\n"
            "允许用 AI 直接翻译吗？\n\n"
            "选「否」将不会翻译，需要先在 词典设置 里添加这门语言的词典。",
            parent=parent,
        )
        if allowed:
            self.service.allow_ai_language(lang)
            log.info("用户允许 %s 只用 AI", lang)
            return True
        messagebox.showinfo(
            "需要词典",
            "请先到 设置 → 词典与发音 → 词典设置 里，给这门语言添加 MDX 词典。",
            parent=parent,
        )
        return False

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
                self._begin(selected, book, anchor)

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
                text = capture_selected_text()
            if not text or not text.strip():
                return
            book = capture.book_from_title(title)
            self.events.put(("sel_button", (gen, text, book, pos)))

        threading.Thread(target=worker, daemon=True, name="selection").start()

    def _open_selection_bubble(self, anchor) -> None:
        if not self._pending_selection:
            return
        text, book, _ = self._pending_selection
        clean = textutil.normalize(text)
        if not clean:
            return
        # 单个词先走本地词典，不花 token
        if textutil.looks_like_word(clean):
            log.info("选词走词典：%r", clean)
            self.bubble.hide()
            self._open_dictionary(clean, anchor)
            return
        log.info("选段走翻译：%r（%d 字）", clean[:40], len(clean))
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
                hits = self.service.lookup_all(word)
            except Exception:  # noqa: BLE001
                log.exception("查词失败")
                hits = []
            log.info("查词 %r → %d 本词典命中", word, len(hits))
            if hits:
                self.events.put(("dict", (word, hits[0]["entry"], anchor, hits)))
            else:
                self.events.put(("dict_missing", (word, anchor)))

        threading.Thread(target=worker, daemon=True, name="lookup").start()

    def show_entry_html(self, word: str, lang: str = "") -> None:
        """打开词典原版条目（Chromium 渲染）。"""
        html = self.service.entry_html(word, lang or "en")
        if not html:
            self.toast("这本词典没有原版条目")
            return
        if self._entry_viewer is None or not self._entry_viewer.win or not self._entry_viewer.win.winfo_exists():
            self._entry_viewer = EntryViewer(
                self.root, on_close=lambda: setattr(self, "_entry_viewer", None)
            )
        self._entry_viewer.show(html, word)

    def _show_details(self, payload: dict, anchor) -> None:
        self.popup.show_result(payload, anchor)

    def _open_chat_from_selection(self, anchor) -> None:
        """悬浮按钮点「聊」：不翻译，直接围绕选中的段落开聊。"""
        if not self._pending_selection:
            return
        text, book, _pos = self._pending_selection
        self.popup.show_chat_pending(text, book, anchor)

    def _bubble_chat(self, payload: dict, anchor) -> None:
        """从气泡直接进入对话：先在浮窗里展示译文，再切到聊天。"""
        self.popup.show_result(payload, anchor)
        self.popup._open_chat()

    # ------------------------------------------------------------------ 对话
    def start_chat(self, payload: dict) -> dict:
        return self.service.start_conversation(
            payload.get("book") or "",
            payload.get("source_lang") or "",
            payload.get("text") or "",
            payload.get("translation") or "",
        )

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
    def save_word(self, data: dict) -> dict:
        result = self.service.add_vocab(**data)
        return result

    def push_anki(self, lang: str) -> None:
        def worker() -> None:
            try:
                result = self.service.push_anki(lang)
                msg = f"Anki：新增 {result.get('added', 0)} 张，重复 {result.get('duplicated', 0)} 张"
                if result.get("skipped"):
                    msg += f"，已存在跳过 {result['skipped']} 个"
                if result.get("failed"):
                    msg += f"，失败 {len(result['failed'])} 张"
            except Exception as exc:  # noqa: BLE001
                msg = f"Anki 同步失败：{exc}"
            self.events.put(("toast", msg))

        threading.Thread(target=worker, daemon=True).start()

    def speak(self, text: str, lang: str, audio_key: str = "") -> None:
        source = str(self.config.get("audio_source", "dict_first"))

        def worker() -> None:
            log.info("发音请求 text=%r lang=%r audio_key=%r source=%r", text, lang, audio_key, source)
            try:
                if source == "tts":
                    self.service.speak(text, lang)
                    return
                if audio_key and self.service.play_dictionary_audio(lang, audio_key):
                    return
                if source == "dict_only":
                    self.events.put(("toast", "这个词没有本地音频"))
                    return
                self.service.speak(text, lang)
            except Exception as exc:  # noqa: BLE001
                log.exception("发音失败 text=%r lang=%r audio_key=%r", text, lang, audio_key)
                msg = str(exc)
                if "音色" in msg:
                    self.events.put(("toast", msg[:120]))
                    return
                if "语音" in msg or "Speak" in msg or "0x8004503A" in msg:
                    self.events.put(
                        (
                            "toast",
                            "系统没有可用的语音：设置 → 时间和语言 → 语音 → 添加语音",
                        )
                    )
                else:
                    self.events.put(("toast", f"发音失败：{msg[:40]}"))

        threading.Thread(target=worker, daemon=True).start()

    def lock_term(self, book: str, source: str, lang: str) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("加入术语表")
        dialog.configure(bg="#1b1d24")
        dialog.geometry("380x170")
        dialog.attributes("-topmost", True)

        tk.Label(dialog, text=f"为《{book or '当前书'}》固定译法", bg="#1b1d24", fg="#e6e9ef",
                 font=("Microsoft YaHei UI", 10)).pack(padx=16, pady=(14, 4), anchor="w")
        row = tk.Frame(dialog, bg="#23262f")
        row.pack(fill="x", padx=16)
        src = tk.Entry(row, bg="#23262f", fg="#e6e9ef", insertbackground="#e6e9ef",
                       relief="flat", font=("Microsoft YaHei UI", 10))
        src.insert(0, source)
        src.pack(side="left", fill="x", expand=True, padx=6, pady=6)
        tk.Label(row, text="→", bg="#23262f", fg="#9aa5b1").pack(side="left")
        dst = tk.Entry(row, bg="#23262f", fg="#e6e9ef", insertbackground="#e6e9ef",
                       relief="flat", font=("Microsoft YaHei UI", 10))
        dst.pack(side="left", fill="x", expand=True, padx=6, pady=6)

        def submit() -> None:
            term_src = src.get().strip()
            term_dst = dst.get().strip()
            if not term_src or not term_dst:
                return
            self.service.add_term(book, term_src, term_dst, lang)
            dialog.destroy()
            self.toast(f"已加入术语表：{term_src} → {term_dst}")

        btn = tk.Label(dialog, text="保存", bg="#7aa2f7", fg="#10131a", padx=16, pady=5,
                       cursor="hand2", font=("Microsoft YaHei UI", 9))
        btn.pack(pady=12)
        btn.bind("<Button-1>", lambda _e: submit())
        dialog.bind("<Return>", lambda _e: submit())
        dst.focus_set()

    # ------------------------------------------------------------------ 设置
    def open_settings(self) -> None:
        if self._settings is None or not self._settings.win.winfo_exists():
            self._settings = SettingsWindow(
                self.root,
                self.service,
                self.on_settings_saved,
                self.shutdown,
                on_restart=self.restart,
            )
        self._settings.show()

    def on_settings_saved(self) -> None:
        self.popup.width = int(self.config.get("popup_width", 560))
        self.restart_hotkeys()
        self._start_selection_watch()

    # ------------------------------------------------------------------ 提示条
    def toast(self, message: str) -> None:
        if self._toast_win is not None and self._toast_win.winfo_exists():
            self._toast_win.destroy()
        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg="#23262f")
        tk.Label(
            win,
            text=message,
            bg="#23262f",
            fg="#e6e9ef",
            font=("Microsoft YaHei UI", 9),
            padx=14,
            pady=8,
        ).pack()
        win.update_idletasks()
        w, h = win.winfo_reqwidth(), win.winfo_reqheight()
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        win.geometry(f"+{sw - w - 24}+{sh - h - 60}")
        self._toast_win = win
        if self._toast_job:
            self.root.after_cancel(self._toast_job)
        self._toast_job = self.root.after(1800, win.destroy)

    # ------------------------------------------------------------------ 生命周期
    def run(self) -> None:
        if self._api_error:
            messagebox.showwarning(
                "Interpres",
                "本地接口启动失败：\n"
                f"{self._api_error}\n\n"
                "通常是已经有一个实例在运行，或者端口被别的程序占用。\n"
                "可以按 Ctrl+Alt+S 打开已有实例的设置，或运行 stop.ps1 退出全部实例。",
            )
            self.shutdown()
            return
        if not self.config.api_key:
            self.root.after(300, self.open_settings)
            self.root.after(500, lambda: self.toast("先填 API Key，然后点「测试连接」"))
        elif not self.silent and self._enable_hotkeys:
            # 用户主动点图标启动时，直接打开主面板
            self.root.after(500, self.open_panel)
        elif self._enable_hotkeys:
            self.root.after(
                700,
                lambda: self.toast("Interpres 已在后台运行 · 划词后点「译」，或按 Ctrl+Alt+T"),
            )
        self._prebuild_fuzzy()
        self._tts_self_test()
        self.root.mainloop()

    def _tts_self_test(self) -> None:
        import threading

        def worker() -> None:
            try:
                self.service.tts.self_test()
            except Exception:
                log.exception("tts 自检失败")

        threading.Thread(target=worker, daemon=True, name="tts-selftest").start()

    def _prebuild_fuzzy(self) -> None:
        import threading

        from rc import fuzzy

        def worker() -> None:
            for code in ("en", "fr", "la", "de", "es"):
                try:
                    dictionary = self.service.dicts.dictionary(code)
                    if dictionary is not None:
                        fuzzy.build_index(dictionary)
                except Exception:
                    continue

        threading.Thread(target=worker, daemon=True, name="fuzzy-index").start()

    def shutdown(self) -> None:
        if self.quitting:
            return
        self.quitting = True
        try:
            self.service.tts.stop()
        except Exception:
            pass
        if self.watcher:
            self.watcher.stop()
        if self._sel_watcher:
            self._sel_watcher.stop()
        if getattr(self, "tray", None):
            self.tray.stop()
        try:
            self.api.stop()
        except Exception:
            pass
        try:
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass


_MUTEX_HANDLE = None


def _single_instance(config) -> bool:
    """单实例：已经有一个在跑就把它叫到前面（隐藏时让它打开面板），自己退出。"""
    global _MUTEX_HANDLE
    import ctypes

    try:
        _MUTEX_HANDLE = ctypes.windll.kernel32.CreateMutexW(
            None, False, "Global\\Interpres_SingleInstance"
        )
        if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            if _focus_existing_window():
                return False
            if _show_panel_of_running(config):
                return False
            if _show_settings_of_running(config):
                return False
            _warn_already_running()
            return False
    except Exception:
        pass
    return True


def _focus_existing_window() -> None:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def enum(hwnd, _lparam):
        n = user32.GetWindowTextLengthW(hwnd)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            title = buf.value
            if title.startswith("Interpres") and user32.IsWindowVisible(hwnd):
                found.append(hwnd)
        return True

    user32.EnumWindows(enum, 0)
    if not found:
        return False
    hwnd = found[0]
    try:
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False


def setup_logging(data_dir: Path, debug: bool) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [logging.FileHandler(data_dir / "app.log", encoding="utf-8")]
    if debug:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Interpres")
    parser.add_argument("--data-dir", help="数据目录（默认 ~/.reading-companion）")
    parser.add_argument("--debug", action="store_true", help="输出日志到控制台")
    parser.add_argument("--translate", help="命令行翻译一段文字后退出（调试用）")
    parser.add_argument("--no-hotkeys", action="store_true", help="不启动热键和本地接口")
    parser.add_argument("--silent", action="store_true", help="启动时不打开设置窗（开机自启用）")
    parser.add_argument("--selftest", action="store_true", help="启动托盘/热键自检后自动退出（调试用）")
    parser.add_argument("--version", action="store_true", help="显示版本")
    args = parser.parse_args(argv)

    if args.version:
        print(f"Interpres {__version__}")
        return 0

    config = Config(args.data_dir)
    from rc import i18n

    i18n.set_language(str(config.get("ui_lang", "zh")))
    i18n.install()
    setup_logging(config.data_dir, args.debug)
    logging.getLogger("app").info("启动 Interpres %s", __version__)
    if args.selftest:
        app = Application(config, enable_hotkeys=True, silent=True)

        def _finish() -> None:
            tray = getattr(app, "tray", None)
            logging.getLogger("app").info(
                "SELFTEST tray=%s active=%s error=%s",
                bool(tray), bool(tray and tray.active), (tray.error if tray else ""),
            )
            try:
                import aiohttp
                import edge_tts

                logging.getLogger("app").info(
                    "SELFTEST edge_tts=%s aiohttp=%s",
                    getattr(edge_tts, "__version__", "?"),
                    aiohttp.__version__,
                )
            except Exception as exc:  # noqa: BLE001
                logging.getLogger("app").warning("SELFTEST edge import failed: %r", exc)
            app.shutdown()

        app.root.after(2500, _finish)
        app.run()
        return 0
    if not args.translate and not args.version and not _single_instance(config):
        logging.getLogger("app").info("已有实例在运行，本次启动退出")
        return 0

    if args.translate:
        service = Service(config)
        try:
            result = service.translate(args.translate)
            import json

            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        except Exception as exc:  # noqa: BLE001
            print(f"翻译失败：{exc}", file=sys.stderr)
            return 1

    if args.no_hotkeys:
        app = Application(config, enable_hotkeys=False)
        app.run()
        return 0

    # 单实例：Windows 上端口占用检查不可靠，用内核互斥体
    # 名字带上数据目录，这样不同 --data-dir 的实例互不干扰
    mutex_name = "Local\\ReadingCompanion-" + hashlib.md5(
        str(config.data_dir).encode("utf-8")
    ).hexdigest()[:12]
    with SingleInstance(mutex_name) as lock:
        if not lock.acquired:
            # 已经有一个在跑：让它把设置窗打开，然后自己退出
            if not _show_settings_of_running(config):
                _warn_already_running()
            return 0
        app = Application(config, enable_hotkeys=True, silent=args.silent)
        app.run()
    return 0


def _show_settings_of_running(config: Config) -> bool:
    """请求已经运行的实例打开设置窗口。"""
    import urllib.error
    import urllib.request

    port = int(config.get("server_port", 18777))
    url = f"http://127.0.0.1:{port}/api/show-settings"
    req = urllib.request.Request(
        url,
        data=b"{}",
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-RC-Token": str(config.get("server_token", "")),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            return resp.status == 200
    except Exception:
        return False


def _show_panel_of_running(config: Config) -> bool:
    """隐藏到托盘时，请求运行中的实例打开主面板。"""
    import urllib.request

    port = int(config.get("server_port", 18777))
    url = f"http://127.0.0.1:{port}/api/show-panel"
    req = urllib.request.Request(
        url,
        data=b"{}",
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-RC-Token": str(config.get("server_token", "")),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            return resp.status == 200
    except Exception:
        return False


def _warn_already_running() -> None:
    """第二个实例只用系统对话框提示，不启动 Tk（避免多出窗口和托盘项）。"""
    text = (
        "Interpres 已经在后台运行了，不用重复启动。\n\n"
        "Ctrl+Alt+T  翻译选中的文字\n"
        "Ctrl+Alt+S  打开设置（退出程序也在这里）"
    )
    try:
        ctypes.windll.user32.MessageBoxW(None, text, "Interpres", 0x40)
    except Exception:
        pass


if __name__ == "__main__":
    raise SystemExit(main())
