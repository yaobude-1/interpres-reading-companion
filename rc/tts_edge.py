"""Edge TTS（微软在线神经音色）：按需合成 mp3。

只在用户把某门语言设成 Edge 引擎时才会用到；需要联网。
"""

from __future__ import annotations

import asyncio
import json
import sys
import threading
from pathlib import Path

_DEFAULT_VOICES = {
    "en": "en-US-AriaNeural",
    "fr": "fr-FR-DeniseNeural",
    "de": "de-DE-KatjaNeural",
    "es": "es-ES-ElviraNeural",
    "it": "it-IT-ElsaNeural",
    "pt": "pt-BR-FranciscaNeural",
    "ru": "ru-RU-SvetlanaNeural",
    "ja": "ja-JP-NanamiNeural",
    "ko": "ko-KR-SunHiNeural",
    "zh": "zh-CN-XiaoxiaoNeural",
    "ar": "ar-SA-ZariyahNeural",
    "nl": "nl-NL-ColetteNeural",
    "pl": "pl-PL-ZofiaNeural",
    "tr": "tr-TR-EmelNeural",
    "sv": "sv-SE-SofieNeural",
    "da": "da-DK-ChristelNeural",
    "fi": "fi-FI-NooraNeural",
    "nb": "nb-NO-PernilleNeural",
    "cs": "cs-CZ-VlastaNeural",
    "el": "el-GR-AthinaNeural",
    "he": "he-IL-HilaNeural",
    "hi": "hi-IN-SwaraNeural",
    "th": "th-TH-PremwadeeNeural",
    "vi": "vi-VN-HoaiMyNeural",
    "uk": "uk-UA-PolinaNeural",
    "ro": "ro-RO-AlinaNeural",
    "hu": "hu-HU-NoemiNeural",
    "id": "id-ID-GadisNeural",
    "ms": "ms-MY-YasminNeural",
    "fa": "fa-IR-DilaraNeural",
    "la": "it-IT-ElsaNeural",
    "grc": "el-GR-AthinaNeural",
}

_lock = threading.Lock()
_voice_cache: list[dict] | None = None


def _ensure_vendor() -> None:
    root = Path(__file__).resolve().parent.parent
    vendor = root / "vendor"
    if vendor.is_dir() and str(vendor) not in sys.path and not getattr(sys, "frozen", False):
        sys.path.insert(0, str(vendor))


def _import_edge():
    _ensure_vendor()
    import edge_tts  # noqa: PLC0415

    return edge_tts


def list_voices(cache_file: Path | None = None) -> list[dict]:
    """拉取在线音色列表（缓存到磁盘，失败时返回空）。"""
    global _voice_cache
    with _lock:
        if _voice_cache is not None:
            return _voice_cache
        if cache_file is not None and cache_file.exists():
            try:
                data = json.loads(cache_file.read_text(encoding="utf-8"))
                if isinstance(data, list) and data:
                    _voice_cache = data
                    return data
            except Exception:
                pass
        try:
            edge_tts = _import_edge()
            voices = asyncio.run(edge_tts.list_voices())
            items = [
                {
                    "name": v.get("ShortName", ""),
                    "culture": v.get("Locale", ""),
                    "gender": v.get("Gender", ""),
                }
                for v in voices
                if v.get("ShortName")
            ]
            _voice_cache = items
            if cache_file is not None and items:
                try:
                    cache_file.parent.mkdir(parents=True, exist_ok=True)
                    cache_file.write_text(
                        json.dumps(items, ensure_ascii=False), encoding="utf-8"
                    )
                except Exception:
                    pass
            return items
        except Exception:
            _voice_cache = []
            return []


def pick_voice(lang: str, cache_file: Path | None = None) -> str:
    lang = (lang or "").lower()
    voices = list_voices(cache_file)
    base = lang.split("-")[0]
    preferred = _DEFAULT_VOICES.get(base)
    if voices and preferred and any(v["name"] == preferred for v in voices):
        return preferred
    if voices:
        exact = [v for v in voices if v["culture"].lower() == lang]
        prefix = [v for v in voices if v["culture"].lower().startswith(lang + "-")]
        for group in (exact, prefix):
            if group:
                return group[0]["name"]
    return preferred or _DEFAULT_VOICES.get(base, _DEFAULT_VOICES["en"])


def synthesize(text: str, voice: str, lang: str, out_path: Path, cache_file: Path | None = None) -> str:
    """合成到 mp3，返回实际使用的音色名。"""
    edge_tts = _import_edge()
    text = (text or "").strip()
    if not text:
        raise ValueError("没有可朗读的文字")
    voice = (voice or "").strip() or pick_voice(lang, cache_file)

    async def run() -> None:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(out_path))

    asyncio.run(run())
    if not out_path.exists() or out_path.stat().st_size <= 1024:
        raise RuntimeError("Edge TTS 没有返回音频")
    return voice
