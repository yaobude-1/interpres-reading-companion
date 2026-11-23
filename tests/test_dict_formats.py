"""DSL / Dictd / XDXF 兼容：最小合成词库。"""

from __future__ import annotations

import gzip
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from tests.tmputil import local_temp  # noqa: E402

from rc.dictionary import Dictionary  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


def test_dsl(base: Path) -> None:
    text = "\n".join(
        [
            '#NAME\t"Mini DSL"',
            '#CONTENTS_LANGUAGE\t"English"',
            "",
            "alpha",
            "\t[b]alpha[/b] [i]first[/i] [ref]beta[/ref]",
            "",
            "beta",
            "\tsecond",
            "",
        ]
    )
    path = base / "mini.dsl"
    path.write_text(text, encoding="utf-8")
    compressed = base / "mini.dsl.dz"
    with gzip.open(compressed, "wb") as f:
        f.write(text.encode("utf-8"))

    for candidate in (path, compressed):
        d = Dictionary(candidate)
        entry = d.lookup("alpha")
        raw = d.raw("alpha") or ""
        print("\n[DSL]", candidate.name)
        check("书名", d.name == "Mini DSL", d.name)
        check("词条", entry is not None and bool(entry.senses), repr(entry))
        check("HTML 标签", "<b>alpha</b>" in raw and "<i>first</i>" in raw, raw[:200])
        check("ref 链接", "interpres://lookup?word=beta" in raw, raw[:300])
        d.close()


def test_dictd(base: Path) -> None:
    base = base / "dictd"
    base.mkdir()
    payload = b"alpha definition\nbeta definition\n"
    (base / "mini.dict").write_bytes(payload)
    (base / "mini.index").write_text(
        "alpha\t0\t17\nbeta\t17\t15\n", encoding="utf-8"
    )
    d = Dictionary(base / "mini.index")
    entry = d.lookup("alpha")
    raw = d.raw("alpha") or ""
    print("\n[Dictd]")
    check("词条", entry is not None and bool(entry.senses), repr(entry))
    check("原始文本", "alpha definition" in raw, raw[:100])
    d.close()


def test_xdxf(base: Path) -> None:
    path = base / "mini.xdxf"
    path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<xdxf>
  <ar><k>alpha</k><def><b>alpha</b> first <i>letter</i></def></ar>
  <ar><k>beta</k><def>second</def></ar>
</xdxf>
""",
        encoding="utf-8",
    )
    d = Dictionary(path)
    entry = d.lookup("alpha")
    raw = d.raw("alpha") or ""
    print("\n[XDXF]")
    check("词条", entry is not None and bool(entry.senses), repr(entry))
    check("HTML", "<b>alpha</b>" in raw and "<i>letter</i>" in raw, raw[:200])
    d.close()


def main() -> int:
    with local_temp(prefix="formats-") as tmp:
        base = Path(tmp)
        test_dsl(base)
        test_dictd(base)
        test_xdxf(base)
    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
