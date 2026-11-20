"""验证法语变位 / 拉丁变格引擎。"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from rc import conjug_fr, conjug_la  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


def main() -> int:
    print("\n[法语变位]")
    parler = conjug_fr.conjugate("parler")
    check("现在时", parler["present"][:3] == ["parle", "parles", "parle"], parler["present"][:3])
    check("简单将来时", parler["futur"][:3] == ["parlerai", "parleras", "parlera"], parler["futur"][:3])
    check("条件式", parler["conditionnel"][:2] == ["parlerais", "parlerais"], parler["conditionnel"][:2])
    check("复合过去", parler["passe_compose"][0] == "ai parlé", parler["passe_compose"][0])

    etre = conjug_fr.conjugate("être")
    check("être 现在时", etre["present"][:3] == ["suis", "es", "est"], etre["present"][:3])
    check("être 将来时", etre["futur"][0] == "serai", etre["futur"][0])

    vendre = conjug_fr.conjugate("vendre")
    check("-re 动词将来时", vendre["futur"][:2] == ["vendrai", "vendras"], vendre["futur"][:2])

    print("\n[法语反查]")

    def lookup(w):
        return True

    check("parlait → parler", conjug_fr.analyse("parlait", lookup)[0] == "parler")
    check("fermerait → fermer", conjug_fr.analyse("fermerait", lookup)[0] == "fermer")
    check("suis → être", conjug_fr.analyse("suis", lookup)[0] == "être")
    check("avait → avoir", conjug_fr.analyse("avait", lookup)[0] == "avoir")
    label = conjug_fr.analyse("parlait", lookup)[1]
    check("标注了人称", "第三人称单数" in label, label)

    print("\n[拉丁变格]")
    def fake_lookup(word: str):
        if word == "puella":
            return (word, "puella puella ~ae f.")
        return None

    rows = conjug_la.table("puella", fake_lookup)[0]["rows"]
    check("六个格", len(rows) == 6, str(len(rows)))
    check("主格单数", rows[0]["sing"] == "puella", rows[0])
    check("属格复数", rows[1]["plur"] == "puellarum", rows[1])

    heads = {
        "puella": "puella puella ~ae f.",
        "dominus": "dominus dominus ~ī m.",
        "bellum": "bellum bellum ~ī neut.",
    }

    def la_lookup(w):
        return (w, heads[w]) if w in heads else None
    hit = conjug_la.analyse("puellae", la_lookup)
    check("puellae → puella", hit and hit[0] == "puella", str(hit[0] if hit else None))
    check("说明是哪个格", hit and "格" in hit[1], str(hit[1] if hit else None))
    hit2 = conjug_la.analyse("dominorum", la_lookup)
    check("dominorum → dominus", hit2 and hit2[0] == "dominus", str(hit2[0] if hit2 else None))

    # 第三变格法（靠属格推词干）与动词变位
    def head(text: str) -> str:
        return text

    class FakeDict:
        data = {
            "rex": "rex rex 1 rēgis m. [regō]",
            "amo": "amō ~āre, ~āuī, ~ātum tr.",
        }

        def lookup(self, word):
            return (word, self.data[word]) if word in self.data else None

    fake = FakeDict()
    info = conjug_la.parse_noun(fake.data["rex"])
    check("rex 第三变格法", info and info["kind"] == "3" and info["stem"] == "rēg", str(info))
    verb = conjug_la.parse_verb(fake.data["amo"])
    check("amō 第一变位法", verb and verb["conj"] == 1 and verb["infinitive"] == "amāre", str(verb))
    rows = conjug_la.noun_table(info)[0]["rows"]
    check("rex 主格单数是 rex", rows[0]["sing"] == "rex", rows[0])
    forms = conjug_la.conjugate_verb(verb)
    check("amō 现在时", forms["present"][:3] == ["amo", "amas", "amat"], forms["present"][:3])
    check("amō 完成时", forms["perfect"][:3] == ["amāuī", "amāuistī", "amāuit"], forms["perfect"][:3])
    check("amō 完成分词", forms["participle_perfect"] == ["amātus"], forms.get("participle_perfect"))

    print("\n[法语简单过去时]")
    etre = conjug_fr.conjugate("être")
    check("être 简单过去时", etre["passe_simple"] == ["fus", "fus", "fut", "fûmes", "fûtes", "furent"], etre["passe_simple"])
    avoir = conjug_fr.conjugate("avoir")
    check("avoir 简单过去时", avoir["passe_simple"][:3] == ["eus", "eus", "eut"], avoir["passe_simple"][:3])
    parler = conjug_fr.conjugate("parler")
    check("parler 简单过去时", parler["passe_simple"][:2] == ["parlai", "parlas"], parler["passe_simple"][:2])
    check("furent → être", conjug_fr.analyse("furent", lookup)[0] == "être")

    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
