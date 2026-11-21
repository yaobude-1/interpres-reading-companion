"""词典抽象层：把不同词典的词条统一成一种结构。

当前支持朗文6（LDOCE6 双解）的 HTML 结构：
    span.hwd       词头
    span.pron      音标
    span.pos       词性
    span.def       英文释义
    span.defcn     中文释义
    span.example > expen / expcn  例句及其翻译
    sound://...    真人发音（音频存在 MDD 里）

其它词典可以用「能力探测」的方式降级：探测不到中文就用英文释义，
探测不到例句就用选中的原句。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html import unescape
from pathlib import Path

from .htmldom import parse
from .mdx import MDD, MDX, MDXError, html_to_text


@dataclass
class Sense:
    definition: str = ""          # 英文释义
    definition_cn: str = ""       # 中文释义
    example: str = ""             # 例句
    example_cn: str = ""          # 例句翻译
    pos: str = ""                 # 该义项所属词性


@dataclass
class DictEntry:
    word: str = ""
    phonetic: str = ""
    pos: str = ""
    senses: list[Sense] = field(default_factory=list)
    audio_keys: list[str] = field(default_factory=list)
    source: str = ""

    # ------------------------------------------------------------------ 便捷
    @property
    def definition_cn(self) -> str:
        return "；".join(s.definition_cn for s in self.senses if s.definition_cn)[:3].rstrip("；")

    @property
    def definition_en(self) -> str:
        defs = [s.definition for s in self.senses if s.definition][:3]
        return "；".join(defs)

    def first_example(self) -> Sense | None:
        for sense in self.senses:
            if sense.example:
                return sense
        return None

    def to_text(self) -> str:
        lines = [self.word]
        if self.phonetic:
            lines.append(f"/{self.phonetic}/")
        if self.pos:
            lines.append(self.pos)
        for i, sense in enumerate(self.senses, start=1):
            cn = sense.definition_cn or sense.definition
            if cn:
                lines.append(f"{i}. {cn}")
            if sense.example:
                lines.append(f"   {sense.example}")
                if sense.example_cn:
                    lines.append(f"   {sense.example_cn}")
        return "\n".join(lines)


class Dictionary:
    """一本 MDX 词典（可选配套 MDD 音频）。"""

    def __init__(
        self,
        mdx_path: str | Path,
        mdd_path: str | Path | None = None,
        profiles: list[dict] | None = None,
    ) -> None:
        self.path = Path(mdx_path)
        self._profiles = profiles or []
        self._mdx = MDX(self.path)
        # 词典自己的名字优先（MDX 头里的 Title），没有才退回文件名
        title = unescape(str(self._mdx.attrs.get("Title") or "")).strip()
        self.name = title or self.path.stem
        self._mdd = None
        if mdd_path and Path(mdd_path).exists():
            try:
                self._mdd = MDD(mdd_path)
            except MDXError:
                self._mdd = None

    # ------------------------------------------------------------------ 元信息
    @property
    def entry_count(self) -> int:
        return self._mdx.entry_count

    def capabilities(self) -> dict:
        """抽样查几个词，看这本词典实际能给出哪些字段。"""
        if getattr(self, "_caps", None) is not None:
            return self._caps
        probes = ("time", "book", "run", "temps", "aimer", "amo", "puella", "amor", "house")
        caps: dict = {}
        for probe in probes:
            entry = self.lookup(probe)
            if entry and entry.senses:
                caps = {
                    "phonetic": bool(entry.phonetic),
                    "pos": bool(entry.pos),
                    "definition_cn": any(s.definition_cn for s in entry.senses),
                    "definition_en": any(s.definition for s in entry.senses),
                    "example": any(s.example for s in entry.senses),
                    "example_cn": any(s.example_cn for s in entry.senses),
                    "audio": bool(entry.audio_keys) and self._mdd is not None,
                }
                break
        self._caps = caps
        return caps

    # ------------------------------------------------------------------ 查询
    def lookup(self, word: str) -> DictEntry | None:
        html = self._mdx.lookup(word)
        if not html:
            return None
        return self._parse(word, html)

    def _parse(self, word: str, html: str) -> DictEntry:
        if self._profiles:
            try:
                from .dict_profiles import match_profile, parse_profile

                profile = match_profile(html, self._profiles)
                if profile is not None:
                    parsed = parse_profile(html, word, profile)
                    if parsed is not None and parsed.senses:
                        parsed.source = self.name
                        return parsed
            except Exception:
                pass
        entry = DictEntry(word=word, source=self.name)
        try:
            if "ohd-entry" in html:
                self._parse_oxford_hachette(entry, html)
            elif 'class="def"' in html or 'class="defcn"' in html:
                self._parse_ldoce(entry, html)
            else:
                self._parse_generic(entry, html)
        except Exception:
            pass
        if not entry.senses:
            text = html_to_text(html)
            if text:
                entry.senses.append(Sense(definition=text[:400]))
        return entry

    # ------------------------------------------------------- 朗文（LDOCE 双解）
    def _parse_ldoce(self, entry: DictEntry, html: str) -> None:
        root = parse(html)
        node = root.find(cls="hwd")
        if node:
            entry.word = node.clean_text() or entry.word
        node = root.find(cls="pron")
        if node:
            entry.phonetic = node.clean_text()
        node = root.find(cls="pos")
        if node:
            entry.pos = node.clean_text()

        entry.audio_keys = re.findall(r'sound://([^"\'\\]+?\.mp3)', html)[:4]

        current_pos = ""
        for node in root.walk():
            classes = (node.attrs.get("class") or "").split()
            if node.tag == "span" and "pos" in classes:
                text = node.clean_text()
                if text and "popup" not in " ".join(classes):
                    current_pos = text
            elif node.tag == "span" and "sense" in classes:
                sense_pos = None
                ancestor = node.parent
                blocked = False
                while ancestor is not None:
                    acls = (ancestor.attrs.get("class") or "").split()
                    if "at-link" in acls or "buttons" in acls:
                        blocked = True
                        break
                    if ancestor.tag == "span" and "entry" in acls:
                        pnode = ancestor.find(cls="pos")
                        if pnode is not None:
                            sense_pos = pnode.clean_text()
                        break
                    ancestor = ancestor.parent
                if blocked:
                    continue
                sense = Sense(pos=sense_pos or current_pos)
                def_node = node.find(cls="def")
                if def_node:
                    sense.definition = def_node.clean_text()
                cn_node = node.find(cls="defcn")
                if cn_node:
                    sense.definition_cn = cn_node.clean_text()
                ex_node = node.find("expen")
                if ex_node:
                    sense.example = ex_node.clean_text()
                excn_node = node.find("expcn")
                if excn_node:
                    sense.example_cn = excn_node.clean_text()
                if sense.definition or sense.definition_cn:
                    entry.senses.append(sense)

    # ------------------------------------------------- 牛津-阿歇特（法英词典）
    def _parse_oxford_hachette(self, entry: DictEntry, html: str) -> None:
        root = parse(html)
        node = root.find("h1", cls="ohd-headword")
        if node:
            entry.word = node.clean_text() or entry.word
        node = root.find("div", cls="ohd-pronunciation")
        if node:
            entry.phonetic = node.clean_text().strip(" /")
        node = root.find("i", cls="ohd-pos")
        if node:
            entry.pos = node.clean_text()

        for block in root.find_all("blockquote", cls="ohd-sense"):
            sense = Sense()
            content = block.find("div", cls="ohd-sense-content")
            if content:
                lines = content.clean_text().split("\n")
                if lines:
                    sense.definition = lines[0]
            examples = block.find_all("blockquote", cls="ohd-example")
            for example in examples:
                source = example.find(cls="ohd-example-source")
                target = example.find(cls="ohd-example-target")
                if source:
                    sense.example = source.clean_text()
                if target:
                    sense.example_cn = target.clean_text()
                if sense.example:
                    break
            if sense.definition:
                entry.senses.append(sense)

    # ------------------------------------------------------ 通用（如拉丁词典）
    def _parse_generic(self, entry: DictEntry, html: str) -> None:
        text = html_to_text(html)
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        if not lines:
            return
        head = lines[0]
        first = re.split(r"[ ,;]", head)[0].strip()
        if first:
            entry.word = first
        # 词性：tr. / intr. / n. / adj. / f. / m. 等
        m = re.search(
            r"\b(tr|intr|trans|dep|n|adj|adv|prep|conj|f|m|nt|v)\.",
            " ".join(lines[:3]),
        )
        if m:
            entry.pos = m.group(0).rstrip(".")

        for line in lines[1:]:
            m = re.match(r"^(\d{1,2})\s+(.{3,})$", line)
            if m:
                entry.senses.append(Sense(definition=m.group(2).strip()))
                continue
            if line.startswith("▶") and entry.senses:
                if not entry.senses[-1].example:
                    entry.senses[-1].example = line.lstrip("▶ ").strip()[:300]
            if len(entry.senses) >= 8:
                break

    def audio(self, sound_key: str) -> bytes | None:
        if not self._mdd:
            return None
        return self._mdd.lookup_audio(sound_key)

    def close(self) -> None:
        self._mdx.close()
        if self._mdd:
            self._mdd.close()
