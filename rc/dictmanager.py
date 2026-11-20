"""词典管理器：按语种加载 MDX/MDD，提供查词和缓存。"""

from __future__ import annotations

import threading
from pathlib import Path

from .dictionary import Dictionary, DictEntry


class DictionaryManager:
    def __init__(self, config) -> None:
        self.config = config
        self._dicts: dict[str, Dictionary | None] = {}
        self._lock = threading.Lock()
        self._cache: dict[tuple[str, str], dict | None] = {}


    # ------------------------------------------------------------------ 加载
    def _paths(self, lang: str) -> tuple[str, str]:
        table = self.config.data.get("dictionaries") or {}
        entry = table.get(lang) or {}
        return str(entry.get("mdx") or ""), str(entry.get("mdd") or "")

    def dictionary(self, lang: str) -> Dictionary | None:
        with self._lock:
            if lang in self._dicts:
                return self._dicts[lang]
        mdx_path, mdd_path = self._paths(lang)
        dictionary = None
        if mdx_path and Path(mdx_path).exists():
            try:
                from .dict_profiles import load_profiles

                profiles = load_profiles(self.config.data_dir / "dict_profiles")
                dictionary = Dictionary(mdx_path, mdd_path or None, profiles=profiles)
            except Exception:
                dictionary = None
        with self._lock:
            self._dicts[lang] = dictionary
        return dictionary

    def reload(self) -> None:
        with self._lock:
            for dictionary in self._dicts.values():
                if dictionary:
                    try:
                        dictionary.close()
                    except Exception:
                        pass
            self._dicts.clear()
            self._cache.clear()

    # ------------------------------------------------------------------ 查询
    def lookup(self, lang: str, word: str) -> dict | None:
        key_text = (word or "").strip()
        if not key_text:
            return None
        cache_key = (lang, key_text.lower())
        with self._lock:
            if cache_key in self._cache:
                return self._cache[cache_key]

        dictionary = self.dictionary(lang)
        result = None
        if dictionary is not None:
            entry = self._try_lookup(dictionary, key_text)
            if entry is not None:
                result = self._to_dict(entry, dictionary)
        with self._lock:
            if len(self._cache) > 2000:
                self._cache.clear()
            self._cache[cache_key] = result
        return result

    def lookup_full(self, lang: str, word: str) -> dict | None:
        """查词模式用：返回完整词条（多个义项 + 例句 + 音标 + 音频键）。"""
        dictionary = self.dictionary(lang)
        if dictionary is None:
            return None
        entry = self._try_lookup(dictionary, word)
        if entry is None:
            return None
        senses = []
        for sense in entry.senses:
            senses.append(
                {
                    "pos": getattr(sense, "pos", "") or entry.pos,
                    "definition": _short(sense.definition, 400),
                    "definition_cn": _short(sense.definition_cn, 400),
                    "example": _short(sense.example, 260),
                    "example_cn": _short(sense.example_cn, 260),
                }
            )
        return {
            "word": entry.word or word,
            "source": dictionary.name,
            "phonetic": entry.phonetic,
            "senses": senses,
            "audio_key": entry.audio_keys[0] if entry.audio_keys else "",
        }

    def _try_lookup(self, dictionary: Dictionary, word: str) -> DictEntry | None:
        candidates = [word]
        stripped = word.strip(".,;:!?\"'()[]{}")
        if stripped != word:
            candidates.append(stripped)
        # 拉丁语 lemma 是「amo, amare, amavi, amatum」，取第一段
        if "," in word:
            candidates.append(word.split(",")[0].strip())
        if "-" in word:
            candidates.append(word.split("-")[0])
        for candidate in candidates:
            if not candidate:
                continue
            entry = dictionary.lookup(candidate)
            if entry is not None:
                return entry
        return None

    def _to_dict(self, entry: DictEntry, dictionary: Dictionary) -> dict:
        example = entry.first_example()
        return {
            "source": dictionary.name,
            "phonetic": entry.phonetic,
            "pos": entry.pos,
            "definition": _short(entry.definition_cn or entry.definition_en, 220),
            "definition_cn": _short(entry.definition_cn, 220),
            "definition_en": _short(entry.definition_en, 220),
            "example": _short(example.example, 180) if example else "",
            "example_cn": _short(example.example_cn, 180) if example else "",
            "audio_key": entry.audio_keys[0] if entry.audio_keys else "",
        }

    def audio(self, lang: str, sound_key: str) -> bytes | None:
        dictionary = self.dictionary(lang)
        if dictionary is None or not sound_key:
            return None
        try:
            return dictionary.audio(sound_key)
        except Exception:
            return None

    # ------------------------------------------------------------------ 状态
    def capabilities(self, lang: str) -> dict:
        dictionary = self.dictionary(lang)
        if dictionary is None:
            return {}
        try:
            return dictionary.capabilities()
        except Exception:
            return {}

    def describe(self, lang: str) -> str:
        mdx_path, _mdd = self._paths(lang)
        if not mdx_path:
            return "未配置"
        if not Path(mdx_path).exists():
            return "文件不存在"
        caps = self.capabilities(lang)
        if not caps:
            return "读取失败"
        marks = []
        if caps.get("phonetic"):
            marks.append("音标")
        if caps.get("definition_cn"):
            marks.append("中文释义")
        elif caps.get("definition_en"):
            marks.append("英文释义")
        if caps.get("example"):
            marks.append("例句")
        if caps.get("audio"):
            marks.append("发音")
        name = Path(mdx_path).stem
        return f"{name}（{'/'.join(marks) or '基础'}）"


def _short(text: str | None, limit: int) -> str:
    """截断长释义/长例句，尽量断在分号或句号处。"""
    value = (text or "").strip()
    if len(value) <= limit:
        return value
    cut = value[:limit]
    for sep in (";", "；", "。"):
        idx = cut.rfind(sep)
        if idx > limit // 3:
            return cut[: idx + 1]
    return cut.rsplit(" ", 1)[0] + "…"
