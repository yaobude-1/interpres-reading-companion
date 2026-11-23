"""Windows.Media.Ocr wrapper for screenshot OCR.

The WinRT packages are optional at import time so the rest of the app still
starts on machines where OCR was not packaged or the language pack is missing.
"""

from __future__ import annotations

import asyncio
import logging
import re
import tempfile
from pathlib import Path

from PIL import Image

log = logging.getLogger("rc")

_BULLET = re.compile(r"^[\s\u2022\u00b7\u25cf\u25aa\u25e6*\-–—]+", re.MULTILINE)
_NUMBER = re.compile(r"^\s*\d{1,3}[.)、]\s*", re.MULTILINE)


def clean_text(text: str) -> str:
    """Remove OCR list bullets / numbering before dictionary lookup."""
    lines: list[str] = []
    for line in (text or "").splitlines():
        line = _BULLET.sub("", line.strip())
        line = _NUMBER.sub("", line).strip()
        if line:
            lines.append(line)
    return "\n".join(lines).strip()


class OcrUnavailable(RuntimeError):
    pass


def available_languages() -> list[str]:
    try:
        from winrt.windows.media.ocr import OcrEngine

        return [str(item.language_tag) for item in OcrEngine.available_recognizer_languages]
    except Exception:
        return []


def _engine(language: str = ""):
    try:
        from winrt.windows.globalization import Language
        from winrt.windows.media.ocr import OcrEngine
    except Exception as exc:  # noqa: BLE001 - optional WinRT dependency
        raise OcrUnavailable(
            "OCR 依赖未安装（需要 winrt-runtime / Windows OCR 包）"
        ) from exc
    if language:
        engine = OcrEngine.try_create_from_language(Language(language))
        if engine is not None:
            return engine, language
    try:
        engine = OcrEngine.try_create_from_user_profile_languages()
        if engine is not None:
            return engine, "user"
    except Exception as exc:  # noqa: BLE001 - user-profile OCR fallback is optional
        log.debug("读取用户默认 OCR 语言失败: %s", exc)
    for tag in available_languages():
        engine = OcrEngine.try_create_from_language(Language(tag))
        if engine is not None:
            return engine, tag
    raise OcrUnavailable(
        "Windows OCR 没有可用语言包。请在 Windows 设置里给需要的语言安装 OCR 可选功能。"
    )


async def _recognize_file(path: Path, language: str) -> str:
    from winrt.windows.graphics.imaging import BitmapDecoder
    from winrt.windows.storage import FileAccessMode, StorageFile

    engine, _tag = _engine(language)
    file = await StorageFile.get_file_from_path_async(str(path))
    stream = await file.open_async(FileAccessMode.READ)
    decoder = await BitmapDecoder.create_async(stream)
    bitmap = await decoder.get_software_bitmap_async()
    result = await engine.recognize_async(bitmap)
    lines = [str(line.text) for line in result.lines if str(line.text).strip()]
    return "\n".join(lines).strip()


def recognize_file(path: Path, language: str = "") -> str:
    return asyncio.run(_recognize_file(Path(path), language))


def recognize_image(image: Image.Image, language: str = "") -> str:
    """OCR a PIL image via a temporary PNG file (Windows OCR API needs a file)."""
    if image.width < 2 or image.height < 2:
        return ""
    # Upscaling small screen text noticeably improves Windows OCR.
    if image.width < 1200:
        image = image.resize(
            (image.width * 2, image.height * 2), Image.Resampling.LANCZOS
        )
    handle = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    path = Path(handle.name)
    handle.close()
    try:
        image.convert("RGB").save(path)
        return recognize_file(path, language)
    finally:
        try:
            path.unlink()
        except OSError:
            pass


def language_hint(config) -> str:
    return str(config.get("ocr_language", "") or "").strip()
