"""用户自定义词形与变位表。

数据放在 <data-dir>/lang_data/<lang>.json，纯 JSON、不执行代码：

    {
      "forms": {"parlo": "parlare", "vado": "andare"},
      "tables": {
        "parlare": [
          {"key": "present", "zh": "现在时", "fr": "Presente",
           "rows": [["io", "parlo"], ["tu", "parli"]]}
        ]
      }
    }

`tables` 里每一行的第二个字段会自动进入反查索引，所以导入一张表
等于同时填好该表里所有形式的“变形 → 原形”。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger("rc")


def _clean_form(value) -> str:
    return str(value or "").strip()


def _clean_lemma(value) -> str:
    return str(value or "").strip()


def _normalize_group(group) -> dict | None:
    if not isinstance(group, dict):
        return None
    rows = []
    for row in group.get("rows") or []:
        if not isinstance(row, (list, tuple)) or len(row) != 2:
            continue
        person = _clean_form(row[0])
        form = _clean_form(row[1])
        if form:
            rows.append([person, form])
    if not rows:
        return None
    return {
        "key": str(group.get("key") or "").strip(),
        "zh": str(group.get("zh") or "").strip(),
        "fr": str(group.get("fr") or "").strip(),
        "rows": rows,
    }


def _normalize(data) -> dict:
    out = {"forms": {}, "tables": {}}
    if not isinstance(data, dict):
        return out
    forms = data.get("forms")
    if isinstance(forms, dict):
        for form, lemma in forms.items():
            key = _clean_form(form).lower()
            value = _clean_lemma(lemma)
            if key and value:
                out["forms"][key] = value
    tables = data.get("tables")
    if isinstance(tables, dict):
        for lemma, groups in tables.items():
            name = _clean_lemma(lemma)
            if not name or not isinstance(groups, list):
                continue
            cleaned = []
            for group in groups:
                item = _normalize_group(group)
                if item is not None:
                    cleaned.append(item)
            if cleaned:
                out["tables"][name] = cleaned
    return out


class UserLangData:
    """按语言读写用户词形/变位表；所有查询不区分大小写。"""

    def __init__(self, data_dir: Path | str) -> None:
        self.dir = Path(data_dir) / "lang_data"
        self._cache: dict[str, dict] = {}
        self._index_cache: dict[str, dict[str, str]] = {}

    # ------------------------------------------------------------------ 文件
    def path(self, lang: str) -> Path:
        return self.dir / f"{lang}.json"

    def load(self, lang: str, *, refresh: bool = False) -> dict:
        lang = (lang or "").strip().lower()
        if not lang:
            return {"forms": {}, "tables": {}}
        if not refresh and lang in self._cache:
            return self._cache[lang]
        data = {"forms": {}, "tables": {}}
        path = self.path(lang)
        if path.exists():
            try:
                data = _normalize(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError) as exc:
                log.warning("读取用户语言数据失败 %s: %s", path, exc)
        self._cache[lang] = data
        self._index_cache.pop(lang, None)
        return data

    def save(self, lang: str, data: dict) -> None:
        lang = (lang or "").strip().lower()
        if not lang:
            return
        normalized = _normalize(data)
        self.dir.mkdir(parents=True, exist_ok=True)
        path = self.path(lang)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(normalized, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        tmp.replace(path)
        self._cache[lang] = normalized
        self._index_cache.pop(lang, None)

    # ------------------------------------------------------------------ 读取
    def forms(self, lang: str) -> dict[str, str]:
        return dict(self.load(lang)["forms"])

    def tables(self, lang: str) -> dict[str, list[dict]]:
        return self.load(lang)["tables"]

    def languages(self) -> list[str]:
        if not self.dir.is_dir():
            return []
        return sorted(path.stem for path in self.dir.glob("*.json"))

    def table(self, lang: str, lemma: str) -> list[dict] | None:
        name = _clean_lemma(lemma)
        if not name:
            return None
        key = name.casefold()
        for stored, groups in self.tables(lang).items():
            if stored.casefold() == key:
                return groups
        return None

    def form_lemma(self, lang: str, form: str) -> str | None:
        key = _clean_form(form).lower()
        if not key:
            return None
        return self._index(lang).get(key)

    def _index(self, lang: str) -> dict[str, str]:
        lang = (lang or "").strip().lower()
        if lang in self._index_cache:
            return self._index_cache[lang]
        data = self.load(lang)
        index: dict[str, str] = {}
        for form, lemma in data["forms"].items():
            key = _clean_form(form).lower()
            if key and lemma:
                index.setdefault(key, lemma)
        # 变位表里的每个形式自动成为反查项
        for lemma, groups in data["tables"].items():
            for group in groups:
                for _person, form in group.get("rows") or []:
                    key = _clean_form(form).lower()
                    if key:
                        index.setdefault(key, lemma)
        self._index_cache[lang] = index
        return index

    # ------------------------------------------------------------------ 写入
    def add_form(self, lang: str, form: str, lemma: str) -> None:
        key = _clean_form(form).lower()
        value = _clean_lemma(lemma)
        if not key or not value:
            return
        data = self.load(lang)
        data["forms"][key] = value
        self.save(lang, data)

    def add_forms(self, lang: str, mapping: dict[str, str], *, overwrite: bool = False) -> int:
        """批量添加；默认保留已有映射，返回实际新增条数。"""
        data = self.load(lang)
        added = 0
        for form, lemma in mapping.items():
            key = _clean_form(form).lower()
            value = _clean_lemma(lemma)
            if not key or not value:
                continue
            if not overwrite and key in data["forms"]:
                continue
            data["forms"][key] = value
            added += 1
        if added:
            self.save(lang, data)
        return added

    def remove_form(self, lang: str, form: str) -> None:
        key = _clean_form(form).lower()
        data = self.load(lang)
        data["forms"].pop(key, None)
        self.save(lang, data)

    def set_table(self, lang: str, lemma: str, groups: list[dict]) -> None:
        name = _clean_lemma(lemma)
        if not name:
            return
        data = self.load(lang)
        cleaned = [item for item in (_normalize_group(group) for group in groups) if item]
        if cleaned:
            data["tables"][name] = cleaned
        else:
            data["tables"].pop(name, None)
        self.save(lang, data)

    def remove_table(self, lang: str, lemma: str) -> None:
        key = _clean_lemma(lemma).casefold()
        data = self.load(lang)
        for stored in list(data["tables"]):
            if stored.casefold() == key:
                data["tables"].pop(stored, None)
        self.save(lang, data)

    # ------------------------------------------------------------------ 导入
    def merge(self, payload, lang: str | None = None) -> int:
        """合并导入数据，返回合并的条目数。

        兼容两种格式：
        - 单语言：{"forms": ..., "tables": ...}
        - 多语言：{"it": {"forms": ...}, "es": {...}}
        """
        if not isinstance(payload, dict):
            return 0
        if "forms" in payload or "tables" in payload:
            target = (lang or "").strip().lower()
            if not target:
                return 0
            return self._merge_one(target, payload)
        count = 0
        for code, value in payload.items():
            if not isinstance(value, dict):
                continue
            if "forms" not in value and "tables" not in value:
                continue
            count += self._merge_one(str(code).strip().lower(), value)
        return count

    def _merge_one(self, lang: str, value: dict) -> int:
        if not lang:
            return 0
        data = self.load(lang)
        added = 0
        forms = value.get("forms") or {}
        if isinstance(forms, dict):
            for form, lemma in forms.items():
                key = _clean_form(form).lower()
                word = _clean_lemma(lemma)
                if key and word:
                    data["forms"][key] = word
                    added += 1
        tables = value.get("tables") or {}
        if isinstance(tables, dict):
            for lemma, groups in tables.items():
                name = _clean_lemma(lemma)
                if not name or not isinstance(groups, list):
                    continue
                cleaned = [item for item in (_normalize_group(group) for group in groups) if item]
                if cleaned:
                    data["tables"][name] = cleaned
                    added += 1
        self.save(lang, data)
        return added

    def export(self, lang: str) -> dict:
        return self.load(lang)
