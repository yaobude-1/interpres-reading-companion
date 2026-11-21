"""业务编排：翻译、生词、术语、Anki、发音。

浮窗界面和本地 HTTP 服务都调用这一层，保证行为一致。
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from pathlib import Path

from .anki import Anki
from .config import Config
from .dictmanager import DictionaryManager
from .llm import LLMError, Translator, _lang_name
from .service_anki import AnkiMixin
from .service_common import (
    CHAT_PERSONA_DEFAULT as CHAT_PERSONA_DEFAULT,
    CHAT_RULES_DEFAULT as CHAT_RULES_DEFAULT,
    CHUNK_CHARS as CHUNK_CHARS,
    _english_mode,
    _tsv,
    split_chunks as split_chunks,
)
from .service_dict import DictMixin
from .service_translate import TranslateMixin
from .service_vocab import VocabMixin
from .store import Store
from .tts import TTS

log = logging.getLogger("rc")


class Service(VocabMixin, AnkiMixin, DictMixin, TranslateMixin):
    def __init__(self, config: Config) -> None:
        self.config = config
        self.data_dir = config.data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.store = Store(self.data_dir / "reading.db")
        self.translator = Translator(config)
        self.tts = TTS(config, self.data_dir / "cache" / "tts")
        self.anki = Anki()
        self.dicts = DictionaryManager(config)
        self._context_lock = threading.Lock()
        # 每个窗口最近一次选中内容，用于给短查询补上下文
        self._recent: dict[str, dict] = {}

    # ------------------------------------------------------------------ 上下文
    def remember(self, window: str, text: str) -> None:
        with self._context_lock:
            self._recent[window] = {"text": text, "ts": time.time()}

    def recent_context(self, window: str, max_chars: int) -> tuple[str, str]:
        """返回 (上文, 下文)。上文来自这个窗口上一次较长的选中。"""
        with self._context_lock:
            item = self._recent.get(window)
        if not item:
            return "", ""
        text = item["text"]
        if len(text) < 40:
            return "", ""
        limit = int(max_chars)
        before = text[-limit:] if len(text) > limit else text
        return before, ""

    # -------------------------------------------------------------------- 对话
    # ------------------------------------------------------------ translations
    def translations(self, book=None, query: str = "", limit: int = 200) -> list[dict]:
        return self.store.translations(book=book, query=query, limit=limit)

    def export_translations(self, book=None, query: str = "", fmt: str = "md") -> dict:
        """把翻译记录导出到数据目录下的 exports/。"""
        rows = self.store.translations(book=book, query=query, limit=100000)
        out_dir = Path(self.config.data_dir) / "exports"
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        suffix = "md" if fmt == "md" else "tsv"
        path = out_dir / f"翻译记录-{stamp}.{suffix}"
        if fmt == "tsv":
            lines = ["原文\t译文\t书名\t时间"]
            for row in rows:
                payload = json.loads(row.get("payload") or "{}")
                lines.append(
                    "\t".join(
                        [
                            _tsv(row.get("text", "")),
                            _tsv(payload.get("translation", "")),
                            _tsv(row.get("book", "")),
                            row.get("updated", ""),
                        ]
                    )
                )
            path.write_text("\n".join(lines), encoding="utf-8-sig")
        else:
            parts = ["# 翻译记录", "", f"共 {len(rows)} 条 · 导出于 {time.strftime('%Y-%m-%d %H:%M')}"]
            current_book = None
            for row in rows:
                book_name = row.get("book") or "（未标书名）"
                if book_name != current_book:
                    current_book = book_name
                    parts.append(f"\n## {book_name}\n")
                payload = json.loads(row.get("payload") or "{}")
                parts.append(f"### {row.get('updated', '')}")
                parts.append(f"**原文**：{row.get('text', '')}")
                parts.append(f"**译文**：{payload.get('translation', '')}")
                terms = payload.get("terms") or []
                if terms:
                    listed = "；".join(
                        f"{t.get('word', '')} {t.get('meaning', '')}" for t in terms
                    )
                    parts.append(f"**生词**：{listed}")
                parts.append("")
            path.write_text("\n".join(parts), encoding="utf-8")
        return {"path": str(path), "count": len(rows), "dir": str(out_dir)}

    def start_conversation(self, book: str, lang: str, passage: str, translation: str) -> dict:
        conv_id = self.store.start_conversation(book, lang, passage, translation)
        return {"id": conv_id, "messages": self.chat_messages(conv_id), "book": book}

    def chat_messages(self, conv_id: int) -> list[dict]:
        return [
            {"role": m["role"], "content": m["content"], "created": m["created"]}
            for m in self.store.messages(conv_id)
        ]

    def ask(self, conv_id: int, question: str, on_delta=None) -> dict:
        question = (question or "").strip()
        if not question:
            raise ValueError("问题不能为空")
        conv = self.store.conversation(conv_id)
        if not conv:
            raise ValueError("这段对话已经不存在了")

        messages = [{"role": "system", "content": self._chat_system(conv)}]
        for item in self.store.messages(conv_id)[-14:]:
            messages.append({"role": item["role"], "content": item["content"]})
        messages.append({"role": "user", "content": question})

        if on_delta is None:
            reply = self.translator.chat(messages)
        else:
            pieces: list[str] = []
            for piece in self.translator.chat_stream(messages):
                pieces.append(piece)
                try:
                    on_delta("".join(pieces))
                except Exception:
                    pass
            reply = "".join(pieces).strip()
            if not reply:
                raise ValueError("模型返回了空内容")
        self.store.add_message(conv_id, "user", question)
        self.store.add_message(conv_id, "assistant", reply)
        return {"reply": reply, "messages": self.chat_messages(conv_id)}

    def _chat_system_en(self, conv: dict) -> str:
        from .prompts_en import CHAT_PERSONA_EN, CHAT_RULES_EN

        book = conv.get("book") or "this book"
        persona = str(self.config.get("prompt_chat_persona") or "").strip()
        try:
            persona = (persona or CHAT_PERSONA_EN).format(book=book)
        except Exception:
            persona = (persona or CHAT_PERSONA_EN).replace("{book}", book)
        parts = [persona]
        passage = (conv.get("passage") or "").strip()
        translation = (conv.get("translation") or "").strip()
        limit = int(self.config.get("chat_passage_chars", 0))
        if limit <= 0:
            limit = 100000
        if passage:
            if len(passage) > limit:
                parts.append(
                    f"The passage the user is reading (only the first {limit} characters are shown; "
                    f"{len(passage) - limit} more are omitted — say so if the question is about them):\n{passage[:limit]}"
                )
            else:
                parts.append(f"The passage the user is reading ({len(passage)} characters, full text):\n{passage}")
        if translation:
            parts.append(f"Translation of the passage:\n{translation[:5000]}")
        recent = [t for t in self.store.recent_history(book, 3) if t and t != passage]
        if recent:
            parts.append(
                "Recently read passages (reference only):\n" + "\n---\n".join(t[:400] for t in recent)
            )
        rules = str(self.config.get("prompt_chat_rules") or "").strip() or CHAT_RULES_EN
        parts.append(rules)
        return "\n\n".join(parts)

    def _chat_system(self, conv: dict) -> str:
        if _english_mode():
            custom = str(self.config.get("prompt_chat_persona") or "").strip()
            if not custom:
                return self._chat_system_en(conv)
        book = conv.get("book") or "这本书"
        persona = str(self.config.get("prompt_chat_persona") or "").strip() or CHAT_PERSONA_DEFAULT
        try:
            persona = persona.format(book=book)
        except Exception:
            pass
        parts = [persona]
        passage = (conv.get("passage") or "").strip()
        translation = (conv.get("translation") or "").strip()
        limit = int(self.config.get("chat_passage_chars", 0))
        if limit <= 0:
            limit = 100000  # 不限制时也留一个硬保护，避免一次发太多直接超上下文
        if passage:
            if len(passage) > limit:
                parts.append(
                    f"用户正在读的段落（原文较长，这里只给出前 {limit} 字，"
                    f"后面还有 {len(passage) - limit} 字没给你；"
                    f"如果用户问到的部分不在这里，就说明你看到的不全）：\n{passage[:limit]}"
                )
            else:
                parts.append(f"用户正在读的段落（共 {len(passage)} 字，以下是全文）：\n{passage}")
        if translation:
            parts.append(f"这段的译文：\n{translation[:5000]}")

        recent = [t for t in self.store.recent_history(book, 3) if t and t != passage]
        if recent:
            parts.append("最近读过的片段（仅供参考）：\n" + "\n---\n".join(t[:400] for t in recent))

        rules = str(self.config.get("prompt_chat_rules") or "").strip() or CHAT_RULES_DEFAULT
        parts.append(rules)
        return "\n\n".join(parts)

    def conversations(self, book: str | None = None) -> list[dict]:
        return self.store.conversations(book)

    def current_book(self) -> str:
        """最近在读的书（用来开一段没有原文的对话）。"""
        books = self.store.books()
        return books[0]["name"] if books else ""

    def latest_conversation(self, book: str) -> dict | None:
        items = self.store.conversations(book, limit=1) if book else []
        return items[0] if items else None

    def update_conversation_context(self, conv_id: int, passage: str, translation: str) -> None:
        self.store.update_conversation_context(conv_id, passage, translation)

    def books_with_conversations(self) -> list[dict]:
        from .capture import book_from_title

        rows = self.store.books_with_conversations()
        return [
            row for row in rows
            if not row.get("book") or row["book"] == "(未命名)" or book_from_title(row["book"])
        ]

    def delete_conversation(self, conv_id: int) -> None:
        self.store.delete_conversation(conv_id)

    def delete_book_conversations(self, book: str) -> int:
        return self.store.delete_book_conversations(book)

    def rename_book(self, old: str, new: str) -> None:
        self.store.rename_book(old, new)

    def export_conversations(self, book: str) -> dict:
        lines = [f"# 与《{book}》的对话", ""]
        items = self.store.conversations(book)
        for conv in items:
            lines.append(f"## {conv['created'][:16]}")
            if conv.get("passage"):
                lines.append(f"> {conv['passage'][:300]}")
                lines.append("")
            for message in self.store.messages(conv["id"]):
                speaker = "我" if message["role"] == "user" else "AI"
                lines.append(f"**{speaker}**：{message['content']}")
                lines.append("")
        out_dir = self.data_dir / "exports"
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        safe = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", book or "book")[:40]
        path = out_dir / f"chat_{safe}_{stamp}.md"
        path.write_text("\n".join(lines), encoding="utf-8")
        return {"ok": True, "path": str(path), "count": len(items)}


    def speak(self, text: str, lang: str) -> dict:
        engine = self.tts.engine_for(lang)
        if engine == "system" and not self.tts.voice_for(lang):
            name = self.lang_label(lang)
            raise RuntimeError(
                f"没有可用的{name}音色：请到 设置 → 语言 里指定，或安装系统语音"
            )
        path = self.tts.speak(text, lang)
        return {"ok": True, "path": str(path), "voice": self.tts.voice_for(lang)}

    def synthesize(self, text: str, lang: str) -> Path:
        return self.tts.synthesize(text, lang)

    # -------------------------------------------------------------------- 状态
    def status(self) -> dict:
        return {
            "ok": True,
            "version": __import__("rc").__version__,
            "api_ready": bool(self.config.api_key),
            "model": self.config.api.get("model", ""),
            "data_dir": str(self.data_dir),
            "vocab_total": self.store.word_count(),
            "anki": self.anki.status(),
            "tts_voices": self.tts.voices(),
        }

    def test_api(self) -> dict:
        try:
            reply = self.translator.test()
            return {"ok": True, "reply": reply, "model": self.config.api.get("model", "")}
        except LLMError as exc:
            return {"ok": False, "error": str(exc)}

    def lang_label(self, code: str) -> str:
        entry = self.config.language(code)
        return entry.get("zh_label") or entry.get("label") or code

    def target_label(self) -> str:
        return _lang_name(self.config.data.get("target_lang"))
