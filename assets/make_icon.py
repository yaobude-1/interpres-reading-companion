"""生成Interpres的桌面图标（打开的书 + 对话气泡）。

独立运行即可重新生成 assets/reading-companion.ico：
    python assets/make_icon.py
"""

from __future__ import annotations

import struct
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
OUT = HERE / "reading-companion.ico"

SS = 4  # 超采样倍数
LIGHT = (234, 231, 224)
DARK = (16, 18, 24)
BUBBLE = (122, 162, 247)
BUBBLE_FG = (16, 19, 26)


def render(size: int) -> Image.Image:
    s = size * SS
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))

    # 圆角深色底
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, s - 1, s - 1], radius=int(s * 0.23), fill=255
    )
    bg = Image.new("RGBA", (s, s), DARK + (255,))
    img.paste(bg, (0, 0), mask)
    d = ImageDraw.Draw(img)

    # 打开的书：左右两页
    left = [(0.15 * s, 0.30 * s), (0.47 * s, 0.24 * s), (0.47 * s, 0.71 * s), (0.15 * s, 0.77 * s)]
    right = [(0.53 * s, 0.24 * s), (0.85 * s, 0.30 * s), (0.85 * s, 0.77 * s), (0.53 * s, 0.71 * s)]
    d.polygon(left, fill=LIGHT + (255,))
    d.polygon(right, fill=(206, 204, 200, 255))
    d.line([(0.5 * s, 0.26 * s), (0.5 * s, 0.73 * s)], fill=(92, 98, 112, 255), width=max(1, int(s * 0.012)))

    # 气泡
    bx, by, bw, bh = 0.44 * s, 0.54 * s, 0.46 * s, 0.28 * s
    d.rounded_rectangle(
        [bx, by, bx + bw, by + bh], radius=int(0.075 * s), fill=BUBBLE + (255,)
    )
    d.polygon(
        [(bx + 0.09 * s, by + bh), (bx + 0.24 * s, by + bh), (bx + 0.09 * s, by + bh + 0.095 * s)],
        fill=BUBBLE + (255,),
    )
    for i in range(3):
        cx = bx + 0.12 * s + i * 0.11 * s
        r = max(1.0, 0.021 * s)
        d.ellipse(
            [cx - r, by + bh / 2 - r, cx + r, by + bh / 2 + r], fill=BUBBLE_FG + (255,)
        )

    return img.resize((size, size), Image.LANCZOS)


def _bmp_frame(img: Image.Image) -> bytes:
    """把一张 RGBA 图编码成 ICO 里的 BMP 帧（DIB + AND 掩码）。"""
    w, h = img.size
    pixels = img.load()
    header = struct.pack(
        "<IiiHHIIiiII", 40, w, h * 2, 1, 32, 0, w * h * 4, 0, 0, 0, 0
    )
    xor = bytearray()
    for y in range(h - 1, -1, -1):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            xor += bytes((b, g, r, a))
    row_bytes = ((w + 31) // 32) * 4
    mask = bytearray()
    for y in range(h - 1, -1, -1):
        row = bytearray(row_bytes)
        for x in range(w):
            if pixels[x, y][3] < 128:
                row[x // 8] |= 0x80 >> (x % 8)
        mask += row
    return header + bytes(xor) + bytes(mask)


def build_ico(path: Path, sizes: list[int]) -> None:
    """标准 BMP 帧 ICO：小尺寸不用 PNG，Explorer 兼容性最好。"""
    frames = [(size, _bmp_frame(render(size))) for size in sizes]
    header = struct.pack("<HHH", 0, 1, len(frames))
    offset = 6 + 16 * len(frames)
    entries = b""
    blobs = b""
    for size, data in frames:
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        blobs += data
        offset += len(data)
    path.write_bytes(header + entries + blobs)


def main() -> int:
    sizes = [16, 24, 32, 48, 64, 128, 256]
    build_ico(OUT, sizes)
    # 同时留一张 256 的 PNG 便于预览
    render(256).save(HERE / "reading-companion.png")
    print(OUT, OUT.stat().st_size, "bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
