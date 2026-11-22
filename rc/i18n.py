"""界面多语言：中文（源语言）/ English。

做法：不改业务逻辑，在 Tk 显示层做翻译——
所有静态文本、窗口标题、菜单、messagebox 在显示前查一次词典。
词典是 zh -> en 的精确映射，另有少量模板规则处理动态字符串
（如「完成 · 123 ms」）。
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

log = logging.getLogger("rc")

LANGUAGE = "zh"
_TRANSLATIONS: dict[str, str] = {}
_PATTERNS: list[tuple[re.Pattern, str]] = []
_PHRASES: list[tuple[str, str]] = []
_INSTALLED = False
_ORIGINALS: dict = {}


def lang_display_name(entry: dict, code: str = "") -> str:
    """按当前界面语言选一个语言的显示名。

    英文界面优先本地名（label），中文界面优先中文名（zh_label）；缺了互相兜底，
    最后回退到语言代码。语言显示名是数据，不该被界面语言硬编码成中文。
    """
    if not isinstance(entry, dict):
        entry = {}
    if LANGUAGE == "en":
        return str(entry.get("label") or entry.get("zh_label") or code)
    return str(entry.get("zh_label") or entry.get("label") or code)


def wordbook_word() -> str:
    """默认词本名里用的名词：中文「词本」，英文「wordbook」。"""
    return "wordbook" if LANGUAGE == "en" else "词本"


def wordbook_suffix() -> str:
    """拼在语言名后面、用作默认词本名的后缀。"""
    return " wordbook" if LANGUAGE == "en" else "词本"


def _locale_dir() -> Path:
    return Path(__file__).resolve().parent / "locales"


def set_language(lang: str) -> None:
    global LANGUAGE, _TRANSLATIONS, _PATTERNS, _PHRASES
    lang = (lang or "zh").strip().lower()
    LANGUAGE = "en" if lang.startswith("en") else "zh"
    _TRANSLATIONS = {}
    _PATTERNS = []
    _PHRASES = []
    if LANGUAGE != "en":
        return
    path = _locale_dir() / "en.json"
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    for key, value in data.items():
        if isinstance(value, str):
            _TRANSLATIONS[key] = value
        elif key == "__patterns__" and isinstance(value, list):
            for item in value:
                try:
                    _PATTERNS.append((re.compile(item["zh"]), item["en"]))
                except Exception:
                    continue
        elif key == "__phrases__" and isinstance(value, list):
            for item in value:
                if isinstance(item, dict) and item.get("zh") and item.get("en"):
                    _PHRASES.append((str(item["zh"]), str(item["en"])))
            _PHRASES.sort(key=lambda pair: len(pair[0]), reverse=True)


def tr(text: str) -> str:
    """精确翻译；查不到就原样返回。"""
    if LANGUAGE == "zh" or not isinstance(text, str) or not text:
        return text
    translated = _TRANSLATIONS.get(text)
    if translated is not None:
        return translated
    for pattern, template in _PATTERNS:
        match = pattern.fullmatch(text)
        if match:
            try:
                out = template
                for index in range(1, match.re.groups + 1):
                    out = out.replace("{" + str(index) + "}", match.group(index) or "")
                return _replace_phrases(out)
            except Exception:
                return text
    return _replace_phrases(text)


def _replace_phrases(text: str) -> str:
    if not _PHRASES:
        return text
    for source, target in _PHRASES:
        if source and source in text:
            text = text.replace(source, target)
    return text


# ----------------------------------------------------------------- Tk 安装
def _patch_init(cls, attr_names=("text",)) -> None:
    original = cls.__init__

    def __init__(self, *args, **kwargs):
        for name in attr_names:
            value = kwargs.get(name)
            if isinstance(value, str):
                kwargs[name] = tr(value)
        original(self, *args, **kwargs)

    cls.__init__ = __init__


def _patch_method(cls, name: str, option: str) -> None:
    original = getattr(cls, name)

    def wrapper(self, *args, **kwargs):
        value = kwargs.get(option)
        if isinstance(value, str):
            kwargs[option] = tr(value)
        elif args and isinstance(args[0], str):
            args = (tr(args[0]),) + args[1:]
        return original(self, *args, **kwargs)

    setattr(cls, name, wrapper)


def _patch_configure(cls) -> None:
    original = cls.configure

    def configure(self, cnf=None, **kwargs):
        if "text" in kwargs and isinstance(kwargs["text"], str):
            kwargs["text"] = tr(kwargs["text"])
        return original(self, cnf, **kwargs)

    cls.configure = configure
    cls.config = configure


def install() -> None:
    """在创建任何 Tk 界面之前调用。重复调用无副作用。"""
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    try:
        import tkinter as tk
        from tkinter import messagebox, ttk
    except Exception:
        return

    for cls in (
        tk.Label,
        tk.Button,
        tk.Checkbutton,
        tk.Radiobutton,
        tk.Menubutton,
        tk.Message,
        tk.Canvas,
        tk.Frame,
        tk.LabelFrame,
        tk.Toplevel,
    ):
        if cls is tk.Canvas or cls is tk.Frame or cls is tk.Toplevel:
            continue
        _patch_init(cls)

    for cls in (ttk.Label, ttk.Button, ttk.Checkbutton, ttk.LabelFrame):
        _patch_init(cls)
    try:
        _patch_method(ttk.Treeview, "heading", "text")
    except (AttributeError, TypeError) as exc:  # noqa: BLE001 - 旧 Tk 可能没有该控件
        log.debug("Treeview 标题本地化挂钩失败: %s", exc)
    try:
        _patch_method(ttk.Notebook, "add", "text")
    except (AttributeError, TypeError) as exc:  # noqa: BLE001 - 旧 Tk 可能没有该控件
        log.debug("Notebook 标签本地化挂钩失败: %s", exc)

    # 窗口标题
    for cls in (tk.Tk, tk.Toplevel):
        original_title = cls.title

        def title(self, string=None, _orig=original_title):
            if isinstance(string, str):
                string = tr(string)
            return _orig(self, string)

        cls.title = title

    # 动态 configure(text=...)
    try:
        _patch_configure(tk.Misc)
    except (AttributeError, TypeError) as exc:  # noqa: BLE001 - 旧 Tk 可能没有 configure
        log.debug("configure 本地化挂钩失败: %s", exc)

    # 菜单
    try:
        for name in ("add_command", "add_cascade", "add_checkbutton", "add_radiobutton"):
            _patch_method(tk.Menu, name, "label")
    except (AttributeError, TypeError) as exc:  # noqa: BLE001 - 旧 Tk 菜单项可能不全
        log.debug("菜单本地化挂钩失败: %s", exc)

    # messagebox
    for name in ("showinfo", "showwarning", "showerror", "askyesno", "askokcancel", "askquestion"):
        original = getattr(messagebox, name, None)
        if original is None:
            continue

        def wrapper(*args, _orig=original, **kwargs):
            if "title" in kwargs and isinstance(kwargs["title"], str):
                kwargs["title"] = tr(kwargs["title"])
            if "message" in kwargs and isinstance(kwargs["message"], str):
                kwargs["message"] = tr(kwargs["message"])
            if args:
                args = tuple(tr(a) if isinstance(a, str) else a for a in args)
            return _orig(*args, **kwargs)

        setattr(messagebox, name, wrapper)
