"""增量查词：lookup_all 的 on_hit 回调（默认词典先出、慢词典后补）。"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from tests.tmputil import local_temp  # noqa: E402

from rc.config import Config  # noqa: E402
from rc.service import Service  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


def build_service(tmp) -> Service:
    cfg = Config(Path(tmp))
    cfg.data["languages"] = {"en": {"label": "English"}}
    cfg.data["dictionaries"] = {"en": {"items": [], "muted": []}}
    cfg.save()
    svc = Service(cfg)

    class FakeDict:
        def __init__(self, dict_id: str, name: str) -> None:
            self.dict_id = dict_id
            self.name = name

    first = FakeDict("dict-a", "First")
    second = FakeDict("dict-b", "Second")
    svc.dicts.dictionaries = (
        lambda lang, context="panel": [first, second] if lang == "en" else []
    )

    def fake_lookup(dictionary, word):
        if word != "test":
            return None
        return {
            "word": word,
            "source": dictionary.name,
            "dict_id": dictionary.dict_id,
            "senses": [{"definition": dictionary.name}],
            "phonetic": "",
            "audio_key": "",
        }

    svc.dicts.lookup_full_with = fake_lookup
    svc.dicts.default_id = lambda lang: "dict-b" if lang == "en" else ""
    return svc


def main() -> int:
    print("\n[增量回调]")
    with local_temp(prefix="dict-incremental-") as tmp:
        svc = build_service(tmp)
        seen: list[str] = []
        hits = svc.lookup_all("test", on_hit=lambda h: seen.append(h["dict_id"]))
        check("on_hit 每本词典回调一次", len(seen) == 2, str(seen))
        check("先出第一本词典", seen and seen[0] == "dict-a", str(seen))
        check("后补第二本词典", len(seen) == 2 and seen[1] == "dict-b", str(seen))
        check("返回值仍然完整", len(hits) == 2, str(hits))
        svc.store.close()

        print("\n[无回调时行为不变]")
        svc = build_service(tmp)
        hits = svc.lookup_all("test")
        check("无回调正常返回", len(hits) == 2, str(hits))
        svc.store.close()

    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
