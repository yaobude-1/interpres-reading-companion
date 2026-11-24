"""词典管理器：按语种加载多本 MDX/MDD/StarDict/DSL，提供查词和缓存。"""

from __future__ import annotations

import logging
import threading
import time
from copy import deepcopy
from pathlib import Path

from . import dict_config
from .dictionary import Dictionary, DictEntry

log = logging.getLogger("rc")


class DictionaryManager:
    def __init__(self, config) -> None:
        self.config = config
        # dict_id -> Dictionary (None = failed/missing)
        self._dicts: dict[str, Dictionary | None] = {}
        self._errors: dict[str, str] = {}
        self._lock = threading.RLock()
        self._cache: dict[tuple[str, str], dict | None] = {}
        self._raw_cache: dict[tuple[str, str], dict] = {}
        self._last_used: dict[str, float] = {}
        self._clock = time.time

    # ------------------------------------------------------------------ 加载
    def _items(
        self, lang: str, *, visible_only: bool = True, context: str = "panel"
    ) -> list[dict]:
        if visible_only:
            return dict_config.visible_items(self.config.data, lang, context)
        return dict_config.items(self.config.data, lang)

    def _load_item(self, lang: str, item: dict) -> Dictionary | None:
        item_id = str(item.get("id") or "")
        with self._lock:
            if item_id in self._dicts:
                return self._dicts[item_id]
        path = str(item.get("mdx") or "")
        dictionary = None
        error = ""
        if path and Path(path).exists():
            try:
                from .dict_profiles import load_profiles

                profiles = load_profiles(self.config.data_dir / "dict_profiles")
                dictionary = Dictionary(path, str(item.get("mdd") or "") or None, profiles=profiles)
                custom_name = str(item.get("name") or "").strip()
                if custom_name:
                    dictionary.name = custom_name
                dictionary.dict_id = item_id
            except Exception as exc:  # noqa: BLE001 - 单本失败不影响其它词典
                error = f"{type(exc).__name__}: {exc}"
                log.warning("加载词典失败 %s: %s", path, exc)
        elif path:
            error = "文件不存在"
        else:
            error = "未配置"
        with self._lock:
            self._dicts[item_id] = dictionary
            self._errors[item_id] = error
            if dictionary is not None:
                self._last_used[item_id] = self._clock()
        return dictionary

    def dictionaries(self, lang: str, context: str = "panel") -> list[Dictionary]:
        """当前可见（未静音）的词典，按用户顺序。"""
        out = []
        for item in self._items(lang, visible_only=True, context=context):
            dictionary = self._load_item(lang, item)
            if dictionary is not None:
                out.append(dictionary)
        return out

    def all_dictionaries(self, lang: str) -> list[tuple[dict, Dictionary | None]]:
        """给设置页用：包含静音项，返回 (item, dictionary) 列表。"""
        out = []
        for item in self._items(lang, visible_only=False):
            out.append((item, self._load_item(lang, item)))
        return out

    def dictionary(self, lang: str, context: str = "panel") -> Dictionary | None:
        """兼容旧代码：返回该语言第一本可见词典。"""
        dictionaries = self.dictionaries(lang, context)
        return dictionaries[0] if dictionaries else None

    def dictionary_by_id(self, dict_id: str) -> Dictionary | None:
        lang = dict_config.language_of(self.config.data, dict_id)
        if not lang:
            return None
        for item in self._items(lang, visible_only=False):
            if item.get("id") == dict_id:
                return self._load_item(lang, item)
        return None

    def language_of(self, dict_id: str) -> str:
        return dict_config.language_of(self.config.data, dict_id)

    def scripts_allowed(self, dict_id: str) -> bool:
        if not dict_id:
            return True
        return dict_config.scripts_allowed(self.config.data, dict_id)

    def default_id(self, lang: str) -> str:
        return dict_config.default_id(self.config.data, lang)

    def anki_dictionary(self, lang: str, stored_id: str = "") -> Dictionary | None:
        """Pick the dictionary used for Anki cards.

        Explicit Anki choice first, then the group's default, then the
        dictionary recorded when the word was saved, then the first visible.
        """
        candidates: list[str] = []
        for item_id in (
            dict_config.anki_id(self.config.data, lang),
            self.default_id(lang),
            stored_id,
        ):
            item_id = str(item_id or "").strip()
            if item_id and item_id not in candidates:
                candidates.append(item_id)
        for item_id in candidates:
            dictionary = self.dictionary_by_id(item_id)
            if dictionary is not None:
                return dictionary
        dictionaries = self.dictionaries(lang)
        return dictionaries[0] if dictionaries else None

    def reload(self) -> None:
        with self._lock:
            for dictionary in self._dicts.values():
                if dictionary:
                    try:
                        dictionary.close()
                    except Exception as exc:  # noqa: BLE001 - 单本关闭失败不影响重新加载
                        log.warning("关闭词典失败: %s", exc)
            self._dicts.clear()
            self._errors.clear()
            self._cache.clear()
            self._raw_cache.clear()
            self._last_used.clear()

    def release_idle(self, seconds: float = 300.0) -> int:
        """Close dictionaries that have not been used for a while."""
        cutoff = self._clock() - max(30.0, float(seconds))
        closed = 0
        with self._lock:
            for item_id, dictionary in list(self._dicts.items()):
                if dictionary is None:
                    continue
                if self._last_used.get(item_id, 0.0) >= cutoff:
                    continue
                try:
                    dictionary.close()
                except Exception as exc:  # noqa: BLE001 - 单本关闭失败不影响其它
                    log.debug("释放空闲词典失败 %s: %s", item_id, exc)
                self._dicts.pop(item_id, None)
                self._last_used.pop(item_id, None)
                self._cache = {
                    key: value for key, value in self._cache.items() if key[0] != item_id
                }
                self._raw_cache = {
                    key: value
                    for key, value in self._raw_cache.items()
                    if key[0] != item_id
                }
                closed += 1
        return closed

    # ------------------------------------------------------------------ 查询
    def lookup(self, lang: str, word: str) -> dict | None:
        key_text = (word or "").strip()
        if not key_text:
            return None
        dictionary = self.dictionary(lang)
        if dictionary is None:
            return None
        entry = self._try_lookup(dictionary, key_text)
        return self._to_dict(entry, dictionary) if entry is not None else None

    def lookup_with(self, dictionary: Dictionary, word: str) -> dict | None:
        entry = self._try_lookup(dictionary, word)
        return self._to_dict(entry, dictionary) if entry is not None else None

    def lookup_full(self, lang: str, word: str) -> dict | None:
        """兼容旧代码：查第一本可见词典。"""
        dictionary = self.dictionary(lang)
        if dictionary is None:
            return None
        return self.lookup_full_with(dictionary, word)

    def lookup_full_in(self, lang: str, dict_id: str, word: str) -> dict | None:
        dictionary = self.dictionary_by_id(dict_id)
        if dictionary is None:
            return None
        return self.lookup_full_with(dictionary, word)

    def lookup_full_with(self, dictionary: Dictionary, word: str) -> dict | None:
        """查词模式用：返回完整词条（多个义项 + 例句 + 音标 + 音频键）。"""
        cache_key = (
            str(getattr(dictionary, "dict_id", "") or id(dictionary)),
            (word or "").lower(),
        )
        with self._lock:
            if cache_key in self._cache:
                cached = self._cache[cache_key]
                self._last_used[str(getattr(dictionary, "dict_id", "") or id(dictionary))] = self._clock()
                return deepcopy(cached) if cached is not None else None
        self._last_used[str(getattr(dictionary, "dict_id", "") or id(dictionary))] = self._clock()
        entry = self._try_lookup(dictionary, word)
        if entry is None:
            with self._lock:
                self._cache[cache_key] = None
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
        result = {
            "word": entry.word or word,
            "source": dictionary.name,
            "dict_id": getattr(dictionary, "dict_id", ""),
            "phonetic": entry.phonetic,
            "senses": senses,
            "audio_key": entry.audio_keys[0] if entry.audio_keys else "",
        }
        with self._lock:
            if len(self._cache) > 2000:
                self._cache.clear()
            self._cache[cache_key] = deepcopy(result)
        return result

    @staticmethod
    def _raw_candidates(word: str) -> list[str]:
        candidates = [word]
        stripped = word.strip(".,;:!?\"'()[]{}")
        if stripped != word:
            candidates.append(stripped)
        if "," in word:
            candidates.append(word.split(",")[0].strip())
        return candidates

    def _raw_entry_with(self, dictionary: Dictionary, word: str) -> dict | None:
        dict_id = str(getattr(dictionary, "dict_id", "") or id(dictionary))
        cache_key = (dict_id, (word or "").lower())
        with self._lock:
            cached = self._raw_cache.get(cache_key)
            if cached is not None:
                self._last_used[dict_id] = self._clock()
                return dict(cached)
        self._last_used[dict_id] = self._clock()
        for candidate in self._raw_candidates(word):
            if not candidate:
                continue
            html = dictionary.raw(candidate)
            if html:
                result = {
                    "word": candidate,
                    "source": dictionary.name,
                    "dict_id": getattr(dictionary, "dict_id", ""),
                    "html": html,
                }
                with self._lock:
                    if len(self._raw_cache) > 120:
                        self._raw_cache.clear()
                    self._raw_cache[cache_key] = dict(result)
                return result
        return None

    def raw_entry(self, lang: str, word: str) -> dict | None:
        dictionary = self.dictionary(lang)
        if dictionary is None:
            return None
        return self._raw_entry_with(dictionary, word)

    def raw_entry_by_id(self, dict_id: str, word: str) -> dict | None:
        dictionary = self.dictionary_by_id(dict_id)
        if dictionary is None:
            return None
        return self._raw_entry_with(dictionary, word)

    def resource(self, lang: str, name: str) -> bytes | None:
        dictionary = self.dictionary(lang)
        if dictionary is None:
            return None
        return dictionary.resource(name)

    def resource_by_id(self, dict_id: str, name: str) -> bytes | None:
        dictionary = self.dictionary_by_id(dict_id)
        if dictionary is None:
            return None
        self._last_used[dict_id] = self._clock()
        return dictionary.resource(name)

    def audio(self, lang: str, sound_key: str) -> bytes | None:
        dictionary = self.dictionary(lang)
        if dictionary is None or not sound_key:
            return None
        try:
            return dictionary.audio(sound_key)
        except Exception:
            return None

    def audio_by_id(self, dict_id: str, sound_key: str) -> bytes | None:
        dictionary = self.dictionary_by_id(dict_id)
        if dictionary is None or not sound_key:
            return None
        self._last_used[dict_id] = self._clock()
        try:
            return dictionary.audio(sound_key)
        except Exception:
            return None

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
            "dict_id": getattr(dictionary, "dict_id", ""),
            "phonetic": entry.phonetic,
            "pos": entry.pos,
            "definition": _short(entry.definition_cn or entry.definition_en, 220),
            "definition_cn": _short(entry.definition_cn, 220),
            "definition_en": _short(entry.definition_en, 220),
            "example": _short(example.example, 180) if example else "",
            "example_cn": _short(example.example_cn, 180) if example else "",
            "audio_key": entry.audio_keys[0] if entry.audio_keys else "",
        }

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
        """兼容旧代码：描述第一本。"""
        items = self._items(lang, visible_only=False)
        if not items:
            return "未配置"
        return self.describe_item(items[0])

    def describe_item(self, item: dict) -> str:
        path = str(item.get("mdx") or "")
        if not path:
            return "未配置"
        if not Path(path).exists():
            return "文件不存在"
        dictionary = self._load_item(
            dict_config.language_of(self.config.data, str(item.get("id") or "")), item
        )
        if dictionary is None:
            error = self._errors.get(str(item.get("id") or ""), "")
            return f"读取失败（{error[:60]}）" if error else "读取失败"
        caps = {}
        try:
            caps = dictionary.capabilities()
        except Exception as exc:  # noqa: BLE001 - 能力探测失败不影响配置列表
            log.debug("探测词典能力失败: %s", exc)
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
        name = item.get("name") or dictionary.name
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
