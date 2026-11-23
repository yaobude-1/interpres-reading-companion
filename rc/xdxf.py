"""XDXF (.xdxf / .xdxf.dz) reader.

XDXF is an XML dictionary exchange format.  We keep the markup readable in the
original view by translating its common tags to HTML.
"""

from __future__ import annotations

import gzip
import html
import xml.etree.ElementTree as ET
from pathlib import Path

from .mdx import html_to_text


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _render(node) -> str:
    tag = _local(node.tag)
    children = "".join(_render(child) for child in node)
    text = html.escape(node.text or "")
    tail = html.escape(node.tail or "")
    if tag in ("k", "b", "strong"):
        inner = f"<b>{text}{children}</b>"
    elif tag in ("i", "em"):
        inner = f"<i>{text}{children}</i>"
    elif tag in ("u",):
        inner = f"<u>{text}{children}</u>"
    elif tag in ("br",):
        inner = f"<br>{text}{children}"
    elif tag in ("tr", "ex", "dtrn", "co", "c", "def", "ar"):
        inner = f'<span class="xdxf-{tag}">{text}{children}</span>'
    else:
        inner = f"{text}{children}"
    return inner + tail


class XDXF:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.attrs = {"Title": self.path.stem}
        self.encoding = "UTF-8"
        self.version = "XDXF"
        self.encrypted = "No"
        self._keys: list[str] = []
        self._bodies: list[str] = []
        self._index: dict[str, int] = {}
        raw = gzip.open(self.path, "rb").read() if self.path.name.lower().endswith(".gz") else self.path.read_bytes()
        root = ET.fromstring(raw)
        for article in root.iter():
            if _local(article.tag) != "ar":
                continue
            key_node = next((n for n in article if _local(n.tag) == "k"), None)
            if key_node is None:
                continue
            word = "".join(key_node.itertext()).strip()
            if not word:
                continue
            body = []
            for child in article:
                if _local(child.tag) == "k":
                    continue
                body.append(_render(child))
            html_body = "".join(body)
            index = len(self._keys)
            self._keys.append(word)
            self._bodies.append(f'<div class="xdxf-entry">{html_body}</div>')
            self._index.setdefault(word.lower(), index)
        self.entry_count = len(self._keys)

    def lookup(self, word: str) -> str | None:
        index = self._index.get((word or "").strip().lower())
        if index is None:
            return None
        return self._bodies[index]

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
        self._bodies.clear()
