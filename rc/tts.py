"""发音（TTS）。

用 Windows 自带的 SAPI 合成语音（离线、免费），生成为 wav 后播放。
系统没装的语种会回退到相近语言的音色，保证「有声音」而不是报错。
"""

from __future__ import annotations

import hashlib
import logging
import subprocess
import sys
import threading
import winsound
from pathlib import Path

# 没有对应音色时的近似回退
VOICE_FALLBACK = {
    "la": ["fr", "it", "es"],
    "grc": ["fr", "it"],
    "de": ["en"],
    "es": ["fr"],
    "it": ["es", "fr"],
    "ja": ["zh"],
    "ko": ["zh", "ja"],
    "ru": ["en"],
}

_PS_VOICES = (
    "Add-Type -AssemblyName System.Speech; "
    "(New-Object System.Speech.Synthesis.SpeechSynthesizer).GetInstalledVoices() | "
    "ForEach-Object { $_.VoiceInfo.Name + '|' + $_.VoiceInfo.Culture.Name }"
)

_SCRIPT_SRC = Path(__file__).with_name("tts_script.ps1")
log = logging.getLogger("tts")


def _decode(raw: bytes) -> str:
    """PowerShell 的错误信息是 GBK，按 UTF-8 硬解会是乱码。"""
    if not raw:
        return ""
    for encoding in ("utf-8", "gbk", "mbcs"):
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", "replace")


class TTS:
    def __init__(self, config, cache_dir: Path | str) -> None:
        self.config = config
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._script = _SCRIPT_SRC
        self._lock = threading.Lock()
        self._voices: list[dict] | None = None
        self._last: Path | None = None

    # ------------------------------------------------------------------ voices
    def voices(self) -> list[dict]:
        if self._voices is not None:
            return self._voices
        result: list[dict] = []
        try:
            proc = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    _PS_VOICES,
                ],
                capture_output=True,
                timeout=20,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            for line in _decode(proc.stdout).splitlines():
                if "|" in line:
                    name, culture = line.split("|", 1)
                    result.append({"name": name.strip(), "culture": culture.strip()})
        except Exception:
            pass
        for voice in self._onecore_voices():
            if all(v["name"] != voice["name"] for v in result):
                result.append(voice)
        self._voices = result
        return result

    def _onecore_voices(self) -> list[dict]:
        """Windows OneCore（设置 → 语音 里添加的）音色，SAPI 列不出来。"""
        import locale
        import winreg

        tokens = r"SOFTWARE\Microsoft\Speech_OneCore\Voices\Tokens"
        result: list[dict] = []
        try:
            root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, tokens)
        except OSError:
            return result
        index = 0
        while True:
            try:
                sub = winreg.EnumKey(root, index)
            except OSError:
                break
            index += 1
            try:
                key = winreg.OpenKey(root, sub)
            except OSError:
                continue
            try:
                name = str(winreg.QueryValueEx(key, "")[0]).strip()
                lcid = ""
                j = 0
                while True:
                    try:
                        value_name, value, _typ = winreg.EnumValue(key, j)
                    except OSError:
                        break
                    j += 1
                    if value_name and value_name.upper() not in (
                        "CLSID", "LANGDATAPATH", "VOICEPATH"
                    ):
                        if all(c in "0123456789abcdefABCDEF" for c in value_name):
                            lcid = value_name
                            break
                culture = ""
                if lcid:
                    try:
                        culture = locale.windows_locale.get(int(lcid, 16), "").replace("_", "-")
                    except ValueError:
                        culture = ""
                if name:
                    result.append({"name": name, "culture": culture, "engine": "onecore"})
            finally:
                key.Close()
        return result

    def _voice_engine(self, voice: str) -> str:
        for item in self._onecore_voices():
            if item["name"] == voice:
                return "onecore"
        return "sapi"

    def engine_for(self, lang: str) -> str:
        entry = self.config.language(lang)
        return (entry.get("tts_engine") or "system").strip().lower()

    def voice_for(self, lang: str) -> str:
        entry = self.config.language(lang)
        wanted = (entry.get("tts_voice") or "").strip()
        installed = self.voices()
        names = [v["name"] for v in installed]
        if wanted and wanted in names:
            return wanted
        # 按语言前缀找
        for prefix in [lang] + VOICE_FALLBACK.get(lang, []):
            for v in installed:
                if v["culture"].lower().startswith(prefix.lower()):
                    return v["name"]
        return ""

    # -------------------------------------------------------------- synthesize
    def synthesize(self, text: str, lang: str) -> Path:
        engine = self.engine_for(lang)
        if engine == "edge":
            return self._edge_synthesize(text, self._configured_voice(lang), lang)
        if engine == "command":
            return self._command_synthesize(text, lang)
        return self._synthesize(text, self.voice_for(lang))

    def _configured_voice(self, lang: str) -> str:
        entry = self.config.language(lang)
        return (entry.get("tts_voice") or "").strip()

    def edge_voice_choices(self, lang: str) -> list[dict]:
        """Edge 音色列表，优先这门语言的；失败返回空。"""
        from . import tts_edge

        items = tts_edge.list_voices(self.cache_dir / "edge_voices.json")
        lang = (lang or "").strip().lower()
        if not lang:
            return items
        exact = [v for v in items if v.get("culture", "").lower() == lang]
        prefix = [
            v for v in items
            if v.get("culture", "").lower().startswith(lang + "-")
            and v not in exact
        ]
        base = lang.split("-")[0]
        same_base = [
            v for v in items
            if v.get("culture", "").lower().startswith(base + "-")
            and v not in exact and v not in prefix
        ]
        chosen = (exact + prefix + same_base) or items
        try:
            default = tts_edge.pick_voice(lang, self.cache_dir / "edge_voices.json")
        except Exception:
            default = ""
        chosen.sort(
            key=lambda v: (
                0 if v.get("name") == default else 1,
                v.get("culture", ""),
            )
        )
        return chosen

    def _edge_synthesize(self, text: str, voice: str, lang: str) -> Path:
        from . import tts_edge

        text = (text or "").strip()
        if not text:
            raise ValueError("没有可朗读的文字")
        key = hashlib.sha1(f"edge\x00{voice}\x00{text}".encode("utf-8")).hexdigest()
        out = self.cache_dir / f"{key}.mp3"
        if out.exists() and out.stat().st_size > 1024:
            return out
        used = tts_edge.synthesize(
            text, voice, lang, out, cache_file=self.cache_dir / "edge_voices.json"
        )
        log.info("Edge TTS 合成完成 voice=%s size=%s", used, out.stat().st_size)
        return out

    def _command_synthesize(self, text: str, lang: str) -> Path:
        entry = self.config.language(lang)
        template = (entry.get("tts_command") or "").strip()
        if not template:
            raise RuntimeError("这门语言没有配置自定义发音命令")
        text = (text or "").strip()
        if not text:
            raise ValueError("没有可朗读的文字")
        key = hashlib.sha1(f"cmd\x00{template}\x00{text}".encode("utf-8")).hexdigest()
        out = self.cache_dir / f"{key}.wav"
        if out.exists() and out.stat().st_size > 1024:
            return out
        text_file = self.cache_dir / f"{key}.txt"
        text_file.write_text(text, encoding="utf-8-sig")
        command = template.format(
            text_file=str(text_file),
            out_file=str(out),
            lang=lang,
            voice=self._configured_voice(lang),
        )
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            timeout=120,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            text_file.unlink()
        except OSError:
            pass
        if proc.returncode != 0 or not out.exists() or out.stat().st_size <= 1024:
            err = _decode(proc.stderr) or _decode(proc.stdout)
            raise RuntimeError(f"自定义发音命令失败：{err.strip()[:80] or proc.returncode}")
        return out

    def speak_with(self, text: str, voice: str, lang: str = "", engine: str = "") -> Path:
        """用指定音色/引擎朗读（设置里试听用）。"""
        engine = (engine or self.engine_for(lang) or "system").strip().lower()
        if engine == "edge":
            path = self._edge_synthesize(text, voice, lang)
        elif engine == "command":
            path = self._command_synthesize(text, lang)
        else:
            path = self._synthesize(text, voice, lang)
        with self._lock:
            winsound.PlaySound(None, winsound.SND_PURGE)
            log.info("播放音频 %s size=%s", path.name, path.stat().st_size)
            if path.suffix.lower() == ".mp3":
                self._play_mp3(path)
            else:
                try:
                    self._play_soundplayer(path)
                except Exception:
                    log.exception("SoundPlayer 播放失败，改用 winsound")
                    winsound.PlaySound(
                        str(path), winsound.SND_FILENAME | winsound.SND_ASYNC
                    )
            self._last = path
        return path

    def _onecore(self, text_file: Path, out: Path, lang: str, voice: str = "") -> bool:
        script = Path(__file__).with_name("tts_onecore.ps1")
        if not script.exists():
            log.warning("OneCore 脚本不存在：%s", script)
            return False
        try:
            proc = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(script),
                    "-TextFile",
                    str(text_file),
                    "-OutFile",
                    str(out),
                    "-Lang",
                    lang or "en",
                    "-Voice",
                    voice or "",
                ],
                capture_output=True,
                timeout=120,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("OneCore 调用失败：%s", exc)
            return False
        if proc.returncode == 0 and out.exists() and out.stat().st_size > 1024:
            return True
        err = _decode(proc.stderr)
        log.warning("OneCore 失败 rc=%s err=%s", proc.returncode, err[:300])
        return False

    def _synthesize(self, text: str, voice: str, lang: str = "") -> Path:
        text = (text or "").strip()
        if not text:
            raise ValueError("没有可朗读的文字")
        key = hashlib.sha1(f"{voice}\x00{text}".encode("utf-8")).hexdigest()
        out = self.cache_dir / f"{key}.wav"
        if out.exists() and out.stat().st_size > 1024:
            return out

        text_file = self.cache_dir / f"{key}.txt"
        text_file.write_text(text, encoding="utf-8-sig")
        if voice and self._voice_engine(voice) == "onecore":
            if not self._onecore(text_file, out, lang, voice):
                raise RuntimeError(f"OneCore 音色合成失败：{voice}")
            try:
                text_file.unlink()
            except OSError:
                pass
            return out
        proc = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(self._script),
                "-InFile",
                str(text_file),
                "-OutFile",
                str(out),
                "-Voice",
                voice,
            ],
            capture_output=True,
            timeout=120,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if proc.returncode != 0 or not out.exists() or out.stat().st_size <= 1024:
            err = _decode(proc.stderr) or _decode(proc.stdout)
            log.warning("SAPI 失败 voice=%r rc=%s err=%s", voice, proc.returncode, err[:300])
            if self._onecore(text_file, out, lang):
                log.info("已回退 OneCore 语音 lang=%r", lang)
            else:
                raise RuntimeError(f"语音合成失败：{err.strip()[:80] or '未知原因'}")
        try:
            text_file.unlink()
        except OSError:
            pass
        if not out.exists() or out.stat().st_size < 2048:
            if out.exists():
                try:
                    out.unlink()
                except OSError:
                    pass
            raise RuntimeError("语音合成失败：系统没有可用的语音")
        return out

    def self_test(self) -> dict:
        """启动自检：枚举语音 + 试合成一句，结果写日志。"""
        info: dict = {"voices": [], "sapi": {}, "onecore": {}, "script": str(self._script),
                      "script_exists": self._script.exists()}
        try:
            info["voices"] = [v.get("name") for v in self.voices()]
        except Exception as exc:  # noqa: BLE001
            info["voices"] = [f"枚举失败: {exc}"]
        for lang, text in (("en", "test"), ("fr", "bonjour")):
            try:
                path = self._synthesize(text, self.voice_for(lang), lang)
                info["sapi"][lang] = f"ok {path.name} {path.stat().st_size}B"
            except Exception as exc:  # noqa: BLE001
                info["sapi"][lang] = f"失败: {str(exc)[:120]}"
        log.info("TTS 自检：%s", info)
        return info

    def speak(self, text: str, lang: str) -> Path:
        engine = self.engine_for(lang)
        if engine == "system":
            voice = self.voice_for(lang)
            if not voice:
                raise RuntimeError(
                    f"没有可用的{lang}音色：请到 设置 → 语言 里指定，或安装系统语音"
                )
        else:
            voice = self._configured_voice(lang)
        return self.speak_with(text, voice, lang, engine=engine)

    def _play_mp3(self, path: Path) -> None:
        """用 MCI 播放 mp3（MediaPlayer 在部分机器上不出声）。"""
        import ctypes

        winmm = ctypes.WinDLL("winmm")
        buf = ctypes.create_unicode_buffer(512)
        alias = "interpres_tts"

        def mci(command: str) -> int:
            return int(winmm.mciSendStringW(command, buf, 512, 0))

        mci(f"close {alias}")
        code = mci(f'open "{path}" type mpegvideo alias {alias}')
        if code != 0:
            raise RuntimeError(f"无法打开音频（MCI {code}）")
        try:
            code = mci(f"play {alias} wait")
            if code != 0:
                raise RuntimeError(f"播放失败（MCI {code}）")
        finally:
            mci(f"close {alias}")
        log.info("MCI 播放完成 %s", path.name)

    def _play_soundplayer(self, path: Path) -> None:
        try:
            subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    f"(New-Object System.Media.SoundPlayer '{path}').PlaySync()",
                ],
                capture_output=True,
                timeout=120,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            log.info("SoundPlayer 播放完成 %s", path.name)
        except Exception:
            log.exception("SoundPlayer 也失败")

    def stop(self) -> None:
        with self._lock:
            winsound.PlaySound(None, winsound.SND_PURGE)


def available() -> bool:
    return sys.platform == "win32"
