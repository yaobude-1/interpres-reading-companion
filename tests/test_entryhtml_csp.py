"""词条 HTML 的 CSP：只放行注入脚本的 SHA-256，不再用 script-src 'unsafe-inline'。

评审 P2：CSP 原本对脚本整体开口子。现在改成对注入脚本做哈希白名单，
这个测试锁住“哈希 = 实际脚本文本”和“不再出现 unsafe-inline”。
"""

from __future__ import annotations

import base64
import hashlib
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
    print("\n[CSP]")
    script = entryhtml._SCRIPT
    expected = base64.b64encode(hashlib.sha256(script.encode("utf-8")).digest()).decode("ascii")

    check("哈希与注入脚本一致", entryhtml._SCRIPT_HASH == expected, entryhtml._SCRIPT_HASH)
    check(
        "script-src 使用 sha256 白名单",
        f"script-src 'sha256-{expected}'" in entryhtml._CSP,
        entryhtml._CSP,
    )
    check(
        "script-src 不再 unsafe-inline",
        "script-src 'unsafe-inline'" not in entryhtml._CSP,
        entryhtml._CSP,
    )
    check("默认来源仍全禁", "default-src 'none'" in entryhtml._CSP, entryhtml._CSP)
    check("连接仍全禁", "connect-src 'none'" in entryhtml._CSP, entryhtml._CSP)

    tag = entryhtml._script_tag()
    check("script 标签内容与哈希源一致", tag == f"<script>{script}</script>", tag[:80])
    inner = tag[len("<script>"):-len("</script>")]
    check(
        "标签内文本可复现哈希",
        base64.b64encode(hashlib.sha256(inner.encode("utf-8")).digest()).decode("ascii")
        == expected,
    )
    check("注入脚本非空", bool(script.strip()))

    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
