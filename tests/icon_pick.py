"""超立方体 / 博罗米安环 精修稿（仅预览）。"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
OUT = HERE / "shots"
FONT = r"C:\Windows\Fonts\msyhbd.ttc"
ACCENT = (122, 162, 247)
ACCENT_DIM = (86, 118, 190)
LIGHT = (236, 234, 230)
GREY = (150, 156, 172)
DARK = (15, 17, 23)

SS = 4


def canvas(size: int) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGBA", (size * SS, size * SS), (0, 0, 0, 0))
    mask = Image.new("L", (size * SS, size * SS), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, size * SS - 1, size * SS - 1], radius=int(size * SS * 0.23), fill=255
    )
    bg = Image.new("RGBA", (size * SS, size * SS), DARK + (255,))
    img.paste(bg, (0, 0), mask)
    return img, ImageDraw.Draw(img)


def finish(img: Image.Image, size: int) -> Image.Image:
    return img.resize((size, size), Image.LANCZOS)


# ---------------------------------------------------------------- 超立方体
def hypercube(size: int, accent_inner: bool = True, thin: bool = False) -> Image.Image:
    img, d = canvas(size)
    s = size * SS
    w = int(s * (0.030 if thin else 0.042))
    ox0, oy0, ox1, oy1 = 0.11, 0.23, 0.77, 0.89          # 前面
    ix0, iy0, ix1, iy1 = 0.31, 0.09, 0.93, 0.71          # 后面（右上方偏移）
    outer = [(ox0, oy0), (ox1, oy0), (ox1, oy1), (ox0, oy1)]
    inner = [(ix0, iy0), (ix1, iy0), (ix1, iy1), (ix0, iy1)]
    inner_color = ACCENT + (255,) if accent_inner else GREY + (255,)
    for square, color in ((outer, LIGHT + (255,)), (inner, inner_color)):
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
        d.line([a, b], fill=GREY + (255,), width=max(1, int(w * 0.55)))
    return finish(img, size)


# ------------------------------------------------------------ 博罗米安环
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


def borromean(size: int, mixed: bool = False, thin: bool = False) -> Image.Image:
    img, d = canvas(size)
    s = size * SS
    w = int(s * (0.050 if thin else 0.066))
    r = 0.258 * s
    dist = 0.152 * s
    colors = (
        [LIGHT + (255,), ACCENT + (255,), LIGHT + (255,)]
        if mixed
        else [LIGHT + (255,)] * 3
    )
    centers = []
    for i in range(3):
        angle = math.radians(-90 + i * 120)
        centers.append((s * 0.5 + dist * math.cos(angle), s * 0.5 + dist * math.sin(angle)))

    def angle_of(center, point):
        return math.atan2(point[1] - center[1], point[0] - center[0])

    half_gap = math.asin(min(0.9, (w * 0.52) / r))

    for i in range(3):
        center = centers[i]
        gaps = []
        for j in range(3):
            if j == i:
                continue
            pts = _circle_intersections(centers[i], r, centers[j], r)
            for c, pt in enumerate(pts):
                # 每对环的两个交点：一个压在上面，一个从下面穿
                over = (i < j and c == 0) or (i > j and c == 1)
                if not over:
                    gaps.append(angle_of(center, pt))
        # 按缺口排序后画弧
        gaps.sort()
        if not gaps:
            d.arc(
                [center[0] - r, center[1] - r, center[0] + r, center[1] + r],
                start=0, end=360, fill=colors[i], width=w,
            )
            continue
        edges = []
        for g in gaps:
            edges.append((g - half_gap, g + half_gap))
        # 把跨越 ±π 的缺口拆开处理
        spans = []
        for k, (_a, b) in enumerate(edges):
            spans.append((b, edges[(k + 1) % len(edges)][0] + (2 * math.pi if k == len(edges) - 1 else 0)))
        for a, b in spans:
            if b <= a:
                b += 2 * math.pi
            d.arc(
                [center[0] - r, center[1] - r, center[0] + r, center[1] + r],
                start=math.degrees(a), end=math.degrees(b),
                fill=colors[i], width=w,
            )
    return finish(img, size)


VARIANTS = [
    ("超立方体 · 白+蓝", lambda s: hypercube(s, accent_inner=True), (48, 32, 16)),
    ("超立方体 · 全蓝细线", lambda s: hypercube(s, accent_inner=True, thin=True), (48, 32, 16)),
    ("博罗米安 · 单色", lambda s: borromean(s, mixed=False), (48, 32, 16)),
    ("博罗米安 · 蓝环", lambda s: borromean(s, mixed=True), (48, 32, 16)),
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
    for i, (name, fn, _sizes) in enumerate(VARIANTS):
        x = pad + i * (big + pad)
        img = fn(big)
        sheet.paste(img, (x, pad), img)
        d.text((x, pad + big + 6), name, font=font, fill=(40, 44, 52))
        for j, sz in enumerate((48, 32, 16)):
            icon = fn(sz)
            sheet.paste(icon, (x + j * 52, pad + big + 30), icon)
    path = OUT / "icon_pick.png"
    sheet.save(path)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
