"""Popup: translation result view (terms, grammar, actions)."""

from __future__ import annotations

import tkinter as tk

from . import textutil
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


class ResultViewMixin:
    def show_result(self, payload: dict, anchor: tuple[int, int]) -> None:
        # 正在聊天时翻译结果回来了：静默更新，不要打断对话
        if self._mode == "chat":
            self.current = payload
            self._pending_payload = payload
            return
        self.current = payload
        self._pending_payload = payload
        if anchor != self._anchor:
            self._user_moved = False
        self._anchor = anchor
        self._expanded = False
        self.saved = set()
        self._input_mode = False
        self._reset_to_translate(chat_button=True)
        self._lang = payload.get("source_lang") or "en"
        book = payload.get("book") or ""

        self.title.configure(text=self._title_text(book, self._lang, payload.get("meta")))
        self._clear()

        # 原文（可折叠）
        source = payload.get("text") or ""
        src_frame = tk.Frame(self.body, bg=BG)
        src_frame.pack(fill="x", pady=(0, 2))
        self._label(
            src_frame,
            source if self._expanded or len(source) <= 180 else source[:180] + " …",
            fg=MUTED,
            font=(FONT_FAMILY, 9),
            wraplength=self.width - 40,
        ).pack(fill="x")
        if len(source) > 180:
            toggle = self._label(
                src_frame, "展开原文" if not self._expanded else "收起", fg=DIM,
                font=(FONT_FAMILY, 8), cursor="hand2",
            )
            toggle.pack(anchor="w", pady=(2, 0))
            toggle.bind("<Button-1>", lambda _e: self._toggle_source())

        self._divider(9)

        # 译文
        translation = tk.Frame(self.body, bg=PANEL)
        translation.pack(fill="x")
        self._label(
            translation,
            payload.get("translation", ""),
            fg=TEXT,
            font=(FONT_FAMILY, 12),
            bg=PANEL,
            wraplength=self.width - 62,
        ).pack(fill="x", padx=14, pady=12)

        # 生词
        terms = payload.get("terms") or []
        if terms:
            self._divider(10)
            head = tk.Frame(self.body, bg=BG)
            head.pack(fill="x")
            self._label(head, "生词", fg=DIM, font=(FONT_FAMILY, 8)).pack(side="left")
            self._label(
                head,
                "数字键收藏 · 点击也可",
                fg=DIM,
                font=(FONT_FAMILY, 8),
            ).pack(side="right")
            for idx, term in enumerate(terms[:9]):
                self._term_row(idx, term, source, book)

        # 语法
        grammar = payload.get("grammar")
        if grammar:
            self._divider(10)
            row = tk.Frame(self.body, bg=PANEL_ALT)
            row.pack(fill="x")
            self._label(
                row,
                "语法",
                fg=ACCENT,
                font=(FONT_FAMILY, 8, "bold"),
                bg=PANEL_ALT,
            ).pack(anchor="w", padx=12, pady=(8, 0))
            self._label(
                row,
                grammar,
                fg=MUTED,
                font=(FONT_FAMILY, 9),
                bg=PANEL_ALT,
                wraplength=self.width - 56,
            ).pack(anchor="w", padx=12, pady=(2, 8))

        # 术语命中
        hits = payload.get("glossary_hits") or []
        if hits:
            self._divider(8)
            text = " · ".join(f"{h['term']} → {h['rendering']}" for h in hits)
            self._label(self.body, f"术语表命中：{text}", fg=DIM, font=(FONT_FAMILY, 8)).pack(
                fill="x"
            )

        meta = payload.get("meta") or {}
        cached = "缓存" if meta.get("cached") else f"{meta.get('elapsed_ms', 0)} ms"
        self.footer.configure(
            text=f"1-9 收藏 · Ctrl+Enter 同步 Anki · 空格朗读 · Enter 复制 · {cached}"
        )
        self._reveal()

    def _title_text(self, book: str, src: str, meta: dict | None) -> str:
        lang_label = self.cb.get("lang_label", lambda c: c)(src) if src else ""
        parts = [f"{lang_label} → 中文"] if lang_label else ["翻译"]
        if book:
            parts.append(textutil.display(book, 28))
        if meta and meta.get("cached"):
            parts.append("缓存")
        return "   ·   ".join(parts)

    def _toggle_source(self) -> None:
        if not self.current:
            return
        saved = set(self.saved)
        self._expanded = not self._expanded
        self.show_result(self.current, self._anchor)
        self.saved = saved
        for idx, term in enumerate(self.current.get("terms") or []):
            if (term.get("lemma") or term.get("word")) in saved:
                self._mark_saved(idx)

    def _term_row(self, idx: int, term: dict, sentence: str, book: str) -> None:
        row = tk.Frame(self.body, bg=PANEL)
        row.pack(fill="x", pady=(6, 0))

        badge = tk.Label(
            row,
            text=str(idx + 1),
            bg=PANEL_ALT,
            fg=MUTED,
            font=(FONT_FAMILY, 8),
            width=2,
        )
        badge.pack(side="left", padx=(10, 8), pady=8)

        text_frame = tk.Frame(row, bg=PANEL)
        text_frame.pack(side="left", fill="x", expand=True, pady=6)

        top = tk.Frame(text_frame, bg=PANEL)
        top.pack(fill="x")
        word = tk.Label(
            top,
            text=term.get("word", ""),
            bg=PANEL,
            fg=TEXT,
            font=(FONT_FAMILY, 11, "bold"),
        )
        word.pack(side="left")
        if term.get("reading"):
            tk.Label(
                top,
                text="  " + term["reading"],
                bg=PANEL,
                fg=DIM,
                font=(FONT_FAMILY, 8),
            ).pack(side="left")
        if term.get("pos"):
            tk.Label(
                top,
                text="  " + term["pos"],
                bg=PANEL,
                fg=ACCENT,
                font=(FONT_FAMILY, 8),
            ).pack(side="left")

        dict_info = term.get("dict") or {}
        if dict_info.get("source"):
            tk.Label(
                top,
                text="  " + source_label(dict_info["source"]),
                bg=PANEL,
                fg=GREEN,
                font=(FONT_FAMILY, 7),
            ).pack(side="left")

        dict_def = (dict_info.get("definition") or "").strip()
        llm_def = (term.get("meaning") or "").strip()
        primary = dict_def or llm_def
        meaning = tk.Label(
            text_frame,
            text=primary,
            bg=PANEL,
            fg=TEXT,
            font=(FONT_FAMILY, 9),
            justify="left",
            anchor="w",
            wraplength=self.width - 110,
        )
        meaning.pack(fill="x", pady=(2, 0))
        if dict_def and llm_def and llm_def != dict_def:
            tk.Label(
                text_frame,
                text=f"文中义：{llm_def}",
                bg=PANEL,
                fg=ACCENT,
                font=(FONT_FAMILY, 8),
                justify="left",
                anchor="w",
                wraplength=self.width - 110,
            ).pack(fill="x", pady=(1, 0))
        note_text = term.get("note") or (dict_info.get("example") or "")
        if note_text:
            tk.Label(
                text_frame,
                text=note_text,
                bg=PANEL,
                fg=DIM,
                font=(FONT_FAMILY, 8),
                justify="left",
                anchor="w",
                wraplength=self.width - 110,
            ).pack(fill="x", pady=(1, 0))

        star = tk.Label(
            row,
            text="☆",
            bg=PANEL,
            fg=DIM,
            font=(FONT_FAMILY, 12),
            cursor="hand2",
            padx=10,
        )
        star.pack(side="right")

        def save(_event=None):
            self._save_word(idx)

        for widget in (row, badge, text_frame, top, word, meaning, star):
            widget.bind("<Button-1>", save)
        for widget in (row, badge, text_frame, top, word, meaning, star):
            widget.bind("<Enter>", lambda _e, r=row, s=star: (r.configure(bg=PANEL_ALT), s.configure(bg=PANEL_ALT)))
            widget.bind("<Leave>", lambda _e, r=row, s=star: (r.configure(bg=PANEL), s.configure(bg=PANEL)))

        self._bind_wheel(row)

    # ------------------------------------------------------------------ 动作
    def _save_word(self, idx: int) -> None:
        if self._input_mode or self._mode == "chat" or not self.current:
            return
        terms = self.current.get("terms") or []
        if idx >= len(terms):
            return
        term = terms[idx]
        key = term.get("lemma") or term.get("word")
        if key in self.saved:
            self.cb.get("toast", lambda _m: None)("已经收藏过了")
            return
        result = self.cb.get("save_word")(
            {
                "lang": self._lang,
                "word": term.get("word", ""),
                "lemma": term.get("lemma", ""),
                "reading": term.get("reading", ""),
                "pos": term.get("pos", ""),
                "meaning": term.get("meaning", ""),
                "sentence": self.current.get("text", ""),
                "book": self.current.get("book", ""),
                "dict_source": (term.get("dict") or {}).get("source", ""),
                "dict_meaning": (term.get("dict") or {}).get("definition", ""),
                "dict_example": (term.get("dict") or {}).get("example", ""),
                "dict_example_cn": (term.get("dict") or {}).get("example_cn", ""),
                "audio_key": (term.get("dict") or {}).get("audio_key", ""),
            }
        )
        self.saved.add(key)
        self.cb.get("toast", lambda _m: None)(
            f"已收藏 {term.get('word', '')}（{result.get('total', 0)} 个）"
        )
        # 行内的星星换成实心
        self._mark_saved(idx)

    def _mark_saved(self, idx: int) -> None:
        rows = [w for w in self.body.winfo_children() if isinstance(w, tk.Frame)]
        counter = -1
        for frame in rows:
            for child in frame.winfo_children():
                if isinstance(child, tk.Label) and child.cget("text") == "☆":
                    counter += 1
                    if counter == idx:
                        child.configure(text="★", fg=GREEN)

    def _toggle(self, idx: int) -> None:
        self._save_word(idx)

    def _make_toggle(self, idx: int):
        return lambda _e: self._save_word(idx)

    def _copy(self) -> None:
        if self._input_mode:
            self._manual()
            return
        if self._mode == "chat" or not self.current:
            return
        self.win.clipboard_clear()
        self.win.clipboard_append(self.current.get("translation", ""))
        self.cb.get("toast", lambda _m: None)("译文已复制")

    def _push_anki(self) -> None:
        if self._input_mode:
            self._manual()
            return
        if self._mode == "chat":
            return
        self.cb.get("push_anki", lambda: None)(self._lang)

    def _speak(self) -> None:
        if self._input_mode or self._mode == "chat" or not self.current:
            if self._mode == "dict" and self._dict_word:
                entry = self._dict or {}
                self.cb.get("speak", lambda *_a: None)(
                    self._dict_word,
                    entry.get("lang") or self._lang,
                    entry.get("audio_key") or "",
                )
            return
        text = self.current.get("text", "")
        self.cb.get("speak", lambda *_a: None)(text, self._lang)

    def _lock_term(self) -> None:
        if not self.current:
            return
        terms = self.current.get("terms") or []
        if not terms:
            return
        self.cb.get("lock_term", lambda *_a: None)(
            self.current.get("book", ""), terms[0].get("word", ""), self._lang
        )

    # ------------------------------------------------------------------ 显示
    def _reveal(self) -> None:
        self._bind_wheel(self.shell)
        self.win.deiconify()
        self.win.update_idletasks()
        self._fit_height()
        if not getattr(self, "_user_moved", False):
            self._place()
        self._visible = True
        try:
            self.win.focus_force()
        except tk.TclError:
            pass
