"""Shared URL/word selection helpers for the panel and popup dictionary views."""

from __future__ import annotations

from urllib.parse import quote


def raw_word_candidates(entry: dict, query: str) -> list[str]:
    """Pick the dictionary headword that should be requested for raw HTML."""
    candidates: list[str] = []
    for key in ("matched", "word"):
        value = str(entry.get(key) or "").strip()
        if value and value not in candidates:
            candidates.append(value)
    lemma = str((entry.get("morph") or {}).get("lemma") or "").strip()
    if lemma and lemma not in candidates:
        candidates.append(lemma)
    query = (query or "").strip()
    if query and query not in candidates:
        candidates.append(query)
    return candidates


def view_url(
    port: int,
    token: str,
    word: str,
    *,
    lang: str = "",
    dict_id: str = "",
) -> str:
    if dict_id:
        query = f"dict_id={quote(dict_id)}&word={quote(word)}"
    else:
        query = f"lang={quote(lang or 'en')}&word={quote(word)}"
    return (
        f"http://127.0.0.1:{int(port)}/api/dict-view?{query}"
        f"&token={quote(token)}"
    )
