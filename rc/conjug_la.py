"""拉丁语名词变格与动词变位。

词干来源：牛津拉丁词典词条头部给出属格（名词）或不定式（动词）：
    puella ~ae f.            → 属格 puellae
    rex 1 rēgis m.           → 属格 rēgis
    tempus ~oris neut.       → 属格 temporis
    diēs ~ēī m.              → 属格 diēī
    amō ~āre, ~āuī, ~ātum    → 不定式 amāre
"""

from __future__ import annotations

import re

CASES = ["主格", "属格", "与格", "宾格", "夺格", "呼格"]
CASE_KEYS = ["nom", "gen", "dat", "acc", "abl", "voc"]

GEN_ENDINGS = [("ae", 1), ("is", 3), ("us", 4), ("ei", 5), ("i", 2)]

NOUN_ENDINGS: dict[str, dict[str, tuple[str, str]]] = {
    "1": {
        "nom": ("a", "ae"), "gen": ("ae", "arum"), "dat": ("ae", "is"),
        "acc": ("am", "as"), "abl": ("a", "is"), "voc": ("a", "ae"),
    },
    "2m": {
        "nom": ("us", "i"), "gen": ("i", "orum"), "dat": ("o", "is"),
        "acc": ("um", "os"), "abl": ("o", "is"), "voc": ("e", "i"),
    },
    "2n": {
        "nom": ("um", "a"), "gen": ("i", "orum"), "dat": ("o", "is"),
        "acc": ("um", "a"), "abl": ("o", "is"), "voc": ("um", "a"),
    },
    "3": {
        "nom": ("", "es"), "gen": ("is", "um"), "dat": ("i", "ibus"),
        "acc": ("em", "es"), "abl": ("e", "ibus"), "voc": ("", "es"),
    },
    "3n": {
        "nom": ("", "a"), "gen": ("is", "um"), "dat": ("i", "ibus"),
        "acc": ("", "a"), "abl": ("e", "ibus"), "voc": ("", "a"),
    },
    "3i": {
        "nom": ("", "es"), "gen": ("is", "ium"), "dat": ("i", "ibus"),
        "acc": ("em", "es"), "abl": ("i", "ibus"), "voc": ("", "es"),
    },
    "3in": {
        "nom": ("", "ia"), "gen": ("is", "ium"), "dat": ("i", "ibus"),
        "acc": ("", "ia"), "abl": ("i", "ibus"), "voc": ("", "ia"),
    },
    "4": {
        "nom": ("us", "us"), "gen": ("us", "uum"), "dat": ("ui", "ibus"),
        "acc": ("um", "us"), "abl": ("u", "ibus"), "voc": ("us", "us"),
    },
    "5": {
        "nom": ("es", "es"), "gen": ("ei", "erum"), "dat": ("ei", "ebus"),
        "acc": ("em", "es"), "abl": ("e", "ebus"), "voc": ("es", "es"),
    },
}

VERB_PERSONS = ["我", "你", "他/她", "我们", "你们", "他们"]

MACRONS = str.maketrans(
    {
        "ā": "a", "ē": "e", "ī": "i", "ō": "o", "ū": "u", "ȳ": "y",
        "ă": "a", "ĕ": "e", "ĭ": "i", "ŏ": "o", "ŭ": "u",
        "v": "u", "j": "i",
    }
)

CUTS = (
    "ibus", "orum", "arum", "āō", "ēō", "īō", "eō", "iō", "uō", "gō", "cō",
    "bō", "pō", "tō", "dō", "xō", "us", "um", "er", "is", "es", "or",
    "x", "o", "e", "a", "u", "s", "ēs", "ī", "ō", "ā", "ū", "",
)


def _fold(text: str) -> str:
    return (text or "").translate(MACRONS).lower()


def _plain(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return " ".join(text.split())


def _head_text(html: str) -> str:
    return _plain(html)[:220]


def _expand(lemma: str, suffix: str) -> list[str]:
    """把 "~xxx" 展开成全形；从长词尾切到短词尾。"""
    folded = _fold(lemma)
    candidates = []
    for cut in CUTS:
        if cut and not folded.endswith(_fold(cut)):
            continue
        candidates.append(lemma[: len(lemma) - len(cut)] + suffix)
    return candidates


def _join(stem: str, suffix: str) -> str:
    """拼合时去掉重复的首尾字母：reg + gere -> regere。"""
    if stem and suffix and _fold(stem[-1]) == _fold(suffix[0]):
        return stem + suffix[1:]
    return stem + suffix


def _find_tilde_or_form(head: str, lemma: str) -> tuple[str, str] | None:
    tokens = re.split(r"[\s,;]+", head)[:10]
    for token in tokens:
        if token.startswith("~") and len(token) > 1:
            return ("tilde", token[1:])
    for token in tokens[1:]:
        token = token.strip(".,;")
        if not re.fullmatch(r"[A-Za-zāēīōūȳăĕĭŏŭ]+", token):
            continue
        if _fold(token) == _fold(lemma):
            continue
        if any(_fold(token).endswith(ending) for ending, _d in GEN_ENDINGS):
            return ("full", token)
        if re.search(r"(are|ere|ire)$", _fold(token)):
            return ("full", token)
    return None


IRREGULAR_VERBS = {
    "sum": {
        "infinitive": "esse",
        "present": ["sum", "es", "est", "sumus", "estis", "sunt"],
        "imperfect": ["eram", "erās", "erat", "erāmus", "erātis", "erant"],
        "future": ["erō", "eris", "erit", "erimus", "eritis", "erunt"],
        "perfect_stem": "fu",
        "imperative": [],
    },
    "possum": {
        "infinitive": "posse",
        "present": ["possum", "potes", "potest", "possumus", "potestis", "possunt"],
        "imperfect": ["poteram", "poterās", "poterat", "poterāmus", "poterātis", "poterant"],
        "future": ["poterō", "poteris", "poterit", "poterimus", "poteritis", "poterunt"],
        "perfect_stem": "potu",
        "imperative": [],
    },
}


def parse_noun(html: str) -> dict | None:
    head = _head_text(html)
    if not head:
        return None
    lemma = head.split()[0]
    gender = "m"
    if "neut" in head[:70]:
        gender = "n"
    elif re.search(r"\bf\.", head[:70]):
        gender = "f"

    found = _find_tilde_or_form(head, lemma)
    if not found:
        return None
    kind, token = found
    genitives = _expand(lemma, token) if kind == "tilde" else [token]
    genitive = None
    for candidate in genitives:
        if any(_fold(candidate).endswith(ending) for ending, _d in GEN_ENDINGS) and len(candidate) > 2:
            genitive = candidate
            break
    if not genitive:
        return None

    folded = _fold(genitive)
    decl = None
    stem = ""
    for ending, number in GEN_ENDINGS:
        if folded.endswith(ending) and len(genitive) > len(ending):
            stem = genitive[: -len(ending)]
            decl = number
            break
    if decl is None or not stem:
        return None

    if decl == 2:
        kind_name = "2n" if gender == "n" else "2m"
    elif decl == 3:
        i_stem = bool(re.search(r"ium\b", head)) or _fold(lemma).endswith("is")
        if gender == "n":
            kind_name = "3in" if i_stem else "3n"
        else:
            kind_name = "3i" if i_stem else "3"
    else:
        kind_name = str(decl)
    return {"lemma": lemma, "stem": stem, "kind": kind_name, "decl": decl, "gender": gender}


def parse_verb(html: str) -> dict | None:
    head = _head_text(html)
    if not head:
        return None
    lemma = head.split()[0]
    irregular = IRREGULAR_VERBS.get(_fold(lemma))
    if irregular:
        return {
            "lemma": lemma,
            "stem": "",
            "conj": 3,
            "infinitive": irregular["infinitive"],
            "perfect_stem": irregular.get("perfect_stem"),
            "supine_stem": None,
            "irregular": irregular,
        }
    found = _find_tilde_or_form(head, lemma)
    if not found:
        return None
    kind, token = found

    candidates: list[str] = []
    if kind == "tilde":
        for cut in CUTS:
            if cut and not _fold(lemma).endswith(_fold(cut)):
                continue
            candidates.append(_join(lemma[: len(lemma) - len(cut)], token))
    else:
        candidates.append(token)

    infinitive = None
    for candidate in candidates:
        folded = _fold(candidate)
        if re.search(r"(are|ere|ire)$", folded) and len(candidate) > 3:
            infinitive = candidate
            break
    if not infinitive:
        return None

    # 完成时词干：词条里 "~āuī" / "~xī" 这类（以 ī 结尾）
    perfect_stem = None
    supine_stem = None
    tokens = re.split(r"[\s,;]+", head)
    for token in tokens:
        word = token.strip(".,;")
        # 不带波浪号的完整形式：fēcī / factum / tulī / lātum
        if not token.startswith("~") and re.fullmatch(r"[A-Za-zāēīōūȳăĕĭŏŭ]+", word):
            if _fold(word) == _fold(lemma):
                continue
            if perfect_stem is None and _fold(word).endswith("i") and len(word) > 2:
                perfect_stem = word[:-1]
                continue
            if supine_stem is None and _fold(word).endswith("um") and len(word) > 3:
                supine_stem = word[:-2]
                continue
        if not token.startswith("~") or len(token) < 2:
            continue
        suffix = token[1:]
        for cut in CUTS:
            if cut and not _fold(lemma).endswith(_fold(cut)):
                continue
            candidate = _join(lemma[: len(lemma) - len(cut)], suffix)
            folded = _fold(candidate)
            if perfect_stem is None and folded.endswith("i") and len(candidate) > 3:
                perfect_stem = candidate[:-1]
            elif supine_stem is None and folded.endswith("um") and len(candidate) > 4:
                supine_stem = candidate[:-2]

    if perfect_stem is None and supine_stem:
        perfect_stem = supine_stem + ("v" if supine_stem.endswith("a") else "u")

    folded_inf = _fold(infinitive)
    if folded_inf.endswith("are"):
        conj = 1
    elif folded_inf.endswith("ere"):
        conj = 2 if infinitive.endswith("ēre") or "ē" in infinitive[:-3] else 3
    else:
        conj = 4
    return {
        "lemma": lemma,
        "stem": infinitive[:-3],
        "conj": conj,
        "infinitive": infinitive,
        "perfect_stem": perfect_stem,
        "supine_stem": supine_stem,
    }


def decline(info: dict) -> dict[str, tuple[str, str]]:
    endings = NOUN_ENDINGS.get(info["kind"]) or NOUN_ENDINGS["3"]
    stem = info["stem"]
    forms = {case: (stem + endings[case][0], stem + endings[case][1]) for case in CASE_KEYS}
    if info["kind"].startswith("3"):
        # 第三变格法主格/呼格单数就是原形本身（rex，不是 rēg）
        forms["nom"] = (info["lemma"], forms["nom"][1])
        forms["voc"] = (info["lemma"], forms["voc"][1])
    return forms


def conjugate_verb(info: dict) -> dict[str, list[str]]:
    irregular = info.get("irregular")
    if irregular:
        perfect_stem = irregular.get("perfect_stem")
        data = {
            "present": irregular["present"],
            "imperfect": irregular["imperfect"],
            "future": irregular["future"],
            "imperative": irregular.get("imperative") or [],
            "infinitive": [irregular["infinitive"]],
            "participle_present": [irregular["infinitive"][:-2] + "ns"],
        }
        if perfect_stem:
            data["perfect"] = [perfect_stem + e for e in ("ī", "istī", "it", "imus", "istis", "ērunt")]
            data["pluperfect"] = [perfect_stem + e for e in ("eram", "erās", "erat", "erāmus", "erātis", "erant")]
            data["future_perfect"] = [perfect_stem + e for e in ("erō", "eris", "erit", "erimus", "eritis", "erint")]
            data["infinitive_perfect"] = [perfect_stem + "isse"]
        return data

    stem = info["stem"]
    conj = info["conj"]
    if conj == 1:
        present = [stem + e for e in ("o", "as", "at", "amus", "atis", "ant")]
        imperfect = [stem + e for e in ("abam", "abas", "abat", "abamus", "abatis", "abant")]
        future = [stem + e for e in ("abo", "abis", "abit", "abimus", "abitis", "abunt")]
        imperative = [stem + "a", stem + "ate"]
    elif conj == 2:
        present = [stem + e for e in ("eo", "es", "et", "emus", "etis", "ent")]
        imperfect = [stem + e for e in ("ebam", "ebas", "ebat", "ebamus", "ebatis", "ebant")]
        future = [stem + e for e in ("ebo", "ebis", "ebit", "ebimus", "ebitis", "ebunt")]
        imperative = [stem + "e", stem + "ete"]
    elif conj == 3:
        present = [stem + e for e in ("o", "is", "it", "imus", "itis", "unt")]
        imperfect = [stem + e for e in ("ebam", "ebas", "ebat", "ebamus", "ebatis", "ebant")]
        future = [stem + e for e in ("am", "es", "et", "emus", "etis", "ent")]
        imperative = [stem + "e", stem + "ite"]
    else:
        present = [stem + e for e in ("io", "is", "it", "imus", "itis", "iunt")]
        imperfect = [stem + e for e in ("iebam", "iebas", "iebat", "iebamus", "iebatis", "iebant")]
        future = [stem + e for e in ("iam", "ies", "iet", "iemus", "ietis", "ient")]
        imperative = [stem + "i", stem + "ite"]
    data = {
        "present": present,
        "imperfect": imperfect,
        "future": future,
        "imperative": imperative,
        "infinitive": [info["infinitive"]],
    }
    perfect_stem = info.get("perfect_stem")
    supine_stem = info.get("supine_stem")
    if perfect_stem:
        data["perfect"] = [perfect_stem + e for e in ("ī", "istī", "it", "imus", "istis", "ērunt")]
        data["pluperfect"] = [perfect_stem + e for e in ("eram", "erās", "erat", "erāmus", "erātis", "erant")]
        data["future_perfect"] = [perfect_stem + e for e in ("erō", "eris", "erit", "erimus", "eritis", "erint")]
        data["infinitive_perfect"] = [perfect_stem + "isse"]
        data["participle_perfect"] = [supine_stem + "us" if supine_stem else perfect_stem + "us"]
    data["participle_present"] = [stem + ("āns" if conj == 1 else "ēns")]
    if supine_stem:
        data["participle_future"] = [supine_stem + "ūrus"]
    return data


def noun_table(info: dict) -> list[dict]:
    forms = decline(info)
    rows = []
    for index, case in enumerate(CASE_KEYS):
        sing, plur = forms[case]
        rows.append({"case": CASES[index], "sing": sing, "plur": plur})
    labels = {1: "第一变格法", 2: "第二变格法", 3: "第三变格法", 4: "第四变格法", 5: "第五变格法"}
    label = labels.get(info["decl"], "变格法")
    if info["gender"] == "n":
        label += "（中性）"
    return [{"key": "decl", "zh": label, "fr": "Declinatio", "rows": rows, "cases": True}]


def verb_table(info: dict) -> list[dict]:
    data = conjugate_verb(info)
    groups = [
        ("present", "现在时", "Praesens"),
        ("imperfect", "未完成过去时", "Imperfectum"),
        ("future", "将来时", "Futurum"),
        ("perfect", "完成时", "Perfectum"),
        ("pluperfect", "过去完成时", "Plusquamperfectum"),
        ("future_perfect", "将来完成时", "Futurum Exactum"),
        ("imperative", "命令式", "Imperativus"),
        ("infinitive", "不定式", "Infinitivus"),
    ]
    out = []
    for key, zh, fr in groups:
        forms = data.get(key) or []
        if key == "imperative":
            rows = [("命令式" if i == 0 else "命令式复数", form) for i, form in enumerate(forms)]
        elif key.startswith("infinitive"):
            rows = [("不定式", forms[0])] if forms else []
        else:
            rows = [(VERB_PERSONS[i], forms[i]) for i in range(min(6, len(forms)))]
        out.append({"key": key, "zh": zh, "fr": fr, "rows": rows})
    participles = [
        ("participle_present", "现在分词", "Participium Praesens"),
        ("participle_perfect", "完成分词", "Participium Perfectum"),
        ("participle_future", "将来分词", "Participium Futurum"),
        ("infinitive_perfect", "不定式（完成）", "Infinitivus Perfectus"),
    ]
    rows = []
    for key, zh, fr in participles:
        values = data.get(key) or []
        for value in values:
            rows.append((zh, value))
    if rows:
        out.append({"key": "participles", "zh": "分词", "fr": "Participia", "rows": rows})
    return out


def table(lemma: str, lookup) -> list[dict]:
    """给原形生成变格/变位表。"""
    raw = lookup(lemma)
    if not raw:
        return []
    html = raw[1] if isinstance(raw, tuple) else raw
    noun = parse_noun(html)
    if noun:
        return noun_table(noun)
    verb = parse_verb(html)
    if verb:
        return verb_table(verb)
    return []


def analyse(word: str, lookup, keys=None) -> tuple[str, str, list[dict]] | None:
    """反查名词变格 / 动词变位形式。"""
    target = (word or "").strip()
    if len(target) < 2:
        return None
    folded_target = _fold(target)

    raw = lookup(target)
    if raw:
        html = raw[1] if isinstance(raw, tuple) else raw
        noun = parse_noun(html)
        if noun:
            return target, "主格单数", noun_table(noun)
        verb = parse_verb(html)
        if verb:
            return target, "现在时，第一人称单数", verb_table(verb)

    # 不定式：amare -> amo
    for inf_ending, stem_kind in (("are", 1), ("ere", 3), ("ire", 4)):
        if folded_target.endswith(inf_ending) and len(target) > len(inf_ending) + 1:
            base = target[: len(target) - len(inf_ending)]
            for suffix in ("o", "or", "io", "eo"):
                lemma = base + suffix
                raw = lookup(lemma)
                if not raw:
                    continue
                html = raw[1] if isinstance(raw, tuple) else raw
                info = parse_verb(html)
                if info and _fold(info["infinitive"]) == folded_target:
                    return lemma, "不定式", verb_table(info)

    # 动词：按人称词尾反推（现在时）
    present_endings = {
        1: ("o", "as", "at", "amus", "atis", "ant"),
        2: ("eo", "es", "et", "emus", "etis", "ent"),
        3: ("o", "is", "it", "imus", "itis", "unt"),
        4: ("io", "is", "it", "imus", "itis", "iunt"),
    }
    for conj, endings in present_endings.items():
        for index, ending in enumerate(endings):
            if not folded_target.endswith(_fold(ending)):
                continue
            base = target[: len(target) - len(ending)]
            if not base:
                continue
            for suffix in ("o", "or", "io", "eo"):
                lemma = base + suffix
                raw = lookup(lemma)
                if not raw:
                    continue
                html = raw[1] if isinstance(raw, tuple) else raw
                info = parse_verb(html)
                if not info:
                    continue
                forms = conjugate_verb(info)
                if index < len(forms["present"]) and _fold(forms["present"][index]) == folded_target:
                    return lemma, f"现在时，{VERB_PERSONS[index]}", verb_table(info)

    # 名词：按格尾反推
    for kind, endings in NOUN_ENDINGS.items():
        for case in CASE_KEYS:
            for number, index in (("单数", 0), ("复数", 1)):
                ending = _fold(endings[case][index])
                if not ending or not folded_target.endswith(ending):
                    continue
                base = target[: len(target) - len(ending)]
                suffixes = ["", "a", "us", "um", "er", "is", "es", "x", "or", "o", "en", "ur"]
                lemmas = [base + suffix for suffix in suffixes]
                if base and base[-1].lower() in "gc":
                    lemmas.append(base[:-1] + "x")
                if base and base[-1].lower() in "dt":
                    lemmas.append(base[:-1] + "s")
                if base.endswith("or"):
                    lemmas.append(base[:-2] + "us")
                if base.endswith("in"):
                    lemmas.append(base[:-2] + "en")
                for lemma in lemmas:
                    if not lemma or _fold(lemma) == folded_target:
                        continue
                    raw = lookup(lemma)
                    if not raw:
                        continue
                    html = raw[1] if isinstance(raw, tuple) else raw
                    info = parse_noun(html)
                    if not info:
                        continue
                    forms = decline(info)
                    if forms.get(case) and any(
                        _fold(form) == folded_target for form in forms[case]
                    ):
                        return lemma, CASES[CASE_KEYS.index(case)] + number, noun_table(info)

    # 完成时反查：amavit -> amo（靠词干前缀在词典里找候选原形）
    perfect_endings = ("istī", "imus", "istis", "ērunt", "eram", "erās", "erat",
                       "erāmus", "erātis", "erant", "erō", "eris", "erit",
                       "erimus", "eritis", "erint", "it", "ī")
    if keys is not None:
        for ending in perfect_endings:
            if not folded_target.endswith(_fold(ending)):
                continue
            base = target[: len(target) - len(_fold(ending))]
            for cut in ("āv", "ēv", "īv", "v", "u", "x", "s", "i"):
                if not _fold(base).endswith(_fold(cut)):
                    continue
                prefix = base[: len(base) - len(cut)]
                if len(prefix) < 2:
                    continue
                direct = [prefix + suffix for suffix in ("o", "io", "eo", "or", "ō")]
                if _fold(prefix).endswith("x") or _fold(base).endswith("x"):
                    direct += [base[:-1] + "go", base[:-1] + "co"]
                if _fold(base).endswith("c"):
                    direct += [base[:-1] + "cio", base[:-1] + "co"]
                try:
                    candidates = list(keys(prefix, 120)) or []
                except Exception:
                    candidates = []
                candidates = direct + [c for c in candidates if c not in direct]
                for lemma in candidates:
                    if _fold(lemma) == folded_target:
                        continue
                    raw = lookup(lemma)
                    if not raw:
                        continue
                    html = raw[1] if isinstance(raw, tuple) else raw
                    info = parse_verb(html)
                    if not info:
                        continue
                    data = conjugate_verb(info)
                    for key in ("perfect", "pluperfect", "future_perfect"):
                        for index, form in enumerate(data.get(key) or []):
                            if _fold(form) == folded_target:
                                label = {"perfect": "完成时", "pluperfect": "过去完成时", "future_perfect": "将来完成时"}[key]
                                return lemma, f"{label}，{VERB_PERSONS[index]}", verb_table(info)
    return None
