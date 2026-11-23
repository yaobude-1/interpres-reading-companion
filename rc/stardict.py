"""StarDict (.ifo + .idx + .dict[.dz]) reader.

Used for dictionaries that are not distributed as MDX/MDD, e.g. the
Liddell-Scott Greek lexicon.  StarDict is a simple key-index format; the
``h``/``g`` payloads are HTML/Pango markup, so the original-layout WebView can
show them directly.
"""

from __future__ import annotations

import gzip
import re
import struct
from pathlib import Path

from .mdx import html_to_text


def _read_ifo(path: Path) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        attrs[key.strip()] = value.strip()
    return attrs


def _strip_pango(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    return (
        text.replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&amp;", "&")
    )


class StarDict:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if self.path.suffix.lower() == ".idx":
            self.path = self.path.with_suffix(".ifo")
        if self.path.suffix.lower() != ".ifo":
            self.path = self.path.with_suffix(".ifo")
        base = self.path.with_suffix("")
        self.attrs = _read_ifo(self.path)
        self.name = self.attrs.get("bookname") or base.name
        self.encoding = "UTF-8"
        self.version = "StarDict"
        self.encrypted = "No"
        self.entry_count = int(self.attrs.get("wordcount") or 0)
        self._keys: list[str] = []
        self._records: list[tuple[int, int]] = []
        self._index: dict[str, int] = {}
        self._aliases: dict[str, int] = {}
        self._items: bytes | None = None
        self._load_index(base)
        self._load_syn(base)

    # ------------------------------------------------------------------ 索引
    def _load_index(self, base: Path) -> None:
        idx = Path(str(base) + ".idx")
        raw = idx.read_bytes()
        pos = 0
        while pos < len(raw):
            end = raw.find(b"\x00", pos)
            if end < 0 or end + 9 > len(raw):
                break
            word = raw[pos:end].decode("utf-8", "replace")
            offset, size = struct.unpack(">II", raw[end + 1 : end + 9])
            self._keys.append(word)
            self._records.append((offset, size))
            self._index.setdefault(word.lower(), len(self._records) - 1)
            pos = end + 9
        if not self.entry_count:
            self.entry_count = len(self._keys)

    def _load_syn(self, base: Path) -> None:
        syn = Path(str(base) + ".syn")
        if not syn.exists():
            return
        try:
            raw = syn.read_bytes()
        except OSError:
            return
        pos = 0
        while pos < len(raw):
            end = raw.find(b"\x00", pos)
            if end < 0 or end + 5 > len(raw):
                break
            word = raw[pos:end].decode("utf-8", "replace")
            index = struct.unpack(">I", raw[end + 1 : end + 5])[0]
            if index < len(self._records):
                self._aliases.setdefault(word.lower(), index)
            pos = end + 5

    # ------------------------------------------------------------------ 数据
    def _data(self, base: Path) -> bytes:
        if self._items is not None:
            return self._items
        dz = Path(str(base) + ".dict.dz")
        plain = Path(str(base) + ".dict")
        if dz.exists():
            with gzip.open(dz, "rb") as f:
                self._items = f.read()
        elif plain.exists():
            self._items = plain.read_bytes()
        else:
            self._items = b""
        return self._items

    def _record(self, index: int) -> str | None:
        if index < 0 or index >= len(self._records):
            return None
        offset, size = self._records[index]
        data = self._data(self.path.with_suffix(""))[offset : offset + size]
        if not data:
            return None
        sequence = self.attrs.get("sametypesequence") or ""
        if sequence:
            kind = sequence[0]
            return self._decode_field(kind, data)
        kind = chr(data[0])
        payload = data[1:]
        return self._decode_field(kind, payload)

    @staticmethod
    def _decode_field(kind: str, data: bytes) -> str:
        text = data.decode("utf-8", "replace")
        if kind in ("m", "l", "t", "x"):
            return html_to_text(text)
        if kind == "g":
            return _strip_pango(text)
        return text

    def lookup(self, word: str) -> str | None:
        key = (word or "").strip()
        if not key:
            return None
        index = self._index.get(key.lower())
        if index is None:
            index = self._aliases.get(key.lower())
        if index is None:
            return None
        return self._record(index)

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
            source=self.name,
        )

    def close(self) -> None:
        self._items = None
