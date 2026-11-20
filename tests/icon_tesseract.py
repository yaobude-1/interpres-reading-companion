"""超立方体：标准"立方体套立方体 + 四角相连"结构。"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
OUT = HERE / "shots"
FONT = r"C:\Windows\Fonts\msyhbd.ttc"

SS = 4
LIGHT = (237, 232, 223)
ACCENT = (126, 166, 248)
DIM = (150, 160, 186)


def bg_layer(size: int) -> Image.Image:
    s = size * SS
    img = Image.new("RGBA", (s, s), (10, 12, 17, 255))
    px = img.load()
    cx = cy = s / 2
    maxd = math.hypot(cx, cy)
    inner = (30, 36, 50)
    for y in range(s):
        for x in range(s):
            t = min(1.0, math.hypot(x - cx, y - cy) / maxd)
            px[x, y] = tuple(int(inner[i] + (12 - inner[i]) * (t ** 0.85)) + 0 for i in range(3)) if False else (
                tuple(int(inner[i] + ((10, 12, 17)[i] - inner[i]) * (t ** 0.85)) for i in range(3)) + (255,)
            )
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.23), fill=255)
    img.putalpha(mask)
    return img


def square(cx, cy, half, radius):
    r = radius
    pts = []
    for x, y, a0, a1 in [
        (cx + half - r, cy - half + r, -90, 0),
        (cx + half - r, cy + half - r, 0, 90),
        (cx - half + r, cy + half - r, 90, 180),
        (cx - half + r, cy - half + r, 180, 270),
    ]:
        for i in range(7):
            a = math.radians(a0 + (a1 - a0) * i / 6)
            pts.append((x + r * math.cos(a), y + r * math.sin(a)))
    return pts


def corners(cx, cy, half):
    return [
        (cx - half, cy - half),
        (cx + half, cy - half),
        (cx + half, cy + half),
        (cx - half, cy + half),
    ]


def stroke(d, pts, width, color, closed=False):
    seq = list(pts) + ([pts[0]] if closed else [])
    d.line(seq, fill=color, width=int(width), joint="curve")
    r = width / 2
    for x, y in seq:
        d.ellipse([x - r, y - r, x + r, y + r], fill=color)


def tesseract(size: int, back_offset=(0.0, 0.0), back_scale=0.62, radius_ratio=0.035) -> Image.Image:
    s = size * SS
    layer = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    w_front = s * 0.030
    w_back = s * 0.026
    w_link = s * 0.022
    rad = s * radius_ratio

    front_c = (s * 0.5, s * 0.5)
    front_half = s * 0.345
    back_c = (s * (0.5 + back_offset[0]), s * (0.5 + back_offset[1]))
    back_half = front_half * back_scale

    fc = corners(*front_c, front_half)
    bc = corners(*back_c, back_half)

    for a, b in zip(fc, bc):
        d.line([a, b], fill=DIM + (200,), width=int(w_link))
    stroke(d, square(*front_c, front_half, rad), w_front, LIGHT + (255,), closed=True)
    stroke(d, square(*back_c, back_half, rad * back_scale), w_back, ACCENT + (255,), closed=True)
    return layer


def compose(size: int, layer: Image.Image, glow: float = 0.5, blur: float = 0.045) -> Image.Image:
    s = size * SS
    base = bg_layer(size)
    blurred = layer.filter(ImageFilter.GaussianBlur(s * blur))
    alpha = blurred.split()[3].point(lambda v: int(v * glow))
    blurred.putalpha(alpha)
    base = Image.alpha_composite(base, blurred)
    base = Image.alpha_composite(base, layer)
    return base.resize((size, size), Image.LANCZOS)


VARIANTS = [
    ("同心 · 后框 0.62", lambda s: compose(s, tesseract(s, back_offset=(0.0, 0.0), back_scale=0.62))),
    ("透视 · 右上偏移", lambda s: compose(s, tesseract(s, back_offset=(0.075, -0.075), back_scale=0.58))),
    ("同心 · 后框 0.55", lambda s: compose(s, tesseract(s, back_offset=(0.0, 0.0), back_scale=0.55))),
    ("正立方体（等轴）", None),
]


def isometric_cube(size: int) -> Image.Image:
    s = size * SS
    layer = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    w = s * 0.030
    c = (s * 0.5, s * 0.5)
    top = (c[0], c[1] - s * 0.30)
    left = (c[0] - s * 0.30, c[1] - s * 0.13)
    right = (c[0] + s * 0.30, c[1] - s * 0.13)
    mid = (c[0], c[1] + s * 0.045)
    bl = (c[0] - s * 0.30, c[1] + s * 0.17)
    br = (c[0] + s * 0.30, c[1] + s * 0.17)
    bot = (c[0], c[1] + s * 0.34)
    for pts in ([top, left, mid, right, top], [left, bl, bot, br, right], [mid, bot]):
        stroke(d, pts, w, LIGHT + (255,))
    return layer


def main() -> int:
    OUT.mkdir(exist_ok=True)
    big = 200
    pad = 24
    sheet = Image.new("RGB", (4 * (big + pad) + pad, big + 150), (246, 246, 248))
    d = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype(FONT, 14)
    except Exception:
        font = ImageFont.load_default()
    for i, (name, fn) in enumerate(VARIANTS):
        x = pad + i * (big + pad)
        img = fn(big) if fn else compose(big, isometric_cube(big))
        sheet.paste(img, (x, pad), img)
        d.text((x, pad + big + 6), name, font=font, fill=(40, 44, 52))
        for j, sz in enumerate((48, 32, 16)):
            icon = fn(sz) if fn else compose(sz, isometric_cube(sz))
            sheet.paste(icon, (x + j * 52, pad + big + 30), icon)
    path = OUT / "icon_tesseract.png"
    sheet.save(path)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
