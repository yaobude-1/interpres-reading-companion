"""StarDict and DSL sidecar indexes."""

from __future__ import annotations

import struct
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from rc.dsl_index import DslIndex  # noqa: E402
from rc.stardict_index import StarDictIndex  # noqa: E402
from tmputil import local_temp  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


def main() -> int:
    with local_temp("dict-sidecar-") as tmp:
        base = Path(tmp) / "mini"
        (Path(str(base) + ".ifo")).write_text(
            "StarDict's dict ifo file\nwordcount=2\nbookname=Mini\n",
            encoding="utf-8",
        )
        idx = bytearray()
        for word, offset, size in (("alpha", 0, 4), ("Beta", 4, 4)):
            idx += word.encode() + b"\x00" + struct.pack(">II", offset, size)
        (Path(str(base) + ".idx")).write_bytes(idx)
        (Path(str(base) + ".syn")).write_bytes(b"alfa\x00\x00\x00\x00\x00")

        index = StarDictIndex.open_or_build(base)
        check("StarDict index", index is not None)
        assert index is not None
        check("StarDict count", index.entry_count == 2, str(index.entry_count))
        check("StarDict exact", index.find_folded("beta") == (4, 4))
        check("StarDict alias", index.find_folded("alfa") == (0, 4))
        check("StarDict prefix", index.prefix("al", 5) == ["alpha"])
        index.close()
        reopened = StarDictIndex.open_or_build(base)
        check("StarDict reopened", reopened is not None)
        assert reopened is not None
        reopened.close()

        dsl = Path(tmp) / "mini.dsl"
        dsl.write_text(
            '#NAME "Mini DSL"\n'
            "alpha\n"
            "  [trn]first[/trn]\n"
            "\n"
            "beta\n"
            "  [trn]second[/trn]\n",
            encoding="utf-8",
        )
        dsl_index = DslIndex.open_or_build(dsl)
        check("DSL index", dsl_index is not None)
        assert dsl_index is not None
        check("DSL count", dsl_index.entry_count == 2, str(dsl_index.entry_count))
        check("DSL body", dsl_index.find_folded("alpha") == "[trn]first[/trn]")
        check("DSL prefix", dsl_index.prefix("be", 5) == ["beta"])
        check("DSL title", dsl_index.attrs.get("Title") == "Mini DSL", str(dsl_index.attrs))
        dsl_index.close()
        dsl_reopened = DslIndex.open_or_build(dsl)
        check("DSL reopened", dsl_reopened is not None)
        assert dsl_reopened is not None
        dsl_reopened.close()

        time.sleep(0.01)
        dsl.write_text(dsl.read_text(encoding="utf-8") + "\ngamma\n  third\n", encoding="utf-8")
        rebuilt = DslIndex.open_or_build(dsl)
        check("DSL rebuilt", rebuilt is not None)
        assert rebuilt is not None
        check("DSL new entry", rebuilt.find_folded("gamma") == "third")
        rebuilt.close()

    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
