"""验证翻译记录：保存、吸收、增量翻译。"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from rc.config import Config  # noqa: E402
from rc.service import Service  # noqa: E402
from tests import mock_openai  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


def main() -> int:
    data = HERE / ".trans"
    shutil.rmtree(data, ignore_errors=True)
    data.mkdir(parents=True)
    mock_openai.start(18778)

    cfg = Config(data)
    cfg.data["api"].update(
        {"base_url": "http://127.0.0.1:18778/v1", "api_key": "k", "model": "mock"}
    )
    cfg.save()
    service = Service(cfg)

    first = "The quick brown fox jumps over the lazy dog. It was a sunny day."
    second = first + " The end came sooner than expected."

    print("\n[保存记录]")
    service.translate(first, book="Book A")
    rows = service.store.translations("Book A")
    check("记录已保存", len(rows) == 1, str(len(rows)))
    check("存的是原文", first in rows[0]["text"], rows[0]["text"][:40])
    payload = __import__("json").loads(rows[0]["payload"])
    check("完整卡片（含译文）", bool(payload.get("translation")), str(payload.keys()))
    check("单词不存", service.store.translation_count("Book A") == 1)
    service.translate("sanguine", book="Book A")
    check("查词后记录数不变", service.store.translation_count("Book A") == 1,
          str(service.store.translation_count("Book A")))

    print("\n[增量：只翻新增部分]")
    mock_openai._Handler.calls = 0
    result = service.translate(second, book="Book A")
    calls = mock_openai._Handler.calls
    check("只调用一次", calls == 1, f"calls={calls}")
    check("标记为增量", result["meta"].get("incremental") is True, str(result["meta"]))
    check(
        "译文包含新旧两部分",
        result["translation"].count(mock_openai.CANNED["translation"]) >= 2,
        result["translation"][:100],
    )
    check("旧记录被吸收", service.store.translation_count("Book A") == 1,
          str(service.store.translation_count("Book A")))
    rows = service.store.translations("Book A")
    check("留下的是长记录", rows[0]["text"] == second, rows[0]["text"][:50])

    print("\n[再翻旧段：被长记录覆盖，不重复存]")
    before = service.store.translation_count("Book A")
    service.translate(first, book="Book A")
    check("没有新增记录", service.store.translation_count("Book A") in (before, before),
          f"{before} → {service.store.translation_count('Book A')}")

    print("\n[搜索]")
    found = service.store.translations(query="sunny day")
    check("能按原文搜到", len(found) >= 1, str(len(found)))

    print("\n[删除]")
    rid = service.store.translations("Book A")[0]["id"]
    service.store.delete_translation(rid)
    check("删除后为空", service.store.translation_count("Book A") == 0)

    service.store.close()
    shutil.rmtree(data, ignore_errors=True)
    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
