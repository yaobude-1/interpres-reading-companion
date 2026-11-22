"""词条模糊搜索：前缀 + 重音归一 + 编辑距离。

MDX 只有一张扁平的词条表，没有索引。这里在内存里建一份「规范化 → 原词条」
的排序数组，前缀用二分查找（<1ms），拼写纠错只在首字母相同的小桶里扫
（法语约 2.7k 词 3ms，英语约 10k 词 7ms），足够做输入即搜。
"""

from __future__ import annotations

import bisect
import unicodedata

__all__ = ["normalize", "FuzzyIndex", "build_index"]


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
        for key in keys:
            norm = normalize(key)
            if norm and norm not in mapping:
                mapping[norm] = key
        self._mapping = mapping
        self._sorted = sorted(mapping)

    def __len__(self) -> int:
        return len(self._sorted)

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
                    if norm in seen:
                        continue
                    if _damerau(norm, query, distance) <= distance:
                        seen[self._mapping[norm]] = level
                if len(seen) >= limit * 2:
                    break

        ranked = sorted(
            seen.items(),
            key=lambda item: (item[1], len(item[0]), item[0].lower()),
        )
        return ranked[:limit]


def build_index(dictionary) -> FuzzyIndex | None:
    """给 Dictionary 建（或取缓存的）模糊索引。"""
    if dictionary is None:
        return None
    cached = getattr(dictionary, "_fuzzy_index", None)
    if cached is not None:
        return cached
    try:
        keys = [key for key, _offset in dictionary._mdx._keys]
    except Exception:
        return None
    index = FuzzyIndex(keys)
    dictionary._fuzzy_index = index
    return index
