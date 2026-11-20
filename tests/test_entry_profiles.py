"""三种词典的原版排版都要保留层次。"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from rc.config import Config  # noqa: E402
from rc.service import Service  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


def main() -> int:
    cfg = Config()
    dicts = cfg.data.get("dictionaries") or {}
    if not dicts:
        print("没配置词典，跳过")
        return 0
    svc = Service(cfg)

    cases = [
        ("en", "seek", ["rc-sec"]),
        ("fr", "fermer", ["ohd-entry", "ohd-sense-no"]),
        ("la", "amo", ["rc-sensenum"]),
    ]
    for lang, word, marks in cases:
        if not (dicts.get(lang) or {}).get("mdx"):
            continue
        html = svc.entry_html(word, lang)
        print(f"\n[{lang}] {word}")
        check("生成成功", bool(html), "空 HTML")
        check("完整文档", html.startswith("<!DOCTYPE html>"), html[:40])
        check("带样式", "<style>" in html)
        check("带折叠脚本", "<script>" in html)
        for mark in marks:
            check(f"含 {mark}", mark in html)

    # 拉丁不应重复词头
    if (dicts.get("la") or {}).get("mdx"):
        html = svc.entry_html("amo", "la")
        check("拉丁只显示一次词头", html.count("amō ~āre") < 4, str(html.count("amō ~āre")))

    # 自定义配色要生效
    if (dicts.get("fr") or {}).get("mdx"):
        print("\n[配色]")
        html = svc.entry_html("fermer", "fr")
        expected = (cfg.data.get("entry_colors") or {}).get("sense") or "#cc2200"
        check("义项号颜色跟随配置", expected in html, f"没看到 {expected}")
        cfg.data["entry_colors"] = {"sense": "#008800", "bg": "#101010"}
        cfg.data["entry_font_size"] = 17
        html2 = svc.entry_html("fermer", "fr")
        check("自定义义项号颜色", "#008800" in html2, "没读到 entry_colors")
        check("自定义背景", "#101010" in html2)
        check("自定义字号", "font-size: 17px" in html2)
        cfg.data.pop("entry_colors", None)
        cfg.data.pop("entry_font_size", None)

    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
