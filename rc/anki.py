"""Anki 集成：AnkiConnect 直推 + CSV 导出兜底。

AnkiConnect 是 Anki 的插件（代码 2055492159），装好后在 Anki 运行时监听
127.0.0.1:8765。直推失败时自动退化为导出 TSV，用户可手动导入。
"""

from __future__ import annotations

import csv
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

MODEL_NAME = "Interpres"

# 自定义卡片时可用的内容来源
CUSTOM_SOURCES = [
    "Word",
    "Phonetic",
    "POS",
    "Meaning",
    "Example",
    "ExampleCN",
    "Audio",
    "Book",
    "Language",
]
DEFAULT_FIELD_MAP = {name: name for name in CUSTOM_SOURCES}

CSS = """
.card {
  font-family: -apple-system, "Segoe UI", "Microsoft YaHei UI", sans-serif;
  font-size: 20px;
  color: #1f2933;
  background: #fbfbfb;
  padding: 18px;
}
.rc-word { font-size: 32px; font-weight: 600; }
.rc-read { color: #6b7280; font-size: 17px; margin-top: 2px; }
.rc-pos { color: #8a6d3b; font-size: 15px; margin-bottom: 6px; }
.rc-meaning { font-size: 17px; line-height: 1.55; }
.rc-posline { margin: 14px 0 4px; font-weight: 600; color: #8a6d3b; font-size: 17px; }
.rc-sense { margin: 2px 0 4px; }
.rc-num { font-weight: 700; color: #b45309; margin-right: 2px; }
.rc-cue { color: #b91c1c; font-style: italic; }
.rc-it { font-style: italic; }
.rc-cn { color: #374151; }
.rc-ex { margin: 2px 0 8px 18px; }
.rc-ex-l { color: #1f2933; font-size: 16px; }
.rc-ex-r { color: #6b7280; font-size: 14px; margin-top: 1px; }
.rc-example { margin-top: 14px; padding: 10px 12px; border-left: 3px solid #c9d1d9;
  color: #374151; font-size: 17px; line-height: 1.5; }
.rc-example-cn { color: #6b7280; font-size: 15px; margin-top: 4px; }
.rc-book { margin-top: 12px; color: #9aa5b1; font-size: 13px; }
"""

DEFAULT_FRONT = """<div class="rc-word">{{Word}}</div>
{{#Phonetic}}<div class="rc-read">/{{Phonetic}}/</div>{{/Phonetic}}
{{#Audio}}<div style="margin-top:8px">{{Audio}}</div>{{/Audio}}"""

DEFAULT_BACK = """{{FrontSide}}
<hr id=answer>
{{#POS}}<div class="rc-pos">{{POS}}</div>{{/POS}}
<div class="rc-meaning">{{Meaning}}</div>
{{#Example}}<div class="rc-example">{{Example}}{{#ExampleCN}}<div class="rc-example-cn">{{ExampleCN}}</div>{{/ExampleCN}}</div>{{/Example}}</div>
<div class="rc-book">{{Book}} · {{Language}}</div>"""

FRONT = DEFAULT_FRONT
BACK = DEFAULT_BACK

FIELDS = ["Word", "Phonetic", "POS", "Meaning", "Example", "ExampleCN", "Audio", "Book", "Language"]

CSV_HEADER = [
    "Word",
    "Phonetic",
    "POS",
    "Meaning",
    "Example",
    "ExampleCN",
    "Audio",
    "Book",
    "Language",
    "Tags",
]


class AnkiError(RuntimeError):
    pass


class Anki:
    def __init__(self, url: str = "http://127.0.0.1:8765", timeout: float = 5.0) -> None:
        self.url = url
        self.timeout = timeout

    # ---------------------------------------------------------------- transport
    def _invoke(self, action: str, **params):
        payload = {"action": action, "version": 6, "params": params}
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            self.url, data=data, method="POST", headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = json.loads(resp.read().decode("utf-8", "replace"))
        except urllib.error.URLError as exc:
            raise AnkiError("连不上 Anki，请先打开 Anki（并确认装了 AnkiConnect）") from exc
        except Exception as exc:  # noqa: BLE001
            raise AnkiError(f"AnkiConnect 调用失败：{exc}") from exc
        if raw.get("error"):
            raise AnkiError(str(raw["error"]))
        return raw.get("result")

    def ping(self) -> bool:
        try:
            self._invoke("version")
            return True
        except AnkiError:
            return False

    def deck_names(self) -> list[str]:
        """当前 Anki 里的牌组名；连不上就返回空列表。"""
        try:
            return sorted(self._invoke("deckNames") or [])
        except AnkiError:
            return []

    def model_names(self) -> list[str]:
        try:
            return sorted(self._invoke("modelNames") or [])
        except AnkiError:
            return []

    # ------------------------------------------------------------------ models
    def ensure_model(self) -> None:
        models = self._invoke("modelNames") or []
        if MODEL_NAME not in models:
            self._invoke(
                "createModel",
                modelName=MODEL_NAME,
                inOrderFields=FIELDS,
                css=CSS,
                isCloze=False,
                cardTemplates=[{"Name": "Card 1", "Front": FRONT, "Back": BACK}],
            )
            return
        # 模型已存在：把模板和样式同步成最新的（覆盖旧版本或占位模板）
        try:
            self._invoke(
                "updateModelTemplates",
                model={
                    "name": MODEL_NAME,
                    "templates": {"Card 1": {"Front": FRONT, "Back": BACK}},
                },
            )
            self._invoke("updateModelStyling", model={"name": MODEL_NAME, "css": CSS})
        except AnkiError:
            pass

    def existing_first_fields(self, deck: str, refresh: bool = False) -> set[str]:
        """目标牌组里现有笔记的首字段（小写），用于跨笔记类型判重。

        每次都重新读，避免用户中途在 Anki 里手动加/删卡片后判断失准。
        """
        ids = self._invoke("findNotes", query=f'deck:"{deck}"') or []
        words: set[str] = set()
        for start in range(0, len(ids), 200):
            chunk = ids[start : start + 200]
            infos = self._invoke("notesInfo", notes=chunk) or []
            for info in infos:
                fields = info.get("fields") or {}
                if not fields:
                    continue
                first = next(iter(fields.values())).get("value", "")
                text = _strip_html(first).strip().lower()
                if text:
                    words.add(text)
        return words

    # -------------------------------------------------------------------- push
    def push_to_model(
        self,
        notes: list[dict],
        deck: str,
        model: str,
        first_field: str,
        skip_existing: bool = True,
    ) -> dict:
        """把已经组装好的字段推到一个指定的笔记类型（如 Dict2Anki）。"""
        self._invoke("createDeck", deck=deck)
        order = self._invoke("modelFieldNames", modelName=model) or []
        if not order:
            raise AnkiError(f"Anki 里没有笔记类型 {model}")
        existing = self.existing_first_fields(deck) if skip_existing else set()

        added = duplicated = skipped = 0
        failed: list[str] = []
        ok_ids: list[int] = []
        for note in notes:
            value = (note.get(first_field) or "").strip()
            if skip_existing and value and value.lower() in existing:
                skipped += 1
                ok_ids.append(int(note["id"]))
                continue
            fields = {name: (note.get(name) or "") for name in order}
            try:
                note_id = self._invoke(
                    "addNote",
                    note={
                        "deckName": deck,
                        "modelName": model,
                        "fields": fields,
                        "options": {"allowDuplicate": False},
                        "tags": ["Interpres"],
                    },
                )
            except AnkiError as exc:
                if "duplicate" in str(exc).lower():
                    duplicated += 1
                    ok_ids.append(int(note["id"]))
                else:
                    failed.append(value or "?")
                continue
            if note_id:
                added += 1
                ok_ids.append(int(note["id"]))
            else:
                failed.append(value or "?")
        return {
            "added": added,
            "duplicated": duplicated,
            "skipped": skipped,
            "failed": failed,
            "ok_ids": ok_ids,
        }

    def model_fields(self, model: str) -> list[str]:
        try:
            return list(self._invoke("modelFieldNames", modelName=model) or [])
        except AnkiError:
            return []

    def model_template_names(self, model: str) -> list[str]:
        try:
            data = self._invoke("modelTemplates", modelName=model) or {}
            return list(data.keys())
        except AnkiError:
            return []

    def existing_field_values(self, deck: str, field: str) -> set[str]:
        ids = self._invoke("findNotes", query=f'deck:"{deck}"') or []
        values: set[str] = set()
        for start in range(0, len(ids), 200):
            chunk = ids[start : start + 200]
            infos = self._invoke("notesInfo", notes=chunk) or []
            for info in infos:
                raw = (info.get("fields") or {}).get(field) or {}
                text = _strip_html(str(raw.get("value", ""))).strip().lower()
                if text:
                    values.add(text)
        return values

    def update_custom_templates(self, model: str, front: str = "", back: str = "", css: str = "") -> None:
        names = self.model_template_names(model)
        if not names:
            raise AnkiError(f"Anki 里没有笔记类型 {model}")
        if front or back:
            # 只改第一个模板；多模板模型的其他模板保留原样，避免抹平
            # 用户自建的“认知/回忆”等卡片设计。
            first = names[:1]
            templates = {
                name: {"Front": front or DEFAULT_FRONT, "Back": back or DEFAULT_BACK}
                for name in first
            }
            self._invoke("updateModelTemplates", model={"name": model, "templates": templates})
        if css:
            self._invoke("updateModelStyling", model={"name": model, "css": css})

    def push_custom(
        self,
        words: list[dict],
        deck: str,
        model: str,
        field_map: dict[str, str],
        audio_loader=None,
        skip_existing: bool = True,
        templates: dict | None = None,
    ) -> dict:
        if model == MODEL_NAME:
            # 只在模型不存在时创建默认模型；已存在时由下面的自定义模板决定是否覆盖
            try:
                if MODEL_NAME not in (self.model_names() or []):
                    self.ensure_model()
            except Exception:
                pass
        else:
            # 独立模式：自动创建「Interpres · 词本名」这类模型
            try:
                if model not in (self.model_names() or []) and model.startswith("Interpres · "):
                    self._invoke(
                        "createModel",
                        modelName=model,
                        inOrderFields=FIELDS,
                        css=(templates or {}).get("css") or CSS,
                        isCloze=False,
                        cardTemplates=[
                            {
                                "Name": "Card 1",
                                "Front": (templates or {}).get("front") or DEFAULT_FRONT,
                                "Back": (templates or {}).get("back") or DEFAULT_BACK,
                            }
                        ],
                    )
            except Exception:
                pass
        self._invoke("createDeck", deck=deck)
        order = self.model_fields(model)
        if not order:
            raise AnkiError(f"Anki 里没有笔记类型 {model}")
        mapping = {
            target: source
            for target, source in (field_map or {}).items()
            if target in order and source in CUSTOM_SOURCES
        }
        if not mapping:
            mapping = {name: name for name in order if name in CUSTOM_SOURCES}
        if templates and (templates.get("front") or templates.get("back") or templates.get("css")):
            try:
                self.update_custom_templates(
                    model, templates.get("front") or "", templates.get("back") or "", templates.get("css") or ""
                )
            except AnkiError:
                pass

        word_field = next((t for t, src in mapping.items() if src == "Word"), order[0])
        existing = self.existing_field_values(deck, word_field) if skip_existing else set()
        audio_field = next((t for t, src in mapping.items() if src == "Audio"), "")

        added = duplicated = skipped = 0
        failed: list[str] = []
        ok_ids: list[int] = []
        for word in words:
            word_text = (word.get("word") or word.get("lemma") or "").strip()
            if skip_existing and word_text and word_text.lower() in existing:
                skipped += 1
                ok_ids.append(int(word["id"]))
                continue
            values = _custom_values(word)
            if audio_field and audio_loader is not None:
                try:
                    media = audio_loader(word)
                    if media:
                        filename, data = media
                        if self.store_media(filename, data):
                            values["Audio"] = f"[sound:{filename}]"
                except Exception:
                    pass
            fields = {target: values.get(source, "") for target, source in mapping.items()}
            note = {
                "deckName": deck,
                "modelName": model,
                "fields": fields,
                "tags": _tags(word),
                "options": {"allowDuplicate": False, "duplicateScope": "deck"},
            }
            try:
                self._invoke("addNote", note=note)
                added += 1
                ok_ids.append(int(word["id"]))
                if word_text:
                    existing.add(word_text.lower())
            except AnkiError as exc:
                msg = str(exc)
                if "duplicate" in msg.lower():
                    duplicated += 1
                    ok_ids.append(int(word["id"]))
                else:
                    failed.append(f"{word_text}: {msg}")
        return {"added": added, "duplicated": duplicated, "skipped": skipped, "failed": failed, "ok_ids": ok_ids}

    def push(self, words: list[dict], deck: str, audio_loader=None, skip_existing: bool = True) -> dict:
        """把生词推进 Anki；返回 {added, duplicated, skipped, failed, ok_ids}。"""
        self._invoke("createDeck", deck=deck)
        self.ensure_model()
        existing = self.existing_first_fields(deck) if skip_existing else set()

        added = 0
        duplicated = 0
        skipped = 0
        failed: list[str] = []
        ok_ids: list[int] = []
        for w in words:
            word_text = (w.get("word") or w.get("lemma") or "").strip()
            if skip_existing and word_text and word_text.lower() in existing:
                skipped += 1
                ok_ids.append(int(w["id"]))
                continue

            audio_tag = ""
            if audio_loader is not None:
                try:
                    media = audio_loader(w)
                    if media:
                        filename, data = media
                        if self.store_media(filename, data):
                            audio_tag = f"[sound:{filename}]"
                except Exception:
                    audio_tag = ""

            note = {
                "deckName": deck,
                "modelName": MODEL_NAME,
                "fields": {
                    "Word": w.get("word") or w.get("lemma") or "",
                    "Phonetic": w.get("reading") or "",
                    "POS": w.get("pos") or "",
                    "Meaning": w.get("dict_meaning") or w.get("meaning") or "",
                    "Example": w.get("dict_example") or w.get("sentence") or "",
                    "ExampleCN": w.get("dict_example_cn") or "",
                    "Audio": audio_tag,
                    "Book": w.get("book") or "",
                    "Language": (w.get("lang") or "").upper(),
                },
                "tags": _tags(w),
                "options": {"allowDuplicate": False, "duplicateScope": "deck"},
            }
            try:
                self._invoke("addNote", note=note)
                added += 1
                ok_ids.append(int(w["id"]))
                if word_text:
                    existing.add(word_text.lower())
            except AnkiError as exc:
                msg = str(exc)
                if "duplicate" in msg.lower():
                    duplicated += 1
                    ok_ids.append(int(w["id"]))
                else:
                    failed.append(f"{note['fields']['Word']}: {msg}")
        return {
            "added": added,
            "duplicated": duplicated,
            "skipped": skipped,
            "failed": failed,
            "ok_ids": ok_ids,
            "deck": deck,
        }

    def store_media(self, filename: str, data: bytes) -> bool:
        """把音频等文件存进 Anki 媒体库。"""
        import base64

        try:
            self._invoke(
                "storeMediaFile", filename=filename, data=base64.b64encode(data).decode()
            )
            return True
        except AnkiError:
            return False

    # -------------------------------------------------------------------- test
    def status(self) -> dict:
        try:
            version = self._invoke("version")
            decks = self._invoke("deckNames") or []
            return {"ok": True, "version": version, "decks": decks}
        except AnkiError as exc:
            return {"ok": False, "error": str(exc)}


# ---------------------------------------------------------------------- export
def export_tsv(words: list[dict], out_dir: Path | str, lang: str) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = out_dir / f"vocab_{lang or 'all'}_{stamp}.tsv"
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh, delimiter="\t", quoting=csv.QUOTE_MINIMAL)
        writer.writerow(CSV_HEADER)
        for w in words:
            writer.writerow(
                [
                    w.get("word") or w.get("lemma") or "",
                    w.get("reading") or "",
                    w.get("pos") or "",
                    w.get("dict_meaning") or w.get("meaning") or "",
                    w.get("dict_example") or w.get("sentence") or "",
                    w.get("dict_example_cn") or "",
                    "",
                    w.get("book") or "",
                    (w.get("lang") or "").upper(),
                    " ".join(_tags(w)),
                ]
            )
    return path


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text or "")


def _custom_values(word: dict) -> dict[str, str]:
    return {
        "Word": word.get("word") or word.get("lemma") or "",
        "Phonetic": word.get("reading") or "",
        "POS": word.get("pos") or "",
        "Meaning": word.get("dict_meaning") or word.get("meaning") or "",
        "Example": word.get("dict_example") or word.get("sentence") or "",
        "ExampleCN": word.get("dict_example_cn") or "",
        "Audio": "",
        "Book": word.get("book") or "",
        "Language": (word.get("lang") or "").upper(),
    }


def _tags(word: dict) -> list[str]:
    tags = ["rc", f"rc::{word.get('lang') or 'xx'}"]
    book = (word.get("book") or "").strip()
    if book:
        tags.append("book::" + re.sub(r"[^\w\-]+", "_", book)[:30])
    difficulty = (word.get("difficulty") or "").strip()
    if difficulty:
        tags.append("level::" + difficulty)
    return tags
