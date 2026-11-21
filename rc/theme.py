"""Shared palette and font used by the popup, panel and settings windows.

主题/强调色在 import 时从 config.json 读取，所以修改后需要重启才能让所有
已经创建的控件换色；尺寸/透明度则可以在下次打开窗口时生效。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

_DARK = {
    "BG": "#1b1d24",
    "PANEL": "#23262f",
    "PANEL_ALT": "#2a2e39",
    "SIDEBAR": "#10131a",
    "TEXT": "#e6e9ef",
    "MUTED": "#9aa5b1",
    "DIM": "#6b7280",
    "ACCENT": "#7aa2f7",
    "ON_ACCENT": "#10131a",
    "GREEN": "#9ece6a",
    "RED": "#f7768e",
    "BORDER": "#3b414f",
    "BORDER_SOFT": "#2f3440",
    "FIELD_BG": "#1b1e26",
    "FIELD_BORDER": "#2c313c",
    "SCROLL_THUMB": "#4b5263",
    "SCROLL_TRACK": "#15171d",
}

_LIGHT = {
    "BG": "#f4f5f7",
    "PANEL": "#ffffff",
    "PANEL_ALT": "#e9edf4",
    "SIDEBAR": "#e3e8f0",
    "TEXT": "#1f2430",
    "MUTED": "#5b6472",
    "DIM": "#8a93a3",
    "ACCENT": "#2563eb",
    "ON_ACCENT": "#ffffff",
    "GREEN": "#2f8f46",
    "RED": "#c0392b",
    "BORDER": "#c9d0dc",
    "BORDER_SOFT": "#d8dee8",
    "FIELD_BG": "#ffffff",
    "FIELD_BORDER": "#c9d0dc",
    "SCROLL_THUMB": "#b6bfcc",
    "SCROLL_TRACK": "#e3e8f0",
}

ACCENTS = {
    "blue": {"dark": "#7aa2f7", "light": "#2563eb"},
    "green": {"dark": "#9ece6a", "light": "#2f8f46"},
    "purple": {"dark": "#bb9af7", "light": "#7c3aed"},
    "orange": {"dark": "#ff9e64", "light": "#c2410c"},
}


def _read_appearance() -> dict:
    base = os.environ.get("RC_DATA_DIR")
    root = Path(base) if base else Path.home() / ".reading-companion"
    try:
        data = json.loads((root / "config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    appearance = data.get("appearance")
    return appearance if isinstance(appearance, dict) else {}


def palette(theme: str, accent: str) -> dict:
    """Return the palette for a theme name and an accent preset."""
    chosen = _LIGHT if theme == "light" else _DARK
    result = dict(chosen)
    name = (accent or "blue").lower()
    if name in ACCENTS:
        result["ACCENT"] = ACCENTS[name]["light" if theme == "light" else "dark"]
        result["ON_ACCENT"] = "#ffffff" if theme == "light" else "#10131a"
    return result


_appearance = _read_appearance()
_theme = str(_appearance.get("theme") or "dark").lower()
_accent = str(_appearance.get("accent") or "blue").lower()
PALETTE = palette(_theme, _accent)

BG = PALETTE["BG"]
PANEL = PALETTE["PANEL"]
PANEL_ALT = PALETTE["PANEL_ALT"]
SIDEBAR = PALETTE["SIDEBAR"]
TEXT = PALETTE["TEXT"]
MUTED = PALETTE["MUTED"]
DIM = PALETTE["DIM"]
ACCENT = PALETTE["ACCENT"]
ON_ACCENT = PALETTE["ON_ACCENT"]
GREEN = PALETTE["GREEN"]
RED = PALETTE["RED"]
BORDER = PALETTE["BORDER"]
BORDER_SOFT = PALETTE["BORDER_SOFT"]
FIELD_BG = PALETTE["FIELD_BG"]
FIELD_BORDER = PALETTE["FIELD_BORDER"]
SCROLL_THUMB = PALETTE["SCROLL_THUMB"]
SCROLL_TRACK = PALETTE["SCROLL_TRACK"]

FONT_FAMILY = "Microsoft YaHei UI"
