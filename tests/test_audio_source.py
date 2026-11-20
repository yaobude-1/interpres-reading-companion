"""验证发音来源设置：词典优先 / 只用 TTS / 只用词典。"""

from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from rc.config import Config  # noqa: E402
from tests import mock_openai  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


def main() -> int:
    data = HERE / ".audiosrc"
    shutil.rmtree(data, ignore_errors=True)
    data.mkdir(parents=True)
    mock_openai.start(18778)

    cfg = Config(data)
    cfg.data["server_port"] = 18816
    cfg.data["api"].update(
        {"base_url": "http://127.0.0.1:18778/v1", "api_key": "k", "model": "mock"}
    )
    cfg.save()

    from app import Application

    app = Application(cfg, enable_hotkeys=False)
    calls: list[str] = []
    app.service.play_dictionary_audio = lambda lang, key: (calls.append("dict"), True)[1]
    app.service.speak = lambda text, lang: calls.append("tts")

    def speak(mode: str, audio_key: str = "hwd/x.mp3", dict_ok: bool = True) -> list[str]:
        calls.clear()
        app.config.data["audio_source"] = mode
        if not dict_ok:
            app.service.play_dictionary_audio = lambda lang, key: (calls.append("dict"), False)[1]
        else:
            app.service.play_dictionary_audio = lambda lang, key: (calls.append("dict"), True)[1]
        app.speak("ephemeral", "en", audio_key)
        time.sleep(0.25)
        app.root.update()
        return list(calls)

    print("\n[词典优先]")
    result = speak("dict_first")
    check("播放词典音频", result == ["dict"], str(result))

    print("\n[只用 TTS]")
    result = speak("tts")
    check("只走 TTS", result == ["tts"], str(result))

    print("\n[只用词典]")
    result = speak("dict_only")
    check("只播放词典音频", result == ["dict"], str(result))

    print("\n[只用词典但没有音频]")
    result = speak("dict_only", audio_key="", dict_ok=False)
    check("不回退 TTS", "tts" not in result, str(result))

    print("\n[词典优先但没音频]")
    result = speak("dict_first", audio_key="", dict_ok=False)
    check("回退 TTS", result == ["tts"], str(result))

    app.shutdown()

    print("\n[连续播放词典音频]")
    real = Path.home() / ".reading-companion" / "config.json"
    if real.exists():
        from rc import audio as audio_mod
        from rc.config import Config as C2
        from rc.dictmanager import DictionaryManager

        dm = DictionaryManager(C2())
        first = dm.audio("en", "hwd/bre/c/ephemeral0205.mp3")
        second = dm.audio("en", "hwd/bre/a/brelasdefashion.mp3")
        check("第一次播放", audio_mod.play_bytes(first))
        time.sleep(0.8)
        check("第二次播放（同文件内容）", audio_mod.play_bytes(first))
        time.sleep(0.8)
        check("第三次播放（不同词）", audio_mod.play_bytes(second))
    else:
        print("  (没有真实词典配置，跳过)")

    shutil.rmtree(data, ignore_errors=True)
    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
