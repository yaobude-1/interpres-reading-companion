"""用户词形/变位表：读写、索引、查词优先级。"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from rc.config import Config  # noqa: E402
from rc.service import Service  # noqa: E402
from rc.user_lang import UserLangData  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


def main() -> int:
    data = HERE / ".userlang"
    shutil.rmtree(data, ignore_errors=True)
    data.mkdir(parents=True)

    print("\n[数据层]")
    ul = UserLangData(data)
    ul.add_form("it", "Parlo", "parlare")
    check("词形保存", ul.form_lemma("it", "parlo") == "parlare", str(ul.forms("it")))
    check("大小写不敏感", ul.form_lemma("it", "PARLO") == "parlare", "")
    ul.set_table(
        "it",
        "parlare",
        [{"key": "present", "zh": "现在时", "rows": [["io", "parlo"], ["tu", "parli"]]}],
    )
    check("表已保存", bool(ul.table("it", "PARLARE")), str(ul.tables("it")))
    check("表内形式自动反查", ul.form_lemma("it", "parli") == "parlare", str(ul.forms("it")))
    check("文件落盘", (data / "lang_data" / "it.json").exists(), "")

    ul2 = UserLangData(data)
    check("重新加载", ul2.form_lemma("it", "parli") == "parlare", str(ul2.forms("it")))

    print("\n[多语言导入]")
    count = ul2.merge(
        {
            "es": {"forms": {"hablo": "hablar"}},
            "it": {"forms": {"vado": "andare"}},
        }
    )
    check("合并计数", count == 2, str(count))
    check("西语词形", ul2.form_lemma("es", "hablo") == "hablar", "")
    check("意语词形", ul2.form_lemma("it", "vado") == "andare", "")

    added = ul2.add_forms("it", {"parli": "parlare", "vado": "andare"})
    check("批量添加只计新增", added == 1, str(added))
    check("批量添加生效", ul2.form_lemma("it", "parli") == "parlare", "")
    check("已有映射不覆盖", ul2.form_lemma("it", "vado") == "andare", "")

    print("\n[查词优先级]")
    cfg = Config(data)
    cfg.data["languages"] = {"it": {"label": "Italiano", "zh_label": "意大利语"}}
    cfg.data["dictionaries"] = {}
    cfg.save()
    svc = Service(cfg)

    class FakeDict:
        def lookup(self, _word):
            return None

    def fake_lookup(lang, word):
        if lang != "it":
            return None
        if word in ("parlo", "parlare"):
            return {
                "word": word,
                "lang": "it",
                "source": "Test Dictionary",
                "senses": [{"pos": "v.", "definition": word}],
            }
        return None

    svc.dicts.dictionary = lambda lang: FakeDict() if lang == "it" else None
    svc.dicts.lookup_full = fake_lookup

    only_user = svc.lookup_all("vado")
    check(
        "无词典也能显示用户词形",
        bool(only_user) and only_user[0]["entry"].get("word") == "andare",
        str(only_user),
    )

    hits = svc.lookup_all("parlo")
    check("用户命中排第一", bool(hits) and hits[0]["entry"].get("match") == "user", str(hits))
    first = hits[0]["entry"] if hits else {}
    check("用户词形原形", first.get("word") == "parlare", str(first))
    check("用户词形字段", first.get("user_form") == "parlo", str(first))
    check("用户来源", first.get("source") == "用户数据", str(first))
    check("用户表挂上", bool((first.get("morph") or {}).get("user")), str(first.get("morph")))
    check(
        "词典精确仍在来源栏",
        any(h["entry"].get("match") == "exact" for h in hits),
        str([(h["entry"].get("word"), h["entry"].get("match")) for h in hits]),
    )

    hits2 = svc.lookup_all("parlare")
    check(
        "原形词条挂用户表",
        any(h["entry"].get("user_table") for h in hits2),
        str([(h["entry"].get("word"), h["entry"].get("user_table")) for h in hits2]),
    )
    table = svc.conjugation_table("parlare", "it")
    check("conjugation_table 用户优先", bool(table) and table.get("user"), str(table))
    analysis = svc.morph_analysis("parlo", "it")
    check("morph_analysis 用户词形", bool(analysis) and analysis.get("lemma") == "parlare", str(analysis))

    svc.store.close()
    shutil.rmtree(data, ignore_errors=True)
    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
