"""Regression checks for the P1 privacy/security fixes."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from rc.config import Config  # noqa: E402
from rc.entryhtml import _sanitize_untrusted  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


def main() -> int:
    data = HERE / ".p1-regressions"
    shutil.rmtree(data, ignore_errors=True)
    data.mkdir(parents=True)

    print("\n[API Key 加密落盘]")
    cfg = Config(data)
    cfg.set_api_key("sk-p1-secret")
    cfg.save()
    raw = (data / "config.json").read_text(encoding="utf-8")
    stored = json.loads(raw)["api"]["api_key"]
    check("配置文件不出现明文", "sk-p1-secret" not in raw, stored[:16])
    check("重新加载可解密", Config(data).api_key == "sk-p1-secret")

    print("\n[词典 HTML 净化]")
    dirty = (
        '<div><script>alert(1)</script>'
        '<img src="x" onerror="alert(2)">'
        '<a href="javascript:alert(3)">x</a>'
        '<iframe src="https://example.com"></iframe>'
        '<p onclick="evil()">text</p></div>'
    )
    clean = _sanitize_untrusted(dirty)
    check("移除 script", "<script" not in clean.lower(), clean)
    check("移除 on* 事件", "onerror" not in clean.lower() and "onclick" not in clean.lower(), clean)
    check("移除 javascript: 链接", "javascript:" not in clean.lower(), clean)
    check("移除 iframe", "<iframe" not in clean.lower(), clean)

    print("\n[不再外发明文音频地址]")
    service_src = (ROOT / "rc" / "service.py").read_text(encoding="utf-8")
    check("没有 youdao 地址", "dict.youdao.com" not in service_src)
    check("没有 dictvoice", "dictvoice" not in service_src)

    shutil.rmtree(data, ignore_errors=True)
    print("\n" + "=" * 50)
    print(f"失败 {len(fails)} 项")
    for name in fails:
        print("  ✗", name)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
