"""Anki：卡片字段、模板与推送。"""

from __future__ import annotations

import json

from . import i18n
from .anki import export_tsv
from .service_base import ServiceBase


class AnkiMixin(ServiceBase):
    _POS_SHORT = {
        "adjective": "adj.",
        "adverb": "adv.",
        "noun": "n.",
        "verb": "v.",
        "preposition": "prep.",
        "pronoun": "pron.",
        "conjunction": "conj.",
        "determiner": "det.",
        "exclamation": "excl.",
        "number": "num.",
    }

    def _rich_word(self, word: dict) -> dict:
        """给 Interpres 模板补全：按词性分区 + 义项编号 + 全部例句（保留加粗）。"""
        from .rich import auto_extract, render_interpres

        lang = (word.get("lang") or "").lower()
        text = (word.get("word") or word.get("lemma") or "").strip()
        dictionary = self.dicts.dictionary(lang)
        if dictionary is None or not text:
            return word
        try:
            raw = dictionary._mdx.lookup(text)
            raw = raw if isinstance(raw, str) else ""
        except Exception:
            return word
        blocks: list[dict] = auto_extract(raw, text)
        if not blocks:
            return word
        # 用结构化词条补齐 HTML 里没配上的例句翻译
        try:
            entry = dictionary.lookup(text)
        except Exception:
            entry = None
        if entry is not None and getattr(entry, "senses", None):
            def norm(value: str) -> str:
                import html as _html
                import re as _re

                text = _html.unescape(_re.sub(r"<[^>]+>", " ", value or ""))
                return _re.sub(r"\s+", " ", text).strip().lower()

            def find_pair(source: str) -> str:
                text = norm(source)
                if not text:
                    return ""
                for key, value in pairs.items():
                    if key and (key in text or text in key):
                        return value
                return ""

            pairs = {
                norm(sense.example): sense.example_cn
                for sense in entry.senses
                if sense.example and sense.example_cn
            }
            if pairs:
                for block in blocks:
                    for sense in block.get("senses") or []:
                        examples = sense.get("examples") or []
                        for index, (source, target) in enumerate(examples):
                            if not target:
                                found = find_pair(source)
                                if found:
                                    examples[index] = (source, found)
        pos_list: list[str] = []
        for block in blocks:
            pos = (block.get("pos") or "").strip()
            if pos and pos not in pos_list:
                pos_list.append(pos)
        enriched = dict(word)
        enriched["dict_meaning"] = render_interpres(blocks)
        enriched["dict_example"] = ""
        enriched["dict_example_cn"] = ""
        if pos_list:
            enriched["pos"] = " / ".join(pos_list)
        return enriched

    def _dict2anki_note(self, word: dict) -> dict:
        """把一条生词组装成 Dict2Anki 笔记的字段。"""
        import re

        from .rich import extract_english

        lang = word.get("lang") or "en"
        text = (word.get("word") or word.get("lemma") or "").strip()
        note = {
            "id": int(word["id"]),
            "term": text,
            "definition": word.get("dict_meaning") or word.get("meaning") or "",
            "definition_en": "",
            "uk": word.get("reading") or "",
            "us": word.get("reading") or "",
            "pronunciation": "",
            "group": "",
            "exam_type": "",
        }
        dictionary = self.dicts.dictionary(lang)
        senses: list[dict] = []
        if dictionary is not None and text:
            try:
                raw = dictionary._mdx.lookup(text)
                senses = extract_english(raw if isinstance(raw, str) else "")
            except Exception:
                senses = []

        if senses:
            groups: list[tuple[str, list[str]]] = []
            for sense in senses:
                pos = (sense.get("pos") or "").strip()
                cn = (sense.get("definition_cn") or "").strip()
                if not cn:
                    continue
                short = self._POS_SHORT.get(pos.lower(), pos)
                for name, items in groups:
                    if name == short:
                        if cn not in items:
                            items.append(cn)
                        break
                else:
                    groups.append((short, [cn]))
            parts = [
                (f"{name} " if name else "") + "，".join(items)
                for name, items in groups
                if items
            ]
            if parts:
                note["definition"] = "；".join(parts)
            en_defs = [s.get("definition") or "" for s in senses if s.get("definition")]
            note["definition_en"] = "; ".join(dict.fromkeys(en_defs))

        examples: list[tuple[str, str]] = []
        for sense in senses:
            for en, cn in sense.get("examples") or []:
                if en and (en, cn) not in examples:
                    examples.append((en, cn))
        # 词典里没有例句时退回收藏时存的那一条
        if not examples and (word.get("dict_example") or word.get("sentence")):
            examples.append(
                (
                    word.get("dict_example") or word.get("sentence") or "",
                    word.get("dict_example_cn") or "",
                )
            )
        for index, (en, cn) in enumerate(examples[:3]):
            if text:
                en = re.sub(
                    rf"(?i)(?<![\w-])({re.escape(text)})(?![\w-])",
                    r"<b>\1</b>",
                    en,
                    count=1,
                )
            note[f"sentence{index}"] = en
            note[f"sentence_explain{index}"] = cn
            note[f"sentence_speech{index}"] = ""
            note[f"splaceHolder{index}"] = "Tap To View"

        media = self._audio_for_word(word)
        if media:
            filename, data = media
            if self.anki.store_media(filename, data):
                note["pronunciation"] = f"[sound:{filename}]"
        return note

    def wordbook_anki(self, book_id: int) -> dict:
        book = self.store.wordbook(int(book_id))
        if not book:
            return {}
        try:
            return json.loads(book.get("anki_json") or "{}")
        except Exception:
            return {}

    def set_wordbook_anki(self, book_id: int, data: dict) -> None:
        self.store.set_wordbook_anki(int(book_id), json.dumps(data or {}, ensure_ascii=False))

    def _model_templates(self, model: str) -> dict:
        models = self.config.data.get("anki_models") or {}
        saved = models.get(model) or {}
        if saved:
            return {
                "front": saved.get("front") or "",
                "back": saved.get("back") or "",
                "css": saved.get("css") or "",
            }
        global_cfg = self.config.get("anki_custom") or {}
        if global_cfg.get("enabled") and (global_cfg.get("model") or "Interpres") == model:
            return {
                "front": global_cfg.get("front") or "",
                "back": global_cfg.get("back") or "",
                "css": global_cfg.get("css") or "",
            }
        return {"front": "", "back": "", "css": ""}

    def _effective_anki(self, wordbook_id: int | None) -> dict | None:
        if wordbook_id:
            book = self.store.wordbook(int(wordbook_id))
            if book:
                cfg = self.wordbook_anki(wordbook_id)
                mode = (cfg.get("mode") or "inherit").lower()
                if mode != "inherit":
                    model = cfg.get("model") or ""
                    if mode == "independent" or not model:
                        model = f"Interpres · {book.get('name') or i18n.wordbook_word()}"
                    return {
                        "mode": mode,
                        "model": model,
                        "fields": cfg.get("fields") or {},
                        "sync": bool(cfg.get("sync_templates", True)),
                        "templates": self._model_templates(model),
                    }
        global_cfg = self.config.get("anki_custom") or {}
        if global_cfg.get("enabled"):
            model = global_cfg.get("model") or "Interpres"
            return {
                "mode": "global",
                "model": model,
                "fields": global_cfg.get("fields") or {},
                "sync": bool(global_cfg.get("sync_templates", True)),
                "templates": self._model_templates(model),
            }
        return None

    def _book_deck(self, wordbook_id: int | None) -> str:
        if not wordbook_id:
            return ""
        book = self.store.wordbook(int(wordbook_id))
        return (book or {}).get("deck") or ""

    def push_anki(
        self,
        lang: str | None = None,
        word_ids: list[int] | None = None,
        wordbook_id: int | None = None,
    ) -> dict:
        deck_from_book = ""
        if wordbook_id:
            book = self.store.wordbook(int(wordbook_id))
            if not book:
                raise ValueError("词本不存在")
            lang = book.get("lang") or "en"
            deck_from_book = book.get("deck") or ""
            # 词本同步以 Anki 为准：已标记同步但卡片可能被删/换模型，
            # 因此每次把整本都交给 Anki，重复的会被跳过。
            words = self.store.words_in_book(int(wordbook_id), limit=5000)
        elif word_ids:
            words = [w for w in (self.store.get_word(i) for i in word_ids) if w]
        else:
            words = [
                w for w in self.store.list_words(lang, limit=5000) if not w.get("synced")
            ]
        if not words:
            return {"ok": True, "added": 0, "duplicated": 0, "failed": [], "message": "没有待同步的生词"}

        deck = (
            deck_from_book
            or self.config.language(lang).get("deck")
            or f"Reading::{lang.title()}"
        )
        effective = self._effective_anki(wordbook_id)
        if effective is not None:
            model = str(effective.get("model") or "Interpres")
            enriched = [self._rich_word(w) for w in words]
            result = self.anki.push_custom(
                enriched,
                deck,
                model,
                effective.get("fields") or {},
                audio_loader=self._audio_for_word,
                skip_existing=bool(self.config.get("anki_skip_existing", True)),
                templates=(effective.get("templates") if effective.get("sync") else None),
            )
            for word_id in result.get("ok_ids", []):
                self.store.mark_synced(int(word_id), None)
            result.pop("ok_ids", None)
            result["ok"] = True
            result["deck"] = deck
            result["model"] = model
            result["count"] = len(words)
            return result
        use_dict2anki = (
            lang == "en"
            and bool(self.config.get("anki_en_dict2anki", True))
            and "Dict2Anki" in (self.anki.model_names() or [])
        )
        if use_dict2anki:
            notes = [self._dict2anki_note(w) for w in words]
            result = self.anki.push_to_model(
                notes,
                deck,
                "Dict2Anki",
                "term",
                skip_existing=bool(self.config.get("anki_skip_existing", True)),
            )
            for word_id in result.get("ok_ids", []):
                self.store.mark_synced(int(word_id), None)
            result.pop("ok_ids", None)
            result["ok"] = True
            result["deck"] = deck
            result["model"] = "Dict2Anki"
            result["count"] = len(words)
            return result
        if lang in ("en", "fr", "la"):
            words = [self._rich_word(w) for w in words]
        result = self.anki.push(
            words,
            deck,
            audio_loader=self._audio_for_word,
            skip_existing=bool(self.config.get("anki_skip_existing", True)),
        )
        for word_id in result.get("ok_ids", []):
            self.store.mark_synced(int(word_id), None)
        result.pop("ok_ids", None)
        result["ok"] = True
        result["deck"] = deck
        result["count"] = len(words)
        return result

    def export_vocab(
        self, lang: str | None = None, wordbook_id: int | None = None
    ) -> dict:
        if wordbook_id:
            book = self.store.wordbook(int(wordbook_id))
            words = self.store.words_in_book(int(wordbook_id), limit=100000) if book else []
            label = (book or {}).get("name") or i18n.wordbook_word()
        else:
            words = self.store.list_words(lang, limit=100000)
            label = lang or "all"
        path = export_tsv(words, self.data_dir / "exports", label)
        return {"ok": True, "path": str(path), "count": len(words)}
