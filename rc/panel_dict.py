"""Main panel: the dictionary tab (lookup, senses, morphology, save)."""

from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from tkinter import messagebox

from .dict_view_controller import raw_word_candidates, view_url
from .i18n import tr
from .lookup_history_ui import LookupHistoryWindow, lookup_time
from .popup_common import source_label
from .theme import (
    ACCENT,
    BG,
    DIM,
    FONT_FAMILY,
    GREEN,
    MUTED,
    PANEL,
    PANEL_ALT,
    TEXT,
)

GOLD = "#e0af68"
log = logging.getLogger("rc")


def _dict_raw_candidates(entry: dict, query: str) -> list[str]:
    """原版页面应查的词：优先用词典实际命中的词头，而不是输入变形。"""
    return raw_word_candidates(entry, query)


class PanelDictMixin:
    def _on_dict_typing(self, _event=None) -> None:
        if self._dict_job is not None:
            try:
                self.win.after_cancel(self._dict_job)
            except tk.TclError:  # 控件可能已销毁，刻意忽略
                pass
        self._dict_job = self.win.after(220, self._dict_typed)

    def _lookup_dict(
        self,
        _keep_suggestions: bool = False,
        sync: bool = False,
        record: bool = False,
        prefer_dict_id: str = "",
    ) -> None:
        # 取消还在等待的“输入停顿”任务，避免查词后下拉又冒出来
        if self._dict_job is not None:
            try:
                self.win.after_cancel(self._dict_job)
            except tk.TclError:  # 控件可能已销毁，刻意忽略
                pass
        self._dict_job = None
        if not _keep_suggestions:
            self._hide_suggestions()
        word = self.dict_input.get().strip()
        self._dict_lookup_gen = getattr(self, "_dict_lookup_gen", 0) + 1
        generation = self._dict_lookup_gen
        self._dict_partial_gen = None
        if self._dict_web_host is not None:
            self._dict_web_host.hide()
        if self._dict_web_frame is not None:
            try:
                self._dict_web_frame.pack_forget()
            except tk.TclError:
                pass
        if not word:
            self._clear_dict_result()
            self._dict_hint("输入一个单词，本地词典查询，不消耗 token")
            self._sync_content_scroll()
            return
        # 同分时书语言只作排序偏好；所有词典都已经查过，不做过滤。
        hint = ""
        getter = self.cb.get("book_lang")
        if callable(getter):
            try:
                hint = getter(self.book) or ""
            except Exception:  # noqa: BLE001 - 查书语言失败按未知处理
                hint = ""
        if sync:
            try:
                hits = self.service.lookup_all(word, lang_hint=hint or None)
            except Exception as exc:  # noqa: BLE001 - 查词失败也要回到界面
                log.exception("查词失败")
                self._apply_dict_lookup(
                    generation, word, [], f"查词失败：{exc}", record, prefer_dict_id
                )
                return
            self._apply_dict_lookup(generation, word, hits, "", record, prefer_dict_id)
            return

        lookup_queue = getattr(self, "_dict_lookup_queue", None)
        if lookup_queue is None:
            lookup_queue = queue.Queue()
            self._dict_lookup_queue = lookup_queue
        self._dict_lookup_pending = getattr(self, "_dict_lookup_pending", 0) + 1
        if getattr(self, "_dict_lookup_poll_job", None) is None:
            self._dict_lookup_poll_job = self.win.after(20, self._poll_dict_lookup)

        def emit(hit: dict) -> None:
            # 每本词典一查完就先送到界面：默认词典先出，慢词典后补。
            lookup_queue.put(("hit", generation, word, hit))

        def worker() -> None:
            try:
                hits = self.service.lookup_all(
                    word, lang_hint=hint or None, on_hit=emit
                )
                error = ""
            except Exception as exc:  # noqa: BLE001 - 后台失败交给界面
                log.exception("查词失败")
                hits = []
                error = f"查词失败：{exc}"
            lookup_queue.put(
                ("done", generation, word, hits, error, record, prefer_dict_id)
            )

        threading.Thread(target=worker, daemon=True, name="dict-lookup").start()

    def _poll_dict_lookup(self) -> None:
        self._dict_lookup_poll_job = None
        lookup_queue = getattr(self, "_dict_lookup_queue", None)
        if lookup_queue is None:
            return
        while True:
            try:
                message = lookup_queue.get_nowait()
            except queue.Empty:
                break
            if message[0] == "hit":
                _, generation, word, hit = message
                self._apply_dict_partial(generation, word, hit)
                continue
            _, generation, word, hits, error, record, prefer_dict_id = message
            self._dict_lookup_pending = max(
                0, getattr(self, "_dict_lookup_pending", 1) - 1
            )
            self._dict_partial_gen = None
            self._apply_dict_lookup(generation, word, hits, error, record, prefer_dict_id)
        if getattr(self, "_dict_lookup_pending", 0) > 0:
            try:
                self._dict_lookup_poll_job = self.win.after(30, self._poll_dict_lookup)
            except tk.TclError:
                self._dict_lookup_poll_job = None

    def _apply_dict_partial(self, generation: int, word: str, hit: dict) -> None:
        """增量结果：只渲染本轮第一本命中的词典，后续词典到了由最终结果补来源。"""
        if generation != getattr(self, "_dict_lookup_gen", 0):
            return
        if self.dict_input.get().strip() != word:
            return
        if getattr(self, "_dict_partial_gen", None) == generation:
            return
        entry = hit.get("entry")
        if not entry:
            return
        try:
            if not self.win.winfo_exists():
                return
        except tk.TclError:
            return
        self._dict_partial_gen = generation
        self._apply_dict_lookup(generation, word, [hit], "", False, "")

    def _clear_dict_result(self) -> None:
        for child in self.dict_result.winfo_children():
            if child is getattr(self, "_dict_web_frame", None):
                continue
            child.destroy()

    def _apply_dict_lookup(
        self,
        generation: int,
        word: str,
        hits: list[dict],
        error: str = "",
        record: bool = False,
        prefer_dict_id: str = "",
    ) -> None:
        if generation != getattr(self, "_dict_lookup_gen", 0):
            return
        if self.dict_input.get().strip() != word:
            return
        try:
            if not self.win.winfo_exists():
                return
        except tk.TclError:
            return
        self._clear_dict_result()
        if error:
            self._dict_hint(error)
            self._sync_content_scroll()
            return
        preferred = (
            next(
                (
                    hit["entry"]
                    for hit in hits
                    if prefer_dict_id
                    and str(hit.get("dict_id") or "") == prefer_dict_id
                    and hit.get("entry")
                ),
                None,
            )
            if prefer_dict_id
            else None
        )
        entry = preferred
        if entry is None:
            entry = (
                next(
                    (h["entry"] for h in hits if (h.get("entry") or {}).get("is_default")),
                    None,
                )
                if hits
                else None
            )
        if entry is None:
            entry = hits[0]["entry"] if hits else None
        if not entry:
            if self.service.has_dictionaries():
                self._dict_hint(f"本地词典里没有「{word}」。")
            else:
                self._dict_hint(
                    "还没配置本地词典。设置 →「词典设置…」添加 MDX，"
                    "或者直接用下面的「用 AI 译」。"
                )
            ai = tk.Label(
                self.dict_result,
                text="用 AI 译",
                bg=PANEL,
                fg=TEXT,
                font=(FONT_FAMILY, 9),
                padx=10,
                pady=5,
                cursor="hand2",
            )
            ai.pack(anchor="w", pady=(4, 8))
            ai.bind("<Button-1>", lambda _e: self.cb.get("translate", lambda *_a: None)(word, self.book))
            self._sync_content_scroll()
            return
        self._render_dict(entry, word, hits)
        if record:
            try:
                self.service.record_lookup(entry, word, self.book)
            except Exception as exc:  # noqa: BLE001 - 历史失败不影响查词
                log.debug("记录查词历史失败: %s", exc)
        self._bind_content_wheel(self.content)
        self._sync_content_scroll()

    def _show_lookup_history_menu(self) -> None:
        self._hide_suggestions()
        try:
            entries = self.service.lookup_history(12)
        except Exception as exc:  # noqa: BLE001 - 历史读取失败不影响查词
            log.debug("读取查词历史失败: %s", exc)
            entries = []
        menu = tk.Menu(
            self.win,
            tearoff=0,
            bg=PANEL,
            fg=TEXT,
            activebackground=ACCENT,
            activeforeground=BG,
            font=(FONT_FAMILY, 9),
        )
        if entries:
            for entry in entries:
                word = str(entry.get("word") or entry.get("lemma") or "")
                source = source_label(entry.get("source") or "")
                when = lookup_time(entry.get("last_used") or "")
                label = f"{word}    {source}    {when}".strip()
                menu.add_command(
                    label=label[:70],
                    command=lambda w=word, e=entry: self._open_lookup_history_word(w, e),
                )
            menu.add_separator()
        else:
            menu.add_command(label=tr("还没有查词记录"), state="disabled")
            menu.add_separator()
        menu.add_command(label=tr("查看全部…"), command=self._open_lookup_history)
        menu.add_command(label=tr("清空…"), command=self._clear_lookup_history)
        self._lookup_history_menu = menu
        try:
            x = self.dict_input.winfo_rootx()
            y = self.dict_input.winfo_rooty() + self.dict_input.winfo_height() + 4
            menu.tk_popup(x, y)
        finally:
            try:
                menu.grab_release()
            except tk.TclError:
                pass

    def _open_lookup_history_word(self, word: str, _entry: dict | None = None) -> None:
        word = (word or "").strip()
        if not word:
            return
        self._show_tab("dict")
        self.dict_input.delete(0, "end")
        self.dict_input.insert(0, word)
        self._lookup_dict(
            record=True,
            prefer_dict_id=str((_entry or {}).get("dict_id") or ""),
        )

    def _open_lookup_history(self) -> None:
        window = getattr(self, "_lookup_history_win", None)
        if window is not None and window.alive():
            window.win.lift()
            window.win.focus_force()
            window.refresh()
            return
        self._lookup_history_win = LookupHistoryWindow(
            self.win,
            self.service,
            on_open=self._open_lookup_history_word,
        )
        self._lookup_history_win.win.lift()

    def _clear_lookup_history(self) -> None:
        if not messagebox.askyesno(
            tr("清空查词历史"),
            tr("确定清空全部查词历史吗？"),
        ):
            return
        self.service.clear_lookup_history()
        window = getattr(self, "_lookup_history_win", None)
        if window is not None and window.alive():
            window.refresh()

    def _dict_lookup_word(self, word: str) -> None:
        """点变位表/原形时，直接在面板里查这个词。"""
        word = (word or "").strip()
        if not word:
            return
        self.dict_input.delete(0, "end")
        self.dict_input.insert(0, word)
        self._lookup_dict(record=True)

    def _dict_typed(self) -> None:
        """输入停顿后只刷新下拉建议；卡片等回车/点选再渲染，避免抖。"""
        self._update_suggestions()

    def _render_dict(self, entry: dict, word: str, alternatives=None) -> None:
        for child in self.dict_result.winfo_children():
            if child is getattr(self, "_dict_web_frame", None):
                continue
            child.destroy()
        self._dict_view_entry = entry
        self._dict_view_query = word
        if self._dict_web_frame is not None:
            try:
                self._dict_web_frame.pack_forget()
            except tk.TclError:
                pass
        if any("~" in str(v) for sense in (entry.get("senses") or []) for v in sense.values() if isinstance(v, str)):
            cleaned = dict(entry)
            new_senses = []
            for sense in entry.get("senses") or []:
                item = dict(sense)
                for key, value in list(item.items()):
                    if isinstance(value, str):
                        item[key] = value.replace("~", word)
                new_senses.append(item)
            cleaned["senses"] = new_senses
            entry = cleaned
        head = tk.Frame(self.dict_result, bg=BG)
        head.pack(fill="x")
        tk.Label(
            head, text=word, bg=BG, fg=TEXT, font=(FONT_FAMILY, 15, "bold")
        ).pack(side="left")
        phonetic = (entry.get("phonetic") or "").strip()
        if phonetic:
            tk.Label(
                head, text=f"/{phonetic}/", bg=BG, fg=MUTED, font=(FONT_FAMILY, 9)
            ).pack(side="left", padx=(8, 0))
        if entry.get("audio_key") or entry.get("lang"):
            speak = tk.Label(
                head, text="🔊", bg=BG, fg=ACCENT, font=(FONT_FAMILY, 11), cursor="hand2"
            )
            speak.pack(side="left", padx=(8, 0))
            speak.bind(
                "<Button-1>",
                lambda _e, w=word, e=entry: self.cb.get("speak", lambda *_a: None)(
                    w,
                    e.get("lang") or "",
                    e.get("audio_key") or "",
                    e.get("dict_id") or "",
                ),
            )
            speak.bind("<Enter>", lambda _e: speak.configure(fg=TEXT))
            speak.bind("<Leave>", lambda _e: speak.configure(fg=ACCENT))
        saved = self.service.find_vocab(entry.get("lang") or "", word)
        if not saved:
            saved = self.service.find_vocab(entry.get("lang") or "", entry.get("matched") or "")
        star = tk.Label(
            head, text="★" if saved else "☆", bg=BG,
            fg="#f5c542" if saved else ACCENT,
            font=(FONT_FAMILY, 13), cursor="hand2"
        )
        star.pack(side="left", padx=(10, 0))
        star.bind(
            "<Button-1>", lambda _e, e=entry, w=word, st=star: self._save_dict(e, w, st)
        )
        star.bind("<Enter>", lambda _e: star.configure(fg=TEXT))
        star.bind("<Leave>", lambda _e: star.configure(fg=star.cget("fg")))
        if entry.get("source"):
            tk.Label(
                head, text=source_label(entry["source"]), bg=BG, fg=GREEN, font=(FONT_FAMILY, 8)
            ).pack(side="left", padx=(8, 0))
        alternatives = alternatives or []
        self._render_dict_sources(entry, word, alternatives)
        user_form = (entry.get("user_form") or "").strip()
        if user_form:
            user_row = tk.Frame(self.dict_result, bg=BG)
            user_row.pack(fill="x", pady=(2, 4))
            tk.Label(
                user_row,
                text=f"用户词形：{user_form} → {entry.get('matched') or entry.get('word') or ''}",
                bg=BG, fg=GOLD, font=(FONT_FAMILY, 8), anchor="w",
            ).pack(fill="x")
        self._render_dict_view_toggle()
        simple = tk.Frame(self.dict_result, bg=BG)
        self._dict_simple = simple
        redirect = (entry.get("redirect") or "").strip()
        if redirect:
            self._render_redirect_notice(redirect, entry, word, parent=simple)

        morph = entry.get("morph") or {}
        if morph:
            lemma_text = morph.get("lemma") or ""
            lemma_label = tk.Label(
                simple,
                text=f"原形 {lemma_text}（{morph.get('label', '')}）",
                bg=BG,
                fg=ACCENT,
                font=(FONT_FAMILY, 9),
                anchor="w",
                cursor="hand2" if lemma_text else "arrow",
            )
            lemma_label.pack(fill="x", pady=(2, 4))
            if lemma_text:
                lemma_label.bind("<Button-1>", lambda _e, w=lemma_text: self._dict_lookup_word(w))
            tabs = tk.Frame(simple, bg=BG)
            tabs.pack(fill="x", pady=(0, 4))
            has_cases = any((t or {}).get("cases") for t in (morph.get("tables") or []))
            self._panel_tab_meaning = tk.Label(
                tabs, text="释义", bg=PANEL, fg=TEXT, font=(FONT_FAMILY, 9, "bold"),
                padx=12, pady=4, cursor="hand2",
            )
            self._panel_tab_meaning.pack(side="left")
            self._panel_tab_conj = tk.Label(
                tabs, text="变格" if has_cases else "时态", bg=BG, fg=DIM,
                font=(FONT_FAMILY, 9, "bold"), padx=12, pady=4, cursor="hand2",
            )
            self._panel_tab_conj.pack(side="left", padx=(6, 0))
            self._panel_tab_meaning.bind("<Button-1>", lambda _e: self._panel_show_tab("meaning"))
            self._panel_tab_conj.bind("<Button-1>", lambda _e: self._panel_show_tab("conj"))

        container = tk.Frame(simple, bg=BG)
        container.pack(fill="x")
        self._panel_meaning = tk.Frame(container, bg=BG)
        self._panel_meaning.pack(fill="x")
        self._panel_conj = tk.Frame(container, bg=BG)
        self._panel_render_senses(self._panel_meaning, entry, word)
        if morph:
            self._panel_render_tables(self._panel_conj, morph)
        self._apply_dict_view_mode()


    # ------------------------------------------------------------ 原版 / 精简
    def _render_dict_view_toggle(self) -> None:
        bar = tk.Frame(self.dict_result, bg=BG)
        bar.pack(fill="x", pady=(4, 2))
        tk.Label(
            bar, text="视图", bg=BG, fg=DIM, font=(FONT_FAMILY, 8)
        ).pack(side="left", padx=(0, 8))
        self._dict_view_buttons: dict[str, tk.Label] = {}
        for key, label in (("simple", "精简"), ("original", "原版")):
            button = tk.Label(
                bar,
                text=label,
                bg=BG,
                fg=DIM,
                font=(FONT_FAMILY, 8),
                padx=8,
                pady=2,
                cursor="hand2",
            )
            button.pack(side="left", padx=(0, 6))
            button.bind("<Button-1>", lambda _e, k=key: self._set_dict_view_mode(k))
            self._dict_view_buttons[key] = button
        self._dict_view_notice = tk.Label(
            bar, text="", bg=BG, fg=GOLD, font=(FONT_FAMILY, 8), anchor="e"
        )
        self._dict_view_notice.pack(side="right")
        self._update_dict_view_buttons()

    def _update_dict_view_buttons(self) -> None:
        for key, button in getattr(self, "_dict_view_buttons", {}).items():
            active = key == self._dict_view_mode
            try:
                button.configure(
                    bg=PANEL if active else BG,
                    fg=TEXT if active else DIM,
                )
            except tk.TclError:
                continue

    def _set_dict_view_mode(self, mode: str) -> None:
        if mode not in ("simple", "original"):
            return
        self._dict_view_mode = mode
        self._update_dict_view_buttons()
        self._apply_dict_view_mode()

    def _apply_dict_view_mode(self) -> None:
        if getattr(self, "_dict_simple", None) is None:
            return
        if self._dict_view_mode == "original":
            self._show_dict_original()
        else:
            self._show_dict_simple()

    def _show_dict_simple(self) -> None:
        if getattr(self, "_dict_web_host", None) is not None:
            self._dict_web_host.hide()
        frame = getattr(self, "_dict_web_frame", None)
        if frame is not None:
            try:
                frame.pack_forget()
            except tk.TclError:
                pass
        simple = getattr(self, "_dict_simple", None)
        if simple is not None:
            try:
                simple.pack(fill="x")
            except tk.TclError:
                pass
        self._update_dict_view_buttons()

    def _ensure_dict_web_frame(self):
        frame = getattr(self, "_dict_web_frame", None)
        if frame is not None:
            try:
                if frame.winfo_exists():
                    return frame
            except tk.TclError:
                pass
        try:
            from .webview_host import WebViewHost

            try:
                height = max(320, min(760, self.win.winfo_height() - 250))
            except tk.TclError:
                height = 520
            frame = tk.Frame(self.dict_result, bg=BG, height=height)
            frame.pack_propagate(False)
            self._dict_web_frame = frame
            self._dict_web_host = WebViewHost(frame, on_lookup=self._dict_lookup_word)
            return frame
        except Exception as exc:  # noqa: BLE001 - WebView 不可用时回退精简
            log.debug("创建 WebView 容器失败: %s", exc)
            return None

    def _dict_server_info(self) -> tuple[int, str, bool]:
        getter = self.cb.get("dict_server")
        if not callable(getter):
            return 0, "", False
        try:
            port, token, running = getter()
            return int(port or 0), str(token or ""), bool(running)
        except Exception as exc:  # noqa: BLE001
            log.debug("读取词典服务信息失败: %s", exc)
            return 0, "", False

    def _show_dict_original(self) -> None:
        entry = getattr(self, "_dict_view_entry", None) or {}
        word = (getattr(self, "_dict_view_query", "") or "").strip()
        lang = str(entry.get("lang") or "").strip()
        if not word or not lang:
            self._dict_view_fallback("原版不可用：缺少词条语言")
            return
        candidates: list[str] = _dict_raw_candidates(entry, word)
        raw_word = ""
        dict_id = str(entry.get("dict_id") or "").strip()
        for candidate in candidates:
            try:
                found = (
                    self.service.dicts.raw_entry_by_id(dict_id, candidate)
                    if dict_id
                    else self.service.dicts.raw_entry(lang, candidate)
                )
                if found:
                    raw_word = candidate
                    break
            except Exception as exc:  # noqa: BLE001
                log.debug("检查原版词条失败 %s: %s", candidate, exc)
        if not raw_word:
            self._dict_view_fallback("原版里没有这个词条，已回退精简")
            return
        port, token, running = self._dict_server_info()
        if not running or not port:
            self._dict_view_fallback("原版不可用：本地词典服务未启动")
            return
        frame = self._ensure_dict_web_frame()
        host = getattr(self, "_dict_web_host", None)
        if frame is None or host is None:
            self._dict_view_fallback("原版不可用：WebView2 未安装")
            return
        if not host.ensure():
            self._dict_view_fallback(f"原版不可用：{host.error or 'WebView2 初始化失败'}")
            return
        url = view_url(
            port,
            token,
            raw_word,
            lang=lang,
            dict_id=dict_id,
        )
        if not host.load_url(url):
            self._dict_view_fallback(f"原版不可用：{host.error or '加载失败'}")
            return
        simple = getattr(self, "_dict_simple", None)
        if simple is not None:
            try:
                simple.pack_forget()
            except tk.TclError:
                pass
        frame.pack(fill="both", expand=True, pady=(4, 0))
        host.show()
        try:
            self.win.update_idletasks()
        except tk.TclError:
            pass
        self._resize_dict_web()
        if getattr(self, "_dict_view_notice", None) is not None:
            self._dict_view_notice.configure(
                text="" if raw_word == word else f"{word} → {raw_word}"
            )
        self._update_dict_view_buttons()

    def _resize_dict_web(self) -> None:
        frame = getattr(self, "_dict_web_frame", None)
        host = getattr(self, "_dict_web_host", None)
        if frame is None or host is None:
            return
        try:
            if not frame.winfo_ismapped():
                return
            height = max(320, min(760, self.win.winfo_height() - 250))
            frame.configure(height=height)
            host.resize()
        except tk.TclError:
            pass

    def _dict_view_fallback(self, message: str) -> None:
        self._dict_view_mode = "simple"
        self._update_dict_view_buttons()
        self._show_dict_simple()
        notice = getattr(self, "_dict_view_notice", None)
        if notice is not None:
            notice.configure(text=message)

    def _dispose_dict_webview(self) -> None:
        host = getattr(self, "_dict_web_host", None)
        if host is not None:
            host.dispose()
            self._dict_web_host = None
        frame = getattr(self, "_dict_web_frame", None)
        if frame is not None:
            try:
                frame.destroy()
            except tk.TclError:
                pass
            self._dict_web_frame = None

    def _render_dict_sources(self, entry: dict, word: str, alternatives: list[dict]) -> None:
        if len(alternatives) <= 1:
            return
        labels = {
            "user": "用户词形",
            "exact": "精确",
            "accent": "重音匹配",
            "lemma": "词形",
            "redirect": "重定向",
        }
        bar = tk.Frame(self.dict_result, bg=BG)
        bar.pack(fill="x", pady=(6, 4))
        current_id = (entry.get("dict_id") or "").strip()
        current = (entry.get("source") or "", entry.get("lang") or "")
        for hit in alternatives:
            hit_entry = hit.get("entry") or {}
            hit_id = str(hit.get("dict_id") or "").strip()
            active = (
                hit_id == current_id
                if current_id
                else (hit.get("source") or "", hit.get("lang") or "") == current
            )
            kind = hit_entry.get("match") or ""
            text = source_label(hit.get("source", ""))
            if labels.get(kind):
                text = f"{text} · {labels[kind]}"
            if active:
                fg = TEXT
            elif kind == "redirect":
                fg = DIM
            else:
                fg = MUTED
            chip = tk.Label(
                bar,
                text=text,
                bg=PANEL if active else BG,
                fg=fg,
                font=(FONT_FAMILY, 8),
                padx=8,
                pady=3,
                cursor="hand2",
            )
            chip.pack(side="left", padx=(0, 6))
            chip.bind(
                "<Button-1>",
                lambda _e, h=hit: self._render_dict(h["entry"], word, alternatives),
            )

    def _render_redirect_notice(self, target: str, entry: dict, word: str, parent=None) -> None:
        """词典把查询词重定向到另一个词条：明确提示，别冒充。"""
        parent = parent or self.dict_result
        box = tk.Frame(parent, bg=PANEL_ALT)
        box.pack(fill="x", pady=(4, 6))
        source = source_label(entry.get("source") or "")
        tk.Label(
            box,
            text=f"{source or '词典'} 把「{word}」重定向到「{target}」，"
            f"下面是 {target} 的词条。",
            bg=PANEL_ALT,
            fg=MUTED,
            font=(FONT_FAMILY, 8),
            justify="left",
            anchor="w",
            wraplength=520,
        ).pack(fill="x", padx=10, pady=(6, 2))
        row = tk.Frame(box, bg=PANEL_ALT)
        row.pack(fill="x", padx=10, pady=(0, 6))
        view = tk.Label(
            row, text=f"查看 {target}", bg=PANEL_ALT, fg=ACCENT,
            font=(FONT_FAMILY, 8), cursor="hand2",
        )
        view.pack(side="left")
        view.bind("<Button-1>", lambda _e: self._dict_lookup_word(target))
        ai = tk.Label(
            row, text="用 AI 译这个词", bg=PANEL_ALT, fg=ACCENT,
            font=(FONT_FAMILY, 8), cursor="hand2",
        )
        ai.pack(side="left", padx=(10, 0))
        ai.bind(
            "<Button-1>",
            lambda _e: self.cb.get("translate", lambda *_a: None)(word, self.book),
        )

    def _panel_show_tab(self, name: str) -> None:
        if not hasattr(self, "_panel_tab_conj") or not hasattr(self, "_panel_conj"):
            return
        if name == "conj":
            self._panel_meaning.pack_forget()
            self._panel_conj.pack(fill="x")
            self._panel_tab_conj.configure(bg=PANEL, fg=TEXT)
            self._panel_tab_meaning.configure(bg=BG, fg=DIM)
        else:
            self._panel_conj.pack_forget()
            self._panel_meaning.pack(fill="x")
            self._panel_tab_meaning.configure(bg=PANEL, fg=TEXT)
            self._panel_tab_conj.configure(bg=BG, fg=DIM)

    def _panel_render_senses(self, parent, entry: dict, word: str) -> None:
        matched = entry.get("matched") or ""
        if (
            matched
            and matched.lower() != word.lower()
            and not entry.get("morph")
            and not entry.get("user_form")
        ):
            accent = entry.get("match") == "accent"
            hint_row = tk.Frame(parent, bg=BG)
            hint_row.pack(fill="x", pady=(0, 4))
            tk.Label(
                hint_row, text="重音匹配到 " if accent else "按原形 ", bg=BG, fg=DIM,
                font=(FONT_FAMILY, 8),
            ).pack(side="left")
            lemma_link = tk.Label(
                hint_row, text=matched, bg=BG, fg=ACCENT,
                font=(FONT_FAMILY, 8, "underline"), cursor="hand2",
            )
            lemma_link.pack(side="left")
            lemma_link.bind("<Button-1>", lambda _e, w=matched: self._dict_lookup_word(w))
            if not accent:
                tk.Label(
                    hint_row, text=" 查到", bg=BG, fg=DIM, font=(FONT_FAMILY, 8),
                ).pack(side="left")
        suggestions = entry.get("lemma_suggestions") or []
        if suggestions:
            hint = tk.Frame(parent, bg=BG)
            hint.pack(fill="x", pady=(2, 4))
            tk.Label(
                hint, text="您是否要查找：", bg=BG, fg=MUTED,
                font=(FONT_FAMILY, 9),
            ).pack(side="left")
            for idx, cand in enumerate(suggestions):
                if idx:
                    tk.Label(
                        hint, text=" / ", bg=BG, fg=MUTED,
                        font=(FONT_FAMILY, 9),
                    ).pack(side="left")
                link = tk.Label(
                    hint, text=cand, bg=BG, fg=ACCENT,
                    font=(FONT_FAMILY, 9, "underline"), cursor="hand2",
                )
                link.pack(side="left")
                link.bind("<Button-1>", lambda _e, w=cand: self._dict_lookup_word(w))
        senses = entry.get("senses") or []
        groups: dict[str, list[dict]] = {}
        order: list[str] = []
        for sense in senses:
            pos = (sense.get("pos") or "").strip()
            if pos not in groups:
                groups[pos] = []
                order.append(pos)
            groups[pos].append(sense)
        for pos in order:
            if pos:
                tk.Label(
                    parent, text=pos, bg=BG, fg=ACCENT,
                    font=(FONT_FAMILY, 9, "bold"), anchor="w",
                ).pack(fill="x", pady=(8, 2))
            for index, sense in enumerate(groups[pos], start=1):
                row = tk.Frame(parent, bg=BG)
                row.pack(fill="x", pady=(2, 0))
                tk.Label(
                    row, text=f"{index}.", bg=BG, fg=ACCENT,
                    font=(FONT_FAMILY, 9), width=2, anchor="w",
                ).pack(side="left", anchor="n", padx=(0, 4))
                tk.Label(
                    row,
                    text=sense.get("definition_cn") or sense.get("definition") or "",
                    bg=BG,
                    fg=TEXT,
                    font=(FONT_FAMILY, 10),
                    justify="left",
                    anchor="w",
                    wraplength=510,
                ).pack(side="left", anchor="w")
                for key, color in (("example", MUTED), ("example_cn", DIM)):
                    value = (sense.get(key) or "").strip()
                    if value:
                        tk.Label(
                            parent, text=value, bg=BG, fg=color, font=(FONT_FAMILY, 9),
                            justify="left", anchor="w", wraplength=520,
                        ).pack(fill="x", padx=(30, 0))

    def _panel_render_tables(self, parent, morph: dict) -> None:
        target = (morph.get("form") or "").lower()
        tables = morph.get("tables") or []
        if morph.get("user"):
            tk.Label(
                parent, text="用户提供", bg=BG, fg=GOLD,
                font=(FONT_FAMILY, 8), anchor="w",
            ).pack(fill="x", pady=(0, 4))

        def has_target(group) -> bool:
            for row in group.get("rows") or []:
                if isinstance(row, dict):
                    if target and target in (
                        (row.get("sing") or "").lower(),
                        (row.get("plur") or "").lower(),
                    ):
                        return True
                elif isinstance(row, (tuple, list)) and len(row) == 2:
                    if (row[1] or "").lower() == target:
                        return True
            return False

        tables = sorted(tables, key=lambda g: 0 if has_target(g) else 1)
        for group in tables:
            card = tk.Frame(parent, bg=PANEL)
            card.pack(fill="x", pady=(0, 8))
            header = tk.Frame(card, bg=PANEL_ALT)
            header.pack(fill="x")
            tk.Label(
                header,
                text=f"{group.get('zh', '')}  {group.get('fr', '')}",
                bg=PANEL_ALT, fg=ACCENT, font=(FONT_FAMILY, 9, "bold"), anchor="w",
            ).pack(fill="x", padx=10, pady=(6, 4))
            body = tk.Frame(card, bg=PANEL)
            body.pack(fill="x", padx=10, pady=(4, 8))
            if group.get("cases"):
                for row in group.get("rows") or []:
                    line = tk.Frame(body, bg=PANEL)
                    line.pack(fill="x")
                    tk.Label(
                        line, text=row.get("case", ""), bg=PANEL, fg=DIM,
                        font=(FONT_FAMILY, 9),
                    ).pack(side="left", pady=1)
                    for key in ("sing", "plur"):
                        value = (row.get(key) or "").strip()
                        if not value:
                            continue
                        mine = value.lower() == target
                        tk.Label(
                            line, text=value, bg=PANEL,
                            fg=ACCENT if mine else TEXT,
                            font=(FONT_FAMILY, 10, "bold" if mine else "normal"),
                        ).pack(side="left", padx=(14, 0), pady=1)
            else:
                for person, form in group.get("rows") or []:
                    line = tk.Frame(body, bg=PANEL)
                    line.pack(fill="x")
                    tk.Label(
                        line, text=person, bg=PANEL, fg=DIM, font=(FONT_FAMILY, 9)
                    ).pack(side="left", pady=1)
                    mine = (form or "").lower() == target
                    form_label = tk.Label(
                        line, text=form, bg=PANEL,
                        fg=ACCENT if mine else TEXT,
                        font=(FONT_FAMILY, 10, "bold" if mine else "normal"),
                    )
                    form_label.pack(side="left", padx=(14, 0), pady=1)
                    if form and " " not in form.strip():
                        form_label.configure(cursor="hand2")
                        form_label.bind(
                            "<Button-1>", lambda _e, w=form: self._dict_lookup_word(w)
                        )

    def _set_dict_status(self, text: str, color: str = GREEN) -> None:
        try:
            label = getattr(self, "_dict_status_label", None)
            if label is None or not label.winfo_exists():
                label = tk.Label(
                    self.dict_result, bg=BG, fg=color, font=(FONT_FAMILY, 9), anchor="w"
                )
                self._dict_status_label = label
            label.configure(text=text, fg=color)
            label.pack(fill="x", pady=(3, 0))
            job = getattr(self, "_dict_status_job", None)
            if job:
                self.win.after_cancel(job)
            self._dict_status_job = self.win.after(4000, self._clear_dict_status)
        except tk.TclError:  # 控件可能已销毁，刻意忽略
            pass

    def _clear_dict_status(self) -> None:
        try:
            label = getattr(self, "_dict_status_label", None)
            if label is not None and label.winfo_exists():
                label.pack_forget()
        except tk.TclError:  # 控件可能已销毁，刻意忽略
            pass

    def _save_dict(self, entry: dict, word: str, star=None) -> None:
        senses = entry.get("senses") or []
        first = senses[0] if senses else {}
        lang = entry.get("lang") or self.book or ""
        existing = self.service.find_vocab(lang, word) or self.service.find_vocab(
            lang, entry.get("matched") or ""
        )
        if existing:
            self.service.remove_vocab(lang, word)
            if star is not None:
                try:
                    star.configure(text="☆", fg=ACCENT)
                except tk.TclError:  # 控件可能已销毁，刻意忽略
                    pass
            self._set_dict_status(f"已从生词本移除：{word}")
            return
        result = self.cb.get("save_word")(
            {
                "lang": lang,
                "word": word,
                "lemma": entry.get("matched") or word,
                "reading": entry.get("phonetic") or "",
                "pos": first.get("pos") or "",
                "meaning": first.get("definition_cn") or first.get("definition") or "",
                "sentence": "",
                "book": self.book,
                "dict_source": entry.get("source") or "",
                "dict_meaning": first.get("definition_cn") or first.get("definition") or "",
                "dict_example": first.get("example") or "",
                "dict_example_cn": first.get("example_cn") or "",
                "audio_key": entry.get("audio_key") or "",
                "dict_id": entry.get("dict_id") or "",
            }
        )
        if star is not None:
            try:
                star.configure(text="★", fg="#f5c542")
            except tk.TclError:  # 控件可能已销毁，刻意忽略
                pass
        self._set_dict_status(f"★ 已加入生词本：{word}（共 {result.get('total', 0)} 个）")

    # ------------------------------------------------------------------ 翻译
