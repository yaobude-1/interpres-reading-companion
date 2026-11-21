"""Main panel: the dictionary tab (lookup, senses, morphology, save)."""

from __future__ import annotations

import tkinter as tk

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


class PanelDictMixin:
    def _on_dict_typing(self, _event=None) -> None:
        if self._dict_job is not None:
            try:
                self.win.after_cancel(self._dict_job)
            except tk.TclError:
                pass
        self._dict_job = self.win.after(220, self._dict_typed)

    def _lookup_dict(self, _keep_suggestions: bool = False) -> None:
        # 取消还在等待的“输入停顿”任务，避免查词后下拉又冒出来
        if self._dict_job is not None:
            try:
                self.win.after_cancel(self._dict_job)
            except tk.TclError:
                pass
        self._dict_job = None
        if not _keep_suggestions:
            self._hide_suggestions()
        word = self.dict_input.get().strip()
        for child in self.dict_result.winfo_children():
            child.destroy()
        if not word:
            self._dict_hint("输入一个单词，本地词典查询，不消耗 token")
            self._sync_content_scroll()
            return
        hits = self.service.lookup_all(word)
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
        self._bind_content_wheel(self.content)
        self._sync_content_scroll()

    def _dict_lookup_word(self, word: str) -> None:
        """点变位表/原形时，直接在面板里查这个词。"""
        word = (word or "").strip()
        if not word:
            return
        self.dict_input.delete(0, "end")
        self.dict_input.insert(0, word)
        self._lookup_dict()

    def _dict_typed(self) -> None:
        """输入停顿后只刷新下拉建议；卡片等回车/点选再渲染，避免抖。"""
        self._update_suggestions()
        if not self._suggest_rows and self.dict_input.get().strip():
            self._lookup_dict()

    def _render_dict(self, entry: dict, word: str, alternatives=None) -> None:
        for child in self.dict_result.winfo_children():
            child.destroy()
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
                    w, e.get("lang") or "", e.get("audio_key") or ""
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
        original = tk.Label(
            head, text="原版", bg=PANEL, fg=TEXT, font=(FONT_FAMILY, 8),
            padx=6, pady=2, cursor="hand2",
        )
        original.pack(side="left", padx=(8, 0))
        entry_lang = entry.get("lang")
        original.bind(
            "<Button-1>",
            lambda _e, w=word, lang=entry_lang: self.cb.get(
                "show_entry", lambda *_a: None
            )(w, lang),
        )
        original.bind("<Enter>", lambda _e: original.configure(bg=PANEL_ALT))
        original.bind("<Leave>", lambda _e: original.configure(bg=PANEL))
        if entry.get("source"):
            tk.Label(
                head, text=entry["source"][:20], bg=BG, fg=GREEN, font=(FONT_FAMILY, 8)
            ).pack(side="left", padx=(8, 0))

        alternatives = alternatives or []
        if len(alternatives) > 1:
            bar = tk.Frame(self.dict_result, bg=BG)
            bar.pack(fill="x", pady=(4, 2))
            current = (entry.get("source") or "", entry.get("lang") or "")
            for hit in alternatives:
                active = (hit.get("source") or "", hit.get("lang") or "") == current
                chip = tk.Label(
                    bar,
                    text=f"{self.cb.get('lang_label', lambda c: c)(hit.get('lang', ''))}·{(hit.get('source') or '')[:14]}",
                    bg=PANEL if active else BG,
                    fg=TEXT if active else DIM,
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

        morph = entry.get("morph") or {}
        if morph:
            lemma_text = morph.get("lemma") or ""
            lemma_label = tk.Label(
                self.dict_result,
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
            tabs = tk.Frame(self.dict_result, bg=BG)
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

        container = tk.Frame(self.dict_result, bg=BG)
        container.pack(fill="x")
        self._panel_meaning = tk.Frame(container, bg=BG)
        self._panel_meaning.pack(fill="x")
        self._panel_conj = tk.Frame(container, bg=BG)
        self._panel_render_senses(self._panel_meaning, entry, word)
        if morph:
            self._panel_render_tables(self._panel_conj, morph)


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
        if matched and matched.lower() != word.lower():
            tk.Label(
                parent, text=f"按原形 {matched} 查到", bg=BG, fg=DIM, font=(FONT_FAMILY, 8),
                anchor="w",
            ).pack(fill="x", pady=(0, 4))
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
        except tk.TclError:
            pass

    def _clear_dict_status(self) -> None:
        try:
            label = getattr(self, "_dict_status_label", None)
            if label is not None and label.winfo_exists():
                label.pack_forget()
        except tk.TclError:
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
                except tk.TclError:
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
            }
        )
        if star is not None:
            try:
                star.configure(text="★", fg="#f5c542")
            except tk.TclError:
                pass
        self._set_dict_status(f"★ 已加入生词本：{word}（共 {result.get('total', 0)} 个）")

    # ------------------------------------------------------------------ 翻译
