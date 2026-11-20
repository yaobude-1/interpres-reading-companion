"""图标 v2：加光晕、圆角、渐变底，改进观感。"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
OUT = HERE / "shots"
FONT = r"C:\Windows\Fonts\msyhbd.ttc"

SS = 4
LIGHT = (233, 230, 223)
ACCENT = (122, 162, 247)
DIM = (150, 160, 184)
GOLD = (214, 188, 132)


def radial_bg(size: int, inner=(30, 35, 48), outer=(10, 12, 17)) -> Image.Image:
    s = size * SS
    img = Image.new("RGBA", (s, s), outer + (255,))
    px = img.load()
    cx = cy = s / 2
    maxd = math.hypot(cx, cy)
    for y in range(s):
        for x in range(0, s, 2):
            t = min(1.0, math.hypot(x - cx, y - cy) / maxd)
            color = tuple(int(inner[i] + (outer[i] - inner[i]) * (t ** 0.9)) for i in range(3))
            px[x, y] = color + (255,)
            if x + 1 < s:
                px[x + 1, y] = color + (255,)
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.23), fill=255)
    img.putalpha(mask)
    return img


def rounded_rect_path(cx, cy, half, radius, steps=6):
    """圆角正方形的点序列。"""
    pts = []
    corners = [
        (cx + half - radius, cy - half + radius, -90, 0),
        (cx + half - radius, cy + half - radius, 0, 90),
        (cx - half + radius, cy + half - radius, 90, 180),
        (cx - half + radius, cy - half + radius, 180, 270),
    ]
    for x, y, a0, a1 in corners:
        for i in range(steps + 1):
            a = math.radians(a0 + (a1 - a0) * i / steps)
            pts.append((x + radius * math.cos(a), y + radius * math.sin(a)))
    return pts


def stroke(d, pts, width, color, halo=None, closed=False, round_caps=True):
    seq = list(pts) + ([pts[0]] if closed else [])
    if halo:
        hw = width + halo * 2
        d.line(seq, fill=(12, 14, 19, 255), width=int(hw), joint="curve")
        if round_caps:
            r = hw / 2
            for x, y in seq:
                d.ellipse([x - r, y - r, x + r, y + r], fill=(12, 14, 19, 255))
    d.line(seq, fill=color, width=int(width), joint="curve")
    if round_caps:
        r = width / 2
        for x, y in seq:
            d.ellipse([x - r, y - r, x + r, y + r], fill=color)


def hypercube(size: int) -> Image.Image:
    img = radial_bg(size)
    d = ImageDraw.Draw(img)
    s = size * SS
    w_front = s * 0.040
    w_back = s * 0.030
    w_link = s * 0.020
    front_center = (s * 0.44, s * 0.56)
    back_center = (s * 0.60, s * 0.40)
    half = s * 0.24
    back_half = s * 0.185
    radius = s * 0.055

    front = rounded_rect_path(front_center[0], front_center[1], half, radius)
    back = rounded_rect_path(back_center[0], back_center[1], back_half, radius * 0.8)
    # 连接线：四角对应
    links = []
    for i in (0, 6, 12, 18):
        links.append((front[i % len(front)], back[i % len(back)]))

    for a, b in links:
        stroke(d, [a, b], w_link, DIM + (150,))
    stroke(d, back, w_back, ACCENT + (255,), halo=s * 0.010, closed=True)
    stroke(d, front, w_front, LIGHT + (255,), halo=s * 0.012, closed=True)
    return img.resize((size, size), Image.LANCZOS)


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
    return [
        (xm + h * dy / dist, ym - h * dx / dist),
        (xm - h * dy / dist, ym + h * dx / dist),
    ]


def borromean(size: int, width_ratio=0.062, color=LIGHT, accent_ring=False) -> Image.Image:
    img = radial_bg(size)
    d = ImageDraw.Draw(img)
    s = size * SS
    w = s * width_ratio
    r = 0.255 * s
    dist = 0.150 * s
    centers = [
        (s * 0.5 + dist * math.cos(math.radians(-90 + i * 120)),
         s * 0.5 + dist * math.sin(math.radians(-90 + i * 120)))
        for i in range(3)
    ]
    colors = [color + (255,)] * 3
    if accent_ring:
        colors[1] = ACCENT + (255,)

    half_gap = math.asin(min(0.9, (w * 0.55) / r))

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
        if not edges:
            d.arc([center[0] - r, center[1] - r, center[0] + r, center[1] + r], 0, 360,
                  fill=colors[i], width=int(w))
            continue
        spans = []
        for k, (_a, b) in enumerate(edges):
            nxt = edges[(k + 1) % len(edges)][0]
            if k == len(edges) - 1 and nxt < b:
                nxt += 2 * math.pi
            spans.append((b, nxt))
        for a, b in spans:
            d.arc([center[0] - r, center[1] - r, center[0] + r, center[1] + r],
                  math.degrees(a), math.degrees(b), fill=colors[i], width=int(w))
        # 圆头端帽：arc 的宽度是向内画的，所以端帽要放在 r - w/2 上
        rad = w / 2
        cap_r = r - rad
        for (a, b) in spans:
            for ang in (a, b):
                px = center[0] + cap_r * math.cos(ang)
                py = center[1] + cap_r * math.sin(ang)
                d.ellipse([px - rad, py - rad, px + rad, py + rad], fill=colors[i])
    return img.resize((size, size), Image.LANCZOS)


VARIANTS = [
    ("超立方体 · 光晕圆角", lambda s: hypercube(s)),
    ("博罗米安 · 圆头", lambda s: borromean(s)),
    ("博罗米安 · 一环蓝", lambda s: borromean(s, accent_ring=True)),
    ("博罗米安 · 细金线", lambda s: borromean(s, width_ratio=0.032, color=GOLD)),
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
    path = OUT / "icon_v2.png"
    sheet.save(path)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
