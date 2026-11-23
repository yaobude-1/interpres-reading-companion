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

import logging
import re
from dataclasses import dataclass, field
from html import unescape
from pathlib import Path

from .htmldom import parse
from .mdx import MDD, MDX, MDXError, html_to_text

log = logging.getLogger("rc")


def _ohd_example_pair(example) -> tuple[str, str]:
    """OHD 例句 → (法语, 英语)；短语块用 b.ohd-phrase 而不是 source/target。"""
    phrase = example.find("b", cls="ohd-phrase")
    if phrase is not None:
        source = phrase.clean_text()
        content = example.find("div", cls="ohd-example-content")
        text = content.clean_text() if content is not None else ""
        return source, text.replace(source, "", 1).strip()
    source_node = example.find(cls="ohd-example-source")
    target_node = example.find(cls="ohd-example-target")
    return (
        source_node.clean_text() if source_node is not None else "",
        target_node.clean_text() if target_node is not None else "",
    )


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
        self._backend = None
        name_lower = self.path.name.lower()
        if name_lower.endswith((".dsl", ".dsl.dz")):
            from .dsl import DSL

            self._backend = DSL(self.path)
        elif self.path.suffix.lower() in (".ifo", ".idx"):
            from .stardict import StarDict

            self._backend = StarDict(self.path)
        elif self.path.suffix.lower() == ".index":
            from .dictd import Dictd

            self._backend = Dictd(self.path)
        elif name_lower.endswith((".xdxf", ".xdxf.dz", ".xdxf.gz")):
            from .xdxf import XDXF

            self._backend = XDXF(self.path)
        self._mdx = self._backend or MDX(self.path)
        # 词典自己的名字优先（MDX 头里的 Title / StarDict 的 bookname），没有才退回文件名
        title = unescape(
            str(self._mdx.attrs.get("Title") or self._mdx.attrs.get("bookname") or "")
        ).strip()
        self.name = title or self.path.stem
        self._mdd = None
        if self._backend is None and mdd_path and Path(mdd_path).exists():
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
        if self._backend is not None:
            return self._backend.entry(word)
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
            except Exception as exc:  # noqa: BLE001 - profile 解析失败时回退到内置解析
                log.debug("词典 profile 解析失败: %s", exc)
        entry = DictEntry(word=word, source=self.name)
        try:
            if "ohd-entry" in html:
                self._parse_oxford_hachette(entry, html)
            elif 'class="def"' in html or 'class="defcn"' in html:
                self._parse_ldoce(entry, html)
            else:
                self._parse_generic(entry, html)
        except Exception as exc:  # noqa: BLE001 - 解析失败时回退到纯文本
            log.debug("内置词条解析失败: %s", exc)
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

        # 每个 ohd-pos-block 是一个词性区（I. nm / II. vtr / III. vi ...）。
        # 只认带 ohd-pos-heading 的顶层块，里面嵌套的子块是同一词性下的短语。
        blocks = [
            block
            for block in root.find_all("div", cls="ohd-pos-block")
            if block.find("div", cls="ohd-pos-heading")
        ]
        first_pos = ""
        for block in blocks:
            heading = block.find("div", cls="ohd-pos-heading")
            pos_node = heading.find("i", cls="ohd-pos") if heading is not None else None
            pos = pos_node.clean_text().strip() if pos_node is not None else ""
            if not pos:
                continue
            if not first_pos:
                first_pos = pos
            added = 0
            for blockquote in block.find_all("blockquote", cls="ohd-sense"):
                # 跳过嵌套子块里的义项，否则会把同一词性的短语重复列出来
                parent = blockquote.parent
                nested = False
                while parent is not None and parent is not block:
                    if "ohd-pos-block" in (parent.attrs.get("class") or "").split():
                        nested = True
                        break
                    parent = parent.parent
                if nested:
                    continue
                sense = Sense(pos=pos)
                content = blockquote.find("div", cls="ohd-sense-content")
                if content is not None:
                    lines = content.clean_text().split("\n")
                    if lines:
                        sense.definition = lines[0]
                for example in blockquote.find_all("blockquote", cls="ohd-example"):
                    source = example.find(cls="ohd-example-source")
                    target = example.find(cls="ohd-example-target")
                    if source is not None:
                        sense.example = source.clean_text()
                    if target is not None:
                        sense.example_cn = target.clean_text()
                    if sense.example:
                        break
                if sense.definition:
                    entry.senses.append(sense)
                    added += 1
            # 有些词性块只有短语表（如 I. nm 的 au sortir de、V. Idiome），
            # 没有 ohd-sense；用第一条短语/例句补一个义项。
            if not added:
                examples = block.find_all("blockquote", cls="ohd-example")
                if examples:
                    src, tgt = _ohd_example_pair(examples[0])
                    if src or tgt:
                        sense = Sense(pos=pos)
                        sense.definition = f"{src} — {tgt}" if tgt else src
                        entry.senses.append(sense)
        if first_pos:
            entry.pos = first_pos

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

    def raw(self, word: str) -> str | None:
        """Word's raw MDX HTML (following @@@LINK), without parsing."""
        return self._mdx.lookup(word)

    def resource(self, name: str) -> bytes | None:
        """Bytes from the dictionary's MDD archive or its folder (CSS/images)."""
        if not name or self._backend is not None:
            return None
        key = str(name).replace("/", "\\").lstrip("\\")
        if self._mdd:
            data = self._mdd.lookup_bytes(key)
            if data is None:
                data = self._mdd.lookup_bytes("\\" + key)
            if data is not None:
                return data
        # 有些词典把 CSS/图片放在 MDX 同目录，而不是 MDD 里
        try:
            base = self.path.parent.resolve()
            target = (base / key.replace("\\", "/")).resolve()
            if base != target and base not in target.parents:
                return None
            if target.is_file():
                return target.read_bytes()
        except OSError:
            return None
        return None

    def audio(self, sound_key: str) -> bytes | None:
        if not self._mdd:
            return None
        return self._mdd.lookup_audio(sound_key)

    def close(self) -> None:
        self._mdx.close()
        if self._mdd:
            self._mdd.close()
