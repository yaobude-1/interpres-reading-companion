"""验证查词卡片：单词走词典、模式正确、查不到有提示。"""

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
    data = HERE / ".dictmode"
    shutil.rmtree(data, ignore_errors=True)
    data.mkdir(parents=True)
    mock_openai.start(18778)

    cfg = Config(data)
    cfg.data["server_port"] = 18815
    cfg.data["api"].update(
        {"base_url": "http://127.0.0.1:18778/v1", "api_key": "k", "model": "mock"}
    )
    cfg.save()

    from app import Application

    app = Application(cfg, enable_hotkeys=False)
    entry = {
        "word": "ephemeral",
        "source": "朗文",
        "phonetic": "ɪˈfemərəl",
        "lang": "en",
        "senses": [
            {
                "pos": "adjective",
                "definition": "lasting a very short time",
                "definition_cn": "短暂的",
                "example": "Fashion is ephemeral.",
                "example_cn": "时尚是短暂的。",
            }
        ],
        "audio_key": "",
    }

    print("\n[词典卡片]")
    app.popup.show_dictionary(entry, (200, 200), "ephemeral")
    app.root.update()
    check("模式是 dict", app.popup._mode == "dict", app.popup._mode)
    check("窗口可见", app.popup.visible)
    body = str([w.winfo_class() for w in app.popup.body.winfo_children()])
    check("有内容", len(app.popup.body.winfo_children()) > 0, body)

    print("\n[查不到]")
    app.popup.show_dict_missing("zzzqqq", (200, 200))
    app.root.update()
    check("模式仍是 dict", app.popup._mode == "dict", app.popup._mode)
    check("提示可见", app.popup.visible)

    print("\n[单词走词典路径]")
    app._pending_selection = ("ephemeral", "Book", (300, 300))
    app._open_selection_bubble((300, 300))
    deadline = time.time() + 10
    while time.time() < deadline and app.popup._mode != "dict":
        app.root.update()
        time.sleep(0.05)
    check("选词后进入查词模式", app.popup._mode == "dict", app.popup._mode)

    print("\n[词典音频]")
    real = Path.home() / ".reading-companion" / "config.json"
    if real.exists():

        # 用真实配置查一个朗文有音频的词
        from rc import audio as audio_mod
        from rc.config import Config as C2
        from rc.dictmanager import DictionaryManager

        cfg2 = C2()
        dm = DictionaryManager(cfg2)
        entry2 = dm.lookup_full("en", "ephemeral")
        key = (entry2 or {}).get("audio_key") or ""
        check("查到了音频键", bool(key), str(key))
        audio_bytes = dm.audio("en", key) if key else None
        check("拿到了音频数据", bool(audio_bytes), str(len(audio_bytes) if audio_bytes else 0))
        check("识别为 mp3", audio_mod.sniff_suffix(audio_bytes) == ".mp3" if audio_bytes else False)
        if audio_bytes:
            check("可以播放", audio_mod.play_bytes(audio_bytes))
    else:
        print("  (没有真实词典配置，跳过)")

    app.shutdown()
    shutil.rmtree(data, ignore_errors=True)
    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
