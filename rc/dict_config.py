"""Global dictionary library + ordered groups.

The first version stored a full dictionary list under each language.  This
module migrates that layout to one shared library plus group references, so a
dictionary can be used by several language groups without being loaded twice.
"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path


def stable_id(path: str) -> str:
    return "d" + hashlib.sha1(str(path).lower().encode("utf-8", "replace")).hexdigest()[:15]


def find_mdd(path: str | Path) -> str:
    p = Path(path)
    candidates = (
        p.with_suffix(".mdd"),
        p.with_name(p.stem + ".1.mdd"),
        p.parent / (p.stem + ".mdd"),
    )
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return ""


def _format(path: str) -> str:
    name = Path(path).name.lower()
    if name.endswith(".dsl.dz") or name.endswith(".dsl"):
        return "dsl"
    if name.endswith(".xdxf.dz") or name.endswith(".xdxf"):
        return "xdxf"
    if name.endswith(".ifo") or name.endswith(".idx"):
        return "stardict"
    if name.endswith(".index"):
        return "dictd"
    return "mdx"


def _new_library_item(path: str, name: str = "", mdd: str = "", item_id: str = "") -> dict:
    return {
        "id": item_id or stable_id(path),
        "name": str(name or "").strip(),
        "mdx": str(path),
        "mdd": str(mdd or "").strip() or find_mdd(path),
        "format": _format(path),
    }


def normalize(data: dict) -> dict:
    """Normalize/migrate both the old single-dict and per-language layouts."""
    library = data.get("dictionary_library")
    if not isinstance(library, dict):
        library = {}
    groups = data.get("dictionary_groups")
    if not isinstance(groups, dict):
        groups = {}

    # ---- migrate the old `dictionaries` layout (or first version's items) ----
    old = data.get("dictionaries")
    if isinstance(old, dict):
        for lang, value in old.items():
            if not isinstance(value, dict):
                value = {}
            raw_items = value.get("items")
            if not isinstance(raw_items, list):
                raw_items = []
            if not raw_items and str(value.get("mdx") or "").strip():
                raw_items = [{"mdx": value.get("mdx"), "mdd": value.get("mdd")}]
            group = groups.setdefault(
                lang, {"items": [], "muted": [], "popup_muted": [], "default": "", "anki_dict": "", "group_muted": False}
            )
            refs = group.setdefault("items", [])
            existing_ids = {ref.get("id") for ref in refs if isinstance(ref, dict)}
            for raw in raw_items:
                if not isinstance(raw, dict):
                    continue
                path = str(raw.get("mdx") or raw.get("path") or "").strip()
                if not path:
                    continue
                old_id = str(raw.get("id") or "")
                canonical = next(
                    (i for i, item in library.items() if item.get("mdx") == path), ""
                )
                item_id = canonical or old_id or stable_id(path)
                if item_id in library and library[item_id].get("mdx") != path:
                    item_id = "d" + uuid.uuid4().hex[:15]
                if item_id not in library:
                    library[item_id] = _new_library_item(
                        path,
                        str(raw.get("name") or ""),
                        str(raw.get("mdd") or ""),
                        item_id,
                    )
                if item_id not in existing_ids:
                    refs.append({"id": item_id, "order": len(refs)})
                    existing_ids.add(item_id)
                if old_id and old_id in (value.get("muted") or []):
                    group.setdefault("muted", []).append(item_id)
        data.pop("dictionaries", None)

    data["dictionary_library"] = library
    data["dictionary_groups"] = groups

    # ---- clean the library ----
    clean_library: dict[str, dict] = {}
    path_to_id: dict[str, str] = {}
    for item_id, raw in library.items():
        if not isinstance(raw, dict):
            continue
        path = str(raw.get("mdx") or raw.get("path") or "").strip()
        if not path:
            continue
        key = path.lower()
        if key in path_to_id:
            clean_library[path_to_id[key]] = clean_library[path_to_id[key]]
            continue
        item_id = str(raw.get("id") or item_id or stable_id(path))
        if item_id in clean_library:
            item_id = "d" + uuid.uuid4().hex[:15]
        clean_library[item_id] = {
            "id": item_id,
            "name": str(raw.get("name") or "").strip(),
            "mdx": path,
            "mdd": str(raw.get("mdd") or "").strip() or find_mdd(path),
            "format": str(raw.get("format") or "").strip() or _format(path),
        }
        path_to_id[key] = item_id
    data["dictionary_library"] = clean_library
    data["dictionaries"] = {}  # 兼容旧脚本的只读入口；迁移后不再使用

    # ---- ensure one group per configured language ----
    languages = data.get("languages") or {}
    for lang in languages:
        groups.setdefault(
            lang, {"items": [], "muted": [], "popup_muted": [], "default": "", "anki_dict": "", "group_muted": False}
        )

    # ---- clean group references ----
    for lang, raw in list(groups.items()):
        if not isinstance(raw, dict):
            raw = {}
        refs = []
        seen: set[str] = set()
        for ref in raw.get("items") or []:
            if isinstance(ref, str):
                item_id = ref
            elif isinstance(ref, dict):
                item_id = str(ref.get("id") or "")
            else:
                continue
            if not item_id or item_id not in clean_library or item_id in seen:
                continue
            seen.add(item_id)
            refs.append({"id": item_id, "order": len(refs)})
        muted = [
            str(item_id)
            for item_id in (raw.get("muted") or [])
            if item_id in seen
        ]
        popup_muted = [
            str(item_id)
            for item_id in (raw.get("popup_muted") or [])
            if item_id in seen
        ]
        default = str(raw.get("default") or "")
        if default not in seen or default in muted:
            default = next((ref["id"] for ref in refs if ref["id"] not in muted), "")
        anki_dict = str(raw.get("anki_dict") or "")
        if anki_dict not in seen:
            anki_dict = ""
        groups[lang] = {
            "label": str(raw.get("label") or languages.get(lang, {}).get("zh_label") or lang),
            "items": refs,
            "muted": muted,
            "popup_muted": popup_muted,
            "default": default,
            "anki_dict": anki_dict,
            "group_muted": bool(raw.get("group_muted")),
        }
    return groups


# ------------------------------------------------------------------ library
def library(data: dict) -> dict[str, dict]:
    normalize(data)
    return data.setdefault("dictionary_library", {})


def item_by_id(data: dict, item_id: str) -> dict | None:
    return library(data).get(str(item_id or ""))


def language_of(data: dict, item_id: str) -> str:
    normalize(data)
    for lang, group in (data.get("dictionary_groups") or {}).items():
        if any(ref.get("id") == item_id for ref in group.get("items") or []):
            return lang
    return ""


def languages_of(data: dict, item_id: str) -> list[str]:
    normalize(data)
    out = []
    for lang, group in (data.get("dictionary_groups") or {}).items():
        if any(ref.get("id") == item_id for ref in group.get("items") or []):
            out.append(lang)
    return out


# ------------------------------------------------------------------ groups
def groups(data: dict) -> dict[str, dict]:
    normalize(data)
    return data.setdefault("dictionary_groups", {})


def group(data: dict, lang: str) -> dict:
    normalize(data)
    return (data.get("dictionary_groups") or {}).setdefault(
        lang, {"label": lang, "items": [], "muted": [], "popup_muted": [], "default": "", "anki_dict": "", "group_muted": False}
    )


def group_ids(data: dict, lang: str) -> list[str]:
    return [ref["id"] for ref in group(data, lang).get("items") or []]


def items(data: dict, lang: str) -> list[dict]:
    """The group's member dictionaries, in order (data, not just ids)."""
    lib = library(data)
    return [lib[item_id] for item_id in group_ids(data, lang) if item_id in lib]


def muted(data: dict, lang: str, context: str = "panel") -> set[str]:
    g = group(data, lang)
    key = "popup_muted" if context == "popup" else "muted"
    return set(g.get(key) or [])


def visible_items(data: dict, lang: str, context: str = "panel") -> list[dict]:
    """Visible dictionaries; `group_muted` disables the whole language group."""
    if bool(group(data, lang).get("group_muted")):
        return []
    hidden = muted(data, lang, context)
    return [item for item in items(data, lang) if item["id"] not in hidden]


def set_group_muted(data: dict, lang: str, muted_group: bool) -> None:
    normalize(data)
    g = (data.get("dictionary_groups") or {}).get(lang) or {}
    g["group_muted"] = bool(muted_group)


def default_id(data: dict, lang: str) -> str:
    return str(group(data, lang).get("default") or "")


def anki_id(data: dict, lang: str) -> str:
    """Explicit Anki dictionary; empty means follow the group's default."""
    return str(group(data, lang).get("anki_dict") or "")


def set_anki(data: dict, lang: str, item_id: str) -> None:
    normalize(data)
    g = (data.get("dictionary_groups") or {}).get(lang) or {}
    if not item_id:
        g["anki_dict"] = ""
        return
    ids = [ref["id"] for ref in g.get("items") or []]
    if item_id in ids:
        g["anki_dict"] = item_id


def set_default(data: dict, lang: str, item_id: str) -> None:
    normalize(data)
    g = (data.get("dictionary_groups") or {}).get(lang) or {}
    ids = [ref["id"] for ref in g.get("items") or []]
    if item_id and item_id in ids and item_id not in (g.get("muted") or []):
        g["default"] = item_id


def label(data: dict, lang: str) -> str:
    return str(group(data, lang).get("label") or lang)


# ------------------------------------------------------------------ mutations
def add_library_item(data: dict, path: str, *, name: str = "") -> dict:
    lib = library(data)
    for item in lib.values():
        if item.get("mdx") == path:
            return item
    item = _new_library_item(path, name)
    while item["id"] in lib:
        item["id"] = "d" + uuid.uuid4().hex[:15]
    lib[item["id"]] = item
    return item


def add_item(data: dict, lang: str, path: str, *, name: str = "", visible: bool = True) -> dict:
    """Compatibility helper: add to the library and the given group."""
    item = add_library_item(data, path, name=name)
    add_to_group(data, lang, item["id"], visible=visible)
    return item


def add_to_group(data: dict, lang: str, item_id: str, *, visible: bool = True) -> None:
    normalize(data)
    g = (data.get("dictionary_groups") or {}).setdefault(
        lang, {"label": lang, "items": [], "muted": [], "popup_muted": [], "default": "", "anki_dict": "", "group_muted": False}
    )
    ids = [ref["id"] for ref in g.get("items") or []]
    if item_id not in ids:
        g.setdefault("items", []).append({"id": item_id, "order": len(ids)})
        ids.append(item_id)
    if visible:
        g["muted"] = [x for x in g.get("muted") or [] if x != item_id]
        g["popup_muted"] = [x for x in g.get("popup_muted") or [] if x != item_id]
    else:
        if item_id not in (g.get("muted") or []):
            g.setdefault("muted", []).append(item_id)
        if item_id not in (g.get("popup_muted") or []):
            g.setdefault("popup_muted", []).append(item_id)
    if not g.get("default") or g.get("default") in (g.get("muted") or []):
        g["default"] = next((x for x in ids if x not in (g.get("muted") or [])), "")


def remove_from_group(data: dict, lang: str, item_id: str) -> None:
    normalize(data)
    g = (data.get("dictionary_groups") or {}).setdefault(
        lang, {"label": lang, "items": [], "muted": [], "popup_muted": [], "default": "", "anki_dict": "", "group_muted": False}
    )
    g["items"] = [ref for ref in g.get("items") or [] if ref.get("id") != item_id]
    g["muted"] = [x for x in g.get("muted") or [] if x != item_id]
    g["popup_muted"] = [x for x in g.get("popup_muted") or [] if x != item_id]
    if g.get("default") == item_id:
        g["default"] = next(
            (
                ref["id"]
                for ref in g.get("items") or []
                if ref["id"] not in (g.get("muted") or [])
            ),
            "",
        )


def remove_library_item(data: dict, item_id: str) -> None:
    normalize(data)
    lib = data.get("dictionary_library") or {}
    lib.pop(item_id, None)
    for lang in list((data.get("dictionary_groups") or {}).keys()):
        remove_from_group(data, lang, item_id)


def set_visible(
    data: dict, lang: str, item_id: str, visible: bool, context: str = "panel"
) -> None:
    normalize(data)
    g = (data.get("dictionary_groups") or {}).setdefault(
        lang, {"label": lang, "items": [], "muted": [], "popup_muted": [], "default": "", "anki_dict": "", "group_muted": False}
    )
    key = "popup_muted" if context == "popup" else "muted"
    if visible:
        g[key] = [x for x in g.get(key) or [] if x != item_id]
    elif item_id not in (g.get(key) or []):
        g.setdefault(key, []).append(item_id)
    if g.get("default") in (g.get("muted") or []):
        g["default"] = next(
            (
                ref["id"]
                for ref in g.get("items") or []
                if ref["id"] not in (g.get("muted") or [])
            ),
            "",
        )


def remove_item(data: dict, lang: str, item_id: str) -> None:
    """Compatibility with the first version: remove from this group."""
    remove_from_group(data, lang, item_id)
