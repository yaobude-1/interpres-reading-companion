"""Dictd (.index + .dict/.dict.dz) reader.

Dictd is a simple table: the index is ``headword<TAB>offset<TAB>size`` and the
data file is usually gzip-compressed.  Entries are plain text, so the original
view shows them in a readable ``pre`` block.
"""

from __future__ import annotations

import gzip
import html
from pathlib import Path

from .mdx import html_to_text


class Dictd:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        base = self.path.with_suffix("")
        self.attrs = {"Title": base.name}
        self.encoding = "UTF-8"
        self.version = "Dictd"
        self.encrypted = "No"
        self._keys: list[str] = []
        self._records: list[tuple[int, int]] = []
        self._index: dict[str, int] = {}
        self._data: bytes | None = None
        self._load_index()
        self.entry_count = len(self._records)

    def _load_index(self) -> None:
        for line in self.path.read_text(encoding="utf-8", errors="replace").splitlines():
            parts = line.split("\t")
            if len(parts) < 3:
                parts = line.rsplit(None, 2)
            if len(parts) != 3:
                continue
            word = parts[0].strip()
            try:
                offset, size = int(parts[1]), int(parts[2])
            except ValueError:
                continue
            self._keys.append(word)
            self._records.append((offset, size))
            self._index.setdefault(word.lower(), len(self._records) - 1)

    def _data_bytes(self) -> bytes:
        if self._data is None:
            base = self.path.with_suffix("")
            dz = Path(str(base) + ".dict.dz")
            plain = Path(str(base) + ".dict")
            if dz.exists():
                with gzip.open(dz, "rb") as f:
                    self._data = f.read()
            elif plain.exists():
                self._data = plain.read_bytes()
            else:
                self._data = b""
        return self._data

    def lookup(self, word: str) -> str | None:
        index = self._index.get((word or "").strip().lower())
        if index is None:
            return None
        offset, size = self._records[index]
        data = self._data_bytes()[offset : offset + size]
        if not data:
            return None
        text = data.decode("utf-8", "replace")
        return f'<div class="dictd-entry"><pre>{html.escape(text)}</pre></div>'

    def keys_matching(self, prefix: str, limit: int = 10) -> list[str]:
        prefix = (prefix or "").lower()
        out = []
        for key in self._keys:
            if key.lower().startswith(prefix):
                out.append(key)
                if len(out) >= limit:
                    break
        return out

    def entry(self, word: str):
        from .dictionary import DictEntry, Sense

        raw = self.lookup(word)
        if not raw:
            return None
        text = html_to_text(raw).strip()
        if not text:
            return None
        return DictEntry(
            word=word,
            senses=[Sense(definition=text[:4000])],
            source=self.attrs.get("Title") or self.path.stem,
        )

    def close(self) -> None:
        self._data = None
