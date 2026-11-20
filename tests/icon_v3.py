"""图标 v3：透明图层上画形状 + 高斯柔光，线条更细。"""

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
GOLD = (216, 190, 136)
DIM = (140, 150, 176)


def bg_layer(size: int) -> Image.Image:
    s = size * SS
    img = Image.new("RGBA", (s, s), (10, 12, 17, 255))
    px = img.load()
    cx = cy = s / 2
    maxd = math.hypot(cx, cy)
    inner = (32, 38, 53)
    for y in range(s):
        for x in range(s):
            t = min(1.0, math.hypot(x - cx, y - cy) / maxd)
            px[x, y] = tuple(int(inner[i] + ((10, 12, 17)[i] - inner[i]) * (t ** 0.85)) for i in range(3)) + (255,)
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.23), fill=255)
    img.putalpha(mask)
    return img


def rounded_rect_path(cx, cy, half, radius, steps=8):
    pts = []
    for x, y, a0, a1 in [
        (cx + half - radius, cy - half + radius, -90, 0),
        (cx + half - radius, cy + half - radius, 0, 90),
        (cx - half + radius, cy + half - radius, 90, 180),
        (cx - half + radius, cy - half + radius, 180, 270),
    ]:
        for i in range(steps + 1):
            a = math.radians(a0 + (a1 - a0) * i / steps)
            pts.append((x + radius * math.cos(a), y + radius * math.sin(a)))
    return pts


def stroke(d, pts, width, color, closed=False):
    seq = list(pts) + ([pts[0]] if closed else [])
    d.line(seq, fill=color, width=int(width), joint="curve")
    r = width / 2
    for x, y in seq:
        d.ellipse([x - r, y - r, x + r, y + r], fill=color)


def shape_hypercube(size: int, w_ratio=0.026) -> Image.Image:
    s = size * SS
    layer = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    w = s * w_ratio
    front_c = (s * 0.43, s * 0.57)
    back_c = (s * 0.61, s * 0.39)
    half = s * 0.25
    back_half = s * 0.185
    rad = s * 0.05
    front = rounded_rect_path(*front_c, half, rad)
    back = rounded_rect_path(*back_c, back_half, rad * 0.85)
    for i in (0, 8, 16, 24):
        a, b = front[i % len(front)], back[i % len(back)]
        d.line([a, b], fill=DIM + (170,), width=max(1, int(w * 0.75)))
    stroke(d, back, w, ACCENT + (255,), closed=True)
    stroke(d, front, w, LIGHT + (255,), closed=True)
    return layer


def _circle_intersections(c1, r1, c2, r2):
    (x1, y1), (x2, y2) = c1, c2
    dx, dy = x2 - x1, y2 - y1
    dist = math.hypot(dx, dy)
    if dist > r1 + r2 or dist < abs(r1 - r2) or dist == 0:
        return []
    a = (r1 * r1 - r2 * r2 + dist * dist) / (2 * dist)
    h2 = r1 * r1 - a * a
    if h2 < 0:
        return []
    h = math.sqrt(h2)
    xm, ym = x1 + a * dx / dist, y1 + a * dy / dist
    return [(xm + h * dy / dist, ym - h * dx / dist), (xm - h * dy / dist, ym + h * dx / dist)]


def shape_borromean(size: int, w_ratio=0.045, color=LIGHT) -> Image.Image:
    s = size * SS
    layer = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    w = s * w_ratio
    r = 0.252 * s
    dist = 0.150 * s
    centers = [
        (s * 0.5 + dist * math.cos(math.radians(-90 + i * 120)),
         s * 0.5 + dist * math.sin(math.radians(-90 + i * 120)))
        for i in range(3)
    ]
    half_gap = math.asin(min(0.9, (w * 0.62) / r))
    for i in range(3):
        center = centers[i]
        gaps = []
        for j in range(3):
            if j == i:
                continue
            for c, pt in enumerate(_circle_intersections(centers[i], r, centers[j], r)):
                over = (i < j and c == 0) or (i > j and c == 1)
                if not over:
                    gaps.append(math.atan2(pt[1] - center[1], pt[0] - center[0]))
        gaps.sort()
        edges = [(g - half_gap, g + half_gap) for g in gaps]
        spans = []
        for k, (_a, b) in enumerate(edges):
            nxt = edges[(k + 1) % len(edges)][0]
            if k == len(edges) - 1 and nxt < b:
                nxt += 2 * math.pi
            spans.append((b, nxt))
        box = [center[0] - r, center[1] - r, center[0] + r, center[1] + r]
        for a, b in spans:
            d.arc(box, math.degrees(a), math.degrees(b), fill=color + (255,), width=int(w))
        rad = w / 2
        cap_r = r - rad
        for (a, b) in spans:
            for ang in (a, b):
                px = center[0] + cap_r * math.cos(ang)
                py = center[1] + cap_r * math.sin(ang)
                d.ellipse([px - rad, py - rad, px + rad, py + rad], fill=color + (255,))
    return layer


def compose(size: int, layer: Image.Image, glow: float = 0.55, blur: float = 0.045) -> Image.Image:
    s = size * SS
    base = bg_layer(size)
    if glow > 0:
        blurred = layer.filter(ImageFilter.GaussianBlur(s * blur))
        alpha = blurred.split()[3].point(lambda v: int(v * glow))
        blurred.putalpha(alpha)
        base = Image.alpha_composite(base, blurred)
    base = Image.alpha_composite(base, layer)
    return base.resize((size, size), Image.LANCZOS)


VARIANTS = [
    ("超立方体 · 细线柔光", lambda s: compose(s, shape_hypercube(s))),
    ("超立方体 · 无光晕", lambda s: compose(s, shape_hypercube(s), glow=0.0)),
    ("博罗米安 · 细线柔光", lambda s: compose(s, shape_borromean(s, w_ratio=0.040))),
    ("博罗米安 · 金色", lambda s: compose(s, shape_borromean(s, w_ratio=0.040, color=GOLD))),
]


def main() -> int:
    OUT.mkdir(exist_ok=True)
    big = 200
    pad = 24
    cols = 4
    sheet = Image.new("RGB", (cols * (big + pad) + pad, big + 150), (246, 246, 248))
    d = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype(FONT, 14)
    except Exception:
        font = ImageFont.load_default()
    for i, (name, fn) in enumerate(VARIANTS):
        x = pad + i * (big + pad)
        img = fn(big)
        sheet.paste(img, (x, pad), img)
        d.text((x, pad + big + 6), name, font=font, fill=(40, 44, 52))
        for j, sz in enumerate((48, 32, 16)):
            icon = fn(sz)
            sheet.paste(icon, (x + j * 52, pad + big + 30), icon)
    path = OUT / "icon_v3.png"
    sheet.save(path)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
