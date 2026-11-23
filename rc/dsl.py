"""ABBYY Lingvo DSL (.dsl / .dsl.dz) reader.

DSL entries are plain text with ``[tag]`` markup.  We keep the dictionary's
markup and turn it into HTML for the same WebView used by MDX/StarDict; the
simplified view gets a plain-text fallback.
"""

from __future__ import annotations

import gzip
import html
import re
from pathlib import Path
from urllib.parse import quote

from .mdx import html_to_text

_HEADER_RE = re.compile(r'^#([A-Z_]+)\s+"(.*)"\s*$')


def _decode(raw: bytes) -> str:
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16", "replace")
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig", "replace")
    return raw.decode("utf-8", "replace")


def _dsl_to_html(body: str) -> str:
    """Convert the common Lingvo tags to HTML, keeping readable layout."""
    text = html.escape(body)

    # Paragraphs are inline in Lingvo; only explicit [br] breaks a line.
    text = re.sub(r"\[p\]", '<span class="dsl-p">', text, flags=re.I)
    text = re.sub(r"\[/p\]", "</span>", text, flags=re.I)
    text = re.sub(r"\[br\]", "<br>", text, flags=re.I)

    # Inline formatting
    for tag in ("b", "i", "u", "s", "sub", "sup"):
        text = re.sub(rf"\[{tag}\]", f"<{tag}>", text, flags=re.I)
        text = re.sub(rf"\[/{tag}\]", f"</{tag}>", text, flags=re.I)

    # [c color] ... [/c]
    text = re.sub(
        r"\[c\s+([^\]]+)\]",
        lambda m: f'<span style="color:{html.escape(m.group(1).strip())}">',
        text,
        flags=re.I,
    )
    text = re.sub(r"\[/c\]", "</span>", text, flags=re.I)

    # [m1] / [m2] sense blocks
    text = re.sub(
        r"\[m\d*\]",
        '<div class="dsl-sense">',
        text,
        flags=re.I,
    )
    text = re.sub(r"\[/m\]", "</div>", text, flags=re.I)

    # Translation block
    text = re.sub(r"\[trn\]", '<div class="dsl-trn">', text, flags=re.I)
    text = re.sub(r"\[/trn\]", "</div>", text, flags=re.I)

    # Language spans
    text = re.sub(
        r"\[lang[^\]]*\]",
        '<span class="dsl-lang">',
        text,
        flags=re.I,
    )
    text = re.sub(r"\[/lang\]", "</span>", text, flags=re.I)

    # Cross references become internal links
    def _ref(match: re.Match) -> str:
        target = re.sub(r"<[^>]+>", "", match.group(1)).strip()
        return (
            f'<a class="dsl-ref" href="interpres://lookup?word={quote(target)}">'
            f"{match.group(1)}</a>"
        )

    text = re.sub(r"\[ref\](.*?)\[/ref\]", _ref, text, flags=re.I | re.S)

    # A few harmless inline tags and unknown containers
    text = re.sub(r"\[/?(?:m\d*|trn|lang[^\]]*|ref|p)\]", "", text, flags=re.I)
    text = re.sub(r"\[/?(?:ex|com|s|c|url|img)[^\]]*\]", "", text, flags=re.I)
    text = text.replace("\\[", "[").replace("\\]", "]")
    text = text.replace("\n", "<br>")
    return f'<div class="dsl-entry">{text}</div>'


class DSL:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._entries: list[tuple[str, str]] = []
        self._index: dict[str, int] = {}
        self._keys: list[str] = []
        self.attrs: dict[str, str] = {}
        self.encoding = "UTF-16"
        self.version = "DSL"
        self.encrypted = "No"
        self._load()

    def _read(self) -> str:
        name = self.path.name.lower()
        if name.endswith((".gz", ".dz")):
            with gzip.open(self.path, "rb") as f:
                return _decode(f.read())
        return _decode(self.path.read_bytes())

    def _load(self) -> None:
        text = self._read()
        lines = text.splitlines()
        current = ""
        body: list[str] = []
        for line in lines:
            if line.startswith("#"):
                m = _HEADER_RE.match(line)
                if m:
                    self.attrs[m.group(1)] = m.group(2)
                continue
            if not line.strip():
                continue
            if line[0] in " \t":
                if current:
                    body.append(line.strip())
                continue
            if current:
                self._add(current, "\n".join(body))
            current = line.strip()
            body = []
        if current:
            self._add(current, "\n".join(body))
        self.entry_count = len(self._entries)
        self.attrs["Title"] = self.attrs.get("NAME") or self.attrs.get("Title") or self.path.stem

    def _add(self, word: str, body: str) -> None:
        if not word:
            return
        index = len(self._entries)
        self._entries.append((word, body))
        self._keys.append(word)
        self._index.setdefault(word.lower(), index)

    def lookup(self, word: str) -> str | None:
        key = (word or "").strip()
        if not key:
            return None
        index = self._index.get(key.lower())
        if index is None:
            return None
        return _dsl_to_html(self._entries[index][1])

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
        self._entries.clear()
