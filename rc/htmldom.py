"""极简 HTML 树，用来按 class / 标签查找词条结构。

只做词典需要的事：解析、找节点、取文本。不追求完整 HTML 规范。
"""

from __future__ import annotations

from html.parser import HTMLParser

VOID_TAGS = {
    "br",
    "img",
    "link",
    "meta",
    "hr",
    "input",
    "area",
    "base",
    "col",
    "embed",
    "param",
    "source",
    "track",
    "wbr",
}


class Node:
    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag: str, attrs: dict | None = None, parent: "Node | None" = None):
        self.tag = tag
        self.attrs = dict(attrs or {})
        self.children: list[Node | str] = []
        self.parent = parent

    # ------------------------------------------------------------------ 文本
    def text(self) -> str:
        parts: list[str] = []
        self._collect(parts)
        return "".join(parts)

    def _collect(self, parts: list[str]) -> None:
        for child in self.children:
            if isinstance(child, str):
                parts.append(child)
            else:
                if child.tag in ("br",):
                    parts.append("\n")
                elif child.tag in ("p", "div", "li", "tr", "h1", "h2", "h3", "blockquote", "article", "header"):
                    parts.append("\n")
                    child._collect(parts)
                    parts.append("\n")
                else:
                    child._collect(parts)

    def clean_text(self) -> str:
        import re

        text = self.text()
        text = re.sub(r"[ \t\u00a0]+", " ", text)
        lines = [line.strip() for line in text.split("\n")]
        return "\n".join(line for line in lines if line)

    # ------------------------------------------------------------------ 查找
    def find(self, tag: str | None = None, cls: str | None = None) -> "Node | None":
        for node in self.walk():
            if node is self:
                continue
            if tag and node.tag != tag:
                continue
            if cls and cls not in (node.attrs.get("class") or "").split():
                continue
            return node
        return None

    def find_all(self, tag: str | None = None, cls: str | None = None) -> list["Node"]:
        out = []
        for node in self.walk():
            if node is self:
                continue
            if tag and node.tag != tag:
                continue
            if cls and cls not in (node.attrs.get("class") or "").split():
                continue
            out.append(node)
        return out

    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.walk()


class _Builder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("#root")
        self.current = self.root

    def handle_starttag(self, tag, attrs):
        node = Node(tag, dict(attrs), self.current)
        self.current.children.append(node)
        if tag not in VOID_TAGS:
            self.current = node

    def handle_startendtag(self, tag, attrs):
        node = Node(tag, dict(attrs), self.current)
        self.current.children.append(node)

    def handle_endtag(self, tag):
        node = self.current
        while node is not None and node.tag != tag:
            node = node.parent
        if node is not None and node.parent is not None:
            self.current = node.parent

    def handle_data(self, data):
        if data:
            self.current.children.append(data)


def parse(html: str) -> Node:
    builder = _Builder()
    try:
        builder.feed(html)
        builder.close()
    except Exception:
        pass
    return builder.root
