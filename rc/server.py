"""本地 HTTP API（只监听 127.0.0.1）。

浮窗界面直接调用 Service，不经过这里；提供 HTTP 是为了：
1. 让别的工具（脚本、浏览器书签、其他编辑器插件）也能用；
2. 方便自动化测试。
"""

from __future__ import annotations

import hmac
import json
import logging
import mimetypes
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import PurePosixPath
from urllib.parse import parse_qs, quote, unquote, urlparse

from . import __version__
from .dict_view import build_raw_page
from .netpolicy import validate_base_url
from .service import Service

log = logging.getLogger("rc")


MAX_BODY = 1024 * 1024


class _LocalServer(ThreadingHTTPServer):
    """只允许一个进程占用端口：Windows 上 SO_REUSEADDR 会让多个进程都绑成功。"""

    daemon_threads = True
    allow_reuse_address = False

    def server_bind(self) -> None:
        if sys.platform == "win32":
            try:
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            except OSError as exc:  # noqa: BLE001 - 系统不支持时退回默认绑定行为
                log.debug("设置 SO_EXCLUSIVEADDRUSE 失败: %s", exc)
        super().server_bind()

    def handle_error(self, request, client_address) -> None:
        # 客户端提前断开是常态（比如第二个实例发完请求立刻退出），不打印堆栈
        import sys as _sys

        exc = _sys.exc_info()[1]
        if isinstance(exc, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)):
            return
        super().handle_error(request, client_address)


class ApiServer:
    def __init__(
        self,
        service: Service,
        port: int = 18777,
        token: str = "",
        on_show_settings=None,
        on_show_panel=None,
    ) -> None:
        self.service = service
        self.port = int(port)
        self.token = token or ""
        self.on_show_settings = on_show_settings
        self.on_show_panel = on_show_panel
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._httpd is not None

    def start(self) -> None:
        handler = _make_handler(
            self.service, self.token, self.on_show_settings, self.on_show_panel
        )
        self._httpd = _LocalServer(("127.0.0.1", self.port), handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True, name="api")
        self._thread.start()

    def stop(self) -> None:
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None


def _make_handler(service: Service, token: str, on_show_settings=None, on_show_panel=None):
    class Handler(BaseHTTPRequestHandler):
        server_version = f"ReadingCompanion/{__version__}"

        # ---------------------------------------------------------- infrastructure
        def log_message(self, fmt: str, *args) -> None:  # 静音
            return

        def _json(self, data: dict | list, status: int = 200) -> None:
            body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _raw(self, data: bytes, content_type: str, status: int = 200) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _body(self) -> dict:
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            if length < 0 or length > MAX_BODY:
                # 读掉有限的一段再拒绝，避免客户端还在上传时收到 RST
                remaining = min(max(length, 0), MAX_BODY * 2)
                while remaining > 0:
                    chunk = self.rfile.read(min(remaining, 65536))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                raise ValueError("request body too large")
            if not length:
                return {}
            raw = self.rfile.read(length)
            try:
                data = json.loads(raw.decode("utf-8"))
                return data if isinstance(data, dict) else {}
            except Exception:
                return {}

        def _authorized(self, query: dict | None = None) -> bool:
            if not token:
                return True
            supplied = self.headers.get("X-RC-Token") or ""
            if not supplied and query:
                supplied = str(query.get("token") or "")
            # 常量时间比较，避免逐字符比较泄露 token 前缀
            return hmac.compare_digest(supplied, token)

        def _route(self) -> tuple[str, dict]:
            parsed = urlparse(self.path)
            query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            return parsed.path.rstrip("/") or "/", query

        # ------------------------------------------------------------- dictionary
        def _dict_view(self, query: dict) -> None:
            lang = str(query.get("lang") or "")
            dict_id = str(query.get("dict_id") or "")
            word = str(query.get("word") or "")
            entry = (
                service.dicts.raw_entry_by_id(dict_id, word)
                if dict_id
                else service.dicts.raw_entry(lang, word)
            )
            if not entry:
                self._json({"ok": False, "error": "dictionary entry not found"}, 404)
                return
            port = int(self.server.server_address[1])
            token_q = quote(token)
            scope = dict_id or lang
            lookup_lang = lang or service.dicts.language_of(scope)
            resource_base = (
                f"http://127.0.0.1:{port}/api/dict-res/{quote(scope)}/{token_q}/"
            )
            lookup_base = (
                f"interpres://lookup?lang={quote(lookup_lang)}&word="
            )
            page = build_raw_page(
                entry["html"],
                source=entry.get("source") or "",
                word=word,
                resource_base=resource_base,
                lookup_base=lookup_base,
                allow_scripts=service.dicts.scripts_allowed(
                    str(entry.get("dict_id") or dict_id)
                ),
            )
            self._raw(page.encode("utf-8"), "text/html; charset=utf-8")

        def _dict_resource(self, path: str) -> None:
            rest = path[len("/api/dict-res/") :]
            parts = rest.split("/", 2)
            if len(parts) < 3:
                self._json({"ok": False, "error": "bad resource path"}, 404)
                return
            scope = unquote(parts[0])
            supplied = unquote(parts[1])
            resource = unquote(parts[2]).replace("\\", "/")
            if token and not hmac.compare_digest(supplied, token):
                self._json({"ok": False, "error": "unauthorized"}, 401)
                return
            if not resource or ".." in PurePosixPath(resource).parts:
                self._json({"ok": False, "error": "unsafe resource path"}, 404)
                return
            if service.dicts.language_of(scope):
                data = service.dicts.resource_by_id(scope, resource)
            else:
                data = service.dicts.resource(scope, resource)
            if data is None:
                self._json({"ok": False, "error": "resource not found"}, 404)
                return
            content_type = mimetypes.guess_type(resource)[0] or "application/octet-stream"
            self._raw(data, content_type)

        def _dict_audio(self, query: dict) -> None:
            lang = str(query.get("lang") or "")
            dict_id = str(query.get("dict_id") or "")
            key = str(query.get("key") or "")
            data = (
                service.dicts.audio_by_id(dict_id, key)
                if dict_id
                else service.dict_audio(lang, key)
            )
            if data is None:
                self._json({"ok": False, "error": "audio not found"}, 404)
                return
            content_type = mimetypes.guess_type(key)[0] or "audio/mpeg"
            self._raw(data, content_type)

        # ------------------------------------------------------------------ verbs
        def do_GET(self) -> None:
            path, query = self._route()
            try:
                if path == "/api/health":
                    self._json({"ok": True, "version": __version__})
                    return
                if path.startswith("/api/dict-res/"):
                    self._dict_resource(path)
                    return
                if not self._authorized(query):
                    self._json({"ok": False, "error": "unauthorized"}, 401)
                    return
                if path == "/api/dict-view":
                    self._dict_view(query)
                elif path == "/api/dict-audio":
                    self._dict_audio(query)
                elif path == "/api/status":
                    self._json(service.status())
                elif path == "/api/vocab":
                    words = service.vocab(query.get("lang"), query.get("book"), int(query.get("limit", 500)))
                    self._json({"ok": True, "words": words})
                elif path == "/api/glossary":
                    self._json({"ok": True, "terms": service.terms(query.get("book", ""))})
                elif path == "/api/tts":
                    text = query.get("text", "")
                    lang = query.get("lang", "en")
                    wav = service.synthesize(text, lang)
                    self._raw(wav.read_bytes(), "audio/wav")
                else:
                    self._json({"ok": False, "error": "not found"}, 404)
            except Exception as exc:  # noqa: BLE001
                self._json({"ok": False, "error": str(exc)}, 500)

        def do_POST(self) -> None:
            path, _query = self._route()
            try:
                if not self._authorized():
                    self._json({"ok": False, "error": "unauthorized"}, 401)
                    return
                try:
                    body = self._body()
                except ValueError:
                    self._json({"ok": False, "error": "request body too large"}, 413)
                    return
                if path == "/api/show-settings":
                    if on_show_settings:
                        on_show_settings()
                    self._json({"ok": True})
                elif path == "/api/show-panel":
                    if on_show_panel:
                        on_show_panel()
                    self._json({"ok": True})
                elif path == "/api/translate":
                    result = service.translate(
                        body.get("text", ""),
                        book=body.get("book", ""),
                        src_lang=body.get("src_lang") or None,
                        context_before=body.get("context_before", ""),
                        context_after=body.get("context_after", ""),
                        use_cache=bool(body.get("use_cache", True)),
                    )
                    self._json({"ok": True, **result})
                elif path == "/api/vocab":
                    self._json(service.add_vocab(**body))
                elif path == "/api/glossary":
                    self._json(service.add_term(**body))
                elif path == "/api/anki/push":
                    self._json(service.push_anki(body.get("lang", ""), body.get("ids")))
                elif path == "/api/export":
                    self._json(service.export_vocab(body.get("lang")))
                elif path == "/api/speak":
                    self._json(service.speak(body.get("text", ""), body.get("lang", "en")))
                elif path == "/api/config/test":
                    self._json(service.test_api())
                elif path == "/api/config":
                    allowed = {"hotkey", "settings_hotkey", "target_lang", "auto_speak", "popup_width"}
                    for key, value in body.items():
                        if key in allowed:
                            service.config.data[key] = value
                        elif key == "api" and isinstance(value, dict):
                            for k in ("base_url", "model", "temperature", "timeout"):
                                if k in value:
                                    if k == "base_url":
                                        service.config.api[k] = validate_base_url(str(value[k]))
                                    else:
                                        service.config.api[k] = value[k]
                            if value.get("api_key"):
                                service.config.set_api_key(str(value["api_key"]))
                    service.config.save()
                    self._json({"ok": True})
                else:
                    self._json({"ok": False, "error": "not found"}, 404)
            except Exception as exc:  # noqa: BLE001
                self._json({"ok": False, "error": str(exc)}, 500)

    return Handler
