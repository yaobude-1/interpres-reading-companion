"""把词典条目转成自包含 HTML：内联 CSS、内联图片、深色覆盖。"""

from __future__ import annotations

import base64
import re

from lxml import html as lxml_html

from .dictionary import Dictionary
from .entrylayout import reorder, reorder_light

_SOUND_MIME = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".m4a": "audio/mp4",
    ".spx": "audio/ogg",
}

_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
}

DEFAULT_COLORS = {
    "text": "#222222",
    "bg": "#ffffff",
    "sense": "#cc2200",
    "pos": "#1a66cc",
    "label": "#8a8f98",
    "example": "#6b7280",
    "section": "#b8860b",
    "arrow": "#b0b6c0",
}

_COLOR_TOKENS = [
    ("#ffffff", "§BG"),
    ("#fff", "§BG"),
    ("#cc2200", "§SENSE"),
    ("#1a66cc", "§POS"),
    ("#b8860b", "§SECTION"),
    ("#6b7280", "§EXAMPLE"),
    ("#8a8f98", "§LABEL"),
    ("#b0b6c0", "§ARROW"),
    ("#888", "§LABEL"),
    ("#333", "§TEXT"),
    ("#222222", "§TEXT"),
    ("#222", "§TEXT"),
]


def _templatize(css: str) -> str:
    for literal, token in _COLOR_TOKENS:
        css = css.replace(literal, token)
    return css


def _colorize(css: str, colors: dict | None = None, font_size: int = 15) -> str:
    merged = dict(DEFAULT_COLORS)
    for key, value in (colors or {}).items():
        if isinstance(value, str) and value.startswith("#"):
            merged[key] = value
    for token in ("§BG", "§SENSE", "§POS", "§SECTION", "§EXAMPLE", "§LABEL", "§ARROW", "§TEXT"):
        css = css.replace(token, merged[token[1:].lower()])
    css = css.replace("§FONTSIZE", str(int(font_size)))
    return css

_BASE_CSS = _templatize("""
html, body { margin: 0; padding: 12px 16px; background: #fff; color: #222; overflow-x: hidden;
  font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif; font-size: §FONTSIZEpx; line-height: 1.7; }
a { color: #1a66cc; text-decoration: none; }
img { max-width: 100%; }
table { max-width: 100%; }
* { max-width: 100%; word-wrap: break-word; }
img[data-orig*="spkr"] { width: 16px; height: 16px; vertical-align: -2px; margin: 0 2px; }
/* 词头 */
.hwd, .wfwd { font-size: 24px; font-weight: 700; color: #111; }
.homnum { font-size: 12px; vertical-align: super; color: #666; }
.proncodes, .pron, .amevarpron { color: #666; font-size: 13px; }
.pos { color: #1a66cc; font-style: italic; }
/* 义项 */
.sense, .sense.newline { display: block; margin: 7px 0; }
.sensenum { color: #cc2200; font-weight: 700; margin-right: 6px; }
.gram { color: #666; font-style: normal; margin-right: 4px; }
.def { color: #111; }
.defcn { color: #444; }
.expen, expen, .example { color: #555; font-style: italic; }
.expcn, expcn { color: #777; font-style: normal; }
/* 搭配、词组、标签 */
.collocate, .colloinexa, .phrase, .phrasetext { color: #1a66cc; }
.registerlab { color: #888; font-style: italic; font-size: 13px; }
.thead, .neutral { color: #555; }
.related_topics, .ws_info { font-size: 12px; color: #888; display: block; }
/* 可折叠区块（词源、同义、搭配…） */
.rc-sec { display: inline-block; border: 1px solid #d5dae2; border-radius: 4px;
  margin: 0 6px 8px 0; padding: 3px 10px; background: #f6f8fb; vertical-align: top; }
.rc-sec-title { color: #1a66cc; font-size: 13px; cursor: pointer; }
.rc-sec-title:hover { color: #0b4ea2; }
.rc-sec-body { display: none; }
.rc-sec.open { display: block; margin: 8px 0; padding: 8px 12px; }
.rc-sec.open .rc-sec-title { font-weight: 600; color: #333;
  border-bottom: 1px solid #e2e5ea; padding-bottom: 6px; margin-bottom: 8px; }
.rc-sec.open .rc-sec-body { display: block; }
.rc-sections { margin-top: 14px; }
.popheader { display: block; font-weight: 700; color: #1a66cc; margin: 10px 0 4px; }
.expandable { color: #333; }
.group { display: inline; }
.chwd, .entryhead { display: block; margin: 4px 0 8px; }
ul { margin: 4px 0 4px 18px; padding: 0; }
li { margin: 2px 0; }

.tail { display: block; margin: 10px 0 6px; }
.phrvbentry { display: block; margin-top: 12px; }
.colloc, .collocate-list, .colloc-list { display: block; margin: 8px 0; }
.etymology, .etymsense { display: block; margin: 2px 0; }
.hyphenation { display: inline; margin-left: 6px; }

""")


def _unwrap_document(fragment: str) -> str:
    """MDX 里存的是整篇 HTML 文档，只取 body 内容再包一次。"""
    if lxml_html is None:
        return fragment
    try:
        tree = lxml_html.fromstring(fragment)
    except Exception:
        return fragment
    body = tree.find(".//body")
    if body is None:
        return fragment
    return "".join(
        lxml_html.tostring(child, encoding="unicode") for child in body
    )


def _mdd_bytes(dictionary: Dictionary, name: str) -> bytes | None:
    mdd = getattr(dictionary, "_mdd", None)
    if mdd is None or not name:
        return None
    try:
        return mdd.lookup_bytes(name)
    except Exception:
        return None


def _inline_sounds(dictionary: Dictionary, html: str, audio_base: str = "") -> str:
    """把 sound:// 链接变成页面里能点的发音按钮。

    audio_base 给了就走本地接口按需取音频（`{key}` 占位）；
    没给就退回 data URI 内联，但最多内联 8 段，避免词条 HTML 涨到几 MB。
    """
    pattern = re.compile(r'<a\b([^>]*?)href="sound://([^"]+)"([^>]*)>', re.I)
    cache: dict[str, str] = {}
    inlined = 0
    inlined_bytes = 0
    max_inline = 60
    max_bytes = 1_500_000

    def replace(match: re.Match) -> str:
        nonlocal inlined, inlined_bytes
        key = match.group(2)
        attrs = match.group(1) + match.group(3)
        if audio_base:
            from urllib.parse import quote

            url = audio_base.replace("{key}", quote(key, safe=""))
            return f'<a{attrs} href="javascript:void(0)" class="rc-sound" data-audio="{url}">'
        if key in cache:
            uri = cache[key]
        else:
            if inlined >= max_inline or inlined_bytes >= max_bytes:
                return match.group(0)
            data = _mdd_bytes(dictionary, key)
            if not data:
                return match.group(0)
            ext = "." + key.rsplit(".", 1)[-1].lower() if "." in key else ".mp3"
            mime = _SOUND_MIME.get(ext, "audio/mpeg")
            uri = f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
            cache[key] = uri
            inlined += 1
            inlined_bytes += len(data)
        return f'<a{attrs} href="javascript:void(0)" class="rc-sound" data-audio="{uri}">'

    return pattern.sub(replace, html)


def _inline_css(dictionary: Dictionary, html: str) -> str:
    pattern = re.compile(r'<link\b[^>]*href="([^"]+\.css)"[^>]*>', re.I)
    for match in list(pattern.finditer(html)):
        css = _mdd_bytes(dictionary, match.group(1))
        if not css:
            continue
        text = css.decode("utf-8", "replace")
        html = html.replace(match.group(0), f"<style>{text}</style>")
    return html


def _inline_images(dictionary: Dictionary, html: str) -> str:
    pattern = re.compile(r'src="([^"]+)"')
    replacements: dict[str, str] = {}
    for match in pattern.finditer(html):
        src = match.group(1)
        if src.startswith("data:") or src.startswith("http"):
            continue
        data = _mdd_bytes(dictionary, src)
        if not data:
            continue
        ext = "." + src.rsplit(".", 1)[-1].lower() if "." in src else ""
        mime = _MIME.get(ext, "image/png")
        encoded = base64.b64encode(data).decode("ascii")
        replacements[f'src="{src}"'] = (
            f'src="data:{mime};base64,{encoded}" data-orig="{src}"'
        )
    for old, new in replacements.items():
        html = html.replace(old, new)
    return html




_LONGMAN_CSS = _templatize("""
.buttons { display: block; margin: 6px 0 4px; }
.buttons .popup-button {
  display: inline-block; border: 1px solid #8fa8c8; border-radius: 3px;
  color: #2f5d8a; background: #f7f9fc; padding: 1px 7px; margin: 2px 2px 2px 0;
  font-size: 12px; line-height: 1.4; cursor: pointer; white-space: nowrap;
  text-transform: uppercase;
}
.buttons .popup-button:hover { background: #e8f0fb; }
.buttons .at-link {
  display: none; width: 100%; box-sizing: border-box; margin: 6px 0 8px;
  background: #fbfcfd; border: 1px solid #8fa8c8; border-radius: 3px;
  padding: 10px 14px; max-height: 70vh; overflow: auto; text-align: left;
}
.buttons .at-link.open { display: block; }
.buttons .at-link .entry { display: block; }
""")

_LONGMAN_JS = """
document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('.buttons .popup-button').forEach(function (b) {
    b.removeAttribute('onclick');
  });
  document.addEventListener('click', function (e) {
    var b = e.target.closest('.buttons .popup-button');
    if (b) {
      var link = b.nextElementSibling;
      while (link && !(link.classList && link.classList.contains('at-link'))) {
        link = link.nextElementSibling;
      }
      if (!link) return;
      var wasOpen = link.classList.contains('open');
      document.querySelectorAll('.buttons .at-link.open').forEach(function (x) {
        x.classList.remove('open');
      });
      if (!wasOpen) link.classList.add('open');
      e.preventDefault();
      return;
    }
    if (!e.target.closest('.buttons .at-link')) {
      document.querySelectorAll('.buttons .at-link.open').forEach(function (x) {
        x.classList.remove('open');
      });
    }
  });
});
"""


_OHD_CSS = _templatize("""
/* 牛津-阿歇特（法语） */
.ohd-entry { max-width: 100%; }
.ohd-header { display: block; margin-bottom: 8px; }
.ohd-header h1, .ohd-header .ohd-headword, .ohd-headword { font-size: 26px; font-weight: 700; margin: 0; }
.ohd-part-number { display: block; font-size: §FONTSIZEpx; font-weight: 700; color: #b8860b; margin: 14px 0 4px; }
.ohd-pos { color: #1a66cc; font-style: italic; font-size: 13px; }
.ohd-pos-block { display: block; margin: 8px 0 6px; }
.ohd-pos-heading { display: block; margin-bottom: 2px; }
.ohd-sense-list { display: block; margin: 2px 0 2px 4px; }
.ohd-sense { display: block; margin: 3px 0 5px 0; }
.ohd-sense-no { display: inline-block; color: #cc2200; font-weight: 700; margin-right: 6px; }
.ohd-sense-content { display: inline; }
.ohd-example-list { display: block; margin: 2px 0 2px 20px; }
.ohd-example { display: block; margin: 2px 0; }
.ohd-example-content { display: inline; }
.ohd-example-mark { color: #b0b6c0; margin-right: 2px; }
.ohd-source-phrase { color: #333; }
.ohd-translation-arrow { color: #b0b6c0; margin: 0 6px; }
.ohd-example-target { color: #6b7280; }
.ohd-label { color: #8a8f98; font-style: italic; font-size: 13px; }
.ohd-translation { color: #444; }
blockquote { margin: 0; }
""")

_LATIN_CSS = _templatize("""
/* 牛津拉丁语 */
div[style*="font-size:150%"] { display: none; }
.rc-sensenum { display: inline-block; color: #cc2200; font-weight: 700; margin: 10px 6px 0 0; font-size: 16px; }
.rc-subsense { display: inline-block; color: #b8860b; font-weight: 700; margin: 4px 4px 0 12px; }
.rc-arrow { color: #b0b6c0; margin-right: 4px; }
strong { color: #1b1e24; }
body { line-height: 1.75; }
""")

_TOGGLE_JS = """
document.addEventListener('click', function (event) {
  var title = event.target.closest ? event.target.closest('.rc-sec-title') : null;
  if (title) {
    title.parentElement.classList.toggle('open');
    return;
  }
  var sound = event.target.closest ? event.target.closest('.rc-sound') : null;
  if (sound && sound.dataset.audio) {
    event.preventDefault();
    try {
      if (!window.__rcAudio) { window.__rcAudio = new Audio(); }
      window.__rcAudio.src = sound.dataset.audio;
      window.__rcAudio.currentTime = 0;
      var p = window.__rcAudio.play();
      if (p && p.catch) { p.catch(function () {}); }
    } catch (err) {}
  }
});
"""


def _profile(html: str) -> str:
    """按词典特征选择排版方案。"""
    if "ohd-entry" in html:
        return "ohd"
    if 'class="lm6"' in html or 'class="entry"' in html:
        return "longman"
    return "plain"


def _prepare_plain(html: str) -> str:
    """拉丁词典：去掉重复词头，把义项号/小标/例句箭头包成可样式化的元素。"""
    import re

    html = re.sub(
        r'<div style="font-size:\s*150%[^"]*">.*?</div>', "", html, count=1, flags=re.S
    )
    html = re.sub(r"<strong>(\d+)</strong>", r'<span class="rc-sensenum">\1</span>', html)
    html = re.sub(r"<strong>([a-z])</strong>", r'<span class="rc-subsense">\1</span>', html)
    html = re.sub(r"▶", '<span class="rc-arrow">▶</span>', html)
    return html


def build_entry_html(
    dictionary: Dictionary,
    word: str,
    title: str = "",
    dark: bool = False,
    colors: dict | None = None,
    font_size: int = 15,
    custom_css: str = "",
    audio_base: str = "",
) -> str:
    """取词条原始 HTML，补全资源，按词典类型补排版层次。"""
    raw = dictionary._mdx.lookup(word)
    if not raw:
        return ""
    html = raw[1] if isinstance(raw, tuple) else raw
    if isinstance(html, bytes):
        html = html.decode("utf-8", "replace")
    html = _unwrap_document(html)
    html = _inline_css(dictionary, html)
    html = _inline_images(dictionary, html)
    html = _inline_sounds(dictionary, html, audio_base)

    profile = _profile(html)
    # 原版视图保持词典自己的 HTML/CSS/按钮，不做重排和精简；
    # 结构化、去重、折叠只用于主界面的释义视图。


    html = html.replace('href="entry://', 'data-entry="')
    heading = title or word
    base_css = _BASE_CSS
    if profile == "ohd":
        base_css += _OHD_CSS
    elif profile == "plain":
        base_css += _LATIN_CSS
    if profile == "longman":
        base_css += _colorize(_LONGMAN_CSS, colors, font_size)
    base_css = _colorize(base_css, colors, font_size)
    if custom_css.strip():
        base_css += "\n" + custom_css
    return (
        "<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>"
        f"<title>{heading}</title>"
        f"<style>{base_css}</style></head><body>{html}"
        f"<script>{_TOGGLE_JS}{_LONGMAN_JS}</script></body></html>"
    )
