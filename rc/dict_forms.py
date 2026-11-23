"""从词典自身的 @@@LINK 重定向里提取“变形 → 原形”。

很多 MDX 词典会把变形词条写成 `@@@LINK=原形`。这里直接扫原始记录，
不解析 HTML、不调用 AI，得到的是词典明确给出的重定向关系。

首次扫描可能较慢（大词典 30–60 秒），结果会缓存到
`<data-dir>/cache/dict_redirect/<hash>.json`，之后同一本词典秒开。
"""

from __future__ import annotations

import hashlib
import json
import logging
from difflib import SequenceMatcher
from pathlib import Path

log = logging.getLogger("rc")

_REDIRECT_PREFIX = "@@@LINK="


def _readable(form: str) -> bool:
    form = form.strip()
    if not form or len(form) > 40 or len(form) < 2:
        return False
    if any(ch.isspace() for ch in form):
        return False
    # 过滤掉带路径/括号/控制字符的条目
    return all(ch.isalpha() or ch in "-'’." for ch in form)


def _cache_path(dictionary, data_dir) -> Path | None:
    if not data_dir:
        return None
    path = Path(getattr(dictionary, "path", "") or "")
    try:
        stat = path.stat()
    except OSError:
        return None
    raw = f"{path.resolve()}|{stat.st_mtime_ns}|{stat.st_size}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]
    return Path(data_dir) / "cache" / "dict_redirect" / f"{digest}.json"


def _load_cache(path: Path | None) -> dict[str, list[str]] | None:
    if path is None or not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    out: dict[str, list[str]] = {}
    for target, forms in data.items():
        if isinstance(target, str) and isinstance(forms, list):
            out[target.casefold()] = [str(form) for form in forms if _readable(str(form))]
    return out


def _save_cache(path: Path | None, index: dict[str, list[str]]) -> None:
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        log.debug("写入重定向缓存失败: %s", exc)


def _build_index(
    dictionary,
    *,
    data_dir=None,
    progress=None,
    cancel=None,
) -> dict[str, list[str]] | None:
    cache_path = _cache_path(dictionary, data_dir)
    cached = _load_cache(cache_path)
    if cached is not None:
        dictionary._user_redirect_index = cached
        return cached

    index: dict[str, list[str]] = {}
    mdx = getattr(dictionary, "_mdx", None)
    keys = getattr(mdx, "_keys", None) or []
    total = len(keys)
    for number, (key, _offset) in enumerate(keys):
        if cancel is not None and number % 500 == 0 and cancel():
            return None
        if progress is not None and number % 1000 == 0:
            progress(number, total)
        form = str(key or "").strip()
        if not _readable(form):
            continue
        try:
            raw = mdx._lookup_raw(form)
        except Exception:  # noqa: BLE001 - 单条损坏不影响整本扫描
            continue
        if not raw:
            continue
        stripped = raw.lstrip()
        if not stripped.startswith(_REDIRECT_PREFIX):
            continue
        target = stripped[len(_REDIRECT_PREFIX):].splitlines()[0].strip()
        if not target or " " in target:
            continue
        if form.casefold() == target.casefold():
            continue
        index.setdefault(target.casefold(), []).append(form)
    if progress is not None:
        progress(total, total)
    dictionary._user_redirect_index = index
    _save_cache(cache_path, index)
    return index


def redirect_forms(
    dictionary,
    lemma: str,
    *,
    data_dir=None,
    progress=None,
    cancel=None,
) -> list[tuple[str, float]] | None:
    """返回 [(变形, 相似度)]；取消时返回 None。"""
    target = (lemma or "").strip()
    if not target:
        return []
    index = getattr(dictionary, "_user_redirect_index", None)
    if index is None:
        index = _build_index(
            dictionary, data_dir=data_dir, progress=progress, cancel=cancel
        )
    if index is None:
        return None
    forms = index.get(target.casefold(), [])
    seen: set[str] = set()
    out: list[tuple[str, float]] = []
    key = target.casefold()
    for form in forms:
        lowered = form.casefold()
        if lowered in seen:
            continue
        seen.add(lowered)
        ratio = SequenceMatcher(None, lowered, key).ratio()
        out.append((form, ratio))
    out.sort(key=lambda item: (-item[1], item[0].lower()))
    return out


def bulk_candidates(
    dictionary,
    *,
    data_dir=None,
    progress=None,
    cancel=None,
    min_ratio: float = 0.0,
) -> list[tuple[str, str, float]] | None:
    """返回全部 [(原形, 变形, 相似度)]；取消时返回 None。

    只做扫描和相似度计算，阈值由界面决定，便于拖动预览。
    """
    index = _build_index(dictionary, data_dir=data_dir, progress=progress, cancel=cancel)
    if index is None:
        return None
    out: list[tuple[str, str, float]] = []
    for target, forms in index.items():
        if len(target) < 2 or not _readable(target):
            continue
        key = target.casefold()
        seen: set[str] = set()
        for form in forms:
            lowered = form.casefold()
            if lowered in seen:
                continue
            seen.add(lowered)
            ratio = SequenceMatcher(None, lowered, key).ratio()
            if ratio >= min_ratio:
                out.append((target, form, ratio))
    out.sort(key=lambda item: (item[0].lower(), -item[2], item[1].lower()))
    return out

