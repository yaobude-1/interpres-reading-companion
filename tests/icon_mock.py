"""生成桌面图标候选稿（仅预览，不改任何东西）。"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
OUT = HERE / "shots"
FONT = r"C:\Windows\Fonts\msyhbd.ttc"
ACCENT = (122, 162, 247)
DARK = (18, 20, 26)
LIGHT = (232, 230, 227)


def gradient(size: int, top, bottom) -> Image.Image:
    img = Image.new("RGB", (size, size))
    draw = ImageDraw.Draw(img)
    for y in range(size):
        t = y / max(1, size - 1)
        color = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        draw.line([(0, y), (size, y)], fill=color)
    return img


def rounded_mask(size: int, radius_ratio: float = 0.22) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, size - 1, size - 1], radius=int(size * radius_ratio), fill=255
    )
    return mask


def base(size: int, top=DARK, bottom=(10, 11, 15)) -> Image.Image:
    img = gradient(size, top, bottom).convert("RGBA")
    img.putalpha(rounded_mask(size))
    return img


def design_a(size: int) -> Image.Image:
    """打开的书 + 蓝色对话气泡"""
    img = base(size)
    d = ImageDraw.Draw(img)
    s = size
    # 书：两块书页
    left = [(0.16 * s, 0.30 * s), (0.47 * s, 0.24 * s), (0.47 * s, 0.72 * s), (0.16 * s, 0.78 * s)]
    right = [(0.53 * s, 0.24 * s), (0.84 * s, 0.30 * s), (0.84 * s, 0.78 * s), (0.53 * s, 0.72 * s)]
    d.polygon(left, fill=LIGHT)
    d.polygon(right, fill=(210, 208, 205))
    d.line([(0.5 * s, 0.26 * s), (0.5 * s, 0.74 * s)], fill=(90, 96, 110), width=max(1, s // 90))
    # 气泡
    bx, by, bw, bh = 0.50 * s, 0.56 * s, 0.44 * s, 0.30 * s
    d.rounded_rectangle([bx, by, bx + bw, by + bh], radius=int(0.08 * s), fill=ACCENT)
    d.polygon([(bx + 0.10 * s, by + bh), (bx + 0.22 * s, by + bh), (bx + 0.10 * s, by + bh + 0.10 * s)], fill=ACCENT)
    for i in range(3):
        cx = bx + 0.12 * s + i * 0.10 * s
        r = max(1, int(0.022 * s))
        d.ellipse([cx - r, by + bh / 2 - r, cx + r, by + bh / 2 + r], fill=(16, 19, 26))
    return img


def design_b(size: int) -> Image.Image:
    """「译」字标"""
    img = base(size)
    d = ImageDraw.Draw(img)
    s = size
    try:
        font = ImageFont.truetype(FONT, int(s * 0.52))
    except Exception:
        font = ImageFont.load_default()
    text = "译"
    box = d.textbbox((0, 0), text, font=font)
    d.text(
        ((s - (box[2] - box[0])) / 2 - box[0], (s - (box[3] - box[1])) / 2 - box[1] - 0.04 * s),
        text,
        font=font,
        fill=LIGHT,
    )
    d.rounded_rectangle(
        [0.24 * s, 0.74 * s, 0.76 * s, 0.78 * s], radius=int(0.02 * s), fill=ACCENT
    )
    return img


def design_c(size: int) -> Image.Image:
    """亮蓝底 + 白书 + 深色气泡"""
    img = gradient(size, (94, 140, 240), (52, 86, 178)).convert("RGBA")
    img.putalpha(rounded_mask(size))
    d = ImageDraw.Draw(img)
    s = size
    d.rounded_rectangle(
        [0.22 * s, 0.20 * s, 0.78 * s, 0.72 * s], radius=int(0.05 * s), fill=LIGHT
    )
    d.rectangle([0.22 * s, 0.20 * s, 0.27 * s, 0.72 * s], fill=(196, 194, 191))
    for y in (0.32, 0.42, 0.52):
        d.rounded_rectangle(
            [0.32 * s, y * s, 0.68 * s, (y + 0.035) * s], radius=int(0.017 * s), fill=(150, 158, 175)
        )
    bx, by, bw, bh = 0.46 * s, 0.60 * s, 0.40 * s, 0.26 * s
    d.rounded_rectangle([bx, by, bx + bw, by + bh], radius=int(0.07 * s), fill=(20, 24, 34))
    d.polygon([(bx + 0.08 * s, by + bh), (bx + 0.20 * s, by + bh), (bx + 0.08 * s, by + bh + 0.08 * s)], fill=(20, 24, 34))
    for i in range(3):
        cx = bx + 0.11 * s + i * 0.09 * s
        r = max(1, int(0.02 * s))
        d.ellipse([cx - r, by + bh / 2 - r, cx + r, by + bh / 2 + r], fill=ACCENT)
    return img


def design_d(size: int) -> Image.Image:
    """气泡里一个「译」，下方书页翻角"""
    img = base(size)
    d = ImageDraw.Draw(img)
    s = size
    d.rounded_rectangle(
        [0.16 * s, 0.18 * s, 0.84 * s, 0.70 * s], radius=int(0.10 * s), fill=LIGHT
    )
    d.polygon(
        [(0.30 * s, 0.70 * s), (0.44 * s, 0.70 * s), (0.30 * s, 0.84 * s)], fill=LIGHT
    )
    try:
        font = ImageFont.truetype(FONT, int(s * 0.34))
    except Exception:
        font = ImageFont.load_default()
    box = d.textbbox((0, 0), "译", font=font)
    d.text(
        ((s - (box[2] - box[0])) / 2 - box[0], (0.44 * s - (box[3] - box[1]) / 2) - box[1]),
        "译",
        font=font,
        fill=(24, 28, 40),
    )
    return img


DESIGNS = [("A 打开的书+气泡", design_a), ("B 译字标", design_b), ("C 蓝底", design_c), ("D 气泡译", design_d)]


def main() -> int:
    OUT.mkdir(exist_ok=True)
    big = 220
    pad = 26
    label_h = 34
    sheet = Image.new("RGB", (4 * (big + pad) + pad, big + pad * 2 + label_h * 2 + 90), (246, 246, 248))
    d = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype(FONT, 16)
        small = ImageFont.truetype(FONT, 13)
    except Exception:
        font = ImageFont.load_default()
        small = font

    for i, (name, fn) in enumerate(DESIGNS):
        x = pad + i * (big + pad)
        img = fn(big)
        sheet.paste(img, (x, pad), img)
        d.text((x, pad + big + 6), name, font=small, fill=(40, 44, 52))
        # 小尺寸预览
        for j, sz in enumerate((48, 32, 16)):
            icon = fn(sz)
            y = pad + big + label_h + j * 0
            sheet.paste(icon, (x + j * 60, pad + big + label_h + 8), icon)
            d.text((x + j * 60, pad + big + label_h + 8 + 52), f"{sz}", font=small, fill=(120, 124, 132))
    path = OUT / "icon_mock.png"
    sheet.save(path)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
