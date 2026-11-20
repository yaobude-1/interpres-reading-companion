"""文本清洗工具。

从 PDF / EPUB 阅读器复制出来的文字通常有两类问题：

1. 段落被硬换行切断（每行一个 \\n）；
2. 行尾连字符断词（``trans-\\nlation``）。

这里做保守的归一化：先拼回段落，再交给模型，避免模型把断行当成句读。
"""

from __future__ import annotations

import re
import unicodedata

LIGATURES = {
    "\ufb00": "ff",
    "\ufb01": "fi",
    "\ufb02": "fl",
    "\ufb03": "ffi",
    "\ufb04": "ffl",
    "\ufb05": "st",
    "\ufb06": "st",
}

_ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff"), None)

# 行尾连字符：字母 + 连字符 + 换行 + 字母
_HYPHEN_BREAK = re.compile(r"(\w)[\-\u2010\u2011\u2013]\s*\n\s*(\w)")

_CJK_RANGES = (
    (0x2E80, 0x9FFF),
    (0xF900, 0xFAFF),
    (0x3040, 0x30FF),  # 假名
    (0xAC00, 0xD7AF),  # 韩文
)


def is_cjk_char(ch: str) -> bool:
    if not ch:
        return False
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in _CJK_RANGES)


def has_cjk(text: str) -> bool:
    return any(is_cjk_char(c) for c in text)


def normalize(text: str) -> str:
    """把阅读器里复制出来的一段文字整理成适合翻译的段落。"""
    if not text:
        return ""
    t = unicodedata.normalize("NFC", text)
    t = t.translate(_ZERO_WIDTH)
    for src, dst in LIGATURES.items():
        t = t.replace(src, dst)

    t = t.replace("\r\n", "\n").replace("\r", "\n")
    t = t.replace("\u00a0", " ").replace("\t", " ")

    # 行尾连字符断词：合并成一个词
    t = _HYPHEN_BREAK.sub(r"\1\2", t)

    paragraphs: list[str] = []
    for block in re.split(r"\n\s*\n", t):
        lines = [ln.strip() for ln in block.split("\n")]
        lines = [ln for ln in lines if ln]
        if not lines:
            continue
        merged = lines[0]
        for nxt in lines[1:]:
            sep = "" if (is_cjk_char(merged[-1:]) or is_cjk_char(nxt[:1])) else " "
            merged += sep + nxt
        paragraphs.append(merged)

    out = "\n\n".join(paragraphs)
    out = re.sub(r"[ \u2009\u202f]{2,}", " ", out)
    return out.strip()


def display(text: str, limit: int = 160) -> str:
    """给界面用的单行摘要。"""
    t = re.sub(r"\s+", " ", (text or "").strip())
    return t if len(t) <= limit else t[: limit - 1] + "…"


def keyword_count(text: str) -> int:
    """粗略词数：拉丁文字按空格，CJK 按字。"""
    t = (text or "").strip()
    if not t:
        return 0
    if has_cjk(t):
        return len(re.sub(r"\s+", "", t))
    return len(t.split())


def looks_like_word(text: str) -> bool:
    """判断选中的是一个词/短语，而不是一整段。"""
    t = (text or "").strip()
    if not t:
        return False
    if has_cjk(t):
        return len(t) <= 12
    words = t.split()
    return len(words) <= 3 and len(t) <= 48


def slugify(text: str, limit: int = 40) -> str:
    """把书名变成 Anki 标签 / 文件名的安全形式。"""
    t = (text or "").strip()
    t = re.sub(r"[\x00-\x1f]", "", t)
    t = re.sub(r'[\\/:*?"<>|#^]', " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    t = t.replace(" ", "_")
    return (t[:limit] or "book")


def detect_script(text: str) -> str:
    """非常粗糙的书写系统判断，用于给模型一个提示（真正的语言识别交给模型）。"""
    t = text or ""
    if has_cjk(t):
        return "cjk"
    if re.search(r"[\u0400-\u04FF]", t):
        return "cyrillic"
    if re.search(r"[\u0370-\u03FF]", t):
        return "greek"
    if re.search(r"[\u0590-\u05FF]", t):
        return "hebrew"
    if re.search(r"[\u0600-\u06FF]", t):
        return "arabic"
    return "latin"
