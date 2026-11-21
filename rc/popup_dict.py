"""Popup: dictionary entry view (senses, morphology, similar words)."""

from __future__ import annotations

import tkinter as tk

from .popup_common import _short_source
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


class DictViewMixin:
    def _dict_action(self, parent, text: str, command) -> tk.Label:
        label = tk.Label(
            parent,
            text=text,
            bg=PANEL,
            fg=TEXT,
            font=(FONT_FAMILY, 9),
            padx=10,
            pady=5,
            cursor="hand2",
        )
        label.bind("<Button-1>", lambda _e: command())
        label.bind("<Enter>", lambda _e: label.configure(bg=PANEL_ALT))
        label.bind("<Leave>", lambda _e: label.configure(bg=PANEL))
        return label

    def show_dictionary(self, entry: dict, anchor, word: str = "", alternatives=None) -> None:
        """本地词典查词结果（不花 token）；有变位/变格时提供「时态」页签。"""
        self._reset_to_translate(chat_button=False)
        self._mode = "dict"
        self._dict = entry
        if anchor != self._anchor:
            self._user_moved = False
        self._anchor = anchor
        self._dict_word = word or entry.get("word") or entry.get("query") or ""
        self.current = None
        self._clear()
        self._dict_editing = False
        self._dict_entry = None
        self.title.configure(text="查词")

        head = tk.Frame(self.body, bg=BG)
        head.pack(fill="x", pady=(2, 6))
        self._dict_word_label = self._label(
            head, self._dict_word, fg=TEXT, font=(FONT_FAMILY, 17, "bold")
        )
        self._dict_word_label.pack(side="left")
        self._dict_word_label.configure(cursor="hand2")
        self._dict_word_label.bind("<Button-1>", lambda _e: self._edit_dict_word())
        self._dict_word_label.bind(
            "<Enter>",
            lambda _e: self._dict_word_label.configure(
                font=(FONT_FAMILY, 17, "bold", "underline")
            ),
        )
        self._dict_word_label.bind(
            "<Leave>",
            lambda _e: self._dict_word_label.configure(font=(FONT_FAMILY, 17, "bold")),
        )
        edit = self._label(head, "✎", fg=DIM, font=(FONT_FAMILY, 11))
        edit.pack(side="left", padx=(8, 0))
        edit.configure(cursor="hand2")
        edit.bind("<Button-1>", lambda _e: self._edit_dict_word())
        edit.bind("<Enter>", lambda _e: edit.configure(fg=ACCENT))
        edit.bind("<Leave>", lambda _e: edit.configure(fg=DIM))
        phonetic = (entry.get("phonetic") or "").strip()
        if phonetic:
            self._label(head, f"/{phonetic}/", fg=MUTED, font=(FONT_FAMILY, 9)).pack(
                side="left", padx=(8, 0)
            )
        if entry.get("audio_key") or entry.get("lang") or self._lang:
            speak = self._label(head, "🔊", fg=ACCENT, font=(FONT_FAMILY, 12))
            speak.pack(side="left", padx=(8, 0))
            speak.configure(cursor="hand2")
            speak.bind("<Button-1>", lambda _e: self._speak())
            speak.bind("<Enter>", lambda _e: speak.configure(fg=TEXT))
            speak.bind("<Leave>", lambda _e: speak.configure(fg=ACCENT))
        finder = self.cb.get("find_word")
        saved = finder(entry.get("lang") or self._lang or "", self._dict_word) if finder else None
        star = self._label(
            head, "★" if saved else "☆",
            fg="#f5c542" if saved else ACCENT, font=(FONT_FAMILY, 13),
        )
        star.pack(side="left", padx=(8, 0))
        star.configure(cursor="hand2")
        star.bind("<Button-1>", lambda _e, st=star: self._save_dict_word(st))
        star.bind("<Enter>", lambda _e: star.configure(fg=TEXT))
        star.bind("<Leave>", lambda _e, st=star: st.configure(fg=st.cget("fg")))
        original = self._label(head, "原版", fg=TEXT, font=(FONT_FAMILY, 8))
        original.pack(side="left", padx=(10, 0))
        original.configure(cursor="hand2")
        original.bind(
            "<Button-1>",
            lambda _e: self.cb.get("show_entry", lambda *_a: None)(
                self._dict_word, entry.get("lang") or ""
            ),
        )
        original.bind("<Enter>", lambda _e: original.configure(fg=ACCENT))
        original.bind("<Leave>", lambda _e: original.configure(fg=TEXT))
        source = entry.get("source") or ""
        if source:
            self._label(head, _short_source(source), fg=GREEN, font=(FONT_FAMILY, 8)).pack(
                side="left", padx=(8, 0)
            )

        alternatives = alternatives or []
        if len(alternatives) > 1:
            bar = tk.Frame(self.body, bg=BG)
            bar.pack(fill="x", pady=(0, 6))
            current = (entry.get("source") or "", entry.get("lang") or "")
            for hit in alternatives:
                active = (hit.get("source") or "", hit.get("lang") or "") == current
                label = tk.Label(
                    bar,
                    text=f"{self.cb.get('lang_label', lambda c: c)(hit.get('lang', ''))}·{_short_source(hit.get('source', ''))}",
                    bg=PANEL if active else BG,
                    fg=TEXT if active else DIM,
                    font=(FONT_FAMILY, 8),
                    padx=8,
                    pady=3,
                    cursor="hand2",
                )
                label.pack(side="left", padx=(0, 6))
                label.bind(
                    "<Button-1>",
                    lambda _e, h=hit: self.show_dictionary(
                        h["entry"], self._anchor, self._dict_word, alternatives
                    ),
                )

        morph = entry.get("morph") or {}
        if morph:
            lemma_text = morph.get("lemma") or ""
            lemma_label = self._label(
                self.body,
                f"原形 {lemma_text}（{morph.get('label', '')}）",
                fg=ACCENT,
                font=(FONT_FAMILY, 9),
            )
            lemma_label.pack(fill="x", pady=(0, 6))
            if lemma_text:
                lemma_label.configure(cursor="hand2")
                lemma_label.bind("<Button-1>", lambda _e, w=lemma_text: self._dict_jump(w))
            tabs = tk.Frame(self.body, bg=BG)
            tabs.pack(fill="x", pady=(0, 4))
            self._dict_tab_meaning = tk.Label(
                tabs, text="释义", bg=PANEL, fg=TEXT, font=(FONT_FAMILY, 9, "bold"),
                padx=12, pady=4, cursor="hand2",
            )
            self._dict_tab_meaning.pack(side="left")
            has_cases = any((t or {}).get("cases") for t in (morph.get("tables") or []))
            self._dict_tab_conj = tk.Label(
                tabs, text="变格" if has_cases else "时态", bg=BG, fg=DIM, font=(FONT_FAMILY, 9, "bold"),
                padx=12, pady=4, cursor="hand2",
            )
            self._dict_tab_conj.pack(side="left", padx=(6, 0))
            self._dict_tab_meaning.bind("<Button-1>", lambda _e: self._show_dict_tab("meaning"))
            self._dict_tab_conj.bind("<Button-1>", lambda _e: self._show_dict_tab("conj"))

        container = tk.Frame(self.body, bg=BG)
        container.pack(fill="x", pady=(4, 0))
        self._dict_meaning = tk.Frame(container, bg=BG)
        self._dict_meaning.pack(fill="x")
        self._dict_conj = tk.Frame(container, bg=BG)
        self._render_dict_senses(self._dict_meaning, entry)
        if morph:
            self._render_morph_tables(self._dict_conj, morph)

        actions = tk.Frame(self.body, bg=BG)
        actions.pack(fill="x", pady=(10, 4))
        self._dict_action(actions, "用 AI 译", self._translate_dict_word).pack(side="right")

        self.footer.configure(text="Enter 收藏 · 空格 发音 · Esc 关闭")
        self._reveal()

    def _show_dict_tab(self, name: str) -> None:
        if name == "conj":
            self._dict_meaning.pack_forget()
            self._dict_conj.pack(fill="x")
            self._dict_tab_conj.configure(bg=PANEL, fg=TEXT)
            self._dict_tab_meaning.configure(bg=BG, fg=DIM)
        else:
            self._dict_conj.pack_forget()
            self._dict_meaning.pack(fill="x")
            self._dict_tab_meaning.configure(bg=PANEL, fg=TEXT)
            self._dict_tab_conj.configure(bg=BG, fg=DIM)

    def _render_dict_senses(self, parent, entry: dict) -> None:
        matched = entry.get("matched") or ""
        if matched and matched.lower() != self._dict_word.lower():
            self._label(
                parent, f"按原形 {matched} 查到", fg=DIM, font=(FONT_FAMILY, 8)
            ).pack(fill="x", pady=(0, 6))
        senses = entry.get("senses") or []
        groups: dict[str, list[dict]] = {}
        order: list[str] = []
        for sense in senses:
            pos = (sense.get("pos") or "").strip()
            if pos not in groups:
                groups[pos] = []
                order.append(pos)
            groups[pos].append(sense)
        suggestions = entry.get("lemma_suggestions") or []
        if suggestions:
            hint = tk.Frame(parent, bg=BG)
            hint.pack(fill="x", pady=(2, 4))
            self._label(hint, "您是否要查找：", fg=MUTED, font=(FONT_FAMILY, 9)).pack(side="left")
            for idx, cand in enumerate(suggestions):
                if idx:
                    self._label(hint, " / ", fg=MUTED, font=(FONT_FAMILY, 9)).pack(side="left")
                link = self._label(
                    hint, cand, fg=ACCENT, font=(FONT_FAMILY, 9, "underline")
                )
                link.pack(side="left")
                link.configure(cursor="hand2")
                link.bind("<Button-1>", lambda _e, w=cand: self._dict_jump(w))
        for pos in order:
            if pos:
                self._label(
                    parent, pos, fg=ACCENT, font=(FONT_FAMILY, 9, "bold")
                ).pack(fill="x", pady=(6, 2))
            for index, sense in enumerate(groups[pos], start=1):
                row = tk.Frame(parent, bg=BG)
                row.pack(fill="x", pady=(0, 2))
                self._label(
                    row, f"{index}.", fg=ACCENT, font=(FONT_FAMILY, 9)
                ).pack(side="left", anchor="n", padx=(0, 4))
                definition = sense.get("definition_cn") or sense.get("definition") or ""
                self._label(
                    row, definition, fg=TEXT, font=(FONT_FAMILY, 10),
                    wraplength=self.width - 110,
                ).pack(side="left", anchor="w")
                example = (sense.get("example") or "").strip()
                if example:
                    self._label(
                        parent, example, fg=MUTED, font=(FONT_FAMILY, 9),
                        wraplength=self.width - 80,
                    ).pack(fill="x", padx=(26, 0), pady=(0, 2))
                example_cn = (sense.get("example_cn") or "").strip()
                if example_cn:
                    self._label(
                        parent, example_cn, fg=DIM, font=(FONT_FAMILY, 9),
                        wraplength=self.width - 80,
                    ).pack(fill="x", padx=(26, 0), pady=(0, 2))
        if not (entry.get("senses") or []):
            self._label(
                parent, "（词典里这个词没有释义）", fg=MUTED, font=(FONT_FAMILY, 9)
            ).pack(fill="x", pady=(0, 6))

    def _render_morph_tables(self, parent, morph: dict) -> None:
        target = (morph.get("form") or "").lower()
        tables = morph.get("tables") or []
        # 含查询形式的时态组排到最前面
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
            self._label(
                header,
                f"{group.get('zh', '')}  {group.get('fr', '')}",
                fg=ACCENT,
                font=(FONT_FAMILY, 9, "bold"),
                bg=PANEL_ALT,
            ).pack(anchor="w", padx=10, pady=(6, 4))
            body = tk.Frame(card, bg=PANEL)
            body.pack(fill="x", padx=10, pady=(4, 8))
            if group.get("cases"):
                for row in group.get("rows") or []:
                    line = tk.Frame(body, bg=PANEL)
                    line.pack(fill="x")
                    self._label(
                        line, row.get("case", ""), fg=DIM, font=(FONT_FAMILY, 9), bg=PANEL
                    ).pack(side="left", pady=1)
                    for key, _fallback in (("sing", ""), ("plur", "")):
                        value = (row.get(key) or "").strip()
                        if not value:
                            continue
                        mine = value.lower() == target
                        value_label = self._label(
                            line,
                            value,
                            fg=ACCENT if mine else TEXT,
                            font=(FONT_FAMILY, 10, "bold" if mine else "normal"),
                            bg=PANEL,
                        )
                        value_label.pack(side="left", padx=(14, 0), pady=1)
                        value_label.configure(cursor="hand2")
                        value_label.bind(
                            "<Button-1>", lambda _e, w=value: self._dict_jump(w)
                        )
            else:
                for person, form in group.get("rows") or []:
                    line = tk.Frame(body, bg=PANEL)
                    line.pack(fill="x")
                    self._label(
                        line, person, fg=DIM, font=(FONT_FAMILY, 9), bg=PANEL
                    ).pack(side="left", pady=1)
                    mine = (form or "").lower() == target
                    form_label = self._label(
                        line,
                        form,
                        fg=ACCENT if mine else TEXT,
                        font=(FONT_FAMILY, 10, "bold" if mine else "normal"),
                        bg=PANEL,
                    )
                    form_label.pack(side="left", padx=(14, 0), pady=1)
                    if form and " " not in form.strip():
                        form_label.configure(cursor="hand2")
                        form_label.bind(
                            "<Button-1>", lambda _e, w=form: self._dict_jump(w)
                        )

    def show_dict_missing(self, word: str, anchor, configured: bool = True) -> None:
        """词典里没有：提示 + 给「用 AI 译」按钮。"""
        self._reset_to_translate(chat_button=False)
        self._mode = "dict"
        if anchor != self._anchor:
            self._user_moved = False
        self._anchor = anchor
        self._dict = None
        self._dict_word = word
        if anchor != self._anchor:
            self._user_moved = False
        self._anchor = anchor
        self.current = None
        self._clear()
        self._dict_editing = False
        self._dict_entry = None
        self.title.configure(text="查词")
        self._label(self.body, word, fg=TEXT, font=(FONT_FAMILY, 16, "bold")).pack(
            fill="x", pady=(2, 4)
        )
        message = (
            "本地词典里没有这个词。"
            if configured
            else "还没配置本地词典：设置 →「词典设置…」添加 MDX。"
        )
        self._label(
            self.body, message, fg=MUTED, font=(FONT_FAMILY, 10)
        ).pack(fill="x", pady=(0, 10))
        self._render_similar(self.body, word, "", anchor)
        actions = tk.Frame(self.body, bg=BG)
        actions.pack(fill="x", pady=(4, 4))
        self._dict_action(actions, "用 AI 译", self._translate_dict_word).pack(side="left")
        self.footer.configure(text="Esc 关闭")
        self._reveal()

    def _edit_dict_word(self) -> None:
        """把词头原地变成输入框，改完回车重新查。"""
        existing = getattr(self, "_dict_entry", None)
        if existing is not None:
            try:
                if existing.winfo_exists():
                    existing.focus_set()
                    return
            except tk.TclError:
                pass
            self._dict_entry = None
            self._dict_editing = False
        label = getattr(self, "_dict_word_label", None)
        if label is None:
            return
        head = label.master
        self._dict_editing = True
        siblings = [
            w for w in head.winfo_children()
            if w is not label and w.winfo_manager() == "pack"
        ]
        first = siblings[0] if siblings else None
        try:
            entry = tk.Entry(
                head,
                bg=PANEL,
                fg=TEXT,
                insertbackground=TEXT,
                relief="flat",
                font=(FONT_FAMILY, 15),
                width=max(8, min(24, len(self._dict_word) + 2)),
            )
            entry.insert(0, self._dict_word)
            if first is not None:
                entry.pack(side="left", padx=(0, 6), before=first)
            else:
                entry.pack(side="left", padx=(0, 6))
            self._dict_entry = entry
            label.pack_forget()
            entry.focus_set()
            entry.select_range(0, "end")
            entry.icursor("end")

            def restore() -> None:
                self._dict_editing = False
                self._dict_entry = None
                try:
                    entry.destroy()
                except tk.TclError:
                    pass
                try:
                    remaining = [
                        w for w in head.winfo_children()
                        if w is not label and w.winfo_manager() == "pack"
                    ]
                    if remaining:
                        label.pack(side="left", before=remaining[0])
                    else:
                        label.pack(side="left")
                except tk.TclError:
                    pass

            def commit(_event=None) -> None:
                text = entry.get().strip()
                restore()
                if text and text != self._dict_word:
                    self._dict_jump(text)

            def cancel(_event=None) -> None:
                restore()

            entry.bind("<Return>", commit)
            entry.bind("<Escape>", cancel)
            entry.bind("<FocusOut>", cancel)
        except Exception:
            self._dict_editing = False

    def _render_similar(self, parent, word: str, lang: str, anchor) -> None:
        """没查到词时列相近的词。"""
        cb = self.cb.get("fuzzy")
        if cb is None:
            return
        try:
            items = cb(word, lang)
        except Exception:
            items = []
        rows = [it for it in (items or []) if (it.get("word") or "").lower() != word.lower()]
        if not rows:
            return
        self._label(
            parent, "相近的词", fg=MUTED, font=(FONT_FAMILY, 8)
        ).pack(fill="x", pady=(4, 4))
        for item in rows[:8]:
            line = tk.Frame(parent, bg=BG)
            line.pack(fill="x", pady=1)
            name = item.get("word") or ""
            name_label = self._label(
                line, name, fg=TEXT, font=(FONT_FAMILY, 10, "bold")
            )
            name_label.pack(side="left")
            name_label.configure(cursor="hand2")
            name_label.bind("<Button-1>", lambda _e, w=name: self._dict_jump(w))
            pos = (item.get("pos") or "").strip()
            if pos:
                self._label(line, pos, fg=ACCENT, font=(FONT_FAMILY, 8)).pack(
                    side="left", padx=(8, 0)
                )
            gloss = (item.get("gloss") or "").strip()
            if gloss:
                self._label(line, gloss, fg=MUTED, font=(FONT_FAMILY, 9)).pack(
                    side="left", padx=(10, 0)
                )

    def _dict_jump(self, word: str) -> None:
        """点原形/变位形式：让宿主再查一次这个词。"""
        word = (word or "").strip()
        if not word:
            return
        cb = self.cb.get("dict_lookup")
        if cb is not None:
            cb(word)

    def _save_dict_word(self, star=None) -> None:
        entry = self._dict or {}
        senses = entry.get("senses") or []
        first = senses[0] if senses else {}
        lang = entry.get("lang") or self._lang or ""
        finder = self.cb.get("find_word")
        remover = self.cb.get("remove_word")
        existing = finder(lang, self._dict_word) if finder else None
        if existing and remover:
            remover(lang, self._dict_word)
            if star is not None:
                try:
                    star.configure(text="☆", fg=ACCENT)
                except tk.TclError:
                    pass
            self.footer.configure(text=f"已从生词本移除：{self._dict_word}")
            self.cb.get("toast", lambda _m: None)(f"已取消收藏 {self._dict_word}")
            return
        saver = self.cb.get("save_word")
        if not saver:
            return
        result = saver(
            {
                "lang": entry.get("lang") or self._lang or "",
                "word": self._dict_word,
                "lemma": entry.get("matched") or self._dict_word,
                "reading": entry.get("phonetic") or "",
                "pos": first.get("pos") or "",
                "meaning": first.get("definition_cn") or first.get("definition") or "",
                "sentence": "",
                "book": "",
                "dict_source": entry.get("source") or "",
                "dict_meaning": first.get("definition_cn") or first.get("definition") or "",
                "dict_example": first.get("example") or "",
                "dict_example_cn": first.get("example_cn") or "",
                "audio_key": entry.get("audio_key") or "",
            }
        )
        if star is not None:
            try:
                star.configure(text="★", fg="#f5c542")
            except tk.TclError:
                pass
        self.footer.configure(text=f"★ 已加入生词本：{self._dict_word}")
        self.cb.get("toast", lambda _m: None)(
            f"已收藏 {self._dict_word}（{result.get('total', 0)} 个）"
        )

    def _translate_dict_word(self) -> None:
        word = self._dict_word
        if not word:
            return
        self.hide()
        self.cb.get("manual_translate", lambda _t: None)(word)
