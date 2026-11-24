"""Persistent headword index for StarDict dictionaries.

StarDict already ships a sorted ``.idx``; the expensive part in Python is
turning every entry into tuples/dicts on each start.  The sidecar keeps the
same ``offset/size`` pairs in SQLite, so lookups and prefix searches only
touch the entries they need.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import struct
import threading
from pathlib import Path
from typing import Iterator

from .index_paths import sidecar

log = logging.getLogger("rc")

SCHEMA_VERSION = 1


def _sidecar_path(base: Path) -> Path:
    return sidecar(base, ".rcidx")


def _meta(path: Path) -> dict[str, str]:
    stat = path.stat()
    return {"size": str(stat.st_size), "mtime_ns": str(stat.st_mtime_ns)}


class StarDictIndex:
    def __init__(self, path: Path, conn: sqlite3.Connection) -> None:
        self.path = path
        self._conn = conn
        self._lock = threading.RLock()
        self.entry_count = int(self._meta("entries") or 0)

    @classmethod
    def open_or_build(cls, base: Path) -> "StarDictIndex | None":
        idx = Path(str(base) + ".idx")
        syn = Path(str(base) + ".syn")
        if not idx.exists():
            return None
        path = _sidecar_path(base)
        existing = cls._try_open(path, idx, syn)
        if existing is not None:
            return existing
        try:
            cls._build(path, idx, syn)
        except (OSError, sqlite3.Error, struct.error) as exc:
            log.debug("StarDict 索引写入失败 %s: %s", path, exc)
            return None
        return cls._try_open(path, idx, syn)

    @classmethod
    def _try_open(
        cls, path: Path, idx: Path, syn: Path
    ) -> "StarDictIndex | None":
        if not path.exists():
            return None
        try:
            conn = sqlite3.connect(str(path), check_same_thread=False)
            conn.execute("PRAGMA query_only = ON")
            meta = dict(conn.execute("SELECT key, value FROM meta"))
            expected = {"idx": _meta(idx), "syn": _meta(syn) if syn.exists() else {}}
            for prefix, values in expected.items():
                for key, value in values.items():
                    if meta.get(f"{prefix}_{key}") != value:
                        conn.close()
                        return None
            if meta.get("schema") != str(SCHEMA_VERSION):
                conn.close()
                return None
            return cls(path, conn)
        except (OSError, sqlite3.Error, ValueError) as exc:
            log.debug("StarDict 索引读取失败 %s: %s", path, exc)
            return None

    @classmethod
    def _build(cls, path: Path, idx: Path, syn: Path) -> None:
        tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
        tmp.unlink(missing_ok=True)
        conn = sqlite3.connect(str(tmp))
        try:
            conn.execute("PRAGMA journal_mode = OFF")
            conn.execute("PRAGMA synchronous = OFF")
            conn.execute("CREATE TABLE words("
                         "record INTEGER PRIMARY KEY, key TEXT, folded TEXT, "
                         "offset INTEGER, size INTEGER)")
            conn.execute("CREATE TABLE aliases(folded TEXT PRIMARY KEY, offset INTEGER, size INTEGER)")
            conn.execute("CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT)")
            raw = idx.read_bytes()
            pos = 0
            rows: list[tuple[int, str, str, int, int]] = []
            record = 0
            while pos < len(raw):
                end = raw.find(b"\x00", pos)
                if end < 0 or end + 9 > len(raw):
                    break
                word = raw[pos:end].decode("utf-8", "replace")
                offset, size = struct.unpack(">II", raw[end + 1 : end + 9])
                rows.append((record, word, word.lower(), int(offset), int(size)))
                record += 1
                if len(rows) >= 10_000:
                    conn.executemany(
                        "INSERT INTO words VALUES(?, ?, ?, ?, ?)", rows
                    )
                    rows.clear()
                pos = end + 9
            if rows:
                conn.executemany("INSERT INTO words VALUES(?, ?, ?, ?, ?)", rows)
            if syn.exists():
                syn_raw = syn.read_bytes()
                pos = 0
                while pos < len(syn_raw):
                    end = syn_raw.find(b"\x00", pos)
                    if end < 0 or end + 5 > len(syn_raw):
                        break
                    word = syn_raw[pos:end].decode("utf-8", "replace")
                    target = struct.unpack(">I", syn_raw[end + 1 : end + 5])[0]
                    row = conn.execute(
                        "SELECT offset, size FROM words WHERE record = ?", (target,)
                    ).fetchone()
                    if row is not None:
                        conn.execute(
                            "INSERT OR IGNORE INTO aliases VALUES(?, ?, ?)",
                            (word.lower(), int(row[0]), int(row[1])),
                        )
                    pos = end + 5
            conn.execute("CREATE INDEX idx_words_folded ON words(folded)")
            conn.execute("CREATE INDEX idx_words_offset ON words(offset)")
            meta = {"schema": str(SCHEMA_VERSION), "entries": str(record)}
            for prefix, values in (
                ("idx", _meta(idx)),
                ("syn", _meta(syn) if syn.exists() else {}),
            ):
                for key, value in values.items():
                    meta[f"{prefix}_{key}"] = value
            conn.executemany("INSERT INTO meta VALUES(?, ?)", list(meta.items()))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        os.replace(tmp, path)

    def _meta(self, key: str) -> str:
        try:
            row = self._conn.execute(
                "SELECT value FROM meta WHERE key = ?", (key,)
            ).fetchone()
            return str(row[0]) if row else ""
        except sqlite3.Error:
            return ""

    def find_folded(self, folded: str) -> tuple[int, int] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT offset, size FROM words WHERE folded = ? ORDER BY record LIMIT 1",
                (folded,),
            ).fetchone()
            if row is not None:
                return int(row[0]), int(row[1])
            row = self._conn.execute(
                "SELECT offset, size FROM aliases WHERE folded = ?", (folded,)
            ).fetchone()
            return (int(row[0]), int(row[1])) if row is not None else None

    def prefix(self, prefix: str, limit: int = 10) -> list[str]:
        if not prefix or limit <= 0:
            return []
        with self._lock:
            rows = self._conn.execute(
                "SELECT key FROM words WHERE folded >= ? AND folded < ? "
                "ORDER BY folded, record LIMIT ?",
                (prefix, prefix + "\U0010ffff", int(limit)),
            ).fetchall()
        return [str(row[0]) for row in rows]

    def iter_keys(self) -> Iterator[tuple[str, int]]:
        try:
            conn = sqlite3.connect(str(self.path), check_same_thread=False)
        except sqlite3.Error:
            return
        try:
            conn.execute("PRAGMA query_only = ON")
            for key, offset in conn.execute("SELECT key, offset FROM words ORDER BY record"):
                yield str(key), int(offset)
        except sqlite3.Error:
            return
        finally:
            conn.close()

    def close(self) -> None:
        try:
            self._conn.close()
        except sqlite3.Error as exc:
            log.debug("关闭 StarDict 索引失败: %s", exc)


class KeyView:
    def __init__(self, index: StarDictIndex) -> None:
        self._index = index

    def __iter__(self):
        return self._index.iter_keys()

    def __len__(self) -> int:
        return self._index.entry_count
