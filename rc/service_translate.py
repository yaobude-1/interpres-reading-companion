"""翻译：分块、缓存、增量与流式合并。"""

from __future__ import annotations

import hashlib
import json
import logging
import time

from . import textutil
from .service_common import (
    CACHE_VERSION,
    TRANSLATE_WORKERS,
    _ends_sentence,
    _english_mode,
    _starts_sentence,
    split_chunks,
)
from .service_base import ServiceBase

log = logging.getLogger("rc")


class TranslateMixin(ServiceBase):
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
