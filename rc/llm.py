"""LLM 调用层：一次请求同时拿到译文、生词和语法点。

只依赖标准库（urllib），兼容任何 OpenAI 风格的 /chat/completions 接口。
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from typing import Any

from .netpolicy import validate_base_url

SYSTEM_PROMPT = """你是一位精通多国语言的专业译者，同时是一位经验丰富的语言教师。用户正在精读一本外文书，会给你一段从阅读器里复制出来的原文（可能是一个词、一个短语、或一整段），以及可选的上下文、术语表和书名。

你的任务：
1. 把原文翻译成目标语言，忠实、通顺，保留段落结构；
2. 从原文中挑出对语言学习者最有价值的词语，给出词典信息；
3. 如果原文里有值得说明的语法结构或难句，用一两句话点明。

只能输出一个 JSON 对象，不要输出任何其他文字，不要用 Markdown 代码块。JSON 结构：

{
  "source_lang": "原文语言的 ISO 639-1 代码，拉丁语用 la，古希腊语用 grc",
  "translation": "译文",
  "glossary_hits": [{"term": "原文术语", "rendering": "术语表要求的译法"}],
  "terms": [
    {
      "word": "原文中出现的形态",
      "lemma": "词典原形",
      "reading": "IPA 音标；拿不准就留空字符串",
      "pos": "词性（中文，如 名词/动词/形容词/副词/介词）",
      "meaning": "结合上下文的中文释义",
      "note": "可选的用法、搭配或易混点，一句话"
    }
  ],
  "grammar": "值得说明的语法结构或难句解析；没有就填 null"
}

规则：
- translation 只给译文。原文是单词或短语时，给简洁的词典式释义，最多 3 个义项，用「；」分隔，不要写“这个词的意思是”这类口头解释。
- terms 给 3~8 个（原文很长时最多 10 个）。优先挑生僻词、一词多义、固定搭配、容易误解的词；不要挑 the/a/is/and/to 这类功能词。原文本身是单个词时，terms 里仍然给出这个词。
- lemma 必须是词典原形：英语动词给原形、名词给单数；法语动词给不定式；德语动词给不定式；拉丁语给完整词典形式，动词如 `amo, amare, amavi, amatum`，名词如 `puella, puellae, f`。
- meaning 要结合上下文，不要只抄词典第一个义项；如果该词在这里是引申义，要点明。
- reading 用 IPA，拿不准就留空字符串，不要瞎编。
- grammar 只在确实有值得讲的点时给出，比如长难句、特殊句式、虚拟式、绝对夺格；普通句子填 null。
- glossary_hits 只在命中用户提供的术语表时填写，且 translation 必须采用术语表指定的译法。
- 上下文只用于消歧，不要把上下文的内容翻译进译文。
- 如果原文是拉丁语，在 note 里说明变格/变位要点（如“第三变位，被动语态”）。"""

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
                        except Exception:
                            pass
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
                except Exception:
                    pass
            return self._parse(raw)
        if on_partial is not None:
            try:
                on_partial(_partial_translation(buffer))
            except Exception:
                pass
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
            raise LLMError("还没有填写 API Key")
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
            raise LLMError("没有配置 API Key，请按 Ctrl+Alt+S 打开设置填写")

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
            raise LLMError("没有配置 API Key，请按 Ctrl+Alt+S 打开设置填写")
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
            except Exception:
                pass

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
            except Exception:
                pass
            raise LLMError(_http_hint(exc.code, detail)) from exc
        except urllib.error.URLError as exc:
            raise LLMError(f"连不上模型服务：{exc.reason}") from exc
        except TimeoutError as exc:
            raise LLMError("模型响应超时，请检查网络或换用更短的选中范围") from exc

    # -------------------------------------------------------------------- parse
    def _parse(self, raw: str) -> dict:
        text = raw.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = _extract_object(text)
            if data is None:
                raise LLMError(f"模型输出无法解析为 JSON：{text[:200]}")

        if not isinstance(data, dict):
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
    """从还没闭合的 JSON 里尽量取出 translation 字段。"""
    match = re.search(r'"translation"\s*:\s*"', buffer)
    if not match:
        return ""
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
