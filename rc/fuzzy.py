"""词条模糊搜索：前缀 + 重音归一 + 编辑距离。

MDX 只有一张扁平的词条表，没有索引。这里在内存里建一份「规范化 → 原词条」
的排序数组，前缀用二分查找（<1ms），拼写纠错只在首字母相同的小桶里扫
（法语约 2.7k 词 3ms，英语约 10k 词 7ms），足够做输入即搜。
"""

from __future__ import annotations

import bisect
import gzip
import logging
import os
import struct
import tempfile
import threading
import unicodedata
from pathlib import Path

log = logging.getLogger("rc")

__all__ = ["normalize", "FuzzyIndex", "build_index"]

_FUZZY_VERSION = 2
_FUZZY_MAGIC = b"RCFZ2\0"


def normalize(text: str) -> str:
    """小写 + 去重音：têt → tet，Test → test。"""
    if not text:
        return ""
    folded = unicodedata.normalize("NFKD", text.lower())
    stripped = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return " ".join(stripped.split())


def _damerau(a: str, b: str, limit: int) -> int:
    """带相邻换位的编辑距离（tset → test 记为 1），超过 limit 提前返回。"""
    if a == b:
        return 0
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    la, lb = len(a), len(b)
    prev2: list[int] | None = None
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        best = i
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if (
                prev2 is not None
                and i > 1
                and j > 1
                and a[i - 1] == b[j - 2]
                and a[i - 2] == b[j - 1]
            ):
                cur[j] = min(cur[j], prev2[j - 2] + 1)
            best = min(best, cur[j])
        if best > limit:
            return limit + 1
        prev2, prev = prev, cur
    return prev[lb]


class FuzzyIndex:
    """一本词典的模糊索引。构建一次，之后查询都是毫秒级。"""

    def __init__(self, keys) -> None:
        mapping: dict[str, str] = {}
        by_norm: dict[str, list[str]] = {}
        for key in keys:
            norm = normalize(key)
            if not norm:
                continue
            by_norm.setdefault(norm, []).append(key)
            if norm not in mapping:
                mapping[norm] = key
        self._mapping = mapping
        self._by_norm = by_norm
        self._sorted = sorted(mapping)

    @classmethod
    def from_rows(cls, rows) -> "FuzzyIndex":
        """Build from pre-normalized ``(normalized, original)`` rows."""
        mapping: dict[str, str] = {}
        by_norm: dict[str, list[str]] = {}
        for norm, original in rows:
            norm = str(norm)
            original = str(original)
            by_norm.setdefault(norm, []).append(original)
            if norm not in mapping:
                mapping[norm] = original
        self = cls.__new__(cls)
        self._mapping = mapping
        self._by_norm = by_norm
        self._sorted = sorted(mapping)
        return self

    def __len__(self) -> int:
        return len(self._sorted)

    def exact_matches(self, query: str) -> list[str]:
        """所有规范化后与 query 相同的原词条：creer → créer。"""
        return list(self._by_norm.get(normalize(query), []))

    def _prefix(self, query: str) -> list[str]:
        start = bisect.bisect_left(self._sorted, query)
        out: list[str] = []
        index = start
        while index < len(self._sorted) and self._sorted[index].startswith(query):
            out.append(self._sorted[index])
            index += 1
        return out

    def _bucket(self, query: str) -> list[str]:
        """同一首字母的那一段词条。"""
        if not query:
            return []
        start = bisect.bisect_left(self._sorted, query[0])
        end = bisect.bisect_left(self._sorted, chr(ord(query[0]) + 1))
        return self._sorted[start:end]

    def search(self, query: str, limit: int = 20) -> list[tuple[str, int]]:
        """返回 [(原词条, 匹配等级)]，等级越小越接近。

        0 = 完全相同，1 = 前缀，2/3 = 编辑距离 1/2（含相邻换位）。
        """
        query = normalize(query)
        if not query:
            return []
        seen: dict[str, int] = {}

        exact = self._mapping.get(query)
        if exact is not None:
            seen[exact] = 0

        for norm in self._prefix(query):
            original = self._mapping[norm]
            seen.setdefault(original, 1)
            if len(seen) >= limit * 3:
                break

        if len(seen) < limit:
            for distance, level in ((1, 2), (2, 3)):
                for norm in self._bucket(query):
                    original = self._mapping[norm]
                    if original in seen:
                        continue
                    if _damerau(norm, query, distance) <= distance:
                        seen[original] = level
                if len(seen) >= limit * 2:
                    break

        ranked = sorted(
            seen.items(),
            key=lambda item: (item[1], len(item[0]), item[0].lower()),
        )
        return ranked[:limit]


def build_index(dictionary) -> FuzzyIndex | None:
    """给 Dictionary 建（或取缓存/磁盘缓存的）模糊索引。"""
    if dictionary is None:
        return None
    cached = getattr(dictionary, "_fuzzy_index", None)
    if cached is not None:
        return cached
    lock = getattr(dictionary, "_fuzzy_lock", None)
    if lock is None:
        lock = threading.Lock()
        dictionary._fuzzy_lock = lock
    with lock:
        cached = getattr(dictionary, "_fuzzy_index", None)
        if cached is not None:
            return cached
        mdx = getattr(dictionary, "_mdx", None)
        cache_path = _cache_path(mdx)
        if cache_path is not None:
            index = _load_cache(cache_path, mdx)
            if index is not None:
                dictionary._fuzzy_index = index
                return index
        try:
            keys = [key for key, _offset in mdx._keys]
        except Exception:
            return None
        index = FuzzyIndex(keys)
        dictionary._fuzzy_index = index
        if cache_path is not None:
            _save_cache(cache_path, mdx, index)
        return index


def _cache_path(mdx) -> Path | None:
    path = getattr(mdx, "path", None)
    if path is None:
        return None
    path = Path(path)
    candidate = path.with_name(path.name + ".rcfuzzy")
    try:
        candidate.parent.mkdir(parents=True, exist_ok=True)
        if os.access(candidate.parent, os.W_OK):
            return candidate
    except OSError:
        pass
    root = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    fallback = Path(root) / "Interpres" / "dict-index"
    try:
        fallback.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    import hashlib

    digest = hashlib.sha1(str(path).encode("utf-8", "replace")).hexdigest()[:16]
    return fallback / f"{digest}.rcfuzzy"


def _stat_key(mdx) -> tuple[int, int]:
    stat = Path(mdx.path).stat()
    return stat.st_size, stat.st_mtime_ns


def _load_cache(cache_path: Path, mdx) -> FuzzyIndex | None:
    try:
        with gzip.open(cache_path, "rb") as fh:
            if fh.read(len(_FUZZY_MAGIC)) != _FUZZY_MAGIC:
                return None
            header = fh.read(24)
            if len(header) != 24:
                return None
            version, size, mtime_ns = struct.unpack(">QQQ", header)
            if version != _FUZZY_VERSION or (size, mtime_ns) != _stat_key(mdx):
                return None
            count_raw = fh.read(8)
            if len(count_raw) != 8:
                return None
            count = struct.unpack(">Q", count_raw)[0]

            def rows():
                for _ in range(int(count)):
                    norm = _read_text(fh)
                    original = _read_text(fh)
                    if norm is None or original is None:
                        raise ValueError("truncated fuzzy cache")
                    yield norm, original

            return FuzzyIndex.from_rows(rows())
    except Exception as exc:  # noqa: BLE001 - corrupt cache must not break lookup
        log.debug("模糊索引缓存读取失败 %s: %s", cache_path, exc)
        return None


def _read_text(fh) -> str | None:
    raw_len = fh.read(4)
    if len(raw_len) != 4:
        return None
    length = struct.unpack(">I", raw_len)[0]
    data = fh.read(length)
    if len(data) != length:
        return None
    return data.decode("utf-8", "surrogatepass")


def _save_cache(cache_path: Path, mdx, index: FuzzyIndex) -> None:
    tmp = cache_path.with_name(cache_path.name + f".{os.getpid()}.tmp")
    try:
        size, mtime_ns = _stat_key(mdx)
        total = sum(len(originals) for originals in index._by_norm.values())
        with gzip.open(tmp, "wb", compresslevel=3) as fh:
            fh.write(_FUZZY_MAGIC)
            fh.write(struct.pack(">QQQ", _FUZZY_VERSION, size, mtime_ns))
            fh.write(struct.pack(">Q", total))
            for norm, originals in index._by_norm.items():
                norm_bytes = norm.encode("utf-8", "surrogatepass")
                for original in originals:
                    original_bytes = original.encode("utf-8", "surrogatepass")
                    fh.write(struct.pack(">I", len(norm_bytes)))
                    fh.write(norm_bytes)
                    fh.write(struct.pack(">I", len(original_bytes)))
                    fh.write(original_bytes)
        os.replace(tmp, cache_path)
    except (OSError, struct.error, ValueError) as exc:
        log.debug("模糊索引缓存写入失败 %s: %s", cache_path, exc)
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
