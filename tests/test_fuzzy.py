"""模糊搜索：重音归一、前缀、拼写纠错、释义预览。"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from rc.config import Config  # noqa: E402
from rc.fuzzy import FuzzyIndex, normalize  # noqa: E402
from rc.gloss import quick_gloss  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


def main() -> int:
    print("\n[归一化]")
    check("去重音", normalize("têt") == "tet", normalize("têt"))
    check("大小写", normalize("Test") == "test")
    check("全大写重音", normalize("TESTÉ") == "teste", normalize("TESTÉ"))
    check("多空格", normalize("  le   test ") == "le test")

    print("\n[纯索引]")
    index = FuzzyIndex(["test", "tester", "têt", "tsetse", "testament", "atest", "test"])
    check("前缀命中", [w for w, _ in index.search("test", 10)][:3] == ["test", "tester", "testament"],
          str([w for w, _ in index.search("test", 10)][:3]))
    check("相邻换位算 1 步", index.search("tset", 10)[0][0] in ("tset", "tsetse") or
          any(w == "test" for w, _ in index.search("tset", 10)), str(index.search("tset", 10)))
    check("重音等价", any(w == "têt" for w, _ in index.search("tet", 5)), str(index.search("tet", 5)))
    check("去重", len([w for w, _ in index.search("test", 10)]) == len(set(w for w, _ in index.search("test", 10))))

    print("\n[真实词典]")
    real = Path.home() / ".reading-companion" / "config.json"
    data = json.loads(real.read_text(encoding="utf-8")) if real.exists() else {}
    dicts = data.get("dictionaries") or {}
    if not (dicts.get("fr") or {}).get("mdx"):
        print("  没配法语词典，跳过")
    else:
        tmp = HERE / "fuzzytmp5"
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True)
        cfg = Config(tmp)
        cfg.data["dictionaries"] = dicts
        cfg.save()
        from rc.service import Service

        svc = Service(cfg)

        rows = svc.fuzzy_lookup("tset", "fr", 10)
        check("纠错找到 test", any(r["word"] == "test" for r in rows), str([r["word"] for r in rows]))
        rows = svc.fuzzy_lookup("test", "fr", 10)
        check("前缀列表有 tester", any(r["word"] == "tester" for r in rows), str([r["word"] for r in rows]))
        check("带词性", any((r.get("pos") or "") for r in rows))
        check("带释义", any((r.get("gloss") or "") for r in rows))
        rows = svc.fuzzy_lookup("tet", "fr", 5)
        check("重音归一找到 têt", any(r["word"] == "têt" for r in rows), str([r["word"] for r in rows]))

        enc = svc.dicts.dictionary("en")
        if enc is not None:
            html = enc._mdx.lookup("test")
            pos, gloss = quick_gloss(html if isinstance(html, str) else "", "en")
            check("英语释义提取", "questions" in gloss or "test" in gloss.lower(), f"{pos} {gloss[:40]}")
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
