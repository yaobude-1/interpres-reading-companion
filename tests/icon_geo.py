"""几何/数学图标候选稿（仅预览）。"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
OUT = HERE / "shots"
FONT = r"C:\Windows\Fonts\msyhbd.ttc"
ACCENT = (122, 162, 247)
LIGHT = (234, 232, 228)
DARK = (16, 18, 24)

SS = 4  # 超采样倍数


def canvas(size: int) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGBA", (size * SS, size * SS), (0, 0, 0, 0))
    mask = Image.new("L", (size * SS, size * SS), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, size * SS - 1, size * SS - 1], radius=int(size * SS * 0.22), fill=255
    )
    bg = Image.new("RGBA", (size * SS, size * SS), DARK + (255,))
    img.paste(bg, (0, 0), mask)
    return img, ImageDraw.Draw(img)


def finish(img: Image.Image, size: int) -> Image.Image:
    return img.resize((size, size), Image.LANCZOS)


def curve(d: ImageDraw.ImageDraw, pts, color, width, close=False):
    seq = list(pts) + ([pts[0]] if close else [])
    d.line(seq, fill=color, width=int(width), joint="curve")
    r = width / 2
    for x, y in seq:
        d.ellipse([x - r, y - r, x + r, y + r], fill=color)


def d_infinity(size: int) -> Image.Image:
    img, d = canvas(size)
    s = size * SS
    pts = []
    for i in range(361):
        t = i * math.pi / 180
        pts.append(
            (
                s * 0.5 + s * 0.30 * math.cos(t) / (1 + math.sin(t) ** 2),
                s * 0.5 + s * 0.30 * math.sin(t) * math.cos(t) / (1 + math.sin(t) ** 2),
            )
        )
    curve(d, pts, LIGHT + (255,), s * 0.075)
    return finish(img, size)


def d_trefoil(size: int) -> Image.Image:
    img, d = canvas(size)
    s = size * SS
    pts = []
    for i in range(361):
        t = i * 2 * math.pi / 360
        pts.append(
            (
                s * 0.5 + s * 0.105 * (math.sin(t) + 2 * math.sin(2 * t)),
                s * 0.5 + s * 0.105 * (math.cos(t) - 2 * math.cos(2 * t)),
            )
        )
    curve(d, pts, ACCENT + (255,), s * 0.062)
    return finish(img, size)


def d_borromean(size: int) -> Image.Image:
    img, d = canvas(size)
    s = size * SS
    r = s * 0.20
    gap = s * 0.145
    for angle in (90, 210, 330):
        cx = s * 0.5 + gap * math.cos(math.radians(angle))
        cy = s * 0.5 - gap * math.sin(math.radians(angle))
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=LIGHT + (255,), width=int(s * 0.055))
    return finish(img, size)


def d_sierpinski(size: int) -> Image.Image:
    img, d = canvas(size)
    s = size * SS
    top = (s * 0.5, s * 0.18)
    left = (s * 0.16, s * 0.82)
    right = (s * 0.84, s * 0.82)

    def tri(a, b, c, depth):
        if depth == 0:
            d.polygon([a, b, c], fill=LIGHT + (255,))
            return
        ab = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        bc = ((b[0] + c[0]) / 2, (b[1] + c[1]) / 2)
        ca = ((c[0] + a[0]) / 2, (c[1] + a[1]) / 2)
        tri(a, ab, ca, depth - 1)
        tri(ab, b, bc, depth - 1)
        tri(ca, bc, c, depth - 1)

    tri(top, left, right, 3)
    return finish(img, size)


def d_penrose(size: int) -> Image.Image:
    img, d = canvas(size)
    s = size * SS
    color = LIGHT + (255,)
    accent = ACCENT + (255,)
    grey = (176, 182, 196, 255)

    def q(*pts):
        return [(x * s, y * s) for x, y in pts]

    d.polygon(q((0.50, 0.12), (0.88, 0.34), (0.88, 0.60), (0.50, 0.38)), fill=color)
    d.polygon(q((0.50, 0.38), (0.88, 0.60), (0.88, 0.88), (0.50, 0.66)), fill=grey)
    d.polygon(q((0.12, 0.34), (0.50, 0.12), (0.50, 0.38), (0.12, 0.60)), fill=accent)
    d.polygon(q((0.12, 0.60), (0.50, 0.38), (0.50, 0.66), (0.12, 0.88)), fill=grey)
    d.polygon(q((0.12, 0.88), (0.50, 0.66), (0.88, 0.88), (0.50, 1.06)), fill=color)
    return finish(img, size)


def d_book_diamond(size: int) -> Image.Image:
    """两个三角形拼成一个打开的"书"，中间一道缝。"""
    img, d = canvas(size)
    s = size * SS
    left = [(0.14 * s, 0.50 * s), (0.50 * s, 0.28 * s), (0.50 * s, 0.72 * s), (0.14 * s, 0.94 * s)]
    right = [(0.50 * s, 0.28 * s), (0.86 * s, 0.50 * s), (0.86 * s, 0.94 * s), (0.50 * s, 0.72 * s)]
    d.polygon(left, fill=LIGHT + (255,))
    d.polygon(right, fill=(186, 192, 206, 255))
    d.line([(0.50 * s, 0.28 * s), (0.50 * s, 0.72 * s)], fill=DARK + (255,), width=int(s * 0.035))
    return finish(img, size)


def d_spiral(size: int) -> Image.Image:
    img, d = canvas(size)
    s = size * SS
    pts = []
    for i in range(361 * 2):
        t = i * 2 * math.pi / 360
        r = s * 0.020 * math.exp(0.22 * t)
        if r > s * 0.40:
            break
        pts.append((s * 0.5 + r * math.cos(t), s * 0.5 + r * math.sin(t)))
    curve(d, pts, ACCENT + (255,), s * 0.055)
    return finish(img, size)


def d_tesseract(size: int) -> Image.Image:
    """超立方体：外框 + 内框 + 四角连线。"""
    img, d = canvas(size)
    s = size * SS
    outer = [(0.14, 0.26), (0.78, 0.26), (0.78, 0.90), (0.14, 0.90)]
    inner = [(0.32, 0.10), (0.96, 0.10), (0.96, 0.74), (0.32, 0.74)]
    w = int(s * 0.045)
    for square, color in ((outer, LIGHT + (255,)), (inner, ACCENT + (255,))):
        pts = [(x * s, y * s) for x, y in square]
        for i in range(4):
            a, b = pts[i], pts[(i + 1) % 4]
            d.line([a, b], fill=color, width=w)
            r = w / 2
            for p in (a, b):
                d.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=color)
    for i in range(4):
        a = (outer[i][0] * s, outer[i][1] * s)
        b = (inner[i][0] * s, inner[i][1] * s)
        d.line([a, b], fill=(150, 156, 172, 255), width=int(s * 0.030))
    return finish(img, size)


def d_pentagram(size: int) -> Image.Image:
    """五角星：黄金分割的经典几何。"""
    img, d = canvas(size)
    s = size * SS
    pts = []
    for i in range(5):
        angle = math.radians(-90 + i * 144)
        pts.append((s * 0.5 + s * 0.34 * math.cos(angle), s * 0.5 + s * 0.34 * math.sin(angle)))
    curve(d, pts, LIGHT + (255,), s * 0.050, close=True)
    return finish(img, size)


DESIGNS = [
    ("∞ 莫比乌斯式", d_infinity),
    ("三叶结", d_trefoil),
    ("博罗米安环", d_borromean),
    ("谢尔宾斯基", d_sierpinski),
    ("彭罗斯三角", d_penrose),
    ("超立方体", d_tesseract),
    ("五角星", d_pentagram),
    ("几何书", d_book_diamond),
]


def main() -> int:
    OUT.mkdir(exist_ok=True)
    big = 190
    pad = 22
    cols = 4
    rows = (len(DESIGNS) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (big + pad) + pad, rows * (big + 96) + pad), (246, 246, 248))
    d = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype(FONT, 15)
    except Exception:
        font = ImageFont.load_default()
    for i, (name, fn) in enumerate(DESIGNS):
        col, row = i % cols, i // cols
        x = pad + col * (big + pad)
        y = pad + row * (big + 96)
        image = fn(big)
        sheet.paste(image, (x, y), image)
        d.text((x, y + big + 6), name, font=font, fill=(40, 44, 52))
        for j, sz in enumerate((32, 16)):
            icon = fn(sz)
            sheet.paste(icon, (x + j * 44, y + big + 30), icon)
    path = OUT / "icon_geo.png"
    sheet.save(path)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
