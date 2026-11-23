"""词典 @@@LINK 变形提取：扫描、排序、缓存、取消。"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from rc.dict_forms import bulk_candidates, redirect_forms  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


class FakeMDX:
    _keys = [
        ("parlo", 0),
        ("parles", 0),
        ("parlons", 0),
        ("vado", 0),
        ("chat", 0),
    ]

    def _lookup_raw(self, key: str) -> str:
        table = {
            "parlo": "@@@LINK=parler",
            "parles": "@@@LINK=parler",
            "parlons": "@@@LINK=parler",
            "vado": "@@@LINK=andare",
            "chat": "<html>cat</html>",
        }
        return table.get(key, "")


class FakeDict:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._mdx = FakeMDX()


def main() -> int:
    data = HERE / ".dictforms"
    shutil.rmtree(data, ignore_errors=True)
    data.mkdir(parents=True)
    path = data / "fake.mdx"
    path.write_bytes(b"fake")

    print("\n[扫描与排序]")
    dictionary = FakeDict(path)
    forms = redirect_forms(dictionary, "parler", data_dir=data)
    check("返回列表", isinstance(forms, list), str(forms))
    names = [form for form, _ratio in forms]
    check("找到 parlo", "parlo" in names, str(names))
    check("找到 parles", "parles" in names, str(names))
    check("不混入别的原形", "vado" not in names, str(names))
    check("相似度降序", all(forms[i][1] >= forms[i + 1][1] for i in range(len(forms) - 1)), str(forms))
    check("另一原形", [f for f, _r in redirect_forms(dictionary, "andare", data_dir=data)] == ["vado"], "")
    check("没有重定向", redirect_forms(dictionary, "chat", data_dir=data) == [], "")

    print("\n[缓存]")
    cache_dir = data / "cache" / "dict_redirect"
    check("缓存已写入", any(cache_dir.glob("*.json")), str(list(cache_dir.glob("*"))))
    fresh = FakeDict(path)
    cached = redirect_forms(fresh, "parler", data_dir=data)
    check("缓存可复用", [f for f, _r in cached] == names, str(cached))

    print("\n[取消]")
    canceled = FakeDict(path)
    result = redirect_forms(canceled, "parler", cancel=lambda: True)
    check("取消返回 None", result is None, str(result))

    print("\n[批量候选]")
    bulk = bulk_candidates(FakeDict(path), data_dir=data)
    check("批量返回列表", isinstance(bulk, list), str(bulk))
    check(
        "批量包含 parler",
        any(target == "parler" and form == "parlo" for target, form, _r in bulk or []),
        str(bulk),
    )
    check(
        "批量包含 andare",
        any(target == "andare" and form == "vado" for target, form, _r in bulk or []),
        str(bulk),
    )
    filtered = [item for item in bulk or [] if item[2] >= 0.5]
    check("阈值过滤", all(ratio >= 0.5 for _t, _f, ratio in filtered), str(filtered))
    check("批量取消", bulk_candidates(FakeDict(path), data_dir=data / "nocache", cancel=lambda: True) is None, "")

    shutil.rmtree(data, ignore_errors=True)
    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
