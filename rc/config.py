"""配置读写。

配置存放在数据目录下的 config.json，首次启动自动生成。
"""

from __future__ import annotations

import base64
import copy
import ctypes
import json
import os
import secrets
from pathlib import Path

DEFAULT_LANGUAGES: dict[str, dict] = {
    "en": {
        "label": "English",
        "zh_label": "英语",
        "target": "zh-CN",
        "tts_voice": "Microsoft Zira Desktop",
        "deck": "Reading::English",
    },
    "fr": {
        "label": "Français",
        "zh_label": "法语",
        "target": "zh-CN",
        "tts_voice": "Microsoft Hortense Desktop",
        "deck": "Reading::Français",
    },
    "la": {
        "label": "Latina",
        "zh_label": "拉丁语",
        "target": "zh-CN",
        # 系统没有拉丁语音色，留空表示回退到法语/英语音色
        "tts_voice": "",
        "deck": "Reading::Latin",
    },
    "de": {
        "label": "Deutsch",
        "zh_label": "德语",
        "target": "zh-CN",
        "tts_voice": "",
        "deck": "Reading::Deutsch",
    },
    "es": {
        "label": "Español",
        "zh_label": "西班牙语",
        "target": "zh-CN",
        "tts_voice": "",
        "deck": "Reading::Español",
    },
}

DEFAULT_CONFIG: dict = {
    "api": {
        "base_url": "https://api.deepseek.com/v1",
        "api_key": "",
        "model": "deepseek-chat",
        "temperature": 0.3,
        "timeout": 90,
        "max_tokens": 1600,
    },
    "target_lang": "zh-CN",
    "hotkey": "ctrl+alt+t",
    "settings_hotkey": "ctrl+alt+s",
    "auto_follow_book": False,
    # 书名识别：窗口标题包含这些词就忽略（用户自定义，每行一条）
    "book_ignore_keywords": [],
    "panel_book": "",
    "quit_on_panel_close": True,
    # 有托盘时，关闭主窗口是否只隐藏到托盘
    "tray_close_hide": True,
    "anki_models": {},
    "anki_custom": {
        "enabled": False,
        "model": "Interpres",
        "fields": {},
        "front": "",
        "back": "",
        "css": "",
        "sync_templates": True,
    },
    "ui_lang": "zh",
    "lang_delete_lock": True,
    "lang_delete_warn": True,
    "ai_lang_consent": [],
    "auto_speak": False,
    "anki_skip_existing": True,
    # 英语同步 Anki 时用 Dict2Anki 模板（多义项 + 例句 + 音频）
    "anki_en_dict2anki": True,
    "popup_width": 560,
    "popup_max_height_ratio": 0.72,
    "server_port": 18777,
    "server_token": "",
    "context_chars": 1800,
    # 流式显示速度（字/秒）
    "stream_speed": 60,
    # 自定义提示词（留空用内置默认）
    "prompt_translate_system": "",
    "prompt_chat_persona": "",
    "prompt_chat_rules": "",
    "chat_passage_chars": 0,
    "audio_source": "dict_first",
    "history_keep": 30,
    # 本地词典：按语种配置 mdx / mdd
    "use_dictionary": True,
    "dictionaries": {
        "en": {"mdx": "", "mdd": ""},
        "fr": {"mdx": "", "mdd": ""},
        "la": {"mdx": "", "mdd": ""},
    },
    # 划词小按钮
    "selection": {
        "enabled": True,
        "drag": True,
        "double_click": True,
        "delay_ms": 150,
        "whitelist": [
            "chrome.exe",
            "msedge.exe",
            "firefox.exe",
            "okular.exe",
            "sumatrapdf.exe",
            "calibre.exe",
            "thorium.exe",
            "acrobat.exe",
            "acrord32.exe",
        ],
        "button": {
            "bg": "#7aa2f7",
            "fg": "#10131a",
            "alpha": 0.95,
            "hide_mode": "timeout",
            "hide_after_ms": 2500,
        },
        "bubble": {
            "bg": "#1b1d24",
            "fg": "#e6e9ef",
            "alpha": 0.97,
            "width": 440,
        },
    },
    "languages": DEFAULT_LANGUAGES,
}


def default_data_dir() -> Path:
    base = os.environ.get("RC_DATA_DIR")
    if base:
        return Path(base)
    return Path.home() / ".reading-companion"


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_char))]


if os.name == "nt":
    _crypt32 = ctypes.windll.crypt32
    _crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(_DATA_BLOB), ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32,
        ctypes.POINTER(_DATA_BLOB),
    ]
    _crypt32.CryptProtectData.restype = ctypes.c_bool
    _crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_DATA_BLOB), ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32,
        ctypes.POINTER(_DATA_BLOB),
    ]
    _crypt32.CryptUnprotectData.restype = ctypes.c_bool
    _kernel32 = ctypes.windll.kernel32
    _kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    _kernel32.LocalFree.restype = ctypes.c_void_p


def _dpapi_protect(text: str) -> str | None:
    if os.name != "nt":
        return None
    raw = text.encode("utf-8")
    buf = ctypes.create_string_buffer(raw)
    src = _DATA_BLOB(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    out = _DATA_BLOB()
    try:
        ok = _crypt32.CryptProtectData(
            ctypes.byref(src), None, None, None, None, 0x1, ctypes.byref(out)
        )
        if not ok:
            return None
        data = ctypes.string_at(out.pbData, out.cbData)
        return "dpapi:" + base64.b64encode(data).decode("ascii")
    finally:
        if out.pbData:
            _kernel32.LocalFree(out.pbData)


def _dpapi_unprotect(value: str) -> str | None:
    if os.name != "nt" or not value.startswith("dpapi:"):
        return None
    try:
        raw = base64.b64decode(value[6:])
        buf = ctypes.create_string_buffer(raw)
        src = _DATA_BLOB(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
        out = _DATA_BLOB()
        ok = _crypt32.CryptUnprotectData(
            ctypes.byref(src), None, None, None, None, 0x1, ctypes.byref(out)
        )
        if not ok:
            return None
        try:
            return ctypes.string_at(out.pbData, out.cbData).decode("utf-8")
        finally:
            if out.pbData:
                _kernel32.LocalFree(out.pbData)
    except Exception:
        return None


class Config:
    """轻量配置对象：点号访问 + 自动保存。"""

    def __init__(self, data_dir: Path | str | None = None) -> None:
        self.data_dir = Path(data_dir) if data_dir else default_data_dir()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.data_dir / "config.json"
        self.data: dict = copy.deepcopy(DEFAULT_CONFIG)
        self._api_key_undecryptable: bool | None = None
        self.load()

    # ---------------------------------------------------------------- load / save
    def load(self) -> None:
        if not self.path.exists():
            self.data["server_token"] = secrets.token_hex(16)
            self.save()
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            raw = {}
        self.data = _merge(copy.deepcopy(DEFAULT_CONFIG), raw)
        if not self.data.get("server_token"):
            self.data["server_token"] = secrets.token_hex(16)
            self.save()
        self._migrate_api_key()

    def _migrate_api_key(self) -> None:
        key = str(self.api.get("api_key") or "").strip()
        if not key or key.startswith("dpapi:"):
            return
        protected = _dpapi_protect(key)
        if protected:
            self.api["api_key"] = protected
            self.save()

    def save(self) -> None:
        key = str(self.api.get("api_key") or "").strip()
        if key and not key.startswith("dpapi:"):
            protected = _dpapi_protect(key)
            if protected:
                self.api["api_key"] = protected
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    # ---------------------------------------------------------------- accessors
    @property
    def api(self) -> dict:
        return self.data["api"]

    @property
    def api_key(self) -> str:
        raw = str(self.api.get("api_key") or "").strip()
        if raw.startswith("dpapi:"):
            plain = _dpapi_unprotect(raw)
            self._api_key_undecryptable = plain is None
            return (plain or "").strip()
        self._api_key_undecryptable = False
        return raw

    @property
    def api_key_error(self) -> str:
        """配置里存了 Key 但解不开时给出可读原因；正常情况返回空串。"""
        raw = str(self.api.get("api_key") or "").strip()
        if not raw.startswith("dpapi:"):
            return ""
        if self._api_key_undecryptable is None:
            self._api_key_undecryptable = _dpapi_unprotect(raw) is None
        if self._api_key_undecryptable:
            return "配置里的 API Key 无法解密（配置文件可能来自另一台电脑或另一个 Windows 用户），请重新填写。"
        return ""

    def set_api_key(self, key: str) -> None:
        key = (key or "").strip()
        self.api["api_key"] = _dpapi_protect(key) if key else ""

    def language(self, code: str | None) -> dict:
        """取某语言的配置；未知语言返回一个安全回退。"""
        table = self.data.get("languages") or {}
        if code and code in table:
            return table[code]
        return {
            "label": code or "unknown",
            "zh_label": code or "未知",
            "target": self.data.get("target_lang", "zh-CN"),
            "tts_voice": "",
            "deck": f"Reading::{(code or 'Other').title()}",
        }

    def ensure_language(self, code: str, label: str | None = None) -> dict:
        """遇到新语言时自动登记，保证生词本 / Anki deck 有归属。"""
        table = self.data.setdefault("languages", {})
        if code not in table:
            table[code] = {
                "label": label or code,
                "zh_label": label or code,
                "target": self.data.get("target_lang", "zh-CN"),
                "tts_voice": "",
                "deck": f"Reading::{(label or code).title()}",
            }
            self.save()
        return table[code]

    def get(self, key: str, default=None):
        return self.data.get(key, default)


def _merge(base: dict, override: dict) -> dict:
    """深合并：override 覆盖 base，但不会丢掉 base 里的默认项。"""
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            base[k] = _merge(base[k], v)
        else:
            base[k] = v
    return base
