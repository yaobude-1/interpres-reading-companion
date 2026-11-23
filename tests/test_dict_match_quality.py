"""跨词典查词：去重音精确匹配与匹配等级。"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from rc.fuzzy import FuzzyIndex  # noqa: E402
from rc.service_dict import DictMixin  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


def main() -> int:
    print("\n[去重音精确]")
    index = FuzzyIndex(["créer", "crier", "crever", "pain"])
    ranked = index.search("creer", 5)
    check("créer 排第一", ranked and ranked[0] == ("créer", 0), str(ranked))
    check("精确等级是 0", ranked and ranked[0][1] == 0, str(ranked))
    check("exact_matches", "créer" in index.exact_matches("creer"), str(index.exact_matches("creer")))
    check("无匹配返回空", index.exact_matches("zzz") == [], str(index.exact_matches("zzz")))

    print("\n[匹配等级]")
    check(
        "精确",
        DictMixin._match_kind({"word": "pain"}, "pain", "pain") == "exact",
        DictMixin._match_kind({"word": "pain"}, "pain", "pain"),
    )
    check(
        "重音匹配",
        DictMixin._match_kind({"word": "créer"}, "creer", "créer") == "accent",
        DictMixin._match_kind({"word": "créer"}, "creer", "créer"),
    )
    check(
        "重定向",
        DictMixin._match_kind({"word": "c", "redirect": "c"}, "creer", "cre") == "redirect",
        DictMixin._match_kind({"word": "c", "redirect": "c"}, "creer", "cre"),
    )
    check(
        "词形",
        DictMixin._match_kind({"word": "cree"}, "creer", "cree") == "lemma",
        DictMixin._match_kind({"word": "cree"}, "creer", "cree"),
    )
    check(
        "音节点不算重定向",
        DictMixin._match_kind({"word": "ge·hen"}, "gehen", "gehen") == "exact",
        DictMixin._match_kind({"word": "ge·hen"}, "gehen", "gehen"),
    )
    check(
        "下加点不算重定向",
        DictMixin._match_kind({"word": "e\u0323s·sen"}, "essen", "essen") == "exact",
        DictMixin._match_kind({"word": "e\u0323s·sen"}, "essen", "essen"),
    )
    check(
        "俄语竖线不算重定向",
        DictMixin._match_kind({"word": "ид|ти́"}, "идти", "идти") != "redirect",
        DictMixin._match_kind({"word": "ид|ти́"}, "идти", "идти"),
    )
    check(
        "下划线不算重定向",
        DictMixin._match_kind({"word": "spi\u0332e\u0332len"}, "spielen", "spielen") == "exact",
        DictMixin._match_kind({"word": "spi\u0332e\u0332len"}, "spielen", "spielen"),
    )

    print("\n[法语 -re 变位]")
    from rc import conjug_fr

    for form in ("vends", "vend", "vendent", "vendu"):
        hit = conjug_fr.analyse(form, lambda w: w == "vendre")
        check(f"{form} → vendre", bool(hit) and hit[0] == "vendre", str(hit))
    for form, lemma in (
        ("parlerions", "parler"),
        ("finirions", "finir"),
        ("vendrai", "vendre"),
        ("vende", "vendre"),
        ("finissons", "finir"),
        ("aimerai", "aimer"),
        ("parlant", "parler"),
    ):
        hit = conjug_fr.analyse(form, lambda w, target=lemma: w == target)
        check(f"{form} → {lemma}", bool(hit) and hit[0] == lemma, str(hit))

    print("\n[法语名词/形容词]")
    from rc.lemma import english_candidates, french_candidates

    for form, expected in (
        ("chevaux", "cheval"),
        ("heureuse", "heureux"),
        ("bateaux", "bateau"),
        ("travaux", "travail"),
        ("première", "premier"),
        ("blanche", "blanc"),
    ):
        candidates = french_candidates(form)
        check(f"{form} → {expected}", expected in candidates, str(candidates))
    check(
        "better → good",
        "good" in english_candidates("better"),
        str(english_candidates("better")),
    )

    print("\n[其他语言不借法语规则]")
    from rc.lemma import candidates as lemma_candidates

    for lang, word in (("it", "parlare"), ("es", "hablar"), ("de", "spielen")):
        check(
            f"{lang} 不生成变位表",
            DictMixin.conjugation_table(None, word, lang) is None,
            str(DictMixin.conjugation_table(None, word, lang)),
        )
        check(
            f"{lang} 不生成法语词形",
            "parler" not in lemma_candidates(word, lang),
            str(lemma_candidates(word, lang)),
        )
    check(
        "法语仍生成变位表",
        DictMixin.conjugation_table(None, "parler", "fr") is not None,
        str(DictMixin.conjugation_table(None, "parler", "fr")),
    )

    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
