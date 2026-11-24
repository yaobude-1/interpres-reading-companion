"""Dictzip random access and StarDict .dict.dz integration."""

from __future__ import annotations

import binascii
import gzip
import os
import struct
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from rc.dictzip import DictZip  # noqa: E402
from rc.stardict import StarDict  # noqa: E402
from tmputil import local_temp  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


def _dictzip(data: bytes, chunk_length: int = 100) -> bytes:
    chunks = [data[pos : pos + chunk_length] for pos in range(0, len(data), chunk_length)]
    compressed = []
    obj = zlib.compressobj(9, zlib.DEFLATED, -15)
    for index, chunk in enumerate(chunks):
        compressed.append(obj.compress(chunk))
        compressed[-1] += obj.flush(
            zlib.Z_FINISH if index == len(chunks) - 1 else zlib.Z_FULL_FLUSH
        )
    sizes = [len(chunk) for chunk in compressed]
    ra = struct.pack("<HHH", 1, chunk_length, len(chunks)) + b"".join(
        struct.pack("<H", size) for size in sizes
    )
    extra = b"RA" + struct.pack("<H", len(ra)) + ra
    header = b"\x1f\x8b\x08\x04" + b"\x00" * 4 + b"\x00\x03"
    header += struct.pack("<H", len(extra)) + extra
    trailer = struct.pack("<II", binascii.crc32(data) & 0xFFFFFFFF, len(data))
    return header + b"".join(compressed) + trailer


def main() -> int:
    with local_temp("dictzip-") as tmp:
        os.environ["INTERPRES_INDEX_DIR"] = str(Path(tmp) / "indexes")
        base = Path(tmp) / "sample"
        data = (
            b"<div>alpha first article</div>"
            + b"x" * 120
            + b"<div>beta second article</div>"
            + b"y" * 77
        )
        dz_path = Path(str(base) + ".dict.dz")
        dz_path.write_bytes(_dictzip(data))
        dz = DictZip(dz_path)
        check("dictzip chunk length", dz.chunk_length == 100)
        check("dictzip total", dz.total_size >= len(data))
        for offset, size in ((0, 10), (95, 30), (220, 40), (len(data) - 5, 20)):
            got = dz.read(offset, size)
            check(
                f"dictzip read {offset}",
                got == data[offset : offset + size],
                f"{got!r} != {data[offset:offset+size]!r}",
            )
        dz.close()
        with gzip.open(dz_path, "rb") as fh:
            check("dictzip gzip-compatible", fh.read() == data)

        (Path(str(base) + ".ifo")).write_text(
            "StarDict's dict ifo file\nwordcount=2\nbookname=Sample\n",
            encoding="utf-8",
        )
        idx = bytearray()
        for word, offset, size in (("alpha", 0, 31), ("beta", 152, 30)):
            idx += word.encode() + b"\x00" + struct.pack(">II", offset, size)
        (Path(str(base) + ".idx")).write_bytes(idx)
        dictionary = StarDict(base)
        check("dictzip StarDict entry", bool(dictionary.lookup("alpha")))
        check("dictzip StarDict second", bool(dictionary.lookup("beta")))
        check("dictzip StarDict prefix", dictionary.keys_matching("be") == ["beta"])
        dictionary.close()

    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
