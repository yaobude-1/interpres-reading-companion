"""词典查询、词形变化、发音与词条 HTML。"""

from __future__ import annotations

import logging

from . import audio, fuzzy, lemma
from .service_base import ServiceBase

log = logging.getLogger("rc")

# 词典词头里的音节分隔点/软连字符/下加点：ge·hen、ẹs·sen 与 gehen、essen 是同一个词
_HEADWORD_IGNORED = (
    "·",
    "|",  # 俄语词典用竖线分隔词干/词尾
    "\u00ad",
    "\u200b",
    "\u0323",  # combining dot below（朗氏用它标短音）
    "\u0324",
    "\u0325",
    "\u0329",
    "\u0331",
    "\u0332",  # combining low line（牛津德语标重音）
    "\u0336",
    "\u0338",
)


def _headword_key(text: str) -> str:
    value = str(text or "")
    for char in _HEADWORD_IGNORED:
        value = value.replace(char, "")
    return value.strip()


class DictMixin(ServiceBase):
    def has_dictionaries(self, context: str = "panel") -> bool:
        """有没有配置任何本地词典。"""
        for code in (self.config.data.get("languages") or {}):
            if self.has_dictionary(code, context):
                return True
        return False

    def has_dictionary(self, lang: str, context: str = "panel") -> bool:
        try:
            return bool(lang) and self._dictionary_for(lang, context) is not None
        except Exception:
            return False

    def _dictionary_for(self, lang: str, context: str = "panel"):
        """兼容只接受一个参数的测试替身。"""
        try:
            return self.dicts.dictionary(lang, context)
        except TypeError:
            return self.dicts.dictionary(lang)

    def fuzzy_lookup(
        self,
        word: str,
        lang_hint: str | None = None,
        limit: int = 20,
        context: str = "panel",
    ) -> list[dict]:
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
        results: list[dict] = []
        seen: set[tuple[str, str, str]] = set()
        dictionary_rank: dict[tuple[str, str], int] = {}
        for code in order:
            dictionaries = self.dicts.dictionaries(code, context)
            for dict_index, dictionary in enumerate(dictionaries):
                dict_id = getattr(dictionary, "dict_id", "")
                dictionary_rank[(code, dict_id)] = dict_index
                index = fuzzy.build_index(dictionary)
                if index is None:
                    continue
                found = index.search(text, limit)
                if not found:
                    continue
                for key, level in found:
                    if (code, dict_id, key) in seen:
                        continue
                    seen.add((code, dict_id, key))
                    raw = dictionary._mdx.lookup(key)
                    pos, meaning = gloss.quick_gloss(raw if isinstance(raw, str) else "", code)
                    results.append(
                        {
                            "lang": code,
                            "dict_id": dict_id,
                            "source": dictionary.name,
                            "word": key,
                            "pos": pos,
                            "gloss": meaning,
                            "level": level,
                        }
                    )
        rank = {code: index for index, code in enumerate(order)}
        results.sort(
            key=lambda item: (
                item["level"],
                rank.get(item["lang"], 999),
                dictionary_rank.get((item["lang"], item.get("dict_id") or ""), 999),
                len(item["word"]),
                item["word"].lower(),
            )
        )
        return results[:limit]

    def lookup_all(
        self,
        word: str,
        lang_hint: str | None = None,
        context: str = "panel",
        on_hit=None,
    ) -> list[dict]:
        """在所有可见词典里查这个词，返回 [{lang, source, dict_id, entry}]。

        on_hit 每查完一本词典就回调一次，让界面可以「默认词典先出、其它词典后补」，
        不必等最慢的词典（例如 OED）解析完才显示第一条结果。
        """
        text = lemma.strip_word(word)
        if not text:
            return []

        def emit(hit: dict) -> None:
            if on_hit is None:
                return
            try:
                on_hit(dict(hit))
            except Exception:  # noqa: BLE001 - 回调方失败不能影响查词
                log.debug("on_hit 回调失败")

        order: list[str] = []
        if lang_hint:
            order.append(lang_hint)
        for code in ("en", "fr", "la", "de", "es", "it"):
            if code not in order:
                order.append(code)
        # 用户数据/词典可能挂在任意语言上，不能只查固定几种
        for code in self.config.data.get("languages") or {}:
            if code not in order:
                order.append(code)
        hits: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for code in order:
            dictionaries = self.dicts.dictionaries(code, context)
            if not dictionaries:
                legacy = self._dictionary_for(code, context)
                if legacy is not None:
                    dictionaries = [legacy]
            default_id = self.dicts.default_id(code)
            user_lemma = None
            user_data = getattr(self, "user_lang", None)
            if user_data is not None:
                try:
                    user_lemma = user_data.form_lemma(code, text)
                except Exception:  # noqa: BLE001 - 用户数据损坏时继续正常查词
                    user_lemma = None
                if user_lemma and user_lemma.casefold() != text.casefold():
                    user_entry = self._user_entry(code, user_lemma, text)
                    user_entry["is_default"] = bool(
                        default_id and user_entry.get("dict_id") == default_id
                    )
                    hits.append(
                        {
                            "lang": code,
                            "source": "用户数据",
                            "dict_id": user_entry.get("dict_id", ""),
                            "entry": user_entry,
                        }
                    )
                    emit(hits[-1])
            for dictionary in dictionaries:
                entry = None
                matched_candidate = text
                entry = self._lookup_full_for(code, dictionary, text)
                if entry:
                    entry["matched"] = text
                if entry is None:
                    # 去重音精确：creer → créer。不猜语言，所有词典都试一遍。
                    try:
                        index = fuzzy.build_index(dictionary)
                    except Exception:  # noqa: BLE001 - 索引构建失败时跳过
                        index = None
                    for key in index.exact_matches(text) if index is not None else []:
                        if key.casefold() == text.casefold():
                            continue
                        entry = self._lookup_full_for(code, dictionary, key)
                        if entry:
                            entry["matched"] = key
                            matched_candidate = key
                            break
                if entry is None:
                    for candidate in lemma.candidates(text, code):
                        entry = self._lookup_full_for(code, dictionary, candidate)
                        if entry:
                            entry["matched"] = candidate
                            matched_candidate = candidate
                            break
                if entry is None:
                    analysis = self.morph_analysis(text, code)
                    if analysis:
                        entry = self._lookup_full_for(code, dictionary, analysis["lemma"])
                        if entry:
                            entry["matched"] = analysis["lemma"]
                            entry["morph"] = analysis
                if not entry:
                    continue
                self._annotate_redirect(entry, text, code)
                entry["match"] = self._match_kind(entry, text, matched_candidate)
                # 英语：即使原词本身有条目，也把可能的原形列出来让用户选
                if code == "en" and (entry.get("matched") or "").lower() == text.lower():
                    suggestions: list[str] = []
                    for cand in lemma.candidates(text, "en"):
                        cand = cand.lower()
                        if cand == text.lower() or cand in suggestions:
                            continue
                        if self._lookup_full_for(code, dictionary, cand):
                            suggestions.append(cand)
                    if suggestions:
                        entry["lemma_suggestions"] = suggestions[:4]
                matched = entry.get("matched") or ""
                if entry.get("redirect"):
                    # 词典把查询词重定向到另一个词条；不要生成变形表
                    pass
                elif matched and matched.lower() != text.lower():
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
                # 用户变位表：查原形时也把用户表挂上去（优先于内置表）
                user_morph = self._user_table_morph(code, entry.get("word") or "", text)
                if user_morph and not entry.get("redirect"):
                    entry["morph"] = user_morph
                    entry["user_table"] = True
                entry["query"] = text
                entry["lang"] = code
                entry["dict_id"] = getattr(dictionary, "dict_id", "")
                entry["is_default"] = bool(default_id and entry["dict_id"] == default_id)
                key = (code, entry["dict_id"] or entry.get("source") or "")
                if key in seen:
                    continue
                seen.add(key)
                hits.append(
                    {
                        "lang": code,
                        "source": entry.get("source") or "",
                        "dict_id": entry["dict_id"],
                        "entry": entry,
                    }
                )
                emit(hits[-1])
        # 按匹配质量排序：精确 → 去重音精确 → 词形还原 → 重定向。
        # 同质量时按语言顺序、词典顺序、来源名排序。
        match_rank = {"user": 0, "exact": 1, "accent": 2, "lemma": 3, "redirect": 4}
        language_rank = {code: index for index, code in enumerate(order)}
        dictionary_rank: dict[tuple[str, str], int] = {}
        for code in order:
            for index, dictionary in enumerate(self.dicts.dictionaries(code, context)):
                dictionary_rank[(code, getattr(dictionary, "dict_id", ""))] = index
        hits.sort(
            key=lambda hit: (
                match_rank.get((hit["entry"].get("match") or ""), 5),
                language_rank.get(hit.get("lang") or "", 999),
                dictionary_rank.get(
                    (hit.get("lang") or "", hit.get("dict_id") or ""), 999
                ),
                hit.get("source") or "",
            )
        )
        return hits

    def _lookup_full_for(self, code: str, dictionary, word: str) -> dict | None:
        """兼容旧测试替身：真实词典走单本接口，无 dict_id 时走旧接口。"""
        if getattr(dictionary, "dict_id", ""):
            return self.dicts.lookup_full_with(dictionary, word)
        return self.dicts.lookup_full(code, word)

    @staticmethod
    def _match_kind(entry: dict, query: str, candidate: str) -> str:
        if entry.get("redirect"):
            return "redirect"
        head = str(entry.get("word") or "")
        if _headword_key(head) == _headword_key(query):
            return "exact"
        if head and fuzzy.normalize(_headword_key(head)) == fuzzy.normalize(_headword_key(query)):
            return "accent"
        return "lemma"

    def _user_table_morph(self, lang: str, lemma: str, form: str = "") -> dict | None:
        """用户提供的变位表；命中时优先于内置表。"""
        user_data = getattr(self, "user_lang", None)
        if user_data is None:
            return None
        try:
            groups = user_data.table(lang, lemma)
        except Exception:  # noqa: BLE001 - 用户数据损坏时不影响正常查词
            groups = None
        if not groups:
            return None
        return {
            "lemma": lemma,
            "label": "用户提供",
            "tables": groups,
            "form": form or lemma,
            "user": True,
        }

    def _user_entry(self, lang: str, lemma: str, form: str) -> dict:
        """用户词形命中的词条：有词典释义就用词典，没有也保留词形/变位表。"""
        entry = self.dicts.lookup_full(lang, lemma)
        if entry is None:
            entry = {
                "word": lemma,
                "lang": lang,
                "source": "用户数据",
                "phonetic": "",
                "senses": [],
            }
        else:
            entry = dict(entry)
        original_source = entry.get("source") or ""
        entry["source"] = "用户数据"
        if original_source and original_source != "用户数据":
            entry["user_dict_source"] = original_source
        entry["matched"] = lemma
        entry["match"] = "user"
        entry["user_form"] = form
        morph = self._user_table_morph(lang, lemma, form)
        if morph:
            entry["morph"] = morph
            entry["user_table"] = True
        return entry

    def _annotate_redirect(self, entry: dict, query: str, code: str) -> str:
        """标记 MDX @@@LINK 重定向：屈折词返回 inflection，词义重定向返回 lexical。"""
        headword = str(entry.get("word") or "").strip()
        if (
            not headword
            or _headword_key(headword) == _headword_key(query)
            # 只差重音（creer / créer）是同一个词，不是重定向
            or fuzzy.normalize(_headword_key(headword)) == fuzzy.normalize(_headword_key(query))
        ):
            return ""
        # 变位/变格反查出来的原形（vends → vendre）是屈折，不是词义重定向
        morph_lemma = str((entry.get("morph") or {}).get("lemma") or "").strip()
        if morph_lemma and morph_lemma.casefold() == headword.casefold():
            entry["matched"] = headword
            return "inflection"
        forms = {c.casefold() for c in lemma.candidates(query, code)}
        if headword.casefold() in forms:
            entry["matched"] = headword
            if not entry.get("morph"):
                analysis = self.morph_analysis(query, code)
                if analysis:
                    entry["morph"] = analysis
                else:
                    table = self.conjugation_table(query, code)
                    if table:
                        entry["morph"] = table
            return "inflection"
        entry["redirect"] = headword
        return "lexical"

    def conjugation_table(self, word: str, lang: str) -> dict | None:
        """原形词条的变位/变格表（查原形时也能看「时态」页签）。"""
        text = (word or "").strip().lower()
        if not text or not lang:
            return None
        user_data = getattr(self, "user_lang", None)
        if user_data is not None:
            try:
                groups = user_data.table(lang, text)
            except Exception:  # noqa: BLE001 - 用户数据损坏时回退内置表
                groups = None
            if groups:
                return {
                    "lemma": text,
                    "label": "用户提供",
                    "tables": groups,
                    "form": text,
                    "user": True,
                }
        try:
            if lang == "fr":
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
        user_data = getattr(self, "user_lang", None)
        if user_data is not None:
            try:
                user_lemma = user_data.form_lemma(lang, text)
            except Exception:  # noqa: BLE001 - 用户数据损坏时回退内置规则
                user_lemma = None
            if user_lemma and user_lemma.casefold() != text.casefold():
                return {
                    "lemma": user_lemma,
                    "label": "用户词形",
                    "tables": user_data.table(lang, user_lemma) or [],
                    "form": text,
                    "user": True,
                }
        dictionary = self.dicts.dictionary(lang)
        if dictionary is None:
            return None
        try:
            if lang == "fr":
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
                    kind = self._annotate_redirect(entry, word, code)
                    if kind != "lexical":
                        if (entry.get("matched") or "").lower() != word.lower():
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

    def dict_audio(self, lang: str, key: str, dict_id: str = "") -> bytes | None:
        """取词典里的音频字节（给原版页面按需播放用）。"""
        if not key:
            return None
        if dict_id:
            try:
                return self.dicts.audio_by_id(dict_id, key)
            except Exception:
                return None
        if not lang:
            return None
        try:
            return self.dicts.audio(lang, key)
        except Exception:
            return None

    def play_dictionary_audio(self, lang: str, sound_key: str, dict_id: str = "") -> bool:
        """播放词典里的音频（MP3/WAV），成功返回 True。"""
        data = (
            self.dicts.audio_by_id(dict_id, sound_key)
            if dict_id
            else self.dicts.audio(lang, sound_key)
        )
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
            dictionary = self.dicts.anki_dictionary(lang)
            if dictionary is None:
                continue
            entry = self.dicts.lookup_with(dictionary, word)
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
            dict_id = str(word.get("dict_id") or "").strip()
            if not dict_id:
                dictionary = self.dicts.anki_dictionary(lang)
                dict_id = str(getattr(dictionary, "dict_id", "") or "")
            data = (
                self.dicts.audio_by_id(dict_id, key)
                if dict_id
                else self.dicts.audio(lang, key)
            )
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
