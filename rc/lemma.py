"""词形还原：把变形词还原成词典里可能收录的原形。

只做本地规则，不调用模型。英语覆盖最好；法语、拉丁语覆盖常见规则。
"""

from __future__ import annotations

import re

IRREGULAR = {
    # 动词
    "am": "be", "is": "be", "are": "be", "was": "be", "were": "be", "been": "be", "being": "be",
    "has": "have", "had": "have", "having": "have",
    "does": "do", "did": "do", "done": "do", "doing": "do",
    "goes": "go", "went": "go", "gone": "go",
    "says": "say", "said": "say",
    "made": "make",
    "took": "take", "taken": "take",
    "came": "come",
    "saw": "see", "seen": "see",
    "knew": "know", "known": "know",
    "got": "get", "gotten": "get",
    "gave": "give", "given": "give",
    "found": "find",
    "thought": "think",
    "told": "tell",
    "became": "become",
    "shown": "show",
    "left": "leave",
    "felt": "feel",
    "brought": "bring",
    "began": "begin", "begun": "begin",
    "kept": "keep",
    "held": "hold",
    "wrote": "write", "written": "write",
    "stood": "stand",
    "heard": "hear",
    "meant": "mean",
    "met": "meet",
    "ran": "run",
    "paid": "pay",
    "sat": "sit",
    "spoke": "speak", "spoken": "speak",
    "led": "lead",
    "grew": "grow", "grown": "grow",
    "lost": "lose",
    "fell": "fall", "fallen": "fall",
    "sent": "send",
    "built": "build",
    "understood": "understand",
    "drew": "draw", "drawn": "draw",
    "broke": "break", "broken": "break",
    "spent": "spend",
    "rose": "rise", "risen": "rise",
    "drove": "drive", "driven": "drive",
    "bought": "buy",
    "wore": "wear", "worn": "wear",
    "chose": "choose", "chosen": "choose",
    "ate": "eat", "eaten": "eat",
    "fought": "fight",
    "flew": "fly", "flown": "fly",
    "taught": "teach",
    "caught": "catch",
    "sang": "sing", "sung": "sing",
    "slept": "sleep",
    "swam": "swim", "swum": "swim",
    "threw": "throw", "thrown": "throw",
    "won": "win",
    "forgot": "forget", "forgotten": "forget",
    "sought": "seek",
    "sold": "sell",
    "shook": "shake", "shaken": "shake",
    # 名词复数
    "men": "man", "women": "woman", "children": "child", "people": "person",
    "mice": "mouse", "feet": "foot", "teeth": "tooth", "geese": "goose",
    "lives": "life", "knives": "knife", "wives": "wife", "leaves": "leaf",
    "halves": "half", "selves": "self", "wolves": "wolf",
    "analyses": "analysis", "crises": "crisis", "theses": "thesis",
    "phenomena": "phenomenon", "criteria": "criterion", "data": "datum",
    "media": "medium", "indices": "index", "matrices": "matrix",
}

_VOWELS = "aeiou"


def _is_consonant(ch: str) -> bool:
    return ch.isalpha() and ch not in _VOWELS


def english_candidates(word: str) -> list[str]:
    word = word.lower()
    out: list[str] = []
    if word in IRREGULAR:
        out.append(IRREGULAR[word])

    def add(value: str) -> None:
        if value and value != word and len(value) >= 2 and value not in out:
            out.append(value)

    if word.endswith("ies") and len(word) > 4:
        add(word[:-3] + "y")
    if word.endswith("ves") and len(word) > 4:
        add(word[:-3] + "f")
        add(word[:-3] + "fe")
    if word.endswith("es") and len(word) > 3:
        add(word[:-2])
        add(word[:-1])
    elif word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        add(word[:-1])
    if word.endswith("ied") and len(word) > 4:
        add(word[:-3] + "y")
    if word.endswith("ed") and len(word) > 3:
        add(word[:-2])
        add(word[:-1])
        if len(word) > 4 and word[-3] == word[-4]:
            add(word[:-3])
    if word.endswith("ing") and len(word) > 5:
        stem = word[:-3]
        add(stem)
        add(stem + "e")
        if len(stem) > 2 and stem[-1] == stem[-2]:
            add(stem[:-1])
    if word.endswith("ly") and len(word) > 4:
        add(word[:-2])
    if word.endswith("est") and len(word) > 5:
        add(word[:-3])
        add(word[:-3] + "e")
    elif word.endswith("er") and len(word) > 4:
        add(word[:-2])
        add(word[:-2] + "e")
    # 大写专名也试小写
    add(word.lower())
    return out


def french_candidates(word: str) -> list[str]:
    word = word.lower()
    out: list[str] = []
    for suffix in ("s", "x", "es", "ent", "ez", "ons", "ais", "ait", "aient", "é", "ée", "és", "ées", "er", "ir", "re"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            stem = word[: -len(suffix)]
            if stem not in out:
                out.append(stem)
            if suffix in ("ent", "ez", "ons", "ais", "ait", "aient"):
                if (stem + "er") not in out:
                    out.append(stem + "er")
                if (stem + "ir") not in out:
                    out.append(stem + "ir")
    return out


def latin_candidates(word: str) -> list[str]:
    word = word.lower()
    out: list[str] = []

    def add(value: str) -> None:
        if value and value != word and len(value) >= 2 and value not in out:
            out.append(value)

    endings = {
        "ibus": ["is", "us", "es"],
        "orum": ["us", "um", "a"],
        "arum": ["a"],
        "orum": ["us"],
        "em": ["is", "es", "us"],
        "es": ["is", "es", "a"],
        "is": ["is", "es"],
        "i": ["us", "um", "is"],
        "o": ["us", "um", "is"],
        "um": ["us", "um"],
        "a": ["a", "us", "is"],
        "ae": ["a"],
        "am": ["a"],
        "as": ["a"],
        "os": ["us", "os"],
        "us": ["us"],
        "e": ["is", "es"],
        "em": ["is"],
    }
    for suffix, stems in endings.items():
        if word.endswith(suffix) and len(word) - len(suffix) >= 2:
            base = word[: -len(suffix)]
            for stem in stems:
                add(base + stem)
    return out


def candidates(word: str, lang: str) -> list[str]:
    """按语言给出一串可能匹配的词形。"""
    text = (word or "").strip()
    if not text:
        return []
    lowered = text.lower()
    if lang == "en":
        return english_candidates(lowered)
    if lang in ("fr", "de", "es", "it"):
        return french_candidates(lowered)
    if lang == "la":
        return latin_candidates(lowered)
    return [lowered]


def strip_word(text: str) -> str:
    """去掉首尾标点，只留单词本体。"""
    return re.sub(r"^[^\w\u00c0-\u024f]+|[^\w\u00c0-\u024f]+$", "", (text or "").strip())
