"""翻译/分块共用的常量与小工具。"""

from __future__ import annotations

import re


# 同一个词在不同书里出现时，context 会影响结果，所以 key 里带上上下文摘要
CACHE_VERSION = "v2"
CHUNK_CHARS = 1200
CHAT_PERSONA_DEFAULT = (
    "你是一位阅读伙伴，正在陪用户精读一本书，回答要具体、贴近原文。\n书名：{book}"
)
CHAT_RULES_DEFAULT = (
    "回答要求：\n"
    "1. 用中文，结合原文说，必要时引用原句；\n"
    "2. 不要编造书里没写的内容，不确定就直接说不确定；\n"
    "3. 回答简洁，别写成论文；\n"
    "4. 如果只看到选中的单词、没有所在句子的上下文，先给出词义、词性和常见搭配，"
    "再明确说明你看不到书中原句，请用户补充前后一句；不要只回“我无法判断”。"
)
TRANSLATE_WORKERS = 4  # 超过这个长度就分段翻译，避免超出模型输出上限

_SENTENCE_END = ".!?。！？…\"'”’"
_SENTENCE_START = "“\"'（《「¡¿"


def _ends_sentence(text: str, idx: int | None = None) -> bool:
    """idx 之前的最后一个非空字符是不是句末标点（idx 省略则看结尾）。"""
    i = (len(text) if idx is None else idx) - 1
    while i >= 0 and text[i] in " \t\r\n":
        i -= 1
    return i < 0 or text[i] in _SENTENCE_END


def _starts_sentence(text: str, idx: int = 0) -> bool:
    i = idx
    while i < len(text) and text[i] in " \t\r\n":
        i += 1
    if i >= len(text):
        return True
    ch = text[i]
    return ch.isupper() or ch in _SENTENCE_START


def _tsv(value: str) -> str:
    return (value or "").replace("\t", " ").replace("\r", " ").replace("\n", " ")


def split_chunks(text: str, limit: int = CHUNK_CHARS) -> list[str]:
    """按段落把长文本切成不超过 limit 的块；超长段落再按句子切。"""
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    current = ""
    for para in text.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        if len(para) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split_long_paragraph(para, limit))
            continue
        candidate = f"{current}\n\n{para}" if current else para
        if current and len(candidate) > limit:
            chunks.append(current)
            current = para
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks or [text]


def _split_long_paragraph(paragraph: str, limit: int) -> list[str]:
    parts = re.split(r"(?<=[。！？!?；;])\s*", paragraph)
    out: list[str] = []
    current = ""
    for part in parts:
        if current and len(current) + len(part) > limit:
            out.append(current)
            current = part
        else:
            current += part
    if current:
        out.append(current)
    final: list[str] = []
    for chunk in out:
        while len(chunk) > limit:
            final.append(chunk[:limit])
            chunk = chunk[limit:]
        if chunk:
            final.append(chunk)
    return final


def _english_mode() -> bool:
    try:
        from . import i18n

        return i18n.LANGUAGE == "en"
    except Exception:
        return False
