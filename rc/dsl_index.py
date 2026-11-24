"""Persistent index for DSL dictionaries.

The DSL reader used to keep every parsed body in memory.  This sidecar stores
the same bodies compressed in SQLite, so startup and lookup only touch the
rows they need.  Building the sidecar is still a one-time full scan of the DSL
source.
"""

from __future__ import annotations

import gzip
import json
import logging
import os
import re
import sqlite3
import threading
import zlib
from pathlib import Path
from typing import Iterator

from .index_paths import sidecar

log = logging.getLogger("rc")

SCHEMA_VERSION = 1
_HEADER_RE = re.compile(r'^#([A-Z_]+)\s+"(.*)"\s*$')


def _sidecar_path(path: Path) -> Path:
    return sidecar(path, ".rcidx")


def _decode(raw: bytes) -> str:
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16", "replace")
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig", "replace")
    return raw.decode("utf-8", "replace")


def _read_source(path: Path) -> str:
    if path.name.lower().endswith((".gz", ".dz")):
        with gzip.open(path, "rb") as fh:
            return _decode(fh.read())
    return _decode(path.read_bytes())


def _iter_entries(text: str):
    attrs: dict[str, str] = {}
    current = ""
    body: list[str] = []
    for line in text.splitlines():
        if line.startswith("#"):
            match = _HEADER_RE.match(line)
            if match:
                attrs[match.group(1)] = match.group(2)
            continue
        if not line.strip():
            continue
        if line[0] in " \t":
            if current:
                body.append(line.strip())
            continue
        if current:
            yield current, "\n".join(body)
        current = line.strip()
        body = []
    if current:
        yield current, "\n".join(body)


class DslIndex:
    def __init__(self, path: Path, conn: sqlite3.Connection) -> None:
        self.path = path
        self._conn = conn
        self._lock = threading.RLock()
        self.entry_count = int(self._meta("entries") or 0)
        try:
            self.attrs = json.loads(self._meta("attrs") or "{}")
        except ValueError:
            self.attrs = {}

    @classmethod
    def open_or_build(cls, source: Path) -> "DslIndex | None":
        sidecar = _sidecar_path(source)
        existing = cls._try_open(sidecar, source)
        if existing is not None:
            return existing
        try:
            cls._build(sidecar, source)
        except (OSError, sqlite3.Error, ValueError, zlib.error) as exc:
            log.debug("DSL 索引写入失败 %s: %s", sidecar, exc)
            return None
        return cls._try_open(sidecar, source)

    @classmethod
    def _try_open(cls, sidecar: Path, source: Path) -> "DslIndex | None":
        if not sidecar.exists():
            return None
        try:
            conn = sqlite3.connect(str(sidecar), check_same_thread=False)
            conn.execute("PRAGMA query_only = ON")
            meta = dict(conn.execute("SELECT key, value FROM meta"))
            stat = source.stat()
            if meta.get("size") != str(stat.st_size):
                conn.close()
                return None
            if meta.get("mtime_ns") != str(stat.st_mtime_ns):
                conn.close()
                return None
            if meta.get("schema") != str(SCHEMA_VERSION):
                conn.close()
                return None
            return cls(sidecar, conn)
        except (OSError, sqlite3.Error, ValueError) as exc:
            log.debug("DSL 索引读取失败 %s: %s", sidecar, exc)
            return None

    @classmethod
    def _build(cls, sidecar: Path, source: Path) -> None:
        text = _read_source(source)
        tmp = sidecar.with_name(sidecar.name + f".{os.getpid()}.tmp")
        tmp.unlink(missing_ok=True)
        conn = sqlite3.connect(str(tmp))
        try:
            conn.execute("PRAGMA journal_mode = OFF")
            conn.execute("PRAGMA synchronous = OFF")
            conn.execute(
                "CREATE TABLE words(record INTEGER PRIMARY KEY, key TEXT, folded TEXT, body BLOB)"
            )
            conn.execute("CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT)")
            attrs: dict[str, str] = {}
            rows: list[tuple[str, str, bytes]] = []
            total = 0
            for word, body in _iter_entries(text):
                rows.append(
                    (
                        word,
                        word.lower(),
                        zlib.compress(body.encode("utf-8")),
                    )
                )
                total += 1
                if len(rows) >= 2000:
                    conn.executemany(
                        "INSERT INTO words(key, folded, body) VALUES(?, ?, ?)", rows
                    )
                    rows.clear()
            if rows:
                conn.executemany(
                    "INSERT INTO words(key, folded, body) VALUES(?, ?, ?)", rows
                )
            # Re-read only the header for attributes; the body scan already
            # happened above.
            for line in text.splitlines():
                if line.startswith("#"):
                    match = _HEADER_RE.match(line)
                    if match:
                        attrs[match.group(1)] = match.group(2)
                elif line.strip() and not line[0].isspace():
                    break
            attrs["Title"] = attrs.get("NAME") or attrs.get("Title") or source.stem
            conn.execute("CREATE INDEX idx_dsl_folded ON words(folded)")
            stat = source.stat()
            meta = {
                "schema": str(SCHEMA_VERSION),
                "size": str(stat.st_size),
                "mtime_ns": str(stat.st_mtime_ns),
                "entries": str(total),
                "attrs": json.dumps(attrs, ensure_ascii=False),
            }
            conn.executemany("INSERT INTO meta VALUES(?, ?)", list(meta.items()))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        os.replace(tmp, sidecar)

    def _meta(self, key: str) -> str:
        try:
            row = self._conn.execute(
                "SELECT value FROM meta WHERE key = ?", (key,)
            ).fetchone()
            return str(row[0]) if row else ""
        except sqlite3.Error:
            return ""

    def find_folded(self, folded: str) -> str | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT body FROM words WHERE folded = ? ORDER BY record LIMIT 1",
                (folded,),
            ).fetchone()
        if row is None:
            return None
        try:
            return zlib.decompress(row[0]).decode("utf-8", "replace")
        except zlib.error:
            return None

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
            for key, offset in conn.execute("SELECT key, record FROM words ORDER BY record"):
                yield str(key), int(offset)
        except sqlite3.Error:
            return
        finally:
            conn.close()

    def close(self) -> None:
        try:
            self._conn.close()
        except sqlite3.Error as exc:
            log.debug("关闭 DSL 索引失败: %s", exc)


class KeyView:
    def __init__(self, index: DslIndex) -> None:
        self._index = index

    def __iter__(self):
        return self._index.iter_keys()

    def __len__(self) -> int:
        return self._index.entry_count
