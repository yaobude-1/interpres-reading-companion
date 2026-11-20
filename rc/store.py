"""本地存储：翻译缓存、生词本、术语表、书目。

全部用 sqlite3，单文件，方便备份。
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from pathlib import Path

LANG_BOOK_NAMES = {
    "en": "英语词本",
    "fr": "法语词本",
    "la": "拉丁语词本",
    "de": "德语词本",
    "es": "西班牙语词本",
    "it": "意大利语词本",
}


SCHEMA = """
CREATE TABLE IF NOT EXISTS cache (
    key      TEXT PRIMARY KEY,
    payload  TEXT NOT NULL,
    created  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS wordbooks (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    lang       TEXT NOT NULL,
    name       TEXT NOT NULL,
    deck       TEXT NOT NULL DEFAULT '',
    is_default INTEGER NOT NULL DEFAULT 0,
    anki_json  TEXT NOT NULL DEFAULT '',
    created    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS vocab (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    lang         TEXT NOT NULL,
    word         TEXT NOT NULL,
    lemma        TEXT NOT NULL DEFAULT '',
    reading      TEXT NOT NULL DEFAULT '',
    pos          TEXT NOT NULL DEFAULT '',
    meaning      TEXT NOT NULL DEFAULT '',
    sentence     TEXT NOT NULL DEFAULT '',
    book         TEXT NOT NULL DEFAULT '',
    difficulty   TEXT NOT NULL DEFAULT '',
    tags         TEXT NOT NULL DEFAULT '',
    created      TEXT NOT NULL,
    updated      TEXT NOT NULL,
    anki_note_id INTEGER,
    synced       INTEGER NOT NULL DEFAULT 0,
    dict_source  TEXT NOT NULL DEFAULT '',
    dict_meaning TEXT NOT NULL DEFAULT '',
    dict_example TEXT NOT NULL DEFAULT '',
    dict_example_cn TEXT NOT NULL DEFAULT '',
    audio_key    TEXT NOT NULL DEFAULT '',
    UNIQUE (lang, lemma)
);

CREATE TABLE IF NOT EXISTS glossary (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    book     TEXT NOT NULL DEFAULT '',
    lang     TEXT NOT NULL DEFAULT '',
    source   TEXT NOT NULL,
    target   TEXT NOT NULL,
    note     TEXT NOT NULL DEFAULT '',
    updated  TEXT NOT NULL,
    UNIQUE (book, source)
);

CREATE TABLE IF NOT EXISTS books (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE,
    lang       TEXT NOT NULL DEFAULT '',
    last_seen  TEXT NOT NULL,
    created    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS history (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    text     TEXT NOT NULL,
    book     TEXT NOT NULL DEFAULT '',
    lang     TEXT NOT NULL DEFAULT '',
    created  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    book        TEXT NOT NULL DEFAULT '',
    lang        TEXT NOT NULL DEFAULT '',
    passage     TEXT NOT NULL DEFAULT '',
    translation TEXT NOT NULL DEFAULT '',
    created     TEXT NOT NULL,
    updated     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    role            TEXT NOT NULL,
    content         TEXT NOT NULL,
    created         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS library (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    path             TEXT NOT NULL UNIQUE,
    title            TEXT NOT NULL DEFAULT '',
    format           TEXT NOT NULL DEFAULT 'epub',
    section_count    INTEGER NOT NULL DEFAULT 0,
    para_count       INTEGER NOT NULL DEFAULT 0,
    position_section INTEGER NOT NULL DEFAULT 0,
    position_para    INTEGER NOT NULL DEFAULT 0,
    imported         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS library_sections (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id  INTEGER NOT NULL,
    idx      INTEGER NOT NULL,
    title    TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS library_paragraphs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id     INTEGER NOT NULL,
    section_idx INTEGER NOT NULL,
    para_idx    INTEGER NOT NULL,
    text        TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS book_fts USING fts5(
    text,
    book_id UNINDEXED,
    section_idx UNINDEXED,
    para_idx UNINDEXED,
    tokenize='unicode61'
);

CREATE TABLE IF NOT EXISTS translations (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    book    TEXT NOT NULL DEFAULT '',
    lang    TEXT NOT NULL DEFAULT '',
    text    TEXT NOT NULL,
    payload TEXT NOT NULL,
    created TEXT NOT NULL,
    updated TEXT NOT NULL,
    hits    INTEGER NOT NULL DEFAULT 1
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_tr_key ON translations (book, text);
CREATE INDEX IF NOT EXISTS idx_tr_book ON translations (book);

CREATE INDEX IF NOT EXISTS idx_vocab_lang ON vocab (lang);
CREATE INDEX IF NOT EXISTS idx_vocab_book ON vocab (book);
CREATE INDEX IF NOT EXISTS idx_glossary_book ON glossary (book);
CREATE INDEX IF NOT EXISTS idx_conv_book ON conversations (book);
CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages (conversation_id);
"""


def now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _normalize_for_match(text: str) -> str:
    """去掉空白和标点后比较，避免换行/断词影响定位。"""
    value = (text or "").lower()
    return re.sub(r"[\W_]+", "", value, flags=re.UNICODE)


class Store:
    def __init__(self, db_path: Path | str) -> None:
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()
            self._migrate()

    def _migrate(self) -> None:
        """老库补字段（生词本后来加了词典相关列）。"""
        columns = {row["name"] for row in self._conn.execute("PRAGMA table_info(vocab)")}
        for name, ddl in (
            ("dict_source", "TEXT NOT NULL DEFAULT ''"),
            ("dict_meaning", "TEXT NOT NULL DEFAULT ''"),
            ("dict_example", "TEXT NOT NULL DEFAULT ''"),
            ("dict_example_cn", "TEXT NOT NULL DEFAULT ''"),
            ("audio_key", "TEXT NOT NULL DEFAULT ''"),
            ("wordbook_id", "INTEGER NOT NULL DEFAULT 0"),
        ):
            if name not in columns:
                self._conn.execute(f"ALTER TABLE vocab ADD COLUMN {name} {ddl}")
        wb_columns = {
            row["name"] for row in self._conn.execute("PRAGMA table_info(wordbooks)")
        }
        if "anki_json" not in wb_columns:
            self._conn.execute(
                "ALTER TABLE wordbooks ADD COLUMN anki_json TEXT NOT NULL DEFAULT ''"
            )
        # 老生词按语言归入各自默认词本
        for row in self._conn.execute(
            "SELECT DISTINCT lang FROM vocab WHERE wordbook_id = 0"
        ).fetchall():
            book_id = self._ensure_default_wordbook_locked((row["lang"] or "??").lower())
            self._conn.execute(
                "UPDATE vocab SET wordbook_id = ? WHERE lang = ? AND wordbook_id = 0",
                (book_id, row["lang"]),
            )
        self._conn.commit()

    # ------------------------------------------------------------- 词本
    def _ensure_default_wordbook_locked(self, lang: str, name: str = "") -> int:
        lang = (lang or "??").strip().lower() or "??"
        row = self._conn.execute(
            "SELECT id FROM wordbooks WHERE lang = ? AND is_default = 1", (lang,)
        ).fetchone()
        if row:
            return int(row["id"])
        name = name or LANG_BOOK_NAMES.get(lang, f"{lang} 词本")
        cur = self._conn.execute(
            "INSERT INTO wordbooks (lang, name, deck, is_default, created) VALUES (?, ?, '', 1, ?)",
            (lang, name, now()),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def ensure_default_wordbook(self, lang: str, name: str = "") -> int:
        with self._lock:
            return self._ensure_default_wordbook_locked(lang, name)

    def default_wordbook(self, lang: str) -> dict | None:
        lang = (lang or "??").strip().lower() or "??"
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM wordbooks WHERE lang = ? AND is_default = 1", (lang,)
            ).fetchone()
        return dict(row) if row else None

    def rename_default_wordbook(self, lang: str, name: str) -> None:
        lang = (lang or "??").strip().lower() or "??"
        with self._lock:
            self._conn.execute(
                "UPDATE wordbooks SET name = ? WHERE lang = ? AND is_default = 1",
                ((name or "").strip(), lang),
            )
            self._conn.commit()

    def wordbooks(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                """SELECT w.*, COUNT(v.id) AS count FROM wordbooks w
                   LEFT JOIN vocab v ON v.wordbook_id = w.id
                   GROUP BY w.id
                   ORDER BY w.lang, w.is_default DESC, w.created"""
            ).fetchall()
        return [dict(r) for r in rows]

    def wordbook(self, book_id: int) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM wordbooks WHERE id = ?", (int(book_id),)
            ).fetchone()
        return dict(row) if row else None

    def create_wordbook(self, lang: str, name: str, deck: str = "") -> int:
        lang = (lang or "??").strip().lower() or "??"
        name = (name or "").strip() or f"{lang} 词本"
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO wordbooks (lang, name, deck, is_default, created) VALUES (?, ?, ?, 0, ?)",
                (lang, name, deck or "", now()),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def set_wordbook_anki(self, book_id: int, payload: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE wordbooks SET anki_json = ? WHERE id = ?",
                (payload or "", int(book_id)),
            )
            self._conn.commit()

    def rename_wordbook(self, book_id: int, name: str, deck: str | None = None) -> None:
        with self._lock:
            if deck is None:
                self._conn.execute(
                    "UPDATE wordbooks SET name = ? WHERE id = ?",
                    ((name or "").strip(), int(book_id)),
                )
            else:
                self._conn.execute(
                    "UPDATE wordbooks SET name = ?, deck = ? WHERE id = ?",
                    ((name or "").strip(), deck, int(book_id)),
                )
            self._conn.commit()

    def delete_wordbook(self, book_id: int) -> int:
        """删词本：里面的词移回该语言的默认词本。"""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM wordbooks WHERE id = ?", (int(book_id),)
            ).fetchone()
            if not row or row["is_default"]:
                return 0
            default_id = self._ensure_default_wordbook_locked(row["lang"])
            cur = self._conn.execute(
                "UPDATE vocab SET wordbook_id = ? WHERE wordbook_id = ?",
                (default_id, int(book_id)),
            )
            self._conn.execute("DELETE FROM wordbooks WHERE id = ?", (int(book_id),))
            self._conn.commit()
            return int(cur.rowcount or 0)

    def move_words(self, word_ids: list[int], book_id: int) -> int:
        ids = [int(i) for i in word_ids]
        if not ids:
            return 0
        marks = ",".join("?" for _ in ids)
        with self._lock:
            cur = self._conn.execute(
                f"UPDATE vocab SET wordbook_id = ? WHERE id IN ({marks})",
                (int(book_id), *ids),
            )
            self._conn.commit()
            return int(cur.rowcount or 0)

    def words_in_book(self, book_id: int, search: str = "", limit: int = 2000) -> list[dict]:
        sql = "SELECT * FROM vocab WHERE wordbook_id = ?"
        args: list = [int(book_id)]
        if search:
            sql += " AND (word LIKE ? OR lemma LIKE ? OR meaning LIKE ?)"
            like = f"%{search}%"
            args.extend([like, like, like])
        sql += " ORDER BY updated DESC LIMIT ?"
        args.append(limit)
        with self._lock:
            rows = self._conn.execute(sql, args).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ------------------------------------------------------------------ cache
    def cache_get(self, key: str) -> dict | None:
        with self._lock:
            row = self._conn.execute("SELECT payload FROM cache WHERE key = ?", (key,)).fetchone()
        if not row:
            return None
        try:
            return json.loads(row["payload"])
        except Exception:
            return None

    def cache_put(self, key: str, payload: dict) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO cache (key, payload, created) VALUES (?, ?, ?)",
                (key, json.dumps(payload, ensure_ascii=False), now()),
            )
            self._conn.commit()

    # ------------------------------------------------------------------ vocab
    def add_word(self, data: dict) -> int:
        """新增或更新一个生词（同一语言下按 lemma 去重）。"""
        lang = (data.get("lang") or "").strip().lower() or "??"
        lemma = (data.get("lemma") or data.get("word") or "").strip()
        if not lemma:
            raise ValueError("empty lemma")
        word = (data.get("word") or lemma).strip()
        ts = now()
        values = (
            word,
            data.get("reading", ""),
            data.get("pos", ""),
            data.get("meaning", ""),
            data.get("sentence", ""),
            data.get("book", ""),
            data.get("difficulty", ""),
            data.get("dict_source", ""),
            data.get("dict_meaning", ""),
            data.get("dict_example", ""),
            data.get("dict_example_cn", ""),
            data.get("audio_key", ""),
        )
        with self._lock:
            row = self._conn.execute(
                "SELECT id FROM vocab WHERE lang = ? AND lemma = ?", (lang, lemma)
            ).fetchone()
            if row:
                self._conn.execute(
                    """UPDATE vocab SET word = ?, reading = ?, pos = ?, meaning = ?,
                       sentence = ?, book = ?, difficulty = ?,
                       dict_source = ?, dict_meaning = ?, dict_example = ?,
                       dict_example_cn = ?, audio_key = ?, updated = ?
                       WHERE id = ?""",
                    (*values, ts, row["id"]),
                )
                self._conn.commit()
                return int(row["id"])
            book_id = int(data.get("wordbook_id") or 0) or self._ensure_default_wordbook_locked(
                lang, str(data.get("book_name") or "")
            )
            cur = self._conn.execute(
                """INSERT INTO vocab
                   (word, reading, pos, meaning, sentence, book, difficulty,
                    dict_source, dict_meaning, dict_example, dict_example_cn, audio_key,
                    lang, lemma, tags, created, updated, wordbook_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (*values, lang, lemma, data.get("tags", ""), ts, ts, book_id),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def find_word(self, lang: str, word: str) -> dict | None:
        text = (word or "").strip()
        if not text:
            return None
        with self._lock:
            row = self._conn.execute(
                """SELECT * FROM vocab
                   WHERE lang = ? AND (lower(word) = lower(?) OR lower(lemma) = lower(?))
                   ORDER BY updated DESC LIMIT 1""",
                (lang, text, text),
            ).fetchone()
        return dict(row) if row else None

    def remove_word(self, lang: str, word: str) -> int:
        text = (word or "").strip()
        if not text:
            return 0
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM vocab WHERE lang = ? AND (lower(word) = lower(?) OR lower(lemma) = lower(?))",
                (lang, text, text),
            )
            self._conn.commit()
            return int(cur.rowcount or 0)

    def list_words(
        self,
        lang: str | None = None,
        book: str | None = None,
        limit: int = 500,
        wordbook_id: int | None = None,
    ) -> list[dict]:
        sql = "SELECT * FROM vocab WHERE 1 = 1"
        args: list = []
        if wordbook_id:
            sql += " AND wordbook_id = ?"
            args.append(int(wordbook_id))
        if lang:
            sql += " AND lang = ?"
            args.append(lang)
        if book:
            sql += " AND book = ?"
            args.append(book)
        sql += " ORDER BY updated DESC LIMIT ?"
        args.append(limit)
        with self._lock:
            rows = self._conn.execute(sql, args).fetchall()
        return [dict(r) for r in rows]

    def word_count(self, lang: str | None = None) -> int:
        sql = "SELECT COUNT(*) AS n FROM vocab"
        args: list = []
        if lang:
            sql += " WHERE lang = ?"
            args.append(lang)
        with self._lock:
            return int(self._conn.execute(sql, args).fetchone()["n"])

    def mark_synced(self, word_id: int, note_id: int | None) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE vocab SET synced = 1, anki_note_id = ? WHERE id = ?", (note_id, word_id)
            )
            self._conn.commit()

    def get_word(self, word_id: int) -> dict | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM vocab WHERE id = ?", (word_id,)).fetchone()
        return dict(row) if row else None

    def delete_words(self, ids: list[int]) -> int:
        ids = [int(i) for i in ids]
        if not ids:
            return 0
        marks = ",".join("?" for _ in ids)
        with self._lock:
            cur = self._conn.execute(f"DELETE FROM vocab WHERE id IN ({marks})", ids)
            self._conn.commit()
            return int(cur.rowcount or 0)

    # ---------------------------------------------------------------- glossary
    def add_term(self, book: str, source: str, target: str, lang: str = "", note: str = "") -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO glossary (book, lang, source, target, note, updated)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(book, source) DO UPDATE SET
                     target = excluded.target,
                     note = excluded.note,
                     updated = excluded.updated""",
                (book or "", lang or "", source.strip(), target.strip(), note or "", now()),
            )
            self._conn.commit()

    def glossary(self, book: str, limit: int = 60) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM glossary WHERE book = ? ORDER BY updated DESC LIMIT ?",
                (book or "", limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def glossary_terms(self, book: str, limit: int = 60) -> list[tuple[str, str]]:
        return [(r["source"], r["target"]) for r in self.glossary(book, limit)]

    def remove_term(self, book: str, source: str) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM glossary WHERE book = ? AND source = ?", (book or "", source)
            )
            self._conn.commit()

    # ------------------------------------------------------------------ books
    def touch_book(self, name: str, lang: str = "") -> None:
        if not name:
            return
        with self._lock:
            self._conn.execute(
                """INSERT INTO books (name, lang, last_seen, created)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(name) DO UPDATE SET
                     last_seen = excluded.last_seen,
                     lang = CASE WHEN excluded.lang != '' THEN excluded.lang ELSE books.lang END""",
                (name, lang or "", now(), now()),
            )
            self._conn.commit()

    def books(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM books ORDER BY last_seen DESC").fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------ translations
    def save_translation(self, book: str, lang: str, text: str, payload: dict) -> int | None:
        """保存一条翻译记录；被更长记录包含的不存，短的被新记录吸收。"""
        norm = _normalize_for_match(text)
        if len(norm) < 12:
            return None
        stamp = now()
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, text FROM translations WHERE book = ?", (book or "",)
            ).fetchall()
            for row in rows:
                other = _normalize_for_match(row["text"])
                if not other:
                    continue
                # 新文本已经被更长的记录覆盖 → 不重复存
                if len(other) > len(norm) and norm in other:
                    self._conn.execute(
                        "UPDATE translations SET hits = hits + 1, updated = ? WHERE id = ?",
                        (stamp, row["id"]),
                    )
                    self._conn.commit()
                    return int(row["id"])
            # 旧的短记录被新记录吸收
            for row in rows:
                other = _normalize_for_match(row["text"])
                if other and len(other) < len(norm) and other in norm:
                    self._conn.execute("DELETE FROM translations WHERE id = ?", (row["id"],))
            existing = self._conn.execute(
                "SELECT id FROM translations WHERE book = ? AND text = ?", (book or "", text)
            ).fetchone()
            if existing:
                self._conn.execute(
                    "UPDATE translations SET payload = ?, updated = ?, hits = hits + 1 WHERE id = ?",
                    (json.dumps(payload, ensure_ascii=False), stamp, existing["id"]),
                )
                self._conn.commit()
                return int(existing["id"])
            cur = self._conn.execute(
                """INSERT INTO translations (book, lang, text, payload, created, updated, hits)
                   VALUES (?, ?, ?, ?, ?, ?, 1)""",
                (book or "", lang or "", text, json.dumps(payload, ensure_ascii=False), stamp, stamp),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def translations(
        self, book: str | None = None, query: str = "", limit: int = 200
    ) -> list[dict]:
        sql = "SELECT * FROM translations"
        params: list = []
        where = []
        if book is not None:
            where.append("book = ?")
            params.append(book)
        if query:
            where.append("(text LIKE ? OR payload LIKE ?)")
            like = f"%{query}%"
            params.extend([like, like])
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY updated DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def translation(self, record_id: int) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM translations WHERE id = ?", (record_id,)
            ).fetchone()
        return dict(row) if row else None

    def delete_translation(self, record_id: int) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM translations WHERE id = ?", (record_id,))
            self._conn.commit()

    def translation_count(self, book: str | None = None) -> int:
        sql = "SELECT COUNT(*) AS n FROM translations"
        params: list = []
        if book is not None:
            sql += " WHERE book = ?"
            params.append(book)
        with self._lock:
            row = self._conn.execute(sql, params).fetchone()
        return int(row["n"]) if row else 0

    def translations_for_book(self, book: str, limit: int = 60) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM translations WHERE book = ? ORDER BY length(text) DESC LIMIT ?",
                (book or "", limit),
            ).fetchall()
        return [dict(r) for r in rows]

    # ---------------------------------------------------------------- history
    def add_history(self, text: str, book: str, lang: str, keep: int = 30) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO history (text, book, lang, created) VALUES (?, ?, ?, ?)",
                (text, book or "", lang or "", now()),
            )
            self._conn.execute(
                """DELETE FROM history WHERE id NOT IN
                   (SELECT id FROM history ORDER BY id DESC LIMIT ?)""",
                (keep,),
            )
            self._conn.commit()

    # ----------------------------------------------------------- conversations
    def recent_history(self, book: str, limit: int = 3) -> list[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT text FROM history WHERE book = ? ORDER BY id DESC LIMIT ?",
                (book or "", limit),
            ).fetchall()
        return [row["text"] for row in rows]

    def purge_empty_conversations(self) -> int:
        """删掉没有任何消息的对话（换书时误建的空白记录）。"""
        with self._lock:
            cur = self._conn.execute(
                """DELETE FROM conversations
                   WHERE id NOT IN (SELECT DISTINCT conversation_id FROM messages)"""
            )
            self._conn.commit()
            return int(cur.rowcount or 0)

    def start_conversation(self, book: str, lang: str, passage: str, translation: str) -> int:
        ts = now()
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO conversations (book, lang, passage, translation, created, updated)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (book or "", lang or "", passage or "", translation or "", ts, ts),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def conversation(self, conv_id: int) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM conversations WHERE id = ?", (conv_id,)
            ).fetchone()
        return dict(row) if row else None

    def update_conversation_context(self, conv_id: int, passage: str, translation: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE conversations SET passage = ?, translation = ?, updated = ? WHERE id = ?",
                (passage or "", translation or "", now(), conv_id),
            )
            self._conn.commit()

    def add_message(self, conv_id: int, role: str, content: str) -> int:
        ts = now()
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO messages (conversation_id, role, content, created) VALUES (?, ?, ?, ?)",
                (conv_id, role, content or "", ts),
            )
            self._conn.execute(
                "UPDATE conversations SET updated = ? WHERE id = ?", (ts, conv_id)
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def messages(self, conv_id: int, limit: int = 200) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id LIMIT ?",
                (conv_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def conversations(self, book: str | None = None, limit: int = 300) -> list[dict]:
        sql = """SELECT c.*, (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) AS msg_count
                 FROM conversations c"""
        args: list = []
        if book is not None:
            sql += " WHERE c.book = ?"
            args.append(book)
        sql += " ORDER BY c.updated DESC LIMIT ?"
        args.append(limit)
        with self._lock:
            rows = self._conn.execute(sql, args).fetchall()
        return [dict(r) for r in rows]

    def books_with_conversations(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                """SELECT book, COUNT(*) AS conv_count, MAX(updated) AS last
                   FROM conversations GROUP BY book ORDER BY last DESC"""
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_conversation(self, conv_id: int) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conv_id,))
            self._conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
            self._conn.commit()

    def delete_book_conversations(self, book: str) -> int:
        with self._lock:
            ids = [
                row["id"]
                for row in self._conn.execute(
                    "SELECT id FROM conversations WHERE book = ?", (book,)
                ).fetchall()
            ]
            for conv_id in ids:
                self._conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conv_id,))
            self._conn.execute("DELETE FROM conversations WHERE book = ?", (book,))
            self._conn.commit()
            return len(ids)

    def rename_book(self, old: str, new: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE conversations SET book = ? WHERE book = ?", (new, old)
            )
            self._conn.commit()

    # -------------------------------------------------------------------- 书
    def import_book(self, path: str, title: str, fmt: str, sections: list[dict]) -> int:
        """把解析好的书写进库（重复导入会覆盖）。"""
        para_count = sum(len(s.get("paragraphs") or []) for s in sections)
        with self._lock:
            row = self._conn.execute("SELECT id FROM library WHERE path = ?", (path,)).fetchone()
            if row:
                book_id = int(row["id"])
                self._conn.execute("DELETE FROM library_sections WHERE book_id = ?", (book_id,))
                self._conn.execute("DELETE FROM library_paragraphs WHERE book_id = ?", (book_id,))
                self._conn.execute("DELETE FROM book_fts WHERE book_id = ?", (book_id,))
                self._conn.execute(
                    """UPDATE library SET title = ?, format = ?, section_count = ?,
                       para_count = ?, imported = ? WHERE id = ?""",
                    (title, fmt, len(sections), para_count, now(), book_id),
                )
            else:
                cur = self._conn.execute(
                    """INSERT INTO library (path, title, format, section_count, para_count, imported)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (path, title, fmt, len(sections), para_count, now()),
                )
                book_id = int(cur.lastrowid)

            fts_rows = []
            for index, section in enumerate(sections):
                self._conn.execute(
                    "INSERT INTO library_sections (book_id, idx, title) VALUES (?, ?, ?)",
                    (book_id, index, section.get("title") or f"第 {index + 1} 节"),
                )
                for para_idx, text in enumerate(section.get("paragraphs") or []):
                    self._conn.execute(
                        """INSERT INTO library_paragraphs (book_id, section_idx, para_idx, text)
                           VALUES (?, ?, ?, ?)""",
                        (book_id, index, para_idx, text),
                    )
                    fts_rows.append((text, book_id, index, para_idx))
            self._conn.executemany(
                "INSERT INTO book_fts (text, book_id, section_idx, para_idx) VALUES (?, ?, ?, ?)",
                fts_rows,
            )
            self._conn.commit()
            return book_id

    def book(self, book_id: int) -> dict | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM library WHERE id = ?", (book_id,)).fetchone()
        return dict(row) if row else None

    def book_by_path(self, path: str) -> dict | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM library WHERE path = ?", (path,)).fetchone()
        return dict(row) if row else None

    def library_books(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM library ORDER BY imported DESC").fetchall()
        return [dict(r) for r in rows]

    def sections(self, book_id: int) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT idx, title FROM library_sections WHERE book_id = ? ORDER BY idx",
                (book_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def section_title(self, book_id: int, idx: int) -> str:
        with self._lock:
            row = self._conn.execute(
                "SELECT title FROM library_sections WHERE book_id = ? AND idx = ?", (book_id, idx)
            ).fetchone()
        return row["title"] if row else ""

    def set_book_position(self, book_id: int, section: int, para: int) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE library SET position_section = ?, position_para = ? WHERE id = ?",
                (int(section), int(para), book_id),
            )
            self._conn.commit()

    def paragraphs(self, book_id: int, section_idx: int, limit: int = 2000) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                """SELECT section_idx, para_idx, text FROM library_paragraphs
                   WHERE book_id = ? AND section_idx = ? ORDER BY para_idx LIMIT ?""",
                (book_id, section_idx, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def search_book(
        self, book_id: int, terms: list[str], max_section: int, limit: int = 6
    ) -> list[dict]:
        """在「开头 → max_section」范围内做全文检索。"""
        words = [t for t in (terms or []) if t and len(t) >= 2]
        if not words:
            return []
        query = " OR ".join('"' + w.replace('"', "") + '"' for w in words[:8])
        try:
            with self._lock:
                rows = self._conn.execute(
                    """SELECT text, book_id, section_idx, para_idx FROM book_fts
                       WHERE book_fts MATCH ? ORDER BY rank LIMIT 400""",
                    (query,),
                ).fetchall()
        except sqlite3.OperationalError:
            return []
        out = []
        for row in rows:
            if int(row["book_id"]) != book_id:
                continue
            if int(row["section_idx"]) > max_section:
                continue
            out.append(dict(row))
            if len(out) >= limit:
                break
        return out

    def find_paragraph(self, book_id: int, text: str) -> dict | None:
        """在书里找一段文字的位置（用于定位读到哪了）。"""
        needle = _normalize_for_match(text)[:120]
        if len(needle) < 12:
            return None
        words = [w for w in re.findall(r"[A-Za-zÀ-ÿ']{4,}", text or "")][:8]
        candidates: list[dict] = []
        if words:
            query = " OR ".join(f'"{w}"' for w in words)
            try:
                with self._lock:
                    rows = self._conn.execute(
                        """SELECT text, book_id, section_idx, para_idx FROM book_fts
                           WHERE book_fts MATCH ? ORDER BY rank LIMIT 200""",
                        (query,),
                    ).fetchall()
                candidates = [dict(r) for r in rows if int(r["book_id"]) == book_id]
            except sqlite3.OperationalError:
                candidates = []
        if not candidates:
            with self._lock:
                rows = self._conn.execute(
                    "SELECT text, book_id, section_idx, para_idx FROM library_paragraphs WHERE book_id = ? LIMIT 5000",
                    (book_id,),
                ).fetchall()
            candidates = [dict(r) for r in rows]

        for row in candidates:
            if needle in _normalize_for_match(row["text"]):
                return row
        return None
