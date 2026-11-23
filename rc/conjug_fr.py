"""法语动词变位：规则动词三组 + 常用不规则动词。

只做阅读查词需要的 8 类时态：
现在时、复合过去、未完成过去、简单将来、条件式现在、虚拟式现在、命令式、分词。
"""

from __future__ import annotations

PERSONS = ["je", "tu", "il", "nous", "vous", "ils"]
PERSON_CN = ["第一人称单数", "第二人称单数", "第三人称单数", "第一人称复数", "第二人称复数", "第三人称复数"]
IMPERATIF_CN = ["第二人称单数", "第一人称复数", "第二人称复数"]

# 规则动词词尾
ER_PRESENT = ["e", "es", "e", "ons", "ez", "ent"]
ER_IMPARFAIT = ["ais", "ais", "ait", "ions", "iez", "aient"]
ER_FUTUR = ["erai", "eras", "era", "erons", "erez", "eront"]
ER_SUBJ = ["e", "es", "e", "ions", "iez", "ent"]

IR_PRESENT = ["is", "is", "it", "issons", "issez", "issent"]
IR_IMPARFAIT = ["issais", "issais", "issait", "issions", "issiez", "issaient"]
IR_FUTUR = ["irai", "iras", "ira", "irons", "irez", "iront"]
IR_SUBJ = ["isse", "isses", "isse", "issions", "issiez", "issent"]

RE_PRESENT = ["s", "s", "", "ons", "ez", "ent"]
RE_IMPARFAIT = ["ais", "ais", "ait", "ions", "iez", "aient"]
RE_FUTUR = ["rai", "ras", "ra", "rons", "rez", "ront"]
RE_SUBJ = ["e", "es", "e", "ions", "iez", "ent"]

# 不规则动词：现在时六个人称、过去分词、辅助动词、将来词干（可选）、虚拟式词干（可选）
IRREGULAR: dict[str, dict] = {
    "être": {
        "present": ["suis", "es", "est", "sommes", "êtes", "sont"],
        "participle": "été",
        "aux": "avoir",
        "futur": "ser",
        "subj": ["sois", "sois", "soit", "soyons", "soyez", "soient"],
        "imparfait": ["étais", "étais", "était", "étions", "étiez", "étaient"],
        "imperatif": ["sois", "soyons", "soyez"],
        "part_present": "étant",
    },
    "avoir": {
        "present": ["ai", "as", "a", "avons", "avez", "ont"],
        "participle": "eu",
        "aux": "avoir",
        "futur": "aur",
        "subj": ["aie", "aies", "ait", "ayons", "ayez", "aient"],
        "imparfait": ["avais", "avais", "avait", "avions", "aviez", "avaient"],
        "imperatif": ["aie", "ayons", "ayez"],
        "part_present": "ayant",
    },
    "aller": {
        "present": ["vais", "vas", "va", "allons", "allez", "vont"],
        "participle": "allé",
        "aux": "être",
        "futur": "ir",
        "subj": ["aille", "ailles", "aille", "allions", "alliez", "aillent"],
        "imparfait": ["allais", "allais", "allait", "allions", "alliez", "allaient"],
        "imperatif": ["va", "allons", "allez"],
        "part_present": "allant",
    },
    "faire": {
        "present": ["fais", "fais", "fait", "faisons", "faites", "font"],
        "participle": "fait",
        "aux": "avoir",
        "futur": "fer",
        "subj": ["fasse", "fasses", "fasse", "fassions", "fassiez", "fassent"],
        "imparfait": ["faisais", "faisais", "faisait", "faisions", "faisiez", "faisaient"],
        "imperatif": ["fais", "faisons", "faites"],
        "part_present": "faisant",
    },
    "pouvoir": {
        "present": ["peux", "peux", "peut", "pouvons", "pouvez", "peuvent"],
        "participle": "pu",
        "aux": "avoir",
        "futur": "pourr",
        "subj": ["puisse", "puisses", "puisse", "puissions", "puissiez", "puissent"],
        "imparfait": ["pouvais", "pouvais", "pouvait", "pouvions", "pouviez", "pouvaient"],
        "part_present": "pouvant",
    },
    "vouloir": {
        "present": ["veux", "veux", "veut", "voulons", "voulez", "veulent"],
        "participle": "voulu",
        "aux": "avoir",
        "futur": "voudr",
        "subj": ["veuille", "veuilles", "veuille", "voulions", "vouliez", "veuillent"],
        "imparfait": ["voulais", "voulais", "voulait", "voulions", "vouliez", "voulaient"],
        "imperatif": ["veuille", "voulons", "voulez"],
        "part_present": "voulant",
    },
    "devoir": {
        "present": ["dois", "dois", "doit", "devons", "devez", "doivent"],
        "participle": "dû",
        "aux": "avoir",
        "futur": "devr",
        "subj": ["doive", "doives", "doive", "devions", "deviez", "doivent"],
        "imparfait": ["devais", "devais", "devait", "devions", "deviez", "devaient"],
        "part_present": "devant",
    },
    "savoir": {
        "present": ["sais", "sais", "sait", "savons", "savez", "savent"],
        "participle": "su",
        "aux": "avoir",
        "futur": "saur",
        "subj": ["sache", "saches", "sache", "sachions", "sachiez", "sachent"],
        "imparfait": ["savais", "savais", "savait", "savions", "saviez", "savaient"],
        "imperatif": ["sache", "sachons", "sachez"],
        "part_present": "sachant",
    },
    "voir": {
        "present": ["vois", "vois", "voit", "voyons", "voyez", "voient"],
        "participle": "vu",
        "aux": "avoir",
        "futur": "verr",
        "subj": ["voie", "voies", "voie", "voyions", "voyiez", "voient"],
        "imparfait": ["voyais", "voyais", "voyait", "voyions", "voyiez", "voyaient"],
        "part_present": "voyant",
    },
    "venir": {
        "present": ["viens", "viens", "vient", "venons", "venez", "viennent"],
        "participle": "venu",
        "aux": "être",
        "futur": "viendr",
        "subj": ["vienne", "viennes", "vienne", "venions", "veniez", "viennent"],
        "imparfait": ["venais", "venais", "venait", "venions", "veniez", "venaient"],
        "part_present": "venant",
    },
    "prendre": {
        "present": ["prends", "prends", "prend", "prenons", "prenez", "prennent"],
        "participle": "pris",
        "aux": "avoir",
        "futur": "prendr",
        "subj": ["prenne", "prennes", "prenne", "prenions", "preniez", "prennent"],
        "imparfait": ["prenais", "prenais", "prenait", "prenions", "preniez", "prenaient"],
        "part_present": "prenant",
    },
    "mettre": {
        "present": ["mets", "mets", "met", "mettons", "mettez", "mettent"],
        "participle": "mis",
        "aux": "avoir",
        "futur": "mettr",
        "subj": ["mette", "mettes", "mette", "mettions", "mettiez", "mettent"],
        "imparfait": ["mettais", "mettais", "mettait", "mettions", "mettiez", "mettaient"],
        "part_present": "mettant",
    },
    "dire": {
        "present": ["dis", "dis", "dit", "disons", "dites", "disent"],
        "participle": "dit",
        "aux": "avoir",
        "futur": "dir",
        "subj": ["dise", "dises", "dise", "disions", "disiez", "disent"],
        "imparfait": ["disais", "disais", "disait", "disions", "disiez", "disaient"],
        "part_present": "disant",
    },
    "lire": {
        "present": ["lis", "lis", "lit", "lisons", "lisez", "lisent"],
        "participle": "lu",
        "aux": "avoir",
        "futur": "lir",
        "subj": ["lise", "lises", "lise", "lisions", "lisiez", "lisent"],
        "imparfait": ["lisais", "lisais", "lisait", "lisions", "lisiez", "lisaient"],
        "part_present": "lisant",
    },
    "écrire": {
        "present": ["écris", "écris", "écrit", "écrivons", "écrivez", "écrivent"],
        "participle": "écrit",
        "aux": "avoir",
        "futur": "écrir",
        "subj": ["écrive", "écrives", "écrive", "écrivions", "écriviez", "écrivent"],
        "imparfait": ["écrivais", "écrivais", "écrivait", "écrivions", "écriviez", "écrivaient"],
        "part_present": "écrivant",
    },
    "boire": {
        "present": ["bois", "bois", "boit", "buvons", "buvez", "boivent"],
        "participle": "bu",
        "aux": "avoir",
        "futur": "boir",
        "subj": ["boive", "boives", "boive", "buvions", "buviez", "boivent"],
        "imparfait": ["buvais", "buvais", "buvait", "buvions", "buviez", "buvaient"],
        "part_present": "buvant",
    },
    "croire": {
        "present": ["crois", "crois", "croit", "croyons", "croyez", "croient"],
        "participle": "cru",
        "aux": "avoir",
        "futur": "croir",
        "subj": ["croie", "croies", "croie", "croyions", "croyiez", "croient"],
        "imparfait": ["croyais", "croyais", "croyait", "croyions", "croyiez", "croyaient"],
        "part_present": "croyant",
    },
    "connaître": {
        "present": ["connais", "connais", "connaît", "connaissons", "connaissez", "connaissent"],
        "participle": "connu",
        "aux": "avoir",
        "futur": "connaîtr",
        "subj": ["connaisse", "connaisses", "connaisse", "connaissions", "connaissiez", "connaissent"],
        "imparfait": ["connaissais", "connaissais", "connaissait", "connaissions", "connaissiez", "connaissaient"],
        "part_present": "connaissant",
    },
    "vivre": {
        "present": ["vis", "vis", "vit", "vivons", "vivez", "vivent"],
        "participle": "vécu",
        "aux": "avoir",
        "futur": "vivr",
        "subj": ["vive", "vives", "vive", "vivions", "viviez", "vivent"],
        "imparfait": ["vivais", "vivais", "vivait", "vivions", "viviez", "vivaient"],
        "part_present": "vivant",
    },
    "partir": {
        "present": ["pars", "pars", "part", "partons", "partez", "partent"],
        "participle": "parti",
        "aux": "être",
        "futur": "partir",
        "subj": ["parte", "partes", "parte", "partions", "partiez", "partent"],
        "imparfait": ["partais", "partais", "partait", "partions", "partiez", "partaient"],
        "part_present": "partant",
    },
    "sortir": {
        "present": ["sors", "sors", "sort", "sortons", "sortez", "sortent"],
        "participle": "sorti",
        "aux": "être",
        "futur": "sortir",
        "subj": ["sorte", "sortes", "sorte", "sortions", "sortiez", "sortent"],
        "imparfait": ["sortais", "sortais", "sortait", "sortions", "sortiez", "sortaient"],
        "part_present": "sortant",
    },
    "dormir": {
        "present": ["dors", "dors", "dort", "dormons", "dormez", "dorment"],
        "participle": "dormi",
        "aux": "avoir",
        "futur": "dormir",
        "subj": ["dorme", "dormes", "dorme", "dormions", "dormiez", "dorment"],
        "imparfait": ["dormais", "dormais", "dormait", "dormions", "dormiez", "dormaient"],
        "part_present": "dormant",
    },
    "ouvrir": {
        "present": ["ouvre", "ouvres", "ouvre", "ouvrons", "ouvrez", "ouvrent"],
        "participle": "ouvert",
        "aux": "avoir",
        "futur": "ouvrir",
        "subj": ["ouvre", "ouvres", "ouvre", "ouvrions", "ouvriez", "ouvrent"],
        "imparfait": ["ouvrais", "ouvrais", "ouvrait", "ouvrions", "ouvriez", "ouvraient"],
        "part_present": "ouvrant",
    },
    "recevoir": {
        "present": ["reçois", "reçois", "reçoit", "recevons", "recevez", "reçoivent"],
        "participle": "reçu",
        "aux": "avoir",
        "futur": "recevr",
        "subj": ["reçoive", "reçoives", "reçoive", "recevions", "receviez", "reçoivent"],
        "imparfait": ["recevais", "recevais", "recevait", "recevions", "receviez", "recevaient"],
        "part_present": "recevant",
    },
    "courir": {
        "present": ["cours", "cours", "court", "courons", "courez", "courent"],
        "participle": "couru",
        "aux": "avoir",
        "futur": "courr",
        "subj": ["coure", "coures", "coure", "courions", "couriez", "courent"],
        "imparfait": ["courais", "courais", "courait", "courions", "couriez", "couraient"],
        "part_present": "courant",
    },
    "mourir": {
        "present": ["meurs", "meurs", "meurt", "mourons", "mourez", "meurent"],
        "participle": "mort",
        "aux": "être",
        "futur": "mourr",
        "subj": ["meure", "meures", "meure", "mourions", "mouriez", "meurent"],
        "imparfait": ["mourais", "mourais", "mourait", "mourions", "mouriez", "mouraient"],
        "part_present": "mourant",
    },
    "tenir": {
        "present": ["tiens", "tiens", "tient", "tenons", "tenez", "tiennent"],
        "participle": "tenu",
        "aux": "avoir",
        "futur": "tiendr",
        "subj": ["tienne", "tiennes", "tienne", "tenions", "teniez", "tiennent"],
        "imparfait": ["tenais", "tenais", "tenait", "tenions", "teniez", "tenaient"],
        "part_present": "tenant",
    },
    "rire": {
        "present": ["ris", "ris", "rit", "rions", "riez", "rient"],
        "participle": "ri",
        "aux": "avoir",
        "futur": "rir",
        "subj": ["rie", "ries", "rie", "riions", "riiez", "rient"],
        "imparfait": ["riais", "riais", "riait", "riions", "riiez", "riaient"],
        "part_present": "riant",
    },
    "plaire": {
        "present": ["plais", "plais", "plaît", "plaisons", "plaisez", "plaisent"],
        "participle": "plu",
        "aux": "avoir",
        "futur": "plair",
        "subj": ["plaise", "plaises", "plaise", "plaisions", "plaisiez", "plaisent"],
        "imparfait": ["plaisais", "plaisais", "plaisait", "plaisions", "plaisiez", "plaisaient"],
        "part_present": "plaisant",
    },
    "naître": {
        "present": ["nais", "nais", "naît", "naissons", "naissez", "naissent"],
        "participle": "né",
        "aux": "être",
        "futur": "naîtr",
        "subj": ["naisse", "naisses", "naisse", "naissions", "naissiez", "naissent"],
        "imparfait": ["naissais", "naissais", "naissait", "naissions", "naissiez", "naissaient"],
        "part_present": "naissant",
    },
    "falloir": {
        "present": ["", "", "faut", "", "", ""],
        "participle": "fallu",
        "aux": "avoir",
        "futur": "faudr",
        "subj": ["", "", "faille", "", "", ""],
        "imparfait": ["", "", "fallait", "", "", ""],
        "part_present": "",
        "impersonal": True,
    },
    "pleuvoir": {
        "present": ["", "", "pleut", "", "", "pleuvent"],
        "participle": "plu",
        "aux": "avoir",
        "futur": "pleuvr",
        "subj": ["", "", "pleuve", "", "", "pleuvent"],
        "imparfait": ["", "", "pleuvait", "", "", "pleuvaient"],
        "part_present": "pleuvant",
        "impersonal": True,
    },
}

MOODS = {
    "present": ("现在时", "Présent"),
    "passe_compose": ("复合过去时", "Passé Composé"),
    "imparfait": ("未完成过去时", "Imparfait"),
    "futur": ("简单将来时", "Futur Simple"),
    "conditionnel": ("条件式现在时", "Conditionnel Présent"),
    "subjonctif": ("虚拟式现在时", "Subjonctif Présent"),
    "imperatif": ("命令式", "Impératif"),
    "participe": ("分词", "Participe"),
}


_IRREGULAR_INDEX: dict | None = None


def irregular_index() -> dict:
    """变形 -> (原形, 时态中文, 人称中文) 的反查表（只含不规则动词）。"""
    global _IRREGULAR_INDEX
    if _IRREGULAR_INDEX is not None:
        return _IRREGULAR_INDEX
    index: dict = {}
    for verb in IRREGULAR:
        data = conjugate(verb)
        if not data:
            continue
        for key, zh in (
            ("present", "现在时"), ("passe_compose", "复合过去时"), ("imparfait", "未完成过去时"),
            ("futur", "简单将来时"), ("conditionnel", "条件式现在时"),
            ("subjonctif", "虚拟式现在时"), ("imperatif", "命令式"),
            ("passe_simple", "简单过去时"),
        ):
            for i, form in enumerate(data[key]):
                if not form:
                    continue
                person = PERSON_CN[i] if i < len(PERSON_CN) else ""
                if key == "imperatif":
                    person = IMPERATIF_CN[i] if i < len(IMPERATIF_CN) else ""
                index.setdefault(form, (verb, zh, person))
        for i, form in enumerate(data["participe"]):
            if form:
                index.setdefault(form, (verb, "分词", "现在分词" if i == 0 else "过去分词"))
    _IRREGULAR_INDEX = index
    return index


# 简单过去时：不规则动词的词干与类型（u = -us/-ut，i = -is/-it）
PASSE_SIMPLE = {
    "être": ("f", "us"),
    "avoir": ("eu", "us2"),
    "faire": ("f", "is"),
    "aller": ("all", "er"),
    "venir": ("vin", "is2"),
    "prendre": ("pr", "is"),
    "mettre": ("m", "is"),
    "dire": ("d", "is"),
    "lire": ("l", "us"),
    "écrire": ("écriv", "is"),
    "boire": ("b", "us"),
    "croire": ("cr", "us"),
    "connaître": ("conn", "us"),
    "vivre": ("véc", "us"),
    "partir": ("part", "is"),
    "sortir": ("sort", "is"),
    "dormir": ("dorm", "is"),
    "ouvrir": ("ouvr", "is"),
    "recevoir": ("reç", "us"),
    "courir": ("cour", "us"),
    "mourir": ("mour", "us"),
    "tenir": ("tin", "is2"),
    "rire": ("r", "is"),
    "plaire": ("pl", "us"),
    "naître": ("naqu", "is"),
    "pouvoir": ("p", "us"),
    "vouloir": ("voul", "us"),
    "devoir": ("d", "us"),
    "savoir": ("s", "us"),
    "voir": ("v", "is"),
    "falloir": ("fall", "us"),
    "pleuvoir": ("pl", "us"),
}

ENDINGS = {
    "er": ["ai", "as", "a", "âmes", "âtes", "èrent"],
    "us": ["us", "us", "ut", "ûmes", "ûtes", "urent"],
    "us2": ["s", "s", "t", "@mes", "@tes", "rent"],
    "is": ["is", "is", "it", "îmes", "îtes", "irent"],
    "is2": ["s", "s", "t", "@mes", "@tes", "rent"],
}

U_ENDINGS = ["us", "us", "ut", "ûmes", "ûtes", "urent"]
I_ENDINGS = ["is", "is", "it", "îmes", "îtes", "irent"]


CIRCUMFLEX = {"a": "â", "e": "ê", "i": "î", "o": "ô", "u": "û"}


def _accent_last_vowel(text: str) -> str:
    for index in range(len(text) - 1, -1, -1):
        if text[index] in CIRCUMFLEX:
            return text[:index] + CIRCUMFLEX[text[index]] + text[index + 1:]
    return text


def _passe_simple(verb: str, stem: str) -> list[str]:
    if verb in PASSE_SIMPLE:
        pstem, kind = PASSE_SIMPLE[verb]
        if "@" in ENDINGS[kind][3]:
            accented = _accent_last_vowel(pstem)
            return [pstem + e if not e.startswith("@") else accented + e[1:] for e in ENDINGS[kind]]
        return [pstem + e for e in ENDINGS[kind]]
    if verb.endswith("er"):
        return [stem + e for e in ENDINGS["er"]]
    return [stem + e for e in ENDINGS["is"]]


def _strip_ons(form: str) -> str:
    return form[:-3] if form.endswith("ons") else form


def conjugate(infinitive: str) -> dict | None:
    """给出 8 类时态的全部形式；不认识的动词返回 None。"""
    verb = infinitive.strip().lower()
    if verb.endswith("er") and verb not in IRREGULAR:
        stem = verb[:-2]
        present = [stem + e for e in ER_PRESENT]
        imparfait = [stem + e for e in ER_IMPARFAIT]
        futur = [stem + e for e in ER_FUTUR]
        subj = [stem + e for e in ER_SUBJ]
        part_present = stem + "ant"
        participle = stem + "é"
        aux = "avoir"
        imperatif = [stem + "e", stem + "ons", stem + "ez"]
    elif verb.endswith("ir") and verb not in IRREGULAR:
        stem = verb[:-2]
        present = [stem + e for e in IR_PRESENT]
        imparfait = [stem + e for e in IR_IMPARFAIT]
        futur = [stem + e for e in IR_FUTUR]
        subj = [stem + e for e in IR_SUBJ]
        part_present = stem + "issant"
        participle = stem + "i"
        aux = "avoir"
        imperatif = [stem + "is", stem + "issons", stem + "issez"]
    elif verb.endswith("re") and verb not in IRREGULAR:
        stem = verb[:-2]
        present = [stem + e for e in RE_PRESENT]
        imparfait = [stem + e for e in RE_IMPARFAIT]
        futur = [verb[:-1] + e for e in ["ai", "as", "a", "ons", "ez", "ont"]]
        subj = [stem + e for e in RE_SUBJ]
        part_present = stem + "ant"
        participle = stem + "u"
        aux = "avoir"
        imperatif = [stem + "s", stem + "ons", stem + "ez"]
    elif verb in IRREGULAR:
        data = IRREGULAR[verb]
        present = data["present"]
        imparfait = data.get("imparfait") or [
            _strip_ons(present[3]) + e for e in ER_IMPARFAIT
        ]
        futur = [(data.get("futur") or verb) + e for e in ["ai", "as", "a", "ons", "ez", "ont"]]
        subj = data.get("subj") or [_strip_ons(present[5]) + e for e in ER_SUBJ]
        part_present = data.get("part_present") or (_strip_ons(present[3]) + "ant")
        participle = data["participle"]
        aux = data.get("aux", "avoir")
        imperatif = data.get("imperatif") or [present[1], present[3], present[4]]
    else:
        return None

    avere = IRREGULAR["avoir"]["present"]
    etre = IRREGULAR["être"]["present"]
    aux_present = etre if aux == "être" else avere
    passe_compose = [
        (f"{aux_present[i]} {participle}" if aux_present[i] else "")
        for i in range(6)
    ]
    # 条件式 = 将来时词干 + 未完成过去时词尾
    futur_stem = futur[0][:-2] if futur[0].endswith("ai") else futur[0][:-1]
    conditionnel = [futur_stem + e for e in ER_IMPARFAIT]

    simple_stem = stem if verb not in IRREGULAR else verb[:-1]
    return {
        "infinitive": verb,
        "aux": aux,
        "passe_simple": _passe_simple(verb, simple_stem),
        "present": present,
        "passe_compose": passe_compose,
        "imparfait": imparfait,
        "futur": futur,
        "conditionnel": conditionnel,
        "subjonctif": subj,
        "imperatif": imperatif,
        "participe": [part_present, participle],
    }


VOWELS = "aeiouéèêàâîïôûùh"


def _elide(person: str, form: str) -> str:
    """je + 元音开头 -> j'...（法语省音）。"""
    if person == "je" and form and form[0].lower() in VOWELS:
        return "j'" + form
    return form


def _persons(tense: str, forms: list[str]) -> list[tuple[str, str]]:
    # 人称和词形数量可能不一致（如命令式只有 3 个），按短的截断
    if tense == "imperatif":
        return list(zip(["(tu)", "(nous)", "(vous)"], forms, strict=False))
    if tense == "participe":
        return list(zip(["现在分词", "过去分词"], forms, strict=False))
    return [(p, _elide(p, f)) for p, f in zip(PERSONS, forms, strict=False)]


def table(infinitive: str) -> list[dict]:
    """生成表格数据：[{key, zh, fr, rows:[(person, form)]}]"""
    data = conjugate(infinitive)
    if not data:
        return []
    groups = [
        ("present", "现在时", "Présent"),
        ("passe_compose", "复合过去时", "Passé Composé"),
        ("imparfait", "未完成过去时", "Imparfait"),
        ("futur", "简单将来时", "Futur Simple"),
        ("passe_simple", "简单过去时", "Passé Simple"),
        ("conditionnel", "条件式现在时", "Conditionnel Présent"),
        ("subjonctif", "虚拟式现在时", "Subjonctif Présent"),
        ("imperatif", "命令式", "Impératif"),
        ("participe", "分词", "Participe"),
    ]
    out = []
    for key, zh, fr in groups:
        rows = _persons(key, data[key])
        out.append(
            {
                "key": key,
                "zh": zh,
                "fr": fr,
                "rows": [(p, f) for p, f in rows if f],
            }
        )
    return out


def analyse(word: str, lookup) -> tuple[str, str] | None:
    """反查一个变形：返回 (原形, 语法说明)。

    lookup(form) 用于确认该原形是否真的存在于词典里。
    """
    from . import lemma

    target = word.strip().lower()
    candidates: list[str] = []
    for base in [target] + lemma.candidates(target, "fr"):
        if base and len(base) > 1 and base not in candidates:
            candidates.append(base)
    # 按词尾反推原形：parlerions → parler（词干已是不定式时不再补 -er），
    # finissons → finir，vendrai → vendre。
    endings = {
        "er": (
            "", "e", "es", "ent", "ons", "ez", "ais", "ait", "ions", "iez",
            "aient", "ai", "as", "a", "âmes", "âtes", "èrent", "erai", "eras",
            "era", "erons", "erez", "eront", "é", "ée", "és", "ées", "ant",
        ),
        "ir": (
            "", "is", "it", "issons", "issez", "issent", "issais", "issait",
            "issions", "issiez", "issaient", "irai", "iras", "ira", "irons",
            "irez", "iront", "isse", "isses", "i", "issant", "îmes", "îtes",
            "irent", "ions", "iez", "ais", "ait", "aient",
        ),
        "re": (
            "", "e", "es", "s", "t", "ons", "ez", "ent", "ais", "ait", "ions",
            "iez", "aient", "ai", "as", "a", "ont", "is", "it", "îmes", "îtes",
            "irent", "u", "us", "ue", "ues", "ant",
        ),
    }
    for infinitive, suffixes in endings.items():
        for suffix in suffixes:
            if suffix and not target.endswith(suffix):
                continue
            stem = target[: -len(suffix)] if suffix else target
            if len(stem) < 3:
                continue
            if stem.endswith(infinitive):
                candidate = stem
            elif infinitive == "re" and stem.endswith("r"):
                # vendrai / vendrais 的词干是 vendr，补 e 才是 vendre
                candidate = stem + "e"
            else:
                candidate = stem + infinitive
            if candidate not in candidates:
                candidates.append(candidate)

    # 1) 不规则动词优先（suis -> être，而不是瞎猜成 suir）
    hit = irregular_index().get(target)
    if hit and lookup(hit[0]):
        verb, zh, person = hit
        return verb, f"{zh}，{person}" if person else zh

    # 2) 规则动词：按词尾猜原形，再用词典验证
    for candidate in candidates:
        data = conjugate(candidate)
        if not data:
            continue
        if not lookup(candidate):
            continue
        for key, zh, _fr in [
            ("present", "现在时", ""),
            ("passe_compose", "复合过去时", ""),
            ("imparfait", "未完成过去时", ""),
            ("futur", "简单将来时", ""),
            ("passe_simple", "简单过去时", ""),
            ("conditionnel", "条件式现在时", ""),
            ("subjonctif", "虚拟式现在时", ""),
            ("imperatif", "命令式", ""),
            ("participe", "分词", ""),
        ]:
            for person, form in _persons(key, data[key]):
                raw = form[2:] if form.startswith("j'") else form
                if form and (raw == target or form == target or form.split()[-1] == target):
                    if person in ("现在分词", "过去分词"):
                        label = f"{zh}，{person}"
                    elif key == "imperatif":
                        label = f"{zh}，{person}"
                    else:
                        idx = PERSONS.index(person) if person in PERSONS else -1
                        label = f"{zh}，{PERSON_CN[idx]}" if idx >= 0 else zh
                    return candidate, label
    return None
