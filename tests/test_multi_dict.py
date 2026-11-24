"""每语言多词典：配置迁移、muted、来源顺序和多结果查词。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from tests.tmputil import local_temp  # noqa: E402

from rc import dict_config  # noqa: E402
from rc.config import Config  # noqa: E402
from rc.service import Service  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


def test_config() -> None:
    print("\n[配置迁移/显示]")
    with local_temp(prefix="dict-config-") as tmp:
        p = Path(tmp)
        (p / "config.json").write_text(
            json.dumps(
                {
                    "languages": {"en": {"label": "English"}},
                    "dictionaries": {
                        "en": {"mdx": r"D:\old\longman.mdx", "mdd": ""},
                    },
                }
            ),
            encoding="utf-8",
        )
        cfg = Config(p)
        items = dict_config.items(cfg.data, "en")
        check("旧配置迁移成一条", len(items) == 1, str(items))
        check("有稳定 id", bool(items[0].get("id")), str(items[0]))
        check("默认可见", len(dict_config.visible_items(cfg.data, "en")) == 1, "")

        second = dict_config.add_item(cfg.data, "en", r"D:\new\vocab.mdx")
        check("追加第二本", len(dict_config.items(cfg.data, "en")) == 2, "")
        dict_config.set_default(cfg.data, "en", second["id"])
        check("默认词典", dict_config.default_id(cfg.data, "en") == second["id"], "")
        dict_config.set_visible(cfg.data, "en", second["id"], False)
        visible = dict_config.visible_items(cfg.data, "en")
        check("静音后不可见", [i["id"] for i in visible] == [items[0]["id"]], str(visible))
        check("静音仍保留在配置", len(dict_config.items(cfg.data, "en")) == 2, "")
        dict_config.set_visible(cfg.data, "en", second["id"], True)
        check("恢复可见", len(dict_config.visible_items(cfg.data, "en")) == 2, "")
        dict_config.set_visible(cfg.data, "en", second["id"], False, context="popup")
        check(
            "弹窗静音不影响面板",
            len(dict_config.visible_items(cfg.data, "en")) == 2,
            "",
        )
        check(
            "弹窗静音生效",
            [i["id"] for i in dict_config.visible_items(cfg.data, "en", "popup")]
            == [items[0]["id"]],
            "",
        )
        dict_config.set_visible(cfg.data, "en", second["id"], True, context="popup")

        print("\n[全局库/多组]")
        cfg.data["languages"]["fr"] = {"label": "Français"}
        dict_config.normalize(cfg.data)
        shared = dict_config.add_library_item(cfg.data, r"D:\shared\bilingual.mdx")
        dict_config.add_to_group(cfg.data, "en", shared["id"])
        dict_config.add_to_group(cfg.data, "fr", shared["id"])
        check(
            "同一本可进两个组",
            set(dict_config.languages_of(cfg.data, shared["id"])) == {"en", "fr"},
            str(dict_config.languages_of(cfg.data, shared["id"])),
        )
        check(
            "英语组有共享词典",
            shared["id"] in [i["id"] for i in dict_config.items(cfg.data, "en")],
            "",
        )
        unassigned = dict_config.add_library_item(cfg.data, r"D:\unassigned\x.mdx")
        check("未分配不在组里", dict_config.languages_of(cfg.data, unassigned["id"]) == [], "")
        check("未分配不参与查词", unassigned["id"] not in [i["id"] for i in dict_config.visible_items(cfg.data, "en")], "")
        check("新词典默认不允许脚本", not dict_config.scripts_allowed(cfg.data, unassigned["id"]), "")
        dict_config.set_scripts_allowed(cfg.data, unassigned["id"], True)
        dict_config.normalize(cfg.data)
        check("脚本开关持久化", dict_config.scripts_allowed(cfg.data, unassigned["id"]), "")
        check("旧迁移词典保留脚本", dict_config.scripts_allowed(cfg.data, items[0]["id"]), "")


def test_multi_lookup() -> None:
    print("\n[多词典查词]")
    with local_temp(prefix="dict-lookup-") as tmp:
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
        hits = svc.lookup_all("test")
        check("两本都命中", len(hits) == 2, str(hits))
        check("dict_id 保留", {h["dict_id"] for h in hits} == {"dict-a", "dict-b"}, str(hits))
        check("顺序第一本优先", hits[0]["dict_id"] == "dict-a", str(hits))
        check(
            "默认词典有命中时标记",
            any(h["entry"].get("is_default") for h in hits if h["dict_id"] == "dict-b"),
            str([(h["dict_id"], h["entry"].get("is_default")) for h in hits]),
        )
        svc.store.close()


def main() -> int:
    test_config()
    test_multi_lookup()
    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
