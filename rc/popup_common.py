"""Small helpers shared by the popup mixins."""

from __future__ import annotations


def _short_source(name: str) -> str:
    """把词典名缩成卡片/浮窗上的小标签。"""
    text = (name or "").lower()
    for key, label in (
        ("朗文", "朗文"),
        ("longman", "朗文"),
        ("牛津", "牛津"),
        ("oxford", "牛津"),
        ("collins", "Collins"),
        ("vocabulary", "Vocabulary"),
        ("larousse", "Larousse"),
        ("robert", "Robert"),
    ):
        if key in text:
            return label
    return (name or "")[:8]
