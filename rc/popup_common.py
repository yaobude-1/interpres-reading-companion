"""Small helpers shared by the popup mixins."""

from __future__ import annotations

# 词典名字保留原样，只在过长时截断；不做「Longman → 朗文」这类中英两套别名。
_MAX_SOURCE_CHARS = 44


def source_label(name: str) -> str:
    text = " ".join(str(name or "").split())
    if len(text) <= _MAX_SOURCE_CHARS:
        return text
    return text[: _MAX_SOURCE_CHARS - 1] + "…"
