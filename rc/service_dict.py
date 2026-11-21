"""词典查询、词形变化、发音与词条 HTML。"""

from __future__ import annotations

import logging

from . import audio, lemma

log = logging.getLogger("rc")


class DictMixin:
    def has_dictionaries(self) -> bool:
        """有没有配置任何本地词典。"""
        for code in (self.config.data.get("languages") or {}):
            if self.has_dictionary(code):
                return True
        return False

    def has_dictionary(self, lang: str) -> bool:
        try:
            return bool(lang) and self.dicts.dictionary(lang) is not None
        except Exception:
            return False

    def fuzzy_lookup(self, word: str, lang_hint: str | None = None, limit: int = 20) -> list[dict]:
        """相近词搜索：前缀 + 重音归一 + 编辑距离，返回 [{lang, word, pos, gloss, level}]。"""
        from . import fuzzy, gloss

        text = (word or "").strip()
        if not text:
            return []
        order: list[str] = []
        if lang_hint:
            order.append(lang_hint)
        for code in (self.config.data.get("languages") or {}):
            if code and code not in order:
                order.append(code)
        for code in ("en", "fr", "la", "de", "es", "it"):
            if code not in order:
                order.append(code)
        for code in order:
            dictionary = self.dicts.dictionary(code)
            if dictionary is None:
                continue
            index = fuzzy.build_index(dictionary)
            if index is None:
                continue
            found = index.search(text, limit)
            if not found:
                continue
            results: list[dict] = []
            for key, level in found:
                raw = dictionary._mdx.lookup(key)
                pos, meaning = gloss.quick_gloss(raw if isinstance(raw, str) else "", code)
                results.append(
                    {"lang": code, "word": key, "pos": pos, "gloss": meaning, "level": level}
                )
            return results
        return []

    def lookup_all(self, word: str, lang_hint: str | None = None) -> list[dict]:
        """在所有词典里查这个词，返回 [{lang, source, entry}]（语言提示排最前）。"""
        text = lemma.strip_word(word)
        if not text:
            return []
        order: list[str] = []
        if lang_hint:
            order.append(lang_hint)
        for code in ("en", "fr", "la", "de", "es", "it"):
            if code not in order:
                order.append(code)
        hits: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for code in order:
            dictionary = self.dicts.dictionary(code)
            if dictionary is None:
                continue
            entry = None
            for candidate in [text] + lemma.candidates(text, code):
                entry = self.dicts.lookup_full(code, candidate)
                if entry:
                    entry["matched"] = candidate
                    break
            if entry is None:
                analysis = self.morph_analysis(text, code)
                if analysis:
                    entry = self.dicts.lookup_full(code, analysis["lemma"])
                    if entry:
                        entry["matched"] = analysis["lemma"]
                        entry["morph"] = analysis
            if not entry:
                continue
            # 英语：即使原词本身有条目，也把可能的原形列出来让用户选
            if code == "en" and (entry.get("matched") or "").lower() == text.lower():
                suggestions: list[str] = []
                for cand in lemma.candidates(text, "en"):
                    cand = cand.lower()
                    if cand == text.lower() or cand in suggestions:
                        continue
                    if self.dicts.lookup_full(code, cand):
                        suggestions.append(cand)
                if suggestions:
                    entry["lemma_suggestions"] = suggestions[:4]
            matched = entry.get("matched") or ""
            if matched and matched.lower() != text.lower():
                # 靠词形还原命中的原形：补上「这是哪个变形」的说明和整表
                analysis = self.morph_analysis(text, code)
                if analysis:
                    entry["morph"] = analysis
            else:
                table = self.conjugation_table(text, code)
                if table:
                    entry["morph"] = table
                else:
                    analysis = self.morph_analysis(text, code)
                    if analysis:
                        entry["morph"] = analysis
            entry["query"] = text
            entry["lang"] = code
            key = (code, entry.get("source") or "")
            if key in seen:
                continue
            seen.add(key)
            hits.append({"lang": code, "source": entry.get("source") or "", "entry": entry})
        # 词头精确命中的语言排前面：Longman 的 "fait" 会命中 "fait accompli"，
        # 而法语词典里 "fait" 才是真正的词头。之后再按语言顺序、来源名排序。
        query_key = text.lower()
        language_rank = {code: index for index, code in enumerate(order)}
        hits.sort(
            key=lambda hit: (
                (hit["entry"].get("word") or "").strip().lower() != query_key,
                language_rank.get(hit.get("lang") or "", 999),
                hit.get("source") or "",
            )
        )
        return hits

    def conjugation_table(self, word: str, lang: str) -> dict | None:
        """原形词条的变位/变格表（查原形时也能看「时态」页签）。"""
        text = (word or "").strip().lower()
        if not text or not lang:
            return None
        try:
            if lang in ("fr", "de", "es", "it"):
                from . import conjug_fr

                tables = conjug_fr.table(text)
                if tables:
                    return {"lemma": text, "label": "原形", "tables": tables, "form": text}
            elif lang == "la":
                from . import conjug_la

                dictionary = self.dicts.dictionary(lang)
                lookup = dictionary._mdx.lookup if dictionary is not None else (lambda _w: None)
                tables = conjug_la.table(text, lookup)
                if tables:
                    return {"lemma": text, "label": "原形", "tables": tables, "form": text}
        except Exception:
            log.exception("生成变位表失败：%s", text)
        return None

    def _latin_keys(self, prefix: str, limit: int = 120) -> list[str]:
        """按前缀找拉丁词条（用缓存的排序索引，MDX 自带顺序不可靠）。"""
        import bisect

        index = getattr(self, "_la_index", None)
        if index is None:
            dictionary = self.dicts.dictionary("la")
            if dictionary is None:
                return []
            keys = [key for key, _offset in dictionary._mdx._keys]
            self._la_names = {key.lower(): key for key in keys}
            self._la_index = sorted(self._la_names)
            index = self._la_index
        prefix = (prefix or "").lower()
        start = bisect.bisect_left(index, prefix)
        out = []
        for key in index[start : start + limit]:
            if not key.startswith(prefix):
                break
            out.append(self._la_names[key])
        return out

    def morph_analysis(self, word: str, lang: str) -> dict | None:
        """分析变位/变格形式：返回 {lemma, label, tables, form}。"""
        text = (word or "").strip().lower()
        if not text or not lang:
            return None
        dictionary = self.dicts.dictionary(lang)
        if dictionary is None:
            return None
        try:
            if lang in ("fr", "de", "es", "it"):
                from . import conjug_fr

                hit = conjug_fr.analyse(text, lambda w: bool(dictionary.lookup(w)))
                if hit:
                    lemma, label = hit
                    return {"lemma": lemma, "label": label, "tables": conjug_fr.table(lemma), "form": text}
            elif lang == "la":
                from . import conjug_la

                hit = conjug_la.analyse(text, lambda w: dictionary._mdx.lookup(w), keys=self._latin_keys)
                if hit:
                    lemma, label, tables = hit
                    return {"lemma": lemma, "label": label, "tables": tables, "form": text}
        except Exception:
            log.exception("变位分析失败：%s", text)
        return None

    def lookup_word(self, text: str, lang: str | None = None) -> dict | None:
        """本地词典查词（不调用模型）：先查原形，再按词形还原规则试。"""
        word = lemma.strip_word(text)
        if not word or len(word) > 40:
            return None
        langs: list[str] = []
        if lang:
            langs.append(lang)
            # 指定语言是法语/拉丁语时，先做变位/变格分析（变形词往往没有词条）
            analysis = self.morph_analysis(word, lang)
            if analysis:
                entry = self.dicts.lookup_full(lang, analysis["lemma"])
                if entry:
                    entry["query"] = word
                    entry["matched"] = analysis["lemma"]
                    entry["lang"] = lang
                    entry["morph"] = analysis
                    return entry
        for code in ("en", "fr", "la", "de", "es"):
            if code not in langs:
                langs.append(code)
        for code in langs:
            for candidate in [word] + lemma.candidates(word, code):
                entry = self.dicts.lookup_full(code, candidate)
                if entry:
                    entry["query"] = word
                    entry["matched"] = candidate
                    entry["lang"] = code
                    if candidate.lower() != word.lower():
                        analysis = self.morph_analysis(word, code)
                        if analysis:
                            entry["morph"] = analysis
                    else:
                        table = self.conjugation_table(word, code)
                        if table:
                            entry["morph"] = table
                        else:
                            analysis = self.morph_analysis(word, code)
                            if analysis:
                                entry["morph"] = analysis
                    return entry
        # 查不到词条时，试着分析变位/变格，给出原形词条
        for code in langs:
            analysis = self.morph_analysis(word, code)
            if not analysis:
                continue
            entry = self.dicts.lookup_full(code, analysis["lemma"])
            if not entry:
                continue
            entry["query"] = word
            entry["matched"] = analysis["lemma"]
            entry["lang"] = code
            entry["morph"] = analysis
            return entry
        return None

    def lookup_audio(self, lang: str, sound_key: str) -> bytes | None:
        return self.dicts.audio(lang, sound_key)

    def entry_html(self, word: str, lang: str) -> str:
        """词典原版条目的自包含 HTML（含 CSS/图片）。"""
        from . import entryhtml

        dictionary = self.dicts.dictionary(lang)
        if dictionary is None:
            return ""
        data = getattr(self.config, "data", {}) or {}
        try:
            from urllib.parse import quote

            port = int(data.get("server_port") or 18777)
            token = str(data.get("server_token") or "")
            base = f"http://127.0.0.1:{port}/api/dict-audio?lang={quote(lang)}&key="
            if token:
                base += "{key}&token=" + quote(token)
            else:
                base += "{key}"
            return entryhtml.build_entry_html(
                dictionary,
                word,
                colors=data.get("entry_colors") or None,
                font_size=int(data.get("entry_font_size") or 15),
                custom_css=str(data.get("entry_custom_css") or ""),
            )
        except Exception:
            log.exception("生成条目 HTML 失败")
            return ""

    def dict_audio(self, lang: str, key: str) -> bytes | None:
        """取词典里的音频字节（给原版页面按需播放用）。"""
        if not lang or not key:
            return None
        try:
            return self.dicts.audio(lang, key)
        except Exception:
            return None

    def play_dictionary_audio(self, lang: str, sound_key: str) -> bool:
        """播放词典里的音频（MP3/WAV），成功返回 True。"""
        data = self.dicts.audio(lang, sound_key)
        return audio.play_bytes(data)

    def _attach_dictionary(self, result: dict) -> None:
        """给模型挑出的每个词补上本地词典的释义/例句/音标。"""
        if not self.config.get("use_dictionary", True):
            return
        lang = result.get("source_lang") or ""
        if not lang:
            return
        for term in result.get("terms") or []:
            word = term.get("lemma") or term.get("word") or ""
            entry = self.dicts.lookup(lang, word)
            if not entry:
                continue
            term["dict"] = entry
            if not term.get("reading"):
                term["reading"] = entry.get("phonetic", "")
            if not term.get("pos"):
                term["pos"] = entry.get("pos", "")

    def _audio_for_word(self, word: dict):
        """给 Anki 推发音：优先词典真人音频，没有就用系统 TTS 生成。"""
        import re

        lang = word.get("lang") or ""
        text = word.get("word") or word.get("lemma") or ""
        safe = re.sub(r"[^0-9A-Za-z_-]+", "_", text or "word")[:40] or "word"

        key = word.get("audio_key") or ""
        if key and lang:
            data = self.dicts.audio(lang, key)
            if data and len(data) > 200:
                return f"rc_{lang}_{safe}.mp3", data

        if not text:
            return None
        try:
            path = self.tts.synthesize(text, lang or "en")
            data = path.read_bytes()
        except Exception:
            return None
        if len(data) < 1000:
            return None
        return f"rc_{lang}_{safe}.wav", data
