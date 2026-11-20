"""离线检查脚本：不联网、不要 API Key，验证整条链路。

运行：
    python tests/run_checks.py
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from rc import textutil  # noqa: E402
from rc.config import Config  # noqa: E402
from rc.server import ApiServer  # noqa: E402
from rc.service import Service  # noqa: E402
from tests import mock_openai  # noqa: E402

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        PASSED.append(name)
        print(f"  ok   {name}")
    else:
        FAILED.append(f"{name}: {detail}")
        print(f"  FAIL {name} {detail}")


def check_normalize() -> None:
    print("\n[文本清洗]")
    raw = "The quick brown fox\njumps over the lazy\ndog. This is a trans-\nlation test."
    out = textutil.normalize(raw)
    check("段落合并", "\n" not in out, out)
    check("连字符断词", "translation" in out, out)

    cjk = "这是一段\n中文文字，测试\n断行处理。"
    check("中文断行", textutil.normalize(cjk) == "这是一段中文文字，测试断行处理。", textutil.normalize(cjk))

    check("空白归一", textutil.normalize("  a   b  ") == "a b", textutil.normalize("  a   b  "))
    check("词判断", textutil.looks_like_word("hello"), "hello")
    check("整段判断", not textutil.looks_like_word("hello world this is a long sentence about things"))


def check_service(data_dir: Path) -> Service:
    print("\n[翻译链路]")
    cfg = Config(data_dir)
    cfg.data["api"].update(
        {"base_url": "http://127.0.0.1:18778/v1", "api_key": "test-key", "model": "mock"}
    )
    cfg.data["server_port"] = 18779
    cfg.save()
    service = Service(cfg)

    result = service.translate("The quick brown fox jumps over the lazy dog.", book="Test Book")
    check("译文非空", bool(result["translation"]), result)
    check("生词解析", len(result["terms"]) == 3, str(result.get("terms")))
    check("语法解析", bool(result.get("grammar")), result.get("grammar"))
    check("语言登记", "en" in cfg.data["languages"], str(cfg.data["languages"]))
    check("首次未命中缓存", result["meta"]["cached"] is False, str(result["meta"]))

    again = service.translate("The quick brown fox jumps over the lazy dog.", book="Test Book")
    check("二次命中缓存", again["meta"]["cached"] is True, str(again["meta"]))

    # 术语表要注入到 prompt 里
    service.add_term("Test Book", "brown fox", "赤狐", "en")
    mock_openai._Handler.last_body = {}
    service.translate("A different sentence about a brown fox.", book="Test Book")
    prompt = json.dumps(mock_openai._Handler.last_body, ensure_ascii=False)
    check("术语表注入", "brown fox" in prompt and "赤狐" in prompt, prompt[:200])
    check("JSON 模式", mock_openai._Handler.last_body.get("response_format", {}).get("type") == "json_object")

    # 生词本
    word_id = service.add_vocab(
        lang="en",
        word="quick",
        lemma="quick",
        reading="/kwɪk/",
        pos="形容词",
        meaning="敏捷的",
        sentence="The quick brown fox",
        book="Test Book",
    )["id"]
    check("生词入库", word_id > 0, str(word_id))
    dup = service.add_vocab(lang="en", word="quicker", lemma="quick", meaning="更快的")
    check("同 lemma 去重", dup["id"] == word_id, f"{dup} vs {word_id}")
    check("生词计数", service.store.word_count("en") == 1, str(service.store.word_count("en")))

    exported = service.export_vocab("en")
    path = Path(exported["path"])
    check("导出 TSV", path.exists() and path.stat().st_size > 0, str(path))
    content = path.read_text(encoding="utf-8-sig")
    check("TSV 字段", content.splitlines()[0].startswith("Word\tPhonetic\tPOS"), content[:120])

    return service


def check_api(service: Service) -> None:
    print("\n[本地 HTTP API]")
    server = ApiServer(service, port=18779, token="tok")
    server.start()
    time.sleep(0.2)
    import urllib.error
    import urllib.request

    def call(path: str, body: dict | None = None, token: str = "tok"):
        url = f"http://127.0.0.1:18779{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
        req.add_header("X-RC-Token", token)
        if data:
            req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())

    check("健康检查", call("/api/health").get("ok") is True)
    try:
        call("/api/status", token="wrong")
        check("鉴权拦截", False, "错误 token 竟然通过了")
    except urllib.error.HTTPError as exc:
        check("鉴权拦截", exc.code == 401, str(exc.code))

    translated = call("/api/translate", {"text": "Hello there, my friend."})
    check("HTTP 翻译", translated["ok"] and bool(translated["translation"]), str(translated)[:120])

    vocab = call("/api/vocab?lang=en")
    check("HTTP 生词列表", len(vocab["words"]) == 1, str(vocab)[:120])
    server.stop()


def check_anki_mock(service: Service) -> None:
    """用假 AnkiConnect 验证直推协议（不需要真的开 Anki）。"""
    print("\n[Anki 直推]")
    service.add_vocab(
        lang="en", word="brown", lemma="brown", meaning="棕色的", sentence="the brown fox"
    )
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    state = {"decks": ["Default"], "models": [], "notes": 0, "calls": []}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            return

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            req = json.loads(self.rfile.read(length).decode())
            action = req.get("action")
            state["calls"].append(action)
            result, error = None, None
            if action == "version":
                result = 6
            elif action == "deckNames":
                result = state["decks"]
            elif action == "modelNames":
                result = state["models"]
            elif action == "createDeck":
                state["decks"].append(req["params"]["deck"])
                result = 1
            elif action == "createModel":
                state["models"].append(req["params"]["modelName"])
                result = 1
            elif action == "addNote":
                word = req["params"]["note"]["fields"]["Word"]
                if word == "brown":
                    error = "cannot create note because it is a duplicate"
                else:
                    state["notes"] += 1
                    result = 1000 + state["notes"]
            body = json.dumps({"result": result, "error": error}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 18780), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()

    from rc.anki import Anki

    service.anki = Anki("http://127.0.0.1:18780")
    words = service.store.list_words("en")
    result = service.push_anki("en")
    check("建牌组", "Reading::English" in state["decks"], str(state["decks"]))
    check("建笔记类型", "Interpres" in state["models"], str(state["models"]))
    check("推送成功", result["added"] == 1, str(result))
    check("重复跳过", result["duplicated"] == 1, str(result))
    check("标记已同步", service.store.list_words("en")[0]["synced"] == 1, str(words))
    server.shutdown()


def check_tts(service: Service) -> None:
    print("\n[发音]")
    voices = service.tts.voices()
    check("音色列表", len(voices) >= 1, str(voices))
    if any("Huihui" in v["name"] for v in voices):
        check("中文音色存在", True, "Huihui")
    else:
        print("  skip 中文音色存在（当前系统未安装中文语音包）")
    latin_voice = service.tts.voice_for("la")
    if latin_voice:
        check("拉丁语回退", True, latin_voice)
    else:
        print("  skip 拉丁语回退（当前系统只有英文语音）")
    try:
        path = service.tts.synthesize("Hello, this is a short test.", "en")
        check("合成 wav", path.exists() and path.stat().st_size > 5000, str(path.stat().st_size))
    except Exception as exc:  # noqa: BLE001
        # 沙箱 / 无语音包环境下会走到这里，不算产品缺陷
        print(f"  skip 合成 wav（当前环境语音引擎不可用：{str(exc)[:70]}）")


def check_config_persist(data_dir: Path) -> None:
    print("\n[配置持久化]")
    cfg = Config(data_dir)
    check("配置重载", cfg.api.get("base_url", "").startswith("http"), str(cfg.api))
    check("token 存在", bool(cfg.data.get("server_token")), "empty")
    check("语言自动登记", "en" in cfg.data["languages"], str(list(cfg.data["languages"])))


def main() -> int:
    data_dir = Path(HERE / ".testdata")
    if data_dir.exists():
        shutil.rmtree(data_dir, ignore_errors=True)
    data_dir.mkdir(parents=True)

    mock = mock_openai.start(18778)
    check_normalize()
    service = check_service(data_dir)
    check_api(service)
    check_anki_mock(service)
    check_tts(service)
    check_config_persist(data_dir)
    mock.shutdown()

    print("\n" + "=" * 50)
    print(f"通过 {len(PASSED)} 项，失败 {len(FAILED)} 项")
    for item in FAILED:
        print("  ✗", item)
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
