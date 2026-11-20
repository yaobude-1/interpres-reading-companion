"""从词条 HTML 里快速取「词性 + 首义」，给搜索列表做预览。

不能用完整解析（英语一条 250ms），这里只做正则提取，1–3ms 一条；
取不到就返回空，列表照常显示单词本身。
"""

from __future__ import annotations

import re

__all__ = ["quick_gloss", "profile_of"]

_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")


def _plain(text: str) -> str:
    return _SPACE.sub(" ", _TAG.sub(" ", text or "")).strip()


def profile_of(html: str) -> str:
    if "ohd-entry" in html:
        return "ohd"
    if 'class="lm6"' in html or 'class="entry"' in html:
        return "longman"
    return "plain"


def _first(pattern: str, text: str) -> str:
    match = re.search(pattern, text, re.S)
    return _plain(match.group(1)) if match else ""


def _cut(text: str, limit: int = 80) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def quick_gloss(html: str, lang: str = "") -> tuple[str, str]:
    """返回 (词性, 首义)。"""
    if not html:
        return "", ""
    profile = profile_of(html)

    if profile == "longman":
        pos = _first(r'class="pos"[^>]*>([^<]{1,20})<', html)
        gloss = _first(r'class="def"[^>]*>(.*?)</span>', html)
        return _cut(pos, 16), _cut(gloss)

    if profile == "ohd":
        pos = _first(r'class="ohd-pos"[^>]*>([^<]{1,16})<', html)
        gloss = _first(r'class="ohd-sense-content"[^>]*>(.*?)</div>', html)
        if not gloss:
            gloss = _first(r'class="ohd-pos-content"[^>]*>(.*?)</div>', html)
        if not gloss:
            gloss = _first(r'class="ohd-body"[^>]*>(.*?)</div>', html)
        return _cut(pos, 12), _cut(gloss)

    # 拉丁：去掉词头和词源方括号，取第一句
    text = _plain(html)
    text = re.sub(r"\[[^\]]*\]", " ", text)
    text = _SPACE.sub(" ", text).strip()
    pos_match = re.search(r"\b(m|f|n|neut|m/f|m\.)\s*\.", text[:80])
    pos = pos_match.group(1) if pos_match else ""
    if pos_match:
        text = text[pos_match.end():]
    sentences = re.split(r"(?<=[.;])\s+", text.strip())
    gloss = sentences[0] if sentences else text
    gloss = re.sub(r"^[A-Z]\s+", "", gloss)
    return _cut(pos, 8), _cut(gloss)
