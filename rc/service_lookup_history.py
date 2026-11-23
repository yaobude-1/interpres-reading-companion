"""Recent lookup history: low-friction, separate from the vocabulary list."""

from __future__ import annotations

from .service_base import ServiceBase


class LookupHistoryMixin(ServiceBase):
    def record_lookup(self, entry: dict, query: str, book: str = "") -> None:
        if not bool(self.config.get("lookup_history_enabled", True)):
            return
        entry = entry or {}
        senses = entry.get("senses") or []
        first = senses[0] if senses else {}
        text = (
            entry.get("matched")
            or entry.get("word")
            or query
            or ""
        ).strip()
        if not text:
            return
        preview = (
            first.get("definition_cn")
            or first.get("definition")
            or entry.get("definition")
            or ""
        ).strip()
        self.store.add_lookup(
            lang=str(entry.get("lang") or ""),
            word=str(entry.get("word") or text),
            lemma=text,
            dict_id=str(entry.get("dict_id") or ""),
            source=str(entry.get("source") or ""),
            preview=preview[:120],
            book=book or "",
            keep=int(self.config.get("lookup_history_keep", 300) or 300),
        )

    def lookup_history(self, limit: int = 50, lang: str = "", book: str = "") -> list[dict]:
        return self.store.lookup_history(limit, lang, book)

    def lookup_books(self) -> list[str]:
        return self.store.lookup_books()

    def lookup_stats(self) -> dict:
        return self.store.lookup_stats()

    def lookup_history_limit(self) -> int:
        return max(20, int(self.config.get("lookup_history_keep", 300) or 300))

    def set_lookup_history_limit(self, keep: int) -> None:
        keep = max(20, min(5000, int(keep)))
        self.config.data["lookup_history_keep"] = keep
        self.config.save()
        self.store.prune_lookup_history(keep)

    def remove_lookup(self, lookup_id: int) -> None:
        self.store.remove_lookup(lookup_id)

    def clear_lookup_history(self) -> int:
        return self.store.clear_lookup_history()
