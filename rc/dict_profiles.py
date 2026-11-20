"""声明式词典映射：用 JSON + XPath 适配不同 MDX 的词条 HTML。

用户配置放在 <data-dir>/dict_profiles/*.json；不需要改代码。
匹配成功时优先于内置的朗文/OHD 解析；解析不出义项则自动回退。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .dictionary import DictEntry, Sense


def _text(node) -> str:
    if isinstance(node, (list, tuple)):
        node = node[0] if node else None
    if node is None:
        return ""
    try:
        raw = "".join(node.itertext())
    except Exception:
        try:
            raw = str(node.text_content())
        except Exception:
            raw = ""
    return re.sub(r"\s+", " ", raw).strip()


def load_profiles(directory: Path | str | None) -> list[dict]:
    """读取目录下所有 .json 映射（无效文件静默跳过）。"""
    if not directory:
        return []
    root = Path(directory)
    if not root.is_dir():
        return []
    profiles: list[dict] = []
    for path in sorted(root.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        if not data.get("id") or not data.get("senses") or not data.get("definition"):
            continue
        data["_path"] = str(path)
        profiles.append(data)
    return profiles


def match_profile(html: str, profiles: list[dict]) -> dict | None:
    for profile in profiles:
        match = profile.get("match") or {}
        contains = match.get("contains")
        any_of = match.get("contains_any")
        regex = match.get("regex")
        if regex:
            try:
                if re.search(str(regex), html):
                    return profile
            except re.error:
                continue
            continue
        if isinstance(contains, str):
            contains = [contains]
        if isinstance(any_of, str):
            any_of = [any_of]
        if contains and all(token in html for token in contains):
            return profile
        if any_of and any(token in html for token in any_of):
            return profile
    return None


def parse_profile(html: str, word: str, profile: dict) -> DictEntry | None:
    """按映射解析词条；失败返回 None，让调用方回退到内置解析。"""
    try:
        from lxml import html as LH
    except Exception:
        return None
    try:
        tree = LH.fromstring(html)
    except Exception:
        return None

    def first(xpath: str) -> str:
        try:
            nodes = tree.xpath(xpath)
        except Exception:
            return ""
        return _text(nodes[0]) if nodes else ""

    entry = DictEntry(word=first(profile.get("headword") or "") or word, source="")
    entry.phonetic = first(profile.get("phonetic") or "")
    entry.pos = first(profile.get("pos") or "")

    audio_xpath = profile.get("audio")
    if audio_xpath:
        attr = str(profile.get("audio_attr") or "href")
        try:
            for node in tree.xpath(audio_xpath):
                value = node.get(attr) if hasattr(node, "get") else ""
                if value and str(value).startswith("sound://"):
                    entry.audio_keys.append(str(value)[len("sound://"):])
        except Exception:
            pass

    sense_nodes = []
    try:
        sense_nodes = tree.xpath(profile.get("senses"))
    except Exception:
        return None
    if not sense_nodes:
        return None

    for node in sense_nodes[:12]:
        definition = _text(node.xpath(profile.get("definition")))
        definition_cn = ""
        if profile.get("definition_cn"):
            definition_cn = _text(node.xpath(profile["definition_cn"]))
        if not definition and not definition_cn:
            continue
        sense = Sense(definition=definition, definition_cn=definition_cn)
        example_xpath = profile.get("example")
        if example_xpath:
            try:
                examples = node.xpath(example_xpath)
            except Exception:
                examples = []
            target_xpath = profile.get("example_cn")
            for example in examples[:4]:
                source = _text(example)
                if not source:
                    continue
                target = ""
                if target_xpath:
                    target = _text(example.xpath(target_xpath))
                    if target:
                        source = source.replace(target, "", 1).strip()
                if not target and target_xpath and sense.example:
                    continue
                if not sense.example:
                    sense.example = source
                    sense.example_cn = target
        entry.senses.append(sense)
    return entry if entry.senses else None


TEMPLATE = {
    "_comment": (
        "把 match.contains 改成这本词典词条 HTML 里独有的一段文字；"
        "所有 XPath 都是相对整篇词条 HTML 的绝对路径，definition/example 等"
        "则以每个 senses 节点为根。保存到 dict_profiles 目录后重载生效。"
    ),
    "id": "my-dictionary",
    "name": "我的词典",
    "match": {"contains": ["把这里换成词条 HTML 里独有的标记"]},
    "headword": "//span[@class='hw']",
    "phonetic": "//span[@class='pron']",
    "pos": "//span[@class='pos']",
    "senses": "//div[@class='sense']",
    "definition": ".//span[@class='def']",
    "definition_cn": ".//span[@class='defcn']",
    "example": ".//span[@class='example']",
    "example_cn": ".//span[@class='excn']",
    "audio": "//a[starts-with(@href,'sound://')]",
    "audio_attr": "href",
}
