"""业务编排：翻译、生词、术语、Anki、发音。

浮窗界面和本地 HTTP 服务都调用这一层，保证行为一致。
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
from pathlib import Path

from . import audio, lemma, textutil
from .anki import Anki, export_tsv
from .config import Config
from .dictmanager import DictionaryManager
from .llm import LLMError, Translator, _lang_name
from .store import Store
from .tts import TTS

log = logging.getLogger("rc")

# 同一个词在不同书里出现时，context 会影响结果，所以 key 里带上上下文摘要
CACHE_VERSION = "v2"
CHUNK_CHARS = 1200
CHAT_PERSONA_DEFAULT = (
    "你是一位阅读伙伴，正在陪用户精读一本书，回答要具体、贴近原文。\n书名：{book}"
)
CHAT_RULES_DEFAULT = (
    "回答要求：\n"
    "1. 用中文，结合原文说，必要时引用原句；\n"
    "2. 不要编造书里没写的内容，不确定就直接说不确定；\n"
    "3. 回答简洁，别写成论文。"
)
TRANSLATE_WORKERS = 4  # 超过这个长度就分段翻译，避免超出模型输出上限

_SENTENCE_END = ".!?。！？…\"'”’"
_SENTENCE_START = "“\"'（《「¡¿"


def _ends_sentence(text: str, idx: int | None = None) -> bool:
    """idx 之前的最后一个非空字符是不是句末标点（idx 省略则看结尾）。"""
    i = (len(text) if idx is None else idx) - 1
    while i >= 0 and text[i] in " \t\r\n":
        i -= 1
    return i < 0 or text[i] in _SENTENCE_END


def _starts_sentence(text: str, idx: int = 0) -> bool:
    i = idx
    while i < len(text) and text[i] in " \t\r\n":
        i += 1
    if i >= len(text):
        return True
    ch = text[i]
    return ch.isupper() or ch in _SENTENCE_START


def _tsv(value: str) -> str:
    return (value or "").replace("\t", " ").replace("\r", " ").replace("\n", " ")


def split_chunks(text: str, limit: int = CHUNK_CHARS) -> list[str]:
    """按段落把长文本切成不超过 limit 的块；超长段落再按句子切。"""
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    current = ""
    for para in text.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        if len(para) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split_long_paragraph(para, limit))
            continue
        candidate = f"{current}\n\n{para}" if current else para
        if current and len(candidate) > limit:
            chunks.append(current)
            current = para
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks or [text]


def _split_long_paragraph(paragraph: str, limit: int) -> list[str]:
    parts = re.split(r"(?<=[。！？!?；;])\s*", paragraph)
    out: list[str] = []
    current = ""
    for part in parts:
        if current and len(current) + len(part) > limit:
            out.append(current)
            current = part
        else:
            current += part
    if current:
        out.append(current)
    final: list[str] = []
    for chunk in out:
        while len(chunk) > limit:
            final.append(chunk[:limit])
            chunk = chunk[limit:]
        if chunk:
            final.append(chunk)
    return final


def _english_mode() -> bool:
    try:
        from . import i18n

        return i18n.LANGUAGE == "en"
    except Exception:
        return False


class Service:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.data_dir = config.data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.store = Store(self.data_dir / "reading.db")
        self.translator = Translator(config)
        self.tts = TTS(config, self.data_dir / "cache" / "tts")
        self.anki = Anki()
        self.dicts = DictionaryManager(config)
        self._context_lock = threading.Lock()
        # 每个窗口最近一次选中内容，用于给短查询补上下文
        self._recent: dict[str, dict] = {}

    # ------------------------------------------------------------------ 上下文
    def remember(self, window: str, text: str) -> None:
        with self._context_lock:
            self._recent[window] = {"text": text, "ts": time.time()}

    def recent_context(self, window: str, max_chars: int) -> tuple[str, str]:
        """返回 (上文, 下文)。上文来自这个窗口上一次较长的选中。"""
        with self._context_lock:
            item = self._recent.get(window)
        if not item:
            return "", ""
        text = item["text"]
        if len(text) < 40:
            return "", ""
        limit = int(max_chars)
        before = text[-limit:] if len(text) > limit else text
        return before, ""

    # -------------------------------------------------------------------- 翻译
    def translate(
        self,
        text: str,
        *,
        book: str = "",
        src_lang: str | None = None,
        context_before: str = "",
        context_after: str = "",
        use_cache: bool = True,
        on_progress=None,
        on_partial=None,
    ) -> dict:
        clean = textutil.normalize(text)
        if not clean:
            raise ValueError("没有读到文字")

        target = "en" if _english_mode() else self.config.data.get("target_lang", "zh-CN")
        glossary = self.store.glossary_terms(book) if book else []

        # 增量：新段只是旧段的前缀/后缀延伸时，只翻新增的句子
        reuse = None
        if use_cache and not textutil.looks_like_word(clean):
            reuse = self._reuse_record(clean, book)
        if reuse is not None:
            return self._translate_incremental(reuse, clean, book, target, glossary, use_cache)

        chunks = split_chunks(clean)
        total = len(chunks)

        results: list[dict | None] = [None] * total
        if total == 1:
            if on_progress is not None:
                try:
                    on_progress(1, 1)
                except Exception:
                    pass
            if on_partial is not None and hasattr(self.translator, "translate_stream"):
                results[0] = self._translate_chunk_stream(
                    chunks[0],
                    book=book,
                    src_lang=src_lang,
                    context_before=context_before,
                    context_after=context_after,
                    target=target,
                    glossary=glossary,
                    use_cache=use_cache,
                    on_partial=on_partial,
                )
            else:
                results[0] = self._translate_chunk(
                    chunks[0],
                    book=book,
                    src_lang=src_lang,
                    context_before=context_before,
                    context_after=context_after,
                    target=target,
                    glossary=glossary,
                    use_cache=use_cache,
                )
        else:
            from concurrent.futures import ThreadPoolExecutor, as_completed

            done = 0
            # 同一个块可能因表格/重复段落出现多次；只翻一次，再按原位置复用结果
            unique: dict[tuple[str, str, str], list[int]] = {}
            for index, chunk in enumerate(chunks):
                context_key = (
                    chunk,
                    context_before if index == 0 else "",
                    context_after if index == total - 1 else "",
                )
                unique.setdefault(context_key, []).append(index)
            with ThreadPoolExecutor(max_workers=TRANSLATE_WORKERS) as pool:
                futures = {}
                for (chunk, ctx_before, ctx_after), indexes in unique.items():
                    future = pool.submit(
                        self._translate_chunk,
                        chunk,
                        book=book,
                        src_lang=src_lang,
                        context_before=ctx_before,
                        context_after=ctx_after,
                        target=target,
                        glossary=glossary,
                        use_cache=use_cache,
                    )
                    futures[future] = indexes
                try:
                    for future in as_completed(futures):
                        result = future.result()
                        indexes = futures[future]
                        for index in indexes:
                            results[index] = result
                            done += 1
                            if on_progress is not None:
                                try:
                                    on_progress(done, total)
                                except Exception:
                                    pass
                        if on_partial is not None:
                            joined = "\n\n".join(
                                str(item.get("translation") or "")
                                for item in results
                                if item
                            )
                            try:
                                on_partial(joined)
                            except Exception:
                                pass
                except Exception:
                    for future in futures:
                        future.cancel()
                    raise
        results = [item for item in results if item]

        payload = results[0] if total == 1 else self._merge_results(results, clean, book, target)
        if total > 1:
            payload["meta"]["chunks"] = total
        if book:
            self.store.touch_book(book, payload.get("source_lang") or "")
        self.store.add_history(
            clean, book, payload.get("source_lang") or "",
            keep=int(self.config.get("history_keep", 30)),
        )
        self._save_translation(book, clean, payload)
        return payload

    def _save_translation(self, book: str, text: str, payload: dict) -> None:
        """存进翻译记录；单词不存。"""
        if textutil.looks_like_word(text) or len(text) < 12:
            return
        try:
            self.store.save_translation(book, payload.get("source_lang") or "", text, payload)
        except Exception:  # noqa: BLE001
            log.exception("保存翻译记录失败")

    def _reuse_record(self, clean: str, book: str):
        """找一条能复用的旧记录：新文本 = 旧文本 + 新句子，或 新句子 + 旧文本。"""
        if not book:
            return None
        for row in self.store.translations_for_book(book):
            old = (row.get("text") or "").strip()
            if len(old) < 30 or len(old) >= len(clean):
                continue
            if clean.startswith(old) and _starts_sentence(clean, len(old)) and _ends_sentence(old):
                return row, "", clean[len(old):].strip()
            if clean.endswith(old) and _ends_sentence(clean, len(clean) - len(old)) and _starts_sentence(old):
                return row, clean[: len(clean) - len(old)].strip(), ""
        return None

    def _translate_incremental(
        self, reuse, clean: str, book: str, target: str, glossary, use_cache: bool
    ) -> dict:
        row, before, after = reuse
        old_payload = json.loads(row.get("payload") or "{}")
        pieces: list[str] = []
        terms: list[dict] = []
        seen: set[str] = set()
        elapsed = 0
        all_cached = True

        if before:
            result = self._translate_chunk(
                before, book=book, src_lang=None, context_before="",
                context_after=row.get("text", ""), target=target, glossary=glossary,
                use_cache=use_cache,
            )
            pieces.append(result.get("translation", ""))
            elapsed += result.get("meta", {}).get("elapsed_ms", 0)
            all_cached = all_cached and result.get("meta", {}).get("cached", False)
            terms.extend(result.get("terms") or [])

        pieces.append(old_payload.get("translation", ""))
        terms.extend(old_payload.get("terms") or [])

        if after:
            result = self._translate_chunk(
                after, book=book, src_lang=None, context_before=row.get("text", ""),
                context_after="", target=target, glossary=glossary, use_cache=use_cache,
            )
            pieces.append(result.get("translation", ""))
            elapsed += result.get("meta", {}).get("elapsed_ms", 0)
            all_cached = all_cached and result.get("meta", {}).get("cached", False)
            terms.extend(result.get("terms") or [])

        merged_terms: list[dict] = []
        for term in terms:
            key = (term.get("lemma") or term.get("word") or "").lower()
            if key and key not in seen:
                seen.add(key)
                merged_terms.append(term)

        payload = {
            "source_lang": old_payload.get("source_lang") or row.get("lang") or "",
            "translation": "\n\n".join(p for p in pieces if p),
            "terms": merged_terms[:10],
            "grammar": None,
            "glossary_hits": old_payload.get("glossary_hits") or [],
            "text": clean,
            "book": book,
            "target": target,
            "meta": {
                "cached": all_cached,
                "elapsed_ms": elapsed,
                "model": self.config.api.get("model", ""),
                "incremental": True,
                "reused_chars": len(row.get("text", "")),
            },
        }
        self.store.add_history(
            clean, book, payload["source_lang"], keep=int(self.config.get("history_keep", 30))
        )
        self._save_translation(book, clean, payload)
        return payload

    def _translate_chunk(
        self,
        clean: str,
        *,
        book: str,
        src_lang: str | None,
        context_before: str,
        context_after: str,
        target: str,
        glossary: list[tuple[str, str]],
        use_cache: bool,
    ) -> dict:
        key = self._cache_key(clean, book, src_lang, target, context_before, context_after, glossary)
        if use_cache:
            cached = self.store.cache_get(key)
            if cached:
                cached["meta"] = {**cached.get("meta", {}), "cached": True, "elapsed_ms": 0}
                self._register_lang(cached.get("source_lang") or src_lang)
                return cached

        started = time.time()
        result = self.translator.translate(
            clean,
            target=target,
            book=book,
            src_lang=src_lang,
            context_before=context_before,
            context_after=context_after,
            glossary=glossary,
        )
        elapsed = int((time.time() - started) * 1000)
        result["source_lang"] = result.get("source_lang") or src_lang or ""
        self._register_lang(result["source_lang"])
        self._attach_dictionary(result)

        payload = {
            **result,
            "text": clean,
            "book": book,
            "target": target,
            "meta": {
                "cached": False,
                "elapsed_ms": elapsed,
                "model": self.config.api.get("model", ""),
                "glossary_used": [f"{s}→{d}" for s, d in glossary],
            },
        }
        if use_cache:
            self.store.cache_put(key, payload)
        return payload

    def _translate_chunk_stream(
        self,
        clean: str,
        *,
        book: str,
        src_lang: str | None,
        context_before: str,
        context_after: str,
        target: str,
        glossary: list[tuple[str, str]],
        use_cache: bool,
        on_partial=None,
    ) -> dict:
        key = self._cache_key(clean, book, src_lang, target, context_before, context_after, glossary)
        if use_cache:
            cached = self.store.cache_get(key)
            if cached:
                cached["meta"] = {**cached.get("meta", {}), "cached": True, "elapsed_ms": 0}
                self._register_lang(cached.get("source_lang") or src_lang)
                if on_partial is not None:
                    try:
                        on_partial(str(cached.get("translation") or ""))
                    except Exception:
                        pass
                return cached

        started = time.time()
        result = self.translator.translate_stream(
            clean,
            on_partial=on_partial,
            target=target,
            book=book,
            src_lang=src_lang,
            context_before=context_before,
            context_after=context_after,
            glossary=glossary,
        )
        elapsed = int((time.time() - started) * 1000)
        result["source_lang"] = result.get("source_lang") or src_lang or ""
        self._register_lang(result["source_lang"])
        self._attach_dictionary(result)
        payload = {
            **result,
            "text": clean,
            "book": book,
            "target": target,
            "meta": {
                "cached": False,
                "elapsed_ms": elapsed,
                "model": self.config.api.get("model", ""),
                "glossary_used": [f"{s}→{d}" for s, d in glossary],
            },
        }
        if use_cache:
            self.store.cache_put(key, payload)
        return payload

    def _merge_results(self, results: list[dict], clean: str, book: str, target: str) -> dict:
        translations = [r.get("translation", "") for r in results if r.get("translation")]
        terms: list[dict] = []
        seen: set[str] = set()
        for result in results:
            for term in result.get("terms") or []:
                key = (term.get("lemma") or term.get("word") or "").lower()
                if not key or key in seen:
                    continue
                seen.add(key)
                terms.append(term)
        grammars = [r["grammar"] for r in results if r.get("grammar")]
        hits: list[dict] = []
        for result in results:
            hits.extend(result.get("glossary_hits") or [])
        return {
            "source_lang": results[0].get("source_lang", ""),
            "translation": "\n\n".join(translations),
            "terms": terms[:10],
            "grammar": "\n".join(grammars) or None,
            "glossary_hits": hits,
            "text": clean,
            "book": book,
            "target": target,
            "meta": {
                "cached": all(r.get("meta", {}).get("cached") for r in results),
                "elapsed_ms": sum(r.get("meta", {}).get("elapsed_ms", 0) for r in results),
                "model": self.config.api.get("model", ""),
                "glossary_used": [],
            },
        }

    def _cache_key(
        self,
        text: str,
        book: str,
        src_lang: str | None,
        target: str,
        before: str,
        after: str,
        glossary: list[tuple[str, str]] | None = None,
    ) -> str:
        raw = json.dumps(
            [
                CACHE_VERSION,
                text,
                book,
                src_lang,
                target,
                before[-400:],
                after[:400],
                self.config.api.get("model", ""),
                self.config.get("prompt_translate_system", ""),
                sorted(glossary or []),
            ],
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _register_lang(self, code: str | None) -> None:
        if code:
            self.config.ensure_language(code)

    # ---------------------------------------------------------------- 查词
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

    # -------------------------------------------------------------------- 生词
    def add_vocab(
        self,
        *,
        lang: str,
        word: str,
        lemma: str,
        reading: str = "",
        pos: str = "",
        meaning: str = "",
        sentence: str = "",
        book: str = "",
        difficulty: str = "",
        dict_source: str = "",
        dict_meaning: str = "",
        dict_example: str = "",
        dict_example_cn: str = "",
        audio_key: str = "",
    ) -> dict:
        lang = (lang or "??").lower()
        word_id = self.store.add_word(
            {
                "lang": lang,
                "word": word,
                "lemma": lemma or word,
                "reading": reading,
                "pos": pos,
                "meaning": meaning,
                "sentence": sentence,
                "book": book,
                "difficulty": difficulty,
                "dict_source": dict_source,
                "dict_meaning": dict_meaning,
                "dict_example": dict_example,
                "dict_example_cn": dict_example_cn,
                "audio_key": audio_key,
                "book_name": f"{self.lang_label(lang)}词本",
            }
        )
        return {"id": word_id, "total": self.store.word_count(lang), "lang": lang}

    # ------------------------------------------------------------------ 语言
    def languages(self) -> dict[str, dict]:
        return dict(self.config.data.get("languages") or {})

    def language_size(self, code: str) -> tuple[int, int]:
        """返回 (生词数, 书籍数)。"""
        words = int(self.store.word_count(code) or 0)
        books = sum(1 for row in self.store.books() if (row.get("lang") or "") == code)
        return words, books

    def set_language(self, code: str, data: dict) -> None:
        """新增或修改语言；默认词本的名字跟着中文名走。"""
        code = (code or "").strip().lower()
        if not code:
            raise ValueError("语言代码不能为空")
        table = self.config.data.setdefault("languages", {})
        old = table.get(code) or {}
        merged = {**old, **data, "code": code}
        table[code] = merged
        self.config.save()
        old_name = (old.get("zh_label") or code) + "词本"
        new_name = (merged.get("zh_label") or code) + "词本"
        book = self.store.default_wordbook(code)
        if book and old_name and book.get("name") == old_name and old_name != new_name:
            self.store.rename_default_wordbook(code, new_name)

    def remove_language(self, code: str) -> None:
        code = (code or "").strip().lower()
        table = self.config.data.setdefault("languages", {})
        table.pop(code, None)
        self.config.save()

    def allow_ai_language(self, code: str) -> None:
        code = (code or "").strip().lower()
        if not code:
            return
        allowed = self.config.data.setdefault("ai_lang_consent", [])
        if code not in allowed:
            allowed.append(code)
            self.config.save()

    def language_allowed(self, code: str) -> bool:
        """有词典，或用户同意过该语言只用 AI。"""
        code = (code or "").strip().lower()
        if not code:
            return True
        if self.has_dictionary(code):
            return True
        return code in (self.config.data.get("ai_lang_consent") or [])

    # ------------------------------------------------------------------ 词本
    def find_vocab(self, lang: str, word: str) -> dict | None:
        return self.store.find_word(lang or "", word or "")

    def remove_vocab(self, lang: str, word: str) -> int:
        return self.store.remove_word(lang or "", word or "")

    def wordbooks(self) -> list[dict]:
        return self.store.wordbooks()

    def wordbook(self, book_id: int) -> dict | None:
        return self.store.wordbook(int(book_id))

    def create_wordbook(self, lang: str, name: str, deck: str = "") -> int:
        return self.store.create_wordbook(lang, name, deck)

    def rename_wordbook(self, book_id: int, name: str, deck: str | None = None) -> None:
        self.store.rename_wordbook(int(book_id), name, deck)

    def delete_wordbook(self, book_id: int) -> int:
        return self.store.delete_wordbook(int(book_id))

    def move_words(self, word_ids: list[int], book_id: int) -> int:
        return self.store.move_words(word_ids, int(book_id))

    def words_in_book(self, book_id: int, search: str = "", limit: int = 2000) -> list[dict]:
        return self.store.words_in_book(int(book_id), search, limit)

    def vocab(self, lang: str | None = None, book: str | None = None, limit: int = 500) -> list[dict]:
        return self.store.list_words(lang, book, limit)

    # -------------------------------------------------------------------- 术语
    def add_term(self, book: str, source: str, target: str, lang: str = "", note: str = "") -> dict:
        self.store.add_term(book, source, target, lang, note)
        return {"ok": True, "count": len(self.store.glossary(book))}

    def terms(self, book: str) -> list[dict]:
        return self.store.glossary(book)

    # -------------------------------------------------------------------- Anki
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
                        model = f"Interpres · {book.get('name') or '词本'}"
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
            label = (book or {}).get("name") or "词本"
        else:
            words = self.store.list_words(lang, limit=100000)
            label = lang or "all"
        path = export_tsv(words, self.data_dir / "exports", label)
        return {"ok": True, "path": str(path), "count": len(words)}

    # -------------------------------------------------------------------- 对话
    # ------------------------------------------------------------ translations
    def translations(self, book=None, query: str = "", limit: int = 200) -> list[dict]:
        return self.store.translations(book=book, query=query, limit=limit)

    def export_translations(self, book=None, query: str = "", fmt: str = "md") -> dict:
        """把翻译记录导出到数据目录下的 exports/。"""
        rows = self.store.translations(book=book, query=query, limit=100000)
        out_dir = Path(self.config.data_dir) / "exports"
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        suffix = "md" if fmt == "md" else "tsv"
        path = out_dir / f"翻译记录-{stamp}.{suffix}"
        if fmt == "tsv":
            lines = ["原文\t译文\t书名\t时间"]
            for row in rows:
                payload = json.loads(row.get("payload") or "{}")
                lines.append(
                    "\t".join(
                        [
                            _tsv(row.get("text", "")),
                            _tsv(payload.get("translation", "")),
                            _tsv(row.get("book", "")),
                            row.get("updated", ""),
                        ]
                    )
                )
            path.write_text("\n".join(lines), encoding="utf-8-sig")
        else:
            parts = ["# 翻译记录", "", f"共 {len(rows)} 条 · 导出于 {time.strftime('%Y-%m-%d %H:%M')}"]
            current_book = None
            for row in rows:
                book_name = row.get("book") or "（未标书名）"
                if book_name != current_book:
                    current_book = book_name
                    parts.append(f"\n## {book_name}\n")
                payload = json.loads(row.get("payload") or "{}")
                parts.append(f"### {row.get('updated', '')}")
                parts.append(f"**原文**：{row.get('text', '')}")
                parts.append(f"**译文**：{payload.get('translation', '')}")
                terms = payload.get("terms") or []
                if terms:
                    listed = "；".join(
                        f"{t.get('word', '')} {t.get('meaning', '')}" for t in terms
                    )
                    parts.append(f"**生词**：{listed}")
                parts.append("")
            path.write_text("\n".join(parts), encoding="utf-8")
        return {"path": str(path), "count": len(rows), "dir": str(out_dir)}

    def start_conversation(self, book: str, lang: str, passage: str, translation: str) -> dict:
        conv_id = self.store.start_conversation(book, lang, passage, translation)
        return {"id": conv_id, "messages": self.chat_messages(conv_id), "book": book}

    def chat_messages(self, conv_id: int) -> list[dict]:
        return [
            {"role": m["role"], "content": m["content"], "created": m["created"]}
            for m in self.store.messages(conv_id)
        ]

    def ask(self, conv_id: int, question: str, on_delta=None) -> dict:
        question = (question or "").strip()
        if not question:
            raise ValueError("问题不能为空")
        conv = self.store.conversation(conv_id)
        if not conv:
            raise ValueError("这段对话已经不存在了")

        messages = [{"role": "system", "content": self._chat_system(conv)}]
        for item in self.store.messages(conv_id)[-14:]:
            messages.append({"role": item["role"], "content": item["content"]})
        messages.append({"role": "user", "content": question})

        if on_delta is None:
            reply = self.translator.chat(messages)
        else:
            pieces: list[str] = []
            for piece in self.translator.chat_stream(messages):
                pieces.append(piece)
                try:
                    on_delta("".join(pieces))
                except Exception:
                    pass
            reply = "".join(pieces).strip()
            if not reply:
                raise ValueError("模型返回了空内容")
        self.store.add_message(conv_id, "user", question)
        self.store.add_message(conv_id, "assistant", reply)
        return {"reply": reply, "messages": self.chat_messages(conv_id)}

    def _chat_system_en(self, conv: dict) -> str:
        from .prompts_en import CHAT_PERSONA_EN, CHAT_RULES_EN

        book = conv.get("book") or "this book"
        persona = str(self.config.get("prompt_chat_persona") or "").strip()
        try:
            persona = (persona or CHAT_PERSONA_EN).format(book=book)
        except Exception:
            persona = (persona or CHAT_PERSONA_EN).replace("{book}", book)
        parts = [persona]
        passage = (conv.get("passage") or "").strip()
        translation = (conv.get("translation") or "").strip()
        limit = int(self.config.get("chat_passage_chars", 0))
        if limit <= 0:
            limit = 100000
        if passage:
            if len(passage) > limit:
                parts.append(
                    f"The passage the user is reading (only the first {limit} characters are shown; "
                    f"{len(passage) - limit} more are omitted — say so if the question is about them):\n{passage[:limit]}"
                )
            else:
                parts.append(f"The passage the user is reading ({len(passage)} characters, full text):\n{passage}")
        if translation:
            parts.append(f"Translation of the passage:\n{translation[:5000]}")
        recent = [t for t in self.store.recent_history(book, 3) if t and t != passage]
        if recent:
            parts.append(
                "Recently read passages (reference only):\n" + "\n---\n".join(t[:400] for t in recent)
            )
        rules = str(self.config.get("prompt_chat_rules") or "").strip() or CHAT_RULES_EN
        parts.append(rules)
        return "\n\n".join(parts)

    def _chat_system(self, conv: dict) -> str:
        if _english_mode():
            custom = str(self.config.get("prompt_chat_persona") or "").strip()
            if not custom:
                return self._chat_system_en(conv)
        book = conv.get("book") or "这本书"
        persona = str(self.config.get("prompt_chat_persona") or "").strip() or CHAT_PERSONA_DEFAULT
        try:
            persona = persona.format(book=book)
        except Exception:
            pass
        parts = [persona]
        passage = (conv.get("passage") or "").strip()
        translation = (conv.get("translation") or "").strip()
        limit = int(self.config.get("chat_passage_chars", 0))
        if limit <= 0:
            limit = 100000  # 不限制时也留一个硬保护，避免一次发太多直接超上下文
        if passage:
            if len(passage) > limit:
                parts.append(
                    f"用户正在读的段落（原文较长，这里只给出前 {limit} 字，"
                    f"后面还有 {len(passage) - limit} 字没给你；"
                    f"如果用户问到的部分不在这里，就说明你看到的不全）：\n{passage[:limit]}"
                )
            else:
                parts.append(f"用户正在读的段落（共 {len(passage)} 字，以下是全文）：\n{passage}")
        if translation:
            parts.append(f"这段的译文：\n{translation[:5000]}")

        recent = [t for t in self.store.recent_history(book, 3) if t and t != passage]
        if recent:
            parts.append("最近读过的片段（仅供参考）：\n" + "\n---\n".join(t[:400] for t in recent))

        rules = str(self.config.get("prompt_chat_rules") or "").strip() or CHAT_RULES_DEFAULT
        parts.append(rules)
        return "\n\n".join(parts)

    def conversations(self, book: str | None = None) -> list[dict]:
        return self.store.conversations(book)

    def current_book(self) -> str:
        """最近在读的书（用来开一段没有原文的对话）。"""
        books = self.store.books()
        return books[0]["name"] if books else ""

    def latest_conversation(self, book: str) -> dict | None:
        items = self.store.conversations(book, limit=1) if book else []
        return items[0] if items else None

    def update_conversation_context(self, conv_id: int, passage: str, translation: str) -> None:
        self.store.update_conversation_context(conv_id, passage, translation)

    def books_with_conversations(self) -> list[dict]:
        from .capture import book_from_title

        rows = self.store.books_with_conversations()
        return [
            row for row in rows
            if not row.get("book") or row["book"] == "(未命名)" or book_from_title(row["book"])
        ]

    def delete_conversation(self, conv_id: int) -> None:
        self.store.delete_conversation(conv_id)

    def delete_book_conversations(self, book: str) -> int:
        return self.store.delete_book_conversations(book)

    def rename_book(self, old: str, new: str) -> None:
        self.store.rename_book(old, new)

    def export_conversations(self, book: str) -> dict:
        lines = [f"# 与《{book}》的对话", ""]
        items = self.store.conversations(book)
        for conv in items:
            lines.append(f"## {conv['created'][:16]}")
            if conv.get("passage"):
                lines.append(f"> {conv['passage'][:300]}")
                lines.append("")
            for message in self.store.messages(conv["id"]):
                speaker = "我" if message["role"] == "user" else "AI"
                lines.append(f"**{speaker}**：{message['content']}")
                lines.append("")
        out_dir = self.data_dir / "exports"
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        safe = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", book or "book")[:40]
        path = out_dir / f"chat_{safe}_{stamp}.md"
        path.write_text("\n".join(lines), encoding="utf-8")
        return {"ok": True, "path": str(path), "count": len(items)}


    def speak(self, text: str, lang: str) -> dict:
        engine = self.tts.engine_for(lang)
        if engine == "system" and not self.tts.voice_for(lang):
            name = self.lang_label(lang)
            raise RuntimeError(
                f"没有可用的{name}音色：请到 设置 → 语言 里指定，或安装系统语音"
            )
        path = self.tts.speak(text, lang)
        return {"ok": True, "path": str(path), "voice": self.tts.voice_for(lang)}

    def synthesize(self, text: str, lang: str) -> Path:
        return self.tts.synthesize(text, lang)

    # -------------------------------------------------------------------- 状态
    def status(self) -> dict:
        return {
            "ok": True,
            "version": __import__("rc").__version__,
            "api_ready": bool(self.config.api_key),
            "model": self.config.api.get("model", ""),
            "data_dir": str(self.data_dir),
            "vocab_total": self.store.word_count(),
            "anki": self.anki.status(),
            "tts_voices": self.tts.voices(),
        }

    def test_api(self) -> dict:
        try:
            reply = self.translator.test()
            return {"ok": True, "reply": reply, "model": self.config.api.get("model", "")}
        except LLMError as exc:
            return {"ok": False, "error": str(exc)}

    def lang_label(self, code: str) -> str:
        entry = self.config.language(code)
        return entry.get("zh_label") or entry.get("label") or code

    def target_label(self) -> str:
        return _lang_name(self.config.data.get("target_lang"))
