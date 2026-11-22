"""LLM 调用层：一次请求同时拿到译文、生词和语法点。

只依赖标准库（urllib），兼容任何 OpenAI 风格的 /chat/completions 接口。
"""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.request
from typing import Any

from .netpolicy import validate_base_url

log = logging.getLogger("rc")

SYSTEM_PROMPT = """你是一位精通多国语言的专业译者。用户正在精读一本外文书，会给你一段从阅读器里复制出来的原文（可能是一个词、一个短语、或一整段），以及可选的上下文和书名。

把原文翻译成目标语言，忠实、通顺，保留段落结构，直接给出译文。原文是单词或短语时，给出词典式释义，不同义项用「；」分隔。上下文只用于消歧，不要把上下文翻译进译文。"""

USER_TEMPLATE = """目标语言：{target}{src_line}
书名：{book}

{context_before}【原文】
{text}
{context_after}{glossary}"""


def _english_mode() -> bool:
    try:
        from . import i18n

        return i18n.LANGUAGE == "en"
    except Exception:
        return False


class LLMError(RuntimeError):
    """带用户可读信息的模型调用错误。"""


class Translator:
    def __init__(self, config) -> None:
        self.config = config

    # ------------------------------------------------------------------ public
    def _system_prompt(self) -> str:
        custom = str(self.config.get("prompt_translate_system") or "").strip()
        if custom:
            return custom
        if _english_mode():
            from .prompts_en import SYSTEM_PROMPT_EN

            return SYSTEM_PROMPT_EN
        return SYSTEM_PROMPT

    def _translate_messages(
        self,
        text: str,
        *,
        target: str = "zh-CN",
        book: str = "",
        src_lang: str | None = None,
        context_before: str = "",
        context_after: str = "",
        glossary: list[tuple[str, str]] | None = None,
    ) -> list[dict]:
        if _english_mode():
            from .prompts_en import USER_TEMPLATE_EN

            prompt = USER_TEMPLATE_EN.format(
                target="English" if target in ("en", "en-US", "en-GB") else _lang_name(target),
                src_line=(
                    f"\nSource language (locked): {_lang_name(src_lang)}" if src_lang else ""
                ),
                book=book or "(unknown)",
                text=_wrap(text.strip()),
                context_before=(
                    f"[Previous context — for disambiguation only]\n{context_before.strip()}\n\n"
                    if context_before.strip() else ""
                ),
                context_after=(
                    f"\n[Following context — for disambiguation only]\n{context_after.strip()}\n"
                    if context_after.strip() else ""
                ),
                glossary=_glossary_block(glossary),
            )
        else:
            prompt = USER_TEMPLATE.format(
                target=_lang_name(target),
                src_line=(f"\n源语言（已锁定）：{_lang_name(src_lang)}" if src_lang else ""),
                book=book or "（未知）",
                text=_wrap(text.strip()),
                context_before=(
                    f"【上文（仅供消歧）】\n{context_before.strip()}\n\n" if context_before.strip() else ""
                ),
                context_after=(
                    f"\n【下文（仅供消歧）】\n{context_after.strip()}\n" if context_after.strip() else ""
                ),
                glossary=_glossary_block(glossary),
            )
        return [
            {"role": "system", "content": self._system_prompt()},
            {"role": "user", "content": prompt},
        ]

    def translate(self, text: str, **kwargs) -> dict:
        messages = self._translate_messages(text, **kwargs)
        raw = self._chat(
            messages, temperature=float(self.config.api.get("temperature", 0.3))
        )
        return self._parse(raw)

    def translate_stream(self, text: str, on_partial=None, **kwargs) -> dict:
        """流式翻译：边生成边回调部分译文，最后返回完整结果。"""
        messages = self._translate_messages(text, **kwargs)
        buffer = ""
        shown = ""
        try:
            stream = self._chat_stream(
                messages, temperature=float(self.config.api.get("temperature", 0.3))
            )
            for chunk in stream:
                buffer += chunk
                if on_partial is not None:
                    partial = _partial_translation(buffer)
                    if partial != shown:
                        shown = partial
                        try:
                            on_partial(partial)
                        except Exception as exc:  # noqa: BLE001 - 回调来自界面层，异常不能中断流式接收
                            log.debug("on_partial 回调失败: %s", exc)
        except Exception:
            buffer = ""
        if not buffer.strip():
            # 服务器不支持流式：退回普通请求，保证有结果
            raw = self._chat(
                messages, temperature=float(self.config.api.get("temperature", 0.3))
            )
            if on_partial is not None:
                try:
                    on_partial(self._parse(raw).get("translation") or "")
                except Exception as exc:  # noqa: BLE001 - 回调来自界面层，异常不能影响翻译结果
                    log.debug("on_partial 回调失败: %s", exc)
            return self._parse(raw)
        if on_partial is not None:
            try:
                on_partial(_partial_translation(buffer))
            except Exception as exc:  # noqa: BLE001 - 回调来自界面层，异常不能影响翻译结果
                log.debug("on_partial 回调失败: %s", exc)
        return self._parse(buffer)

    def chat(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.7,
        max_tokens: int = 1400,
    ) -> str:
        """普通对话（不带 JSON 约束）。"""
        return self._chat(
            messages, temperature=temperature, max_tokens=max_tokens, json_mode=False
        )

    def chat_stream(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.7,
        max_tokens: int = 1400,
    ):
        """流式对话：逐段产出文本；服务器不支持流式时退回整段。"""
        got = False
        try:
            for piece in self._chat_stream(
                messages, temperature=temperature, max_tokens=max_tokens, json_mode=False
            ):
                got = True
                yield piece
        except Exception:
            got = False
        if not got:
            yield self._chat(
                messages, temperature=temperature, max_tokens=max_tokens, json_mode=False
            )

    def test(self) -> str:
        if not self.config.api_key:
            raise LLMError(self.config.api_key_error or "还没有填写 API Key")
        reply = self._chat(
            [
                {"role": "system", "content": "你是一个连接测试助手。"},
                {"role": "user", "content": "请只回复两个字：可用"},
            ],
            temperature=0.0,
            max_tokens=16,
            json_mode=False,
        )
        return reply.strip()[:40]

    # ------------------------------------------------------------------ request
    def _chat(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.3,
        max_tokens: int | None = None,
        json_mode: bool = True,
    ) -> str:
        api = self.config.api
        key = self.config.api_key
        if not key:
            raise LLMError("没有配置 API Key，请先打开设置填写")

        try:
            base = validate_base_url(api.get("base_url") or "https://api.deepseek.com/v1")
        except ValueError as exc:
            raise LLMError(str(exc)) from exc
        url = base + "/chat/completions"
        payload: dict[str, Any] = {
            "model": api.get("model") or "deepseek-chat",
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens or int(api.get("max_tokens", 1600)),
            "stream": False,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        started = time.time()
        try:
            body = self._post(url, payload)
        except LLMError as exc:
            # 某些兼容服务不认识 response_format，去掉再试一次
            if json_mode and "response_format" in str(exc):
                payload.pop("response_format", None)
                body = self._post(url, payload)
            else:
                raise
        finally:
            _ = time.time() - started

        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            raise LLMError(f"接口返回的不是 JSON：{body[:200]}") from exc

        choices = data.get("choices") or []
        if not choices:
            raise LLMError(f"接口没有返回内容：{json.dumps(data, ensure_ascii=False)[:300]}")
        message = choices[0].get("message") or {}
        content = message.get("content") or ""
        if not content:
            raise LLMError("模型返回了空内容，可能是触发了长度限制，请缩短选中范围")
        return content

    def _chat_stream(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.3,
        max_tokens: int | None = None,
        json_mode: bool = True,
    ):
        """流式请求：逐段产出模型输出的文本增量。"""
        api = self.config.api
        if not self.config.api_key:
            raise LLMError(
                self.config.api_key_error or "没有配置 API Key，请先打开设置填写"
            )
        try:
            base = validate_base_url(api.get("base_url") or "https://api.deepseek.com/v1")
        except ValueError as exc:
            raise LLMError(str(exc)) from exc
        url = base + "/chat/completions"
        payload: dict[str, Any] = {
            "model": api.get("model") or "deepseek-chat",
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens or int(api.get("max_tokens", 1600)),
            "stream": True,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.api_key}",
                "Accept": "text/event-stream",
                "User-Agent": "ReadingCompanion/0.1",
            },
        )
        timeout = float(api.get("timeout", 90))
        try:
            resp = urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            if json_mode and "response_format" in body:
                yield from self._chat_stream(
                    messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    json_mode=False,
                )
                return
            raise LLMError(f"接口返回错误：{body[:200]}") from exc
        except Exception as exc:  # noqa: BLE001
            raise LLMError(f"请求失败：{exc}") from exc
        try:
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line or not line.startswith("data:"):
                    continue
                body = line[5:].strip()
                if body == "[DONE]":
                    break
                try:
                    event = json.loads(body)
                except json.JSONDecodeError:
                    continue
                choices = event.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                piece = delta.get("content") or ""
                if piece:
                    yield piece
        finally:
            try:
                resp.close()
            except OSError as exc:  # noqa: BLE001 - 关闭失败无副作用
                log.debug("关闭响应失败: %s", exc)

    def _post(self, url: str, payload: dict) -> str:
        api = self.config.api
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.api_key}",
                "Accept": "application/json",
                "User-Agent": "ReadingCompanion/0.1",
            },
        )
        timeout = float(api.get("timeout", 90))
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", "replace")[:400]
            except (OSError, ValueError) as exc2:  # noqa: BLE001 - 读不到详情时用空字符串
                log.debug("读取错误详情失败: %s", exc2)
            raise LLMError(_http_hint(exc.code, detail)) from exc
        except urllib.error.URLError as exc:
            raise LLMError(f"连不上模型服务：{exc.reason}") from exc
        except TimeoutError as exc:
            raise LLMError("模型响应超时，请检查网络或换用更短的选中范围") from exc

    # -------------------------------------------------------------------- parse
    def _parse(self, raw: str) -> dict:
        text = raw.strip()
        text = re.sub(r"^```(?:json|text)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = _extract_object(text)
            if data is None:
                # 默认提示词直接输出纯译文；也兼容旧的自定义 JSON 提示词
                plain = text.strip().strip('"').strip()
                if not plain:
                    raise LLMError("模型没有给出译文，请重试或换一段文字") from None
                return {
                    "source_lang": "",
                    "translation": plain,
                    "terms": [],
                    "grammar": None,
                    "glossary_hits": [],
                }

        if not isinstance(data, dict):
            plain = text.strip().strip('"').strip()
            if plain:
                return {
                    "source_lang": "",
                    "translation": plain,
                    "terms": [],
                    "grammar": None,
                    "glossary_hits": [],
                }
            raise LLMError("模型输出格式不对，请重试")
        translation = str(data.get("translation") or "").strip()
        if not translation:
            raise LLMError("模型没有给出译文，请重试或换一段文字")

        terms: list[dict] = []
        for item in data.get("terms") or []:
            if not isinstance(item, dict):
                continue
            word = str(item.get("word") or "").strip()
            if not word:
                continue
            terms.append(
                {
                    "word": word,
                    "lemma": str(item.get("lemma") or word).strip(),
                    "reading": str(item.get("reading") or "").strip(),
                    "pos": str(item.get("pos") or "").strip(),
                    "meaning": str(item.get("meaning") or "").strip(),
                    "note": str(item.get("note") or "").strip(),
                }
            )

        hits = []
        for item in data.get("glossary_hits") or []:
            if isinstance(item, dict) and item.get("term"):
                hits.append(
                    {
                        "term": str(item["term"]).strip(),
                        "rendering": str(item.get("rendering") or "").strip(),
                    }
                )

        return {
            "source_lang": str(data.get("source_lang") or "").strip().lower(),
            "translation": translation,
            "terms": terms[:10],
            "grammar": (str(data.get("grammar")).strip() if data.get("grammar") else None),
            "glossary_hits": hits,
        }


# --------------------------------------------------------------------- helpers
def _extract_object(text: str) -> dict | None:
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _partial_translation(buffer: str) -> str:
    """从流式输出里尽量取出译文：默认纯文本，也兼容旧 JSON 提示词。"""
    if not buffer.strip():
        return ""
    match = re.search(r'"translation"\s*:\s*"', buffer)
    if not match:
        if buffer.lstrip().startswith("{") or '"translation"' in buffer:
            return ""
        partial = buffer.strip()
        partial = re.sub(r"^```(?:json|text)?\s*", "", partial)
        return re.sub(r"\s*```$", "", partial).strip()
    index = match.end()
    chars: list[str] = []
    escaped = False
    while index < len(buffer):
        char = buffer[index]
        if escaped:
            chars.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == '"':
            break
        else:
            chars.append(char)
        index += 1
    raw = "".join(chars)
    try:
        return json.loads('"' + raw + '"')
    except Exception:
        return raw.replace("\\n", "\n").replace('\\"', '"')


def _wrap(text: str) -> str:
    return text


def _glossary_block(glossary: list[tuple[str, str]] | None) -> str:
    if not glossary:
        return ""
    lines = [f"- {src} → {dst}" for src, dst in glossary if src and dst]
    if not lines:
        return ""
    return "\n【术语表（必须采用以下译法）】\n" + "\n".join(lines) + "\n"


LANG_NAMES = {
    "zh-CN": "简体中文",
    "zh-TW": "繁体中文",
    "en": "English",
    "fr": "Français",
    "la": "拉丁语",
    "de": "Deutsch",
    "es": "Español",
    "it": "Italiano",
    "ja": "日本語",
    "ko": "한국어",
    "ru": "Русский",
    "grc": "古希腊语",
}


def _lang_name(code: str | None) -> str:
    if not code:
        return "简体中文"
    return LANG_NAMES.get(code, code)


def _http_hint(status: int, detail: str) -> str:
    if status == 401:
        return "API Key 无效或已失效，请在设置里重新填写（Ctrl+Alt+S）"
    if status == 402:
        return "账户余额不足，请到 platform.deepseek.com 充值"
    if status == 429:
        return "请求太频繁被限流了，稍等几秒再试"
    if status >= 500:
        return f"模型服务暂时不可用（HTTP {status}），稍后重试"
    return f"模型接口报错（HTTP {status}）：{detail[:200]}"
