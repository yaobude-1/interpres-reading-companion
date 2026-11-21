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
from rc import capture
from rc.bubble import Bubble, QuickButton
from rc.config import Config
from rc.hotkey import HotkeyWatcher
from rc.instance import SingleInstance
from rc.panel import MainPanel
from rc.popup import PopupWindow
from rc.selection import MouseWatcher, foreground_exe
from rc.server import ApiServer
from rc.service import Service
from rc.settings_ui import SettingsWindow

from app_flow import FlowMixin
from app_media import MediaMixin
from app_panel import PanelMixin

log = logging.getLogger("rc")


def restore_panel_geometry(config, panel) -> None:
    """把上次保存的主面板尺寸/位置套回去。

    必须在 MainPanel 创建之后调用：之前调用会命中 AttributeError 并被吞掉，
    保存的几何信息就永远不会生效。
    """
    try:
        geometry = str(config.get("panel_geometry") or "")
        if geometry:
            panel.win.geometry(geometry)
    except Exception:
        log.debug("恢复面板几何失败", exc_info=True)


class Application(PanelMixin, FlowMixin, MediaMixin):
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
                "word_card": self.show_word_card,
                "close": self._close_panel,
            },
        )
        restore_panel_geometry(self.config, self.panel)

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
            self._pump_events()
        except Exception:
            log.exception("事件循环异常")
        self._follow_active_book()
        if not self.quitting:
            self.root.after(25, self._pump)

    def _pump_events(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "hotkey":
                    self._on_hotkey(payload)
                elif kind == "loading":
                    text, book, anchor = payload
                    self.popup.show_loading(text, book, "", anchor)
                elif kind == "begin":
                    text, book, anchor = payload
                    self._begin(text, book, anchor)
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
