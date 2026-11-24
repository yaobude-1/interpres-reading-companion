"""Persistent headword index for MDX/MDD dictionaries.

Parsing every key block on every process start costs several seconds for a
large dictionary (the OED has ~935k entries).  This module keeps a compact
SQLite sidecar next to the dictionary, with:

    words(key, folded, offset)      original headwords in file order
    alias_exact(key, offset)        macron-stripped aliases
    alias_folded(folded, offset)

Exact lookups and prefix searches go through SQL indexes; the article itself
is still read lazily from the original file by offset.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
from array import array
from pathlib import Path
from typing import Callable, Iterable, Iterator

from .index_paths import sidecar

log = logging.getLogger("rc")

SCHEMA_VERSION = 1
BUILD_BATCH = 10_000


class MdxIndexError(RuntimeError):
    pass


def _source_meta(source: Path) -> dict[str, str]:
    stat = source.stat()
    return {
        "schema": str(SCHEMA_VERSION),
        "size": str(stat.st_size),
        "mtime_ns": str(stat.st_mtime_ns),
    }


def _sidecar_path(source: Path) -> Path:
    return sidecar(source, ".rcidx")


class MdxIndex:
    def __init__(self, path: Path, conn: sqlite3.Connection) -> None:
        self.path = path
        self._conn = conn
        self._lock = threading.RLock()
        self.entry_count = int(self._meta("entries") or 0)
        self._offsets = self._load_offsets()

    # ------------------------------------------------------------------ 打开
    @classmethod
    def open_or_build(
        cls,
        source: Path,
        key_iter: Callable[[], Iterable[tuple[str, int]]],
        alias: Callable[[str], str],
    ) -> "MdxIndex | None":
        sidecar_path = _sidecar_path(source)
        index = cls._try_open(sidecar_path, source)
        if index is not None:
            return index
        try:
            cls._build(sidecar_path, source, key_iter(), alias)
        except (OSError, sqlite3.Error, MdxIndexError) as exc:
            log.debug("MDX 索引写入失败 %s: %s", sidecar_path, exc)
            return None
        return cls._try_open(sidecar_path, source)

    @classmethod
    def _try_open(cls, path: Path, source: Path) -> "MdxIndex | None":
        if not path.exists():
            return None
        try:
            conn = sqlite3.connect(str(path), check_same_thread=False)
            conn.execute("PRAGMA query_only = ON")
            meta = _source_meta(source)
            rows = dict(conn.execute("SELECT key, value FROM meta"))
            if any(rows.get(key) != value for key, value in meta.items()):
                conn.close()
                return None
            return cls(path, conn)
        except (OSError, sqlite3.Error, ValueError) as exc:
            log.debug("MDX 索引读取失败 %s: %s", path, exc)
            return None

    @classmethod
    def _build(
        cls,
        path: Path,
        source: Path,
        keys: Iterable[tuple[str, int]],
        alias: Callable[[str], str],
    ) -> None:
        tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
        tmp.unlink(missing_ok=True)
        conn = sqlite3.connect(str(tmp))
        try:
            conn.execute("PRAGMA journal_mode = OFF")
            conn.execute("PRAGMA synchronous = OFF")
            conn.execute("PRAGMA locking_mode = EXCLUSIVE")
            conn.execute(
                "CREATE TABLE words("
                "id INTEGER PRIMARY KEY, key TEXT NOT NULL, "
                "folded TEXT NOT NULL, offset INTEGER NOT NULL)"
            )
            conn.execute("CREATE TABLE alias_exact(key TEXT PRIMARY KEY, offset INTEGER)")
            conn.execute(
                "CREATE TABLE alias_folded(folded TEXT PRIMARY KEY, offset INTEGER)"
            )
            conn.execute("CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT)")
            rows: list[tuple[str, str, int]] = []
            exact_aliases: list[tuple[str, int]] = []
            folded_aliases: list[tuple[str, int]] = []
            total = 0
            for key, offset in keys:
                rows.append((key, key.lower(), int(offset)))
                total += 1
                plain = alias(key)
                if plain and plain != key:
                    exact_aliases.append((plain, int(offset)))
                    folded_aliases.append((plain.lower(), int(offset)))
                if len(rows) >= BUILD_BATCH:
                    conn.executemany(
                        "INSERT INTO words(key, folded, offset) VALUES(?, ?, ?)", rows
                    )
                    conn.executemany(
                        "INSERT OR IGNORE INTO alias_exact(key, offset) VALUES(?, ?)",
                        exact_aliases,
                    )
                    conn.executemany(
                        "INSERT OR IGNORE INTO alias_folded(folded, offset) VALUES(?, ?)",
                        folded_aliases,
                    )
                    rows.clear()
                    exact_aliases.clear()
                    folded_aliases.clear()
            if rows:
                conn.executemany(
                    "INSERT INTO words(key, folded, offset) VALUES(?, ?, ?)", rows
                )
            if exact_aliases:
                conn.executemany(
                    "INSERT OR IGNORE INTO alias_exact(key, offset) VALUES(?, ?)",
                    exact_aliases,
                )
            if folded_aliases:
                conn.executemany(
                    "INSERT OR IGNORE INTO alias_folded(folded, offset) VALUES(?, ?)",
                    folded_aliases,
                )
            conn.execute("CREATE INDEX idx_words_key ON words(key)")
            conn.execute("CREATE INDEX idx_words_folded ON words(folded)")
            conn.execute("CREATE INDEX idx_words_offset ON words(offset)")
            meta = _source_meta(source)
            meta["entries"] = str(total)
            conn.executemany(
                "INSERT INTO meta(key, value) VALUES(?, ?)", list(meta.items())
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        try:
            os.replace(tmp, path)
        except OSError:
            tmp.unlink(missing_ok=True)
            raise

    # ------------------------------------------------------------------ 查询
    def _meta(self, key: str) -> str:
        try:
            row = self._conn.execute(
                "SELECT value FROM meta WHERE key = ?", (key,)
            ).fetchone()
            return str(row[0]) if row else ""
        except sqlite3.Error:
            return ""

    def _load_offsets(self) -> array:
        with self._lock:
            try:
                return array(
                    "Q",
                    (
                        int(row[0])
                        for row in self._conn.execute(
                            "SELECT DISTINCT offset FROM words ORDER BY offset"
                        )
                    ),
                )
            except sqlite3.Error:
                return array("Q")

    @property
    def offsets(self) -> array:
        return self._offsets

    def find_exact(self, key: str) -> int | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT offset FROM words WHERE key = ? ORDER BY id LIMIT 1", (key,)
            ).fetchone()
            if row is not None:
                return int(row[0])
            row = self._conn.execute(
                "SELECT offset FROM alias_exact WHERE key = ?", (key,)
            ).fetchone()
            return int(row[0]) if row is not None else None

    def find_folded(self, folded: str) -> int | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT offset FROM words WHERE folded = ? ORDER BY id LIMIT 1",
                (folded,),
            ).fetchone()
            if row is not None:
                return int(row[0])
            row = self._conn.execute(
                "SELECT offset FROM alias_folded WHERE folded = ?", (folded,)
            ).fetchone()
            return int(row[0]) if row is not None else None

    def prefix(self, prefix: str, limit: int = 10) -> list[str]:
        if not prefix or limit <= 0:
            return []
        upper = prefix + "\U0010ffff"
        with self._lock:
            rows = self._conn.execute(
                "SELECT key FROM words WHERE folded >= ? AND folded < ? "
                "ORDER BY folded, id LIMIT ?",
                (prefix, upper, int(limit)),
            ).fetchall()
        return [str(row[0]) for row in rows]

    def iter_keys(self) -> Iterator[tuple[str, int]]:
        # Use a private connection: the fuzzy builder may iterate all keys
        # while another thread is doing an exact lookup.
        try:
            conn = sqlite3.connect(str(self.path), check_same_thread=False)
        except sqlite3.Error:
            return
        try:
            conn.execute("PRAGMA query_only = ON")
            cursor = conn.execute("SELECT key, offset FROM words ORDER BY id")
            for key, offset in cursor:
                yield str(key), int(offset)
        except sqlite3.Error:
            return
        finally:
            conn.close()

    def close(self) -> None:
        try:
            self._conn.close()
        except sqlite3.Error as exc:
            log.debug("关闭 MDX 索引失败: %s", exc)


class KeyView:
    """Sequence-like compatibility layer for code that iterates ``MDX._keys``."""

    def __init__(self, index: MdxIndex) -> None:
        self._index = index

    def __iter__(self) -> Iterator[tuple[str, int]]:
        return self._index.iter_keys()

    def __len__(self) -> int:
        return self._index.entry_count

    def __getitem__(self, item):
        if isinstance(item, slice):
            return list(self)[item]
        if item < 0:
            item += len(self)
        if item < 0:
            raise IndexError(item)
        for position, value in enumerate(self):
            if position == item:
                return value
        raise IndexError(item)
