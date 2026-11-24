"""Turn a dictionary's raw MDX HTML into a standalone page for WebView2."""

from __future__ import annotations

import re
from html import escape
from urllib.parse import quote

_LINK_RE = re.compile(r"<link\b[^>]*>", re.IGNORECASE)
_STYLE_RE = re.compile(r"<style\b[^>]*>.*?</style>", re.IGNORECASE | re.DOTALL)
_SCRIPT_RE = re.compile(r"<script\b[^>]*>.*?</script>", re.IGNORECASE | re.DOTALL)
_HEAD_TAG_RE = re.compile(r"</?head\b[^>]*>", re.IGNORECASE)
_EVENT_ATTR_RE = re.compile(
    r"""\son\w+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)""", re.IGNORECASE
)
_JS_HREF_RE = re.compile(
    r"""(href\s*=\s*["'])\s*javascript:[^"']*(["'])""", re.IGNORECASE
)


def _extract_styles(html: str) -> tuple[str, str]:
    styles: list[str] = []

    def take_link(match: re.Match) -> str:
        tag = match.group(0)
        if re.search(r"""rel\s*=\s*["']?stylesheet""", tag, re.IGNORECASE):
            styles.append(tag)
            return ""
        return tag

    html = _LINK_RE.sub(take_link, html)
    html = _STYLE_RE.sub(lambda match: styles.append(match.group(0)) or "", html)
    return html, "".join(styles)


def _sanitize_fragment(html: str) -> str:
    html = _SCRIPT_RE.sub("", html)
    html = _HEAD_TAG_RE.sub("", html)
    html = _EVENT_ATTR_RE.sub("", html)
    html = _JS_HREF_RE.sub(r"\1#\2", html)
    return html


def build_raw_page(
    raw_html: str,
    *,
    source: str,
    word: str,
    resource_base: str,
    lookup_base: str,
    allow_scripts: bool = True,
) -> str:
    """Wrap raw dictionary HTML, rewriting MDX schemes and keeping its layout."""
    html = str(raw_html or "")

    # sound:// -> local MDD resource
    def _sound(match: re.Match) -> str:
        path = match.group(1).replace("\\", "/").lstrip("/")
        return resource_base + quote(path, safe="/")

    html = re.sub(r'sound://([^"\'\s>]+)', _sound, html, flags=re.IGNORECASE)

    # entry:// -> lookup page
    def _entry(match: re.Match) -> str:
        target = match.group(1)
        if target.startswith("#"):
            return target
        target = target.split("#", 1)[0]
        if not target:
            return match.group(0)
        return lookup_base + quote(target, safe="")

    html = re.sub(r'entry://([^"\'\s>]+)', _entry, html, flags=re.IGNORECASE)

    styles = ""
    if not allow_scripts:
        html, styles = _extract_styles(html)
        html = _sanitize_fragment(html)

    title = escape(source or word or "Dictionary")
    return f"""<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; media-src 'self'; font-src 'self' data:; connect-src 'none'; object-src 'none'; frame-src 'none'; form-action 'none'; base-uri 'self'">
<base href="{escape(resource_base, quote=True)}">
<title>{title}</title>
<style>
  html, body {{ margin: 0; padding: 0; }}
  body {{ background: #fff; color: #111; }}
  .gd-raw {{ padding: 16px 18px 28px; overflow-wrap: anywhere; }}
  .gd-raw img {{ max-width: 100%; height: auto; }}
  .gd-raw table {{ max-width: 100%; }}
  .gd-raw a {{ color: #0b57d0; }}
  .gd-raw .dsl-entry {{ line-height: 1.58; }}
  .gd-raw .dsl-trn, .gd-raw .dsl-sense {{ display: block; margin: .18em 0; }}
  .gd-raw .dsl-p {{ display: inline; }}
  .gd-raw .dsl-ref {{ color: #0b57d0; text-decoration: none; }}
</style>
{styles}
<script>
  window.addEventListener('load', function () {{
    try {{
      if ('scrollRestoration' in history) history.scrollRestoration = 'manual';
      window.scrollTo(0, 0);
      document.documentElement.scrollTop = 0;
      setTimeout(function () {{ window.scrollTo(0, 0); }}, 60);
    }} catch (e) {{}}
  }});

  // Dictionary audio icons are ordinary links rewritten to the local
  // resource URL. Navigating to the MP3 replaces the article with
  // Chromium's standalone media player; play it in place instead.
  document.addEventListener('click', function (event) {{
    var node = event.target;
    while (node && node !== document && node.tagName !== 'A') {{
      node = node.parentElement;
    }}
    if (!node || node.tagName !== 'A') return;
    var href = node.href || '';
    if (!/\\.(?:mp3|wav|ogg|oga|m4a|aac|flac|spx)(?:$|[?#])/i.test(href)) return;
    event.preventDefault();
    event.stopPropagation();
    try {{
      new Audio(href).play();
    }} catch (e) {{}}
    return false;
  }}, true);
</script>
</head>
<body><div class="gd-raw">{html}</div></body></html>"""
