"""验证「词典 → 翻译结果 → 生词本 → Anki 卡片」整条链路。"""

from __future__ import annotations

import json
import shutil
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from rc.config import Config  # noqa: E402
from rc.service import Service  # noqa: E402
from tests import mock_openai  # noqa: E402

BASE = (
    r"D:\Downloads\Compressed\Longman Dictionary of Contemporary English 6th ed. "
    r"Summer Edition (MDX)\朗文当代高级英语辞典 第6版 夏日清凉版 V3.2"
)
MDX_PATH = BASE + r"\朗文当代高级英语词典6th.mdx"
MDD_PATH = BASE + r"\朗文当代高级英语词典6th.mdd"

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


class AnkiMock(BaseHTTPRequestHandler):
    notes: list[dict] = []
    media: list[dict] = []
    existing: set[str] = set()

    def log_message(self, *args):
        return

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        req = json.loads(self.rfile.read(length).decode())
        action = req.get("action")
        result, error = None, None
        if action == "version":
            result = 6
        elif action == "deckNames":
            result = ["daily"]
        elif action == "modelNames":
            result = []
        elif action in ("createDeck", "createModel", "updateModelTemplates", "updateModelStyling"):
            result = 1
        elif action == "findNotes":
            result = [i + 1 for i in range(len(AnkiMock.existing))]
        elif action == "notesInfo":
            result = [
                {"noteId": i + 1, "fields": {"Word": {"value": word}}}
                for i, word in enumerate(sorted(AnkiMock.existing))
            ]
        elif action == "storeMediaFile":
            AnkiMock.media.append(req["params"])
            result = req["params"]["filename"]
        elif action == "addNote":
            AnkiMock.notes.append(req["params"]["note"])
            result = 1001
        body = json.dumps({"result": result, "error": error}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> int:
    data = HERE / ".dictflow"
    shutil.rmtree(data, ignore_errors=True)
    data.mkdir(parents=True)

    mock_openai.CANNED["terms"] = [
        {
            "word": "ephemeral",
            "lemma": "ephemeral",
            "reading": "",
            "pos": "",
            "meaning": "转瞬即逝的",
            "note": "",
        }
    ]

    mock = mock_openai.start(18778)
    anki = ThreadingHTTPServer(("127.0.0.1", 18780), AnkiMock)
    anki.daemon_threads = True
    threading.Thread(target=anki.serve_forever, daemon=True).start()

    cfg = Config(data)
    cfg.data["api"].update(
        {"base_url": "http://127.0.0.1:18778/v1", "api_key": "k", "model": "mock"}
    )
    cfg.data["server_port"] = 18798
    cfg.data["dictionaries"]["en"] = {"mdx": MDX_PATH, "mdd": MDD_PATH}
    cfg.save()

    from rc.anki import Anki

    service = Service(cfg)
    service.anki = Anki("http://127.0.0.1:18780")

    print("\n[词典能力]")
    print("  ", service.dicts.describe("en"))
    caps = service.dicts.capabilities("en")
    check("识别出中文释义", caps.get("definition_cn") is True, str(caps))
    check("识别出真人发音", caps.get("audio") is True, str(caps))

    print("\n[翻译时自动查词典]")
    result = service.translate("Fashion is by nature ephemeral.", book="Sapiens")
    term = result["terms"][0]
    info = term.get("dict") or {}
    check("词条带上了词典", bool(info), str(term)[:120])
    check("释义来自词典", "短暂" in (info.get("definition") or ""), info.get("definition", ""))
    check("例句来自词典", "Fashion" in (info.get("example") or ""), info.get("example", ""))
    check("例句翻译来自词典", "潮流" in (info.get("example_cn") or ""), info.get("example_cn", ""))
    check("音标补全", bool(term.get("reading")), term.get("reading", ""))

    print("\n[存入生词本]")
    word = service.add_vocab(
        lang="en",
        word=term["word"],
        lemma=term["lemma"],
        reading=term.get("reading", ""),
        pos=term.get("pos", ""),
        meaning=term.get("meaning", ""),
        sentence=result["text"],
        book="Sapiens",
        dict_source=info.get("source", ""),
        dict_meaning=info.get("definition", ""),
        dict_example=info.get("example", ""),
        dict_example_cn=info.get("example_cn", ""),
        audio_key=info.get("audio_key", ""),
    )
    stored = service.store.get_word(word["id"])
    check("生词本存了词典释义", "短暂" in (stored.get("dict_meaning") or ""), str(stored)[:120])
    check("生词本存了音频键", bool(stored.get("audio_key")), stored.get("audio_key", ""))

    print("\n[推进 Anki]")
    result = service.push_anki("en")
    check("推送成功", result.get("added") == 1, str(result))
    check("媒体音频已上传", len(AnkiMock.media) == 1, str(AnkiMock.media))
    note = AnkiMock.notes[0]["fields"] if AnkiMock.notes else {}
    check("卡片释义用词典", "短暂" in note.get("Meaning", ""), note.get("Meaning", ""))
    check("卡片有例句", "Fashion" in note.get("Example", ""), note.get("Example", ""))
    combined = " ".join(
        str(note.get(key, "")) for key in ("Meaning", "Example", "ExampleCN")
    )
    check("卡片有例句翻译", "潮流" in combined, combined[:200])
    check("卡片有发音", note.get("Audio", "").startswith("[sound:rc_en_"), note.get("Audio", ""))
    check("卡片有音标", bool(note.get("Phonetic")), note.get("Phonetic", ""))

    print("\n[没有真人音频时退回 TTS]")
    fake_wav = data / "fake.wav"
    fake_wav.write_bytes(b"RIFF" + b"\x00" * 8000)
    service.tts.synthesize = lambda text, lang: fake_wav  # type: ignore[assignment]
    service.add_vocab(lang="fr", word="temps", lemma="temps", meaning="时间", book="Test")
    AnkiMock.media.clear()
    AnkiMock.notes.clear()
    pushed = service.push_anki("fr")
    check("TTS 回退推送成功", pushed.get("added") == 1, str(pushed))
    check(
        "媒体是 wav",
        bool(AnkiMock.media) and AnkiMock.media[0]["filename"].endswith(".wav"),
        str(AnkiMock.media)[:120],
    )
    note_fr = AnkiMock.notes[0]["fields"] if AnkiMock.notes else {}
    check("卡片带 TTS 发音", note_fr.get("Audio", "").endswith(".wav]"), note_fr.get("Audio", ""))

    print("\n[跨笔记类型判重]")
    AnkiMock.existing = {"ephemeral"}
    before = len(AnkiMock.notes)
    res = service.anki.push(
        [{"id": 999, "word": "ephemeral", "lemma": "ephemeral", "lang": "en"}], "daily"
    )
    check("牌组里已存在则跳过", res.get("skipped") == 1 and res.get("added") == 0, str(res))
    check("没有新增卡片", len(AnkiMock.notes) == before, str(len(AnkiMock.notes)))

    AnkiMock.existing = {"temps"}
    res = service.anki.push(
        [{"id": 1000, "word": "temps", "lemma": "temps", "lang": "fr"}], "daily"
    )
    check("别的语言同样跳过", res.get("skipped") == 1, str(res))
    AnkiMock.existing = set()

    service.store.close()
    mock.shutdown()
    anki.shutdown()
    shutil.rmtree(data, ignore_errors=True)
    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
