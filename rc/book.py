"""书籍解析：EPUB（可扩展 PDF）。

只做两件事：
1. 把书拆成「章 → 段」，存进本地库；
2. 提供按章顺序的检索窗口（只搜读过的部分）。
"""

from __future__ import annotations

import posixpath
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from .htmldom import Node, parse

BLOCK_TAGS = {
    "p",
    "div",
    "li",
    "blockquote",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "td",
    "pre",
    "section",
    "article",
}
HEADING_TAGS = {"h1", "h2", "h3"}


class BookError(RuntimeError):
    pass


def parse_book(path: str | Path) -> dict:
    """解析书籍文件，返回 {title, format, sections:[{title, paragraphs}]}"""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".epub":
        return parse_epub(path)
    if suffix == ".pdf":
        raise BookError("PDF 解析还没做：先用 EPUB，或者在阅读器里导出成 EPUB")
    raise BookError(f"不支持的格式：{suffix}")


# ---------------------------------------------------------------------- EPUB
def parse_epub(path: Path) -> dict:
    try:
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
            opf_path = _find_opf(zf, names)
            opf_dir = posixpath.dirname(opf_path)
            root = ET.fromstring(zf.read(opf_path))
            title = _dc_title(root) or path.stem
            manifest = _manifest(root, opf_dir)
            nav_labels = _nav_labels(zf, names, manifest, opf_dir)

            sections: list[dict] = []
            for item_id in _spine(root):
                item = manifest.get(item_id)
                if not item:
                    continue
                href = item["href"]
                if href not in names:
                    continue
                try:
                    raw = zf.read(href)
                except KeyError:
                    continue
                html = raw.decode("utf-8", "replace")
                if "nav" in href.lower() and len(html) < 5000:
                    continue
                section_title = nav_labels.get(href) or ""
                paragraphs, heading = _extract_paragraphs(html)
                if not paragraphs:
                    continue
                sections.append(
                    {
                        "title": section_title or heading or f"第 {len(sections) + 1} 节",
                        "paragraphs": paragraphs,
                    }
                )
            if not sections:
                raise BookError("这本 EPUB 里没抽到文字（可能是纯图片版）")
            return {"title": title, "format": "epub", "sections": sections}
    except zipfile.BadZipFile as exc:
        raise BookError("这个文件不是有效的 EPUB") from exc


def _find_opf(zf: zipfile.ZipFile, names: set[str]) -> str:
    container = "META-INF/container.xml"
    if container in names:
        try:
            root = ET.fromstring(zf.read(container))
            for node in root.iter():
                if node.tag.endswith("rootfile"):
                    full = node.attrib.get("full-path") or ""
                    if full in names:
                        return full
        except ET.ParseError:
            pass
    for name in names:
        if name.lower().endswith(".opf"):
            return name
    raise BookError("EPUB 里找不到 OPF 清单")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _dc_title(root: ET.Element) -> str:
    for node in root.iter():
        if _local(node.tag) == "title" and node.text:
            return node.text.strip()
    return ""


def _manifest(root: ET.Element, opf_dir: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for node in root.iter():
        if _local(node.tag) != "manifest":
            continue
        for item in node:
            if _local(item.tag) != "item":
                continue
            item_id = item.attrib.get("id") or ""
            href = item.attrib.get("href") or ""
            if not item_id or not href:
                continue
            out[item_id] = {
                "href": _resolve(opf_dir, href),
                "media": item.attrib.get("media-type") or "",
                "props": item.attrib.get("properties") or "",
            }
    return out


def _spine(root: ET.Element) -> list[str]:
    order: list[str] = []
    for node in root.iter():
        if _local(node.tag) != "spine":
            continue
        for item in node:
            if _local(item.tag) == "itemref":
                ref = item.attrib.get("idref")
                if ref:
                    order.append(ref)  # 之后用 manifest 换成 href
    return order


def _resolve(base: str, href: str) -> str:
    if not base:
        return href
    return posixpath.normpath(posixpath.join(base, href))


def _nav_labels(zf: zipfile.ZipFile, names: set[str], manifest: dict, opf_dir: str) -> dict:
    """EPUB3 的 nav 或 EPUB2 的 NCX → {文件路径: 章节名}"""
    labels: dict[str, str] = {}
    nav_href = ""
    for item in manifest.values():
        if "nav" in item["props"].split():
            nav_href = item["href"]
            break
    if not nav_href:
        for item in manifest.values():
            if "dtbncx" in item["media"]:
                nav_href = item["href"]
                break
    if not nav_href or nav_href not in names:
        return labels
    try:
        root = ET.fromstring(zf.read(nav_href))
    except ET.ParseError:
        return labels
    base = posixpath.dirname(nav_href)
    for node in root.iter():
        if _local(node.tag) not in ("a", "content"):
            continue
        href = node.attrib.get("href") or node.attrib.get("src") or ""
        if not href:
            continue
        target_part = href.split("#")[0]
        if not target_part:
            continue
        target = _resolve(base, target_part)
        text = (node.text or "").strip()
        if target and text:
            labels.setdefault(target, text)
    return labels


def _extract_paragraphs(html: str) -> tuple[list[str], str]:
    root = parse(html)
    paragraphs: list[str] = []
    heading = ""
    body = root
    for node in root.walk():
        if node.tag == "body":
            body = node
            break
    _collect_blocks(body, paragraphs)
    for node in body.walk():
        if node.tag in HEADING_TAGS:
            text = node.clean_text()
            if text:
                heading = text
                break
    cleaned = []
    for text in paragraphs:
        text = " ".join(text.split())
        if len(text) >= 2:
            cleaned.append(text)
    return cleaned, heading


def _collect_blocks(node: Node, out: list[str]) -> None:
    for child in node.children:
        if not isinstance(child, Node):
            continue
        if child.tag in BLOCK_TAGS:
            has_block_child = any(
                isinstance(grand, Node) and grand.tag in BLOCK_TAGS for grand in child.children
            )
            if has_block_child:
                _collect_blocks(child, out)
            else:
                text = child.clean_text()
                if text:
                    out.append(text)
        else:
            _collect_blocks(child, out)
