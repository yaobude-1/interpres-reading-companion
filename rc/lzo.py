"""Small pure-Python LZO1X decompressor.

MDX 1.2 stores key/record blocks as LZO1X streams.  This is adapted from
``dissect.util.compression.lzo`` (Apache-2.0, Fox-IT / Dissect Team), which is
itself based on the Linux LZO1X decompressor.  Only decompression is needed;
the stream has no length header in MDX blocks, so the expected size is passed
in explicitly.
"""

from __future__ import annotations

import io

_MAX_OUTPUT = 64 * 1024 * 1024


def _read_length(src: io.BytesIO, val: int, mask: int, out_len: int) -> int:
    length = val & mask
    if length:
        return length
    while True:
        byte = src.read(1)
        if not byte:
            raise ValueError("Invalid LZO stream")
        if byte[0]:
            return length + mask + byte[0]
        length += 255
        if length > out_len:
            raise ValueError("Invalid LZO length")


def decompress(data: bytes, expected: int) -> bytes:
    """Decompress a raw LZO1X stream into exactly ``expected`` bytes."""
    if expected < 0 or expected > _MAX_OUTPUT:
        raise ValueError("Invalid LZO output length")
    src = io.BytesIO(data)
    dst = bytearray()

    first = src.read(1)
    if not first:
        raise ValueError("Empty LZO stream")
    val = first[0]

    if val > 17:
        literal = val - 17
        dst += src.read(literal)
        byte = src.read(1)
        if not byte:
            if len(dst) == expected:
                return bytes(dst)
            raise ValueError("Invalid LZO stream")
        val = byte[0]
        if val < 16:
            raise ValueError("Invalid LZO stream")

    state = 0
    while True:
        if val > 15:
            if val > 63:
                length = (val >> 5) - 1
                dist = (src.read(1)[0] << 3) + ((val >> 2) & 7) + 1
            elif val > 31:
                length = _read_length(src, val, 31, expected)
                byte = src.read(1)
                if not byte:
                    raise ValueError("Invalid LZO stream")
                val = byte[0]
                dist = (src.read(1)[0] << 6) + (val >> 2) + 1
            else:
                length = _read_length(src, val, 7, expected)
                dist = (1 << 14) + ((val & 8) << 11)
                byte = src.read(1)
                if not byte:
                    raise ValueError("Invalid LZO stream")
                val = byte[0]
                dist += (src.read(1)[0] << 6) + (val >> 2)
                if dist == (1 << 14):
                    if length != 1:
                        raise ValueError("Invalid LZO stream")
                    break
        elif not state:
            length = _read_length(src, val, 15, expected)
            dst += src.read(length + 3)
            byte = src.read(1)
            if not byte:
                break
            val = byte[0]
            if val > 15:
                continue
            length = 1
            dist = (1 << 11) + (src.read(1)[0] << 2) + (val >> 2) + 1
        else:
            length = 0
            dist = (src.read(1)[0] << 2) + (val >> 2) + 1

        remaining = length + 2
        while remaining > 0:
            if dist <= 0 or dist > len(dst):
                raise ValueError("Invalid LZO distance")
            match_size = min(remaining, dist)
            dst += dst[-dist : (-dist + match_size) or None]
            remaining -= match_size

        state = length = val & 3
        dst += src.read(length)

        if len(dst) >= expected:
            break
        byte = src.read(1)
        if not byte:
            break
        val = byte[0]

    if len(dst) != expected:
        raise ValueError(f"LZO size mismatch: {len(dst)} != {expected}")
    return bytes(dst)
