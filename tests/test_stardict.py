"""StarDict 兼容：合成一份最小词库，验证索引、HTML 和词头。"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from tests.tmputil import local_temp  # noqa: E402

from rc.dictionary import Dictionary  # noqa: E402
from rc.stardict import StarDict  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


def build(base: Path) -> Path:
    entries = {
        "alpha": b"<b>alpha</b> first letter",
        "lambda": "<b>\u03bb\u03cc\u03b3\u03bf\u03c2</b> word, reason".encode(),
    }
    data = b""
    offsets = []
    for word, payload in entries.items():
        offsets.append((word, len(data), len(payload)))
        data += payload
    idx = b""
    for word, offset, size in offsets:
        idx += word.encode() + b"\x00" + struct.pack(">II", offset, size)
    (base / "mini.dict").write_bytes(data)
    (base / "mini.idx").write_bytes(idx)
    (base / "mini.ifo").write_text(
        "\n".join(
            [
                "StarDict's dict ifo file",
                "version=2.4.2",
                "bookname=Mini StarDict",
                f"wordcount={len(entries)}",
                f"idxfilesize={len(idx)}",
                "sametypesequence=h",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return base / "mini.ifo"


def main() -> int:
    with local_temp(prefix="stardict-") as tmp:
        ifo = build(Path(tmp))
        raw = StarDict(ifo)
        print("\n[StarDict]")
        check("书名", raw.name == "Mini StarDict", raw.name)
        check("词条数", raw.entry_count == 2, str(raw.entry_count))
        check("HTML 原样", "<b>alpha</b>" in (raw.lookup("alpha") or ""), "")
        check("希腊语词条", "λόγος" in (raw.lookup("lambda") or ""), "")
        check("前缀", raw.keys_matching("al") == ["alpha"], str(raw.keys_matching("al")))
        raw.close()

        print("\n[Dictionary 适配]")
        dictionary = Dictionary(ifo)
        entry = dictionary.lookup("alpha")
        check("能解析", entry is not None and bool(entry.senses), repr(entry))
        check("原始 HTML", "<b>alpha</b>" in (dictionary.raw("alpha") or ""), "")
        check("没有 MDD", dictionary.audio("x") is None, "")
        dictionary.close()

    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
