"""回归：多词典查询必须给变形词挂上时态表。"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from rc.config import Config  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


def main() -> int:
    real = Path.home() / ".reading-companion" / "config.json"
    if not real.exists():
        print("没有配置，跳过")
        return 0
    data = json.loads(real.read_text(encoding="utf-8"))
    dicts = data.get("dictionaries") or {}
    if not (dicts.get("fr") or {}).get("mdx"):
        print("没配法语词典，跳过")
        return 0

    tmp = HERE / "uxtmp10"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    cfg = Config(tmp)
    cfg.data["dictionaries"] = dicts
    cfg.save()

    from rc.service import Service

    svc = Service(cfg)

    print("\n[多词典查询：变形词要带时态表]")
    for word, label in (("parlait", "未完成过去时"), ("furent", "简单过去时"), ("fait", "现在时")):
        hits = svc.lookup_all(word)
        fr = next((h for h in hits if h["lang"] == "fr"), None)
        morph = ((fr or {}).get("entry") or {}).get("morph") or {}
        check(f"{word} 有 morph", bool(morph), str(morph)[:60])
        check(f"{word} 标注正确", label in (morph.get("label") or ""), morph.get("label"))
        check(f"{word} 带整表", len(morph.get("tables") or []) >= 8, str(len(morph.get("tables") or [])))
        check(f"{word} 排在最前", bool(hits) and hits[0]["lang"] == "fr", str([h["lang"] for h in hits]))

    shutil.rmtree(tmp, ignore_errors=True)
    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
