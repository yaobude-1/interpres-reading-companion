"""生词本、语言登记、术语表。"""

from __future__ import annotations


class VocabMixin:
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
