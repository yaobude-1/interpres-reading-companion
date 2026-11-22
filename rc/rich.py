"""从词条 HTML 里快速抽出「多义项 + 例句」，给 Anki 的 Dict2Anki 模板用。

不用 lookup_full（那会内联图片/CSS，一条要 1 秒），这里纯正则，
一条 1–5ms，够同步几千个词。
"""

from __future__ import annotations

import logging
import re

log = logging.getLogger("rc")

_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")


def _plain(text: str) -> str:
    text = _TAG.sub(" ", text or "")
    text = text.replace("&nbsp;", " ")
    return _SPACE.sub(" ", text).strip()


def _first(pattern: str, text: str) -> str:
    match = re.search(pattern, text, re.S)
    return _plain(match.group(1)) if match else ""


def _examples(chunk: str, limit: int = 2) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for match in re.finditer(r"<expen>(.*?)</expen>(?:\s*<expcn>(.*?)</expcn>)?", chunk, re.S):
        en = _plain(match.group(1))
        cn = _plain(match.group(2) or "")
        if en:
            out.append((en, cn))
        if len(out) >= limit:
            break
    if out:
        return out
    # 有些词条没有 expen，只有 example
    for match in re.finditer(r'<span class="example">(.*?)</span>', chunk, re.S):
        en = _plain(match.group(1))
        if en:
            out.append((en, ""))
        if len(out) >= limit:
            break
    return out


def extract_english(html: str, limit_senses: int = 6, limit_examples: int = 2) -> list[dict]:
    """返回 [{pos, definition, definition_cn, examples: [(en, cn)]}]。"""
    if not html:
        return []
    starts = [m.start() for m in re.finditer(r'<span class="sense">', html)]
    pos_marks = [
        (m.start(), _plain(m.group(1)))
        for m in re.finditer(r'class="pos"[^>]*>([^<]{1,24})<', html)
    ]
    chunks = re.split(r'<span class="sense">', html)[1:] or [html]
    senses: list[dict] = []
    for index, chunk in enumerate(chunks):
        # 只取到下一个义项锚点前，避免把整页例句都算进来
        chunk = re.split(r"<a name=", chunk)[0]
        if not chunk.strip():
            continue
        pos = ""
        if starts and index < len(starts):
            before = [name for off, name in pos_marks if off < starts[index]]
            if before:
                pos = before[-1]
        definition = _first(r'<span class="def">(.*?)</span>', chunk)
        definition_cn = _first(r'<span class="defcn">(.*?)</span>', chunk)
        if not definition and not definition_cn:
            continue
        senses.append(
            {
                "pos": pos,
                "definition": definition,
                "definition_cn": definition_cn,
                "examples": _examples(chunk, limit_examples),
            }
        )
        if len(senses) >= limit_senses:
            break
    if not senses:
        definition = _first(r'<span class="def">(.*?)</span>', html)
        definition_cn = _first(r'<span class="defcn">(.*?)</span>', html)
        pos = _first(r'class="pos"[^>]*>([^<]{1,24})<', html)
        if definition or definition_cn:
            senses.append(
                {
                    "pos": pos,
                    "definition": definition,
                    "definition_cn": definition_cn,
                    "examples": _examples(html, limit_examples),
                }
            )
    return senses


def extract_ohd(html: str, headword: str = "", limit_senses: int = 8, limit_examples: int = 3) -> list[dict]:
    """法语词典（牛津-阿歇特）：返回 [{pos, definition, examples: [(src, cn)]}]。"""
    if not html:
        return []
    try:
        from lxml import html as LH
    except Exception:
        return []
    try:
        tree = LH.fromstring(html)
    except Exception:
        return []
    senses: list[dict] = []
    for block in tree.xpath('//div[contains(@class, "ohd-pos-block")]'):
        pos = " ".join("".join(block.xpath('.//i[contains(@class, "ohd-pos")]//text()')).split())
        for sense in block.xpath('./div[contains(@class, "ohd-pos-content")]//blockquote[contains(@class, "ohd-sense")]'):
            content = sense.xpath('./div[contains(@class, "ohd-sense-content")]')
            if not content:
                continue
            first = content[0].xpath('./span[1]')
            def_text = "".join(first[0].itertext()) if first else ""
            def_text = " ".join(def_text.split())
            def_text = def_text.replace("~", headword) if headword else def_text
            examples: list[tuple[str, str]] = []
            for ex in sense.xpath('.//blockquote[contains(@class, "ohd-example")]'):
                src = " ".join("".join(ex.xpath('.//span[contains(@class, "ohd-example-source")]//text()')).split())
                tgt = " ".join("".join(ex.xpath('.//span[contains(@class, "ohd-example-target")]//text()')).split())
                if src:
                    if headword:
                        src = src.replace("~", headword)
                    examples.append((src, tgt))
                if len(examples) >= limit_examples:
                    break
            if not def_text and not examples:
                continue
            senses.append({"pos": pos, "definition": def_text, "definition_cn": "", "examples": examples})
            if len(senses) >= limit_senses:
                return senses
        # 有些词性块只有短语（如 nm 下的固定搭配），也收进来
        loose: list[tuple[str, str]] = []
        for ex in block.xpath('./div[contains(@class, "ohd-pos-content")]/div[contains(@class, "ohd-example-list")]/blockquote[contains(@class, "ohd-example")]'):
            src = " ".join("".join(ex.xpath('.//span[contains(@class, "ohd-example-source")]//text()')).split())
            tgt = " ".join("".join(ex.xpath('.//span[contains(@class, "ohd-example-target")]//text()')).split())
            if src:
                if headword:
                    src = src.replace("~", headword)
                loose.append((src, tgt))
        if loose:
            senses.append({"pos": pos, "definition": "", "definition_cn": "", "examples": loose[:limit_examples]})
    return senses


def _sanitize(fragment: str) -> str:
    """只保留加粗/斜体/换行，其余标签剥掉，属性清空。"""
    if not fragment:
        return ""
    try:
        from lxml import html as LH
    except Exception:
        return _plain(fragment)
    try:
        frag = LH.fragment_fromstring(fragment, create_parent="div")
    except Exception:
        return _plain(fragment)
    for el in list(frag.iter()):
        if el is frag:
            continue
        tag = el.tag.lower() if isinstance(el.tag, str) else "span"
        classes = (el.get("class") or "").lower()
        if tag in ("b", "strong"):
            el.tag = "b"
        elif tag in ("i", "em"):
            if "cue" in classes or "governance" in classes:
                el.tag = "span"
                el.set("class", "rc-cue")
            else:
                el.tag = "span"
                el.set("class", "rc-it")
        elif tag == "br":
            pass
        else:
            el.tag = "span"
        el.attrib.pop("title", None)
        for key in list(el.attrib):
            del el.attrib[key]
        if el.tag == "span" and el.get("class") not in ("rc-cue", "rc-it"):
            el.attrib.pop("class", None)
    return _text_html(frag)


def _text_html(el) -> str:
    from lxml import etree

    parts = [el.text or ""]
    for child in el:
        parts.append(etree.tostring(child, encoding="unicode", with_tail=False))
        parts.append(child.tail or "")
    return "".join(parts)


def extract_ohd_rich(html: str, headword: str = "") -> list[dict]:
    """法语词条 → [{part, pos, senses:[{no, def_html, examples:[(src_html, tgt_html)]}]}]。"""
    if not html:
        return []
    try:
        from lxml import html as LH
    except Exception:
        return []
    try:
        tree = LH.fromstring(html)
    except Exception:
        return []
    out: list[dict] = []
    for block in tree.xpath('//div[contains(@class, "ohd-pos-block")]'):
        part = " ".join("".join(block.xpath('.//span[contains(@class, "ohd-part-number")]//text()')).split())
        pos = " ".join("".join(block.xpath('.//i[contains(@class, "ohd-pos")]//text()')).split())
        senses: list[dict] = []
        for sense in block.xpath('./div[contains(@class, "ohd-pos-content")]//blockquote[contains(@class, "ohd-sense")]'):
            content = sense.xpath('./div[contains(@class, "ohd-sense-content")]')
            if not content:
                continue
            first = content[0].xpath('./span[1]')
            no = " ".join("".join(sense.xpath('./span[contains(@class, "ohd-sense-no")]//text()')).split())
            def_html = _sanitize(_text_html(first[0])) if first else ""
            if headword:
                def_html = def_html.replace("~", f"<b>{headword}</b>")
            examples: list[tuple[str, str]] = []
            for ex in sense.xpath('.//blockquote[contains(@class, "ohd-example")]'):
                src_el = ex.xpath('.//span[contains(@class, "ohd-example-source")]')
                tgt_el = ex.xpath('.//span[contains(@class, "ohd-example-target")]')
                src = _sanitize(_text_html(src_el[0])) if src_el else ""
                tgt = _sanitize(_text_html(tgt_el[0])) if tgt_el else ""
                if headword:
                    src = src.replace("~", f"<b>{headword}</b>")
                if src:
                    examples.append((src, tgt))
            if def_html or examples:
                senses.append({"no": no, "def_html": def_html, "examples": examples})
        # 只有短语、没有义项的块（如 nm 下的固定搭配）
        loose: list[tuple[str, str]] = []
        for ex in block.xpath('./div[contains(@class, "ohd-pos-content")]/div[contains(@class, "ohd-example-list")]/blockquote[contains(@class, "ohd-example")]'):
            src_el = ex.xpath('.//span[contains(@class, "ohd-example-source")]')
            tgt_el = ex.xpath('.//span[contains(@class, "ohd-example-target")]')
            src = _sanitize(_text_html(src_el[0])) if src_el else ""
            tgt = _sanitize(_text_html(tgt_el[0])) if tgt_el else ""
            if headword:
                src = src.replace("~", f"<b>{headword}</b>")
            if src:
                loose.append((src, tgt))
        if loose:
            senses.append({"no": "", "def_html": "", "examples": loose})
        if senses:
            out.append({"part": part, "pos": pos, "senses": senses})
    return out


def extract_english_rich(html: str, headword: str = "") -> list[dict]:
    """英语词条 → 同结构（Longman）。"""
    if not html:
        return []
    try:
        from lxml import html as LH
    except Exception:
        return []
    try:
        tree = LH.fromstring(html)
    except Exception:
        return []
    pos_marks = tree.xpath('//span[@class="pos"]')
    pos_nodes = {el: " ".join("".join(el.itertext()).split()) for el in pos_marks}
    out: list[dict] = []
    for sense in tree.xpath('//span[contains(@class, "sense")]'):
        prev = sense.xpath("preceding::span[@class='pos'][1]")
        pos = pos_nodes.get(prev[0], "") if prev else ""
        def_el = sense.xpath('.//span[@class="def"]')
        cn_el = sense.xpath('.//span[@class="defcn"]')
        def_html = _sanitize(_text_html(def_el[0])) if def_el else ""
        cn_html = _sanitize(_text_html(cn_el[0])) if cn_el else ""
        examples: list[tuple[str, str]] = []
        for ex in sense.xpath('.//expen'):
            src = _sanitize(_text_html(ex))
            if headword:
                src = src.replace("~", f"<b>{headword}</b>")
            if src:
                examples.append((src, ""))
        if def_html or cn_html or examples:
            out.append({"pos": pos, "senses": [{"no": "", "def_html": def_html, "def_cn": cn_html, "examples": examples}]})
    return _merge_by_pos(out)


def _merge_by_pos(items: list[dict]) -> list[dict]:
    merged: list[dict] = []
    for item in items:
        pos = item.get("pos") or ""
        if merged and merged[-1]["pos"] == pos:
            merged[-1]["senses"].extend(item["senses"])
        else:
            merged.append({"part": item.get("part", ""), "pos": pos, "senses": list(item["senses"])})
    return merged


def render_interpres(blocks: list[dict]) -> str:
    """把结构化义项渲染成 Anki 字段 HTML（词性分区 + 编号 + 例句成对）。"""
    out: list[str] = []
    for block in blocks:
        pos = (block.get("pos") or "").strip()
        part = (block.get("part") or "").strip()
        title = " ".join(x for x in (part, pos) if x)
        if title:
            out.append(f'<div class="rc-posline">{title}</div>')
        for sense in block.get("senses") or []:
            no = (sense.get("no") or "").strip()
            body = sense.get("def_html") or ""
            cn = sense.get("def_cn") or ""
            if body or cn:
                prefix = f'<span class="rc-num">{no}</span> ' if no else ""
                extra = f' <span class="rc-cn">{cn}</span>' if cn else ""
                out.append(f'<div class="rc-sense">{prefix}{body}{extra}</div>')
            for src, target in sense.get("examples") or []:
                if target:
                    out.append(
                        f'<div class="rc-ex"><div class="rc-ex-l">{src}</div>'
                        f'<div class="rc-ex-r">{target}</div></div>'
                    )
                else:
                    out.append(f'<div class="rc-ex"><div class="rc-ex-l">{src}</div></div>')
    return "".join(out)


def extract_latin_rich(html: str, headword: str = "") -> list[dict]:
    """牛津拉丁语词典：<strong>1</strong> 编号义项 + ▶ 引文例句。"""
    if not html:
        return []
    text = re.sub(r"<link[^>]*>", "", html)
    text = re.sub(r'<div style="font-size:150%[^>]*>.*?</div>', "", text, count=1, flags=re.S)
    text = re.sub(r"<strong>.*?</strong>", "", text, count=1, flags=re.S)  # 词头行
    text = re.sub(r"<sup>.*?</sup>", "", text, flags=re.S)
    text = re.sub(r"Forms:.*?<br\s*/?>", "", text, flags=re.S)
    text = re.sub(r"\[[^\]]*\]", " ", text)  # 词源方括号
    if headword:
        text = text.replace("~", headword)

    def clean_definition(raw: str) -> str:
        value = _plain(raw)
        value = re.sub(r"^\s*\d+\s*", "", value)
        # 去掉开头的变位形式与词性标记（m. / f. / n. / tr. / intr.）
        value = re.sub(r"^\s*(?:[A-Za-zāēīōūȳ]+\s+){0,3}?(?:m|f|n|tr|intr|absol|pass)\.\s*", "", value)
        value = re.sub(r"^\s*[A-Za-zāēīōūȳ]+\s+(?=[A-Z])", "", value)
        return value.strip()

    parts = re.split(r"<strong>\s*(\d+)\s*</strong>", text)
    senses: list[dict] = []
    if len(parts) > 1:
        segments = [(parts[i], parts[i + 1]) for i in range(1, len(parts) - 1, 2)]
    else:
        segments = [("", parts[0])]
    for no, chunk in segments:
        pieces = re.split(r"<br\s*/?>", chunk)
        head = clean_definition(pieces[0]) if pieces else ""
        if not head:
            continue
        examples: list[tuple[str, str]] = []
        for piece in pieces[1:]:
            piece = piece.replace("&emsp;", " ")
            if "▶" in piece:
                item = _plain(piece.split("▶", 1)[1])
                item = re.sub(r"\s{2,}", " ", item).strip()
                if len(item) > 260:
                    item = item[:257].rstrip() + "…"
                if item:
                    examples.append((item, ""))
            if len(examples) >= 2:
                break
        senses.append(
            {
                "no": no + "." if no else "",
                "def_html": head,
                "def_cn": "",
                "examples": examples,
            }
        )
    if not senses:
        head = clean_definition(re.split(r"<br", text)[0])
        if head:
            senses.append({"no": "", "def_html": head, "def_cn": "", "examples": []})
    return [{"part": "", "pos": "", "senses": senses[:8]}] if senses else []




def extract_generic(html: str, headword: str = "") -> list[dict]:
    """认不出的词典：按“段落/编号”粗略切义项，至少保证不丢内容。"""
    if not html:
        return []
    text = re.sub(r"<(link|script|style)[^>]*>.*?</\1>", "", html, flags=re.S | re.I)
    pieces = re.split(r"<br\s*/?>|<p[^>]*>|<div[^>]*>", text)
    blanks: list[str] = []
    for piece in pieces:
        value = _plain(piece)
        if value and value not in blanks and len(value) > 1:
            blanks.append(value)
    if headword:
        blanks = [b.replace("~", headword) for b in blanks]
    if not blanks:
        return []
    # 首段当释义，后面像例句的（短、含标点）取最多 2 条
    head = blanks[0][:400]
    examples = [(b, "") for b in blanks[1:3]] if len(blanks) > 1 else []
    return [{"part": "", "pos": "", "senses": [{"no": "", "def_html": head, "def_cn": "", "examples": examples}]}]


def auto_extract(html: str, headword: str = "") -> list[dict]:
    """按 HTML 特征识别词典类型，认不出就用通用兜底。"""
    if not html:
        return []
    try:
        if 'ohd-pos-block' in html:
            return extract_ohd_rich(html, headword)
        if 'OxfordLatin' in html or 'font-size:150%' in html:
            return extract_latin_rich(html, headword)
        if 'class="sense"' in html and 'class="def"' in html:
            return extract_english_rich(html, headword)
        if 'class="def"' in html or 'class="defcn"' in html:
            return extract_english_rich(html, headword)
    except Exception as exc:  # noqa: BLE001 - 专用格式解析失败时回退到通用解析
        log.debug("专用格式解析失败，回退通用解析: %s", exc)
    return extract_generic(html, headword)
