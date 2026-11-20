"""一个假的 OpenAI 兼容服务，用于离线联调。"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CANNED = {
    "source_lang": "en",
    "translation": "敏捷的棕色狐狸跳过了那只懒狗。",
    "glossary_hits": [],
    "terms": [
        {
            "word": "quick",
            "lemma": "quick",
            "reading": "/kwɪk/",
            "pos": "形容词",
            "meaning": "敏捷的；迅速的",
            "note": "与 fast 相比更强调动作轻快",
        },
        {
            "word": "brown",
            "lemma": "brown",
            "reading": "/braʊn/",
            "pos": "形容词",
            "meaning": "棕色的",
            "note": "",
        },
        {
            "word": "jumps",
            "lemma": "jump",
            "reading": "/dʒʌmp/",
            "pos": "动词",
            "meaning": "跳；跃过",
            "note": "第三人称单数形式",
        },
    ],
    "grammar": "一般现在时，主语 The quick brown fox 是第三人称单数，谓语用 jumps。",
}


class _Handler(BaseHTTPRequestHandler):
    last_body: dict = {}
    calls: int = 0

    def log_message(self, *args) -> None:  # noqa: D401
        return

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception:
            body = {}
        _Handler.last_body = body
        _Handler.calls += 1
        if "response_format" in body:
            content = json.dumps(CANNED, ensure_ascii=False)
        else:
            content = "这是测试回复：作者在这里强调的是短暂性，与前文的对比有关。"
        payload = {
            "id": "mock",
            "object": "chat.completion",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 10},
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def start(port: int = 18778) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


if __name__ == "__main__":
    import time

    print("mock listening on 18778")
    start(18778)
    while True:
        time.sleep(3600)
