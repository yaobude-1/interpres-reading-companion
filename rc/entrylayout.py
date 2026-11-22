"""把词典条目 HTML 重排成有层次的页面。

朗文的条目结构是：
    词头 → 一堆可折叠区块（THESAURUS / WORD ORIGIN / VERB TABLE …）→ 义项
直接渲染出来义项被压到最后，看起来没有层次。

这里用 lxml 做一次重排：
1. 把每个 <div class="content"> 收进 <details> 折叠面板；
2. 标题取它最近的前置 .popheader / .expandable 文字；
3. 所有折叠面板挪到义项之后。
"""

from __future__ import annotations

from typing import Any

try:
    from lxml import html as lxml_html
except Exception:  # pragma: no cover
    lxml_html = None

_TITLE_CLASSES = ("popheader", "expandable", "thead")


def _text(node) -> str:
    text = " ".join((node.text_content() or "").split())
    # 编号/项目符号是单个字符集合，strip 按字符剥离（不是剥子串）
    return text.strip(" ►·:")  # noqa: B005


def _nearest_title(content) -> str:
    """找 content 前面最近的区块标题。"""
    node = content
    for _ in range(6):
        node = node.getprevious()
        if node is None:
            break
        classes = (node.get("class") or "").split()
        if any(c in classes for c in _TITLE_CLASSES):
            text = _text(node)
            if text:
                return text
    parent = content.getparent()
    if parent is not None:
        for node in parent.itersiblings(preceding=True):
            classes = (node.get("class") or "").split()
            if any(c in classes for c in _TITLE_CLASSES):
                text = _text(node)
                if text:
                    return text
    return "更多"


def reorder(fragment: str) -> str:
    """把"义项主体"提到最前，其余区块（词源/变位/同义/搭配…）收成折叠面板。

    朗文把 12 个并列的 .entry 区块放在同一层，其中只有一个是义项主体，
    其它都是附加资料，却在文档里排在它前面。这里按语义重排。
    """
    if lxml_html is None or not fragment:
        return fragment
    try:
        tree = lxml_html.fromstring(fragment)
    except Exception:
        return fragment

    try:
        # 先清掉欧路的弹窗按钮与条目菜单（MENU FOR …）。菜单内部也带
        # .entry + sensenum，不先删掉会被误认成正文主体。
        for node in tree.xpath(
            './/*[contains(concat(" ", normalize-space(@class), " "), " entrymenu ") '
            'or contains(concat(" ", normalize-space(@class), " "), " popup-button ")]'
        ):
            parent = node.getparent()
            if parent is not None:
                parent.remove(node)

        spans = tree.xpath('.//*[contains(concat(" ", normalize-space(@class), " "), " entry ")]')
        spans = [
            span for span in spans
            if not span.xpath(
                'ancestor::*[contains(@class, "entrymenu") '
                'or contains(@class, "buttons")]'
            )
        ]
        if not spans:
            return _strip_scripts(tree)
        # 只处理最外层的 entry，避免把嵌套 entry 反复搬走
        span_ids = {id(span) for span in spans}
        top_level = [
            span for span in spans
            if not any(id(ancestor) in span_ids for ancestor in span.iterancestors())
        ]
        if top_level:
            spans = top_level

        # 含 sensenum 的多个 entry 里，选正文最多的那个当主条目
        main = None
        extras = []
        for span in spans:
            if span.xpath('.//*[contains(@class, "sensenum")]'):
                if main is None or len(span.text_content()) > len(main.text_content()):
                    if main is not None:
                        extras.append(main)
                    main = span
                else:
                    extras.append(span)
            else:
                extras.append(span)

        if main is not None:
            parent = main.getparent()
            if parent is not None:
                parent.remove(main)
                ordered = []
                merged: dict[str, Any] = {}
                for span in extras:
                    parent_span = span.getparent()
                    if parent_span is None:
                        continue
                    text_len = len((span.text_content() or "").strip())
                    if text_len < 12:
                        parent_span.remove(span)
                        continue
                    title = _section_title(span)
                    block = merged.get(title)
                    if block is None:
                        block = lxml_html.fragment_fromstring(
                            f'<div class="rc-sec"><div class="rc-sec-title">{title}</div>'
                            '<div class="rc-sec-body"></div></div>'
                        )
                        merged[title] = block
                        ordered.append(block)
                    body = block.xpath('.//div[@class="rc-sec-body"]')[0]
                    parent_span.remove(span)
                    body.append(span)
                # 重建干净文档：只留词头+义项和折叠块，避免原页面的包裹层影响布局
                clean = lxml_html.fragment_fromstring('<div class="rc-entry"></div>')
                clean.append(main)
                for block in ordered:
                    clean.append(block)
                body_node = tree.find(".//body")
                holder = body_node if body_node is not None else tree
                holder.clear()
                holder.append(clean)

        # 去掉词典自带的弹窗按钮行（它们原本配合欧路的脚本用）
        for node in tree.xpath('.//*[contains(concat(" ", normalize-space(@class), " "), " buttons ")]'):
            parent = node.getparent()
            if parent is not None:
                parent.remove(node)
        # 去掉空的弹窗容器
        for node in tree.xpath('.//*[contains(concat(" ", normalize-space(@class), " "), " at-link ")]'):
            parent = node.getparent()
            if parent is not None:
                parent.remove(node)
        for arrow in tree.xpath('.//span[contains(@class, "arrow")]'):
            arrow.getparent().remove(arrow)
        for node in tree.xpath('.//*[@onclick]'):
            del node.attrib["onclick"]
        return _strip_scripts(tree)
    except Exception:
        return fragment


def _section_title(span) -> str:
    """取区块标题：优先 .popheader 的文字。"""
    headers = span.xpath('.//*[contains(@class, "popheader")]')
    if headers:
        text = " ".join((headers[0].text_content() or "").split())
        if text:
            return text[:40]
    if span.xpath('.//div[contains(@class, "verbtable")]'):
        return "VERB TABLE"
    # 没有 popheader 的区块：取第一个子元素的短文本，别把整段正文都塞进标题
    for child in span:
        text = " ".join((child.text_content() or "").split())
        if text:
            return text[:24]
    text = " ".join((span.text_content() or "").split())
    return (text[:24] or "更多")


def _strip_scripts(tree) -> str:
    for script in tree.xpath(".//script"):
        script.getparent().remove(script)
    return lxml_html.tostring(tree, encoding="unicode")


def reorder_light(fragment: str) -> str:
    """只去掉脚本，别的都不动（拉丁词典这种扁平 HTML 用）。"""
    if lxml_html is None or not fragment:
        return fragment
    try:
        tree = lxml_html.fromstring(fragment)
    except Exception:
        return fragment
    for script in tree.xpath(".//script"):
        parent = script.getparent()
        if parent is not None:
            parent.remove(script)
    return lxml_html.tostring(tree, encoding="unicode")
