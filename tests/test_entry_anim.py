"""词条视图的动画 CSS：只做淡入，且尊重系统“减少动态效果”。"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from rc import entryhtml  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


def main() -> int:
    css = entryhtml._BASE_CSS
    print("\n[词条动画 CSS]")
    check("有淡入关键帧", "@keyframes rc-fade-in" in css)
    check("折叠区使用淡入", "animation: rc-fade-in" in css)
    check("尊重 prefers-reduced-motion", "prefers-reduced-motion" in css)
    check("减少动态效果时关动画", "animation: none" in css)
    keyframe = next((line for line in css.splitlines() if "@keyframes rc-fade-in" in line), "")
    check(
        "关键帧只做 opacity",
        "opacity" in keyframe and "transform" not in keyframe,
        keyframe,
    )

    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
