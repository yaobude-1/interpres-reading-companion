"""音频播放：优先播放词典里的音频文件（MP3/WAV），播不了再退回 TTS。"""

from __future__ import annotations

import ctypes
import itertools
import tempfile
import time
import winsound
from pathlib import Path

_ALIAS = "rc_dict_audio"
_counter = itertools.count(1)


def _mci(command: str) -> int:
    try:
        return int(ctypes.windll.winmm.mciSendStringW(command, None, 0, 0))
    except Exception:
        return -1


def stop() -> None:
    """停掉正在播的词典音频和 TTS。"""
    _mci(f"close {_ALIAS}")
    try:
        winsound.PlaySound(None, winsound.SND_PURGE)
    except Exception:
        pass


def sniff_suffix(data: bytes) -> str:
    head = data[:12]
    if head[:3] == b"ID3" or head[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return ".mp3"
    if head[:4] == b"RIFF":
        return ".wav"
    if head[:4] == b"OggS":
        return ".ogg"
    return ".mp3"


def _cleanup_old() -> None:
    """删掉之前播过的临时文件（正在播的会被锁住，删不掉就跳过）。"""
    try:
        now = time.time()
        for path in Path(tempfile.gettempdir()).glob("rc_dict_audio_*"):
            try:
                if now - path.stat().st_mtime > 30:
                    path.unlink()
            except OSError:
                pass
    except Exception:
        pass


def play_bytes(data: bytes | None) -> bool:
    """播放一段音频数据；成功返回 True。"""
    if not data:
        return False
    stop()
    _cleanup_old()
    suffix = sniff_suffix(data)
    # MCI 播放时会把文件锁住，所以每次都用新文件名，避免第二次写入失败
    path = Path(tempfile.gettempdir()) / f"rc_dict_audio_{next(_counter)}{suffix}"
    try:
        path.write_bytes(data)
    except OSError:
        return False
    if suffix == ".mp3":
        if _mci(f'open "{path}" type mpegvideo alias {_ALIAS}') == 0:
            if _mci(f"play {_ALIAS}") == 0:
                return True
        return False
    try:
        winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
        return True
    except Exception:
        return False
