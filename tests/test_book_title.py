"""书名识别要过滤浏览器垃圾页；空白对话要清理。"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from rc.capture import book_from_title  # noqa: E402
from rc.store import Store  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


def main() -> int:
    print("\n[书名识别]")
    cases = [
        ("新建标签页 - Google Chrome", ""),
        ("新建标签页 - 个人 - Microsoft Edge", ""),
        ("新标签页", ""),
        ("New Tab - Microsoft Edge", ""),
        ("about:blank", ""),
        ("https://example.com/x - Google Chrome", ""),
        ("设置 - 个人 - Microsoft Edge", ""),
        ("The Art of the Ridiculous Sublime - Google Chrome", "The Art of the Ridiculous Sublime"),
        ("Cicero - De Officiis.pdf - SumatraPDF", "Cicero - De Officiis"),
        ("红楼梦 第三回 - 微信读书", "红楼梦 第三回"),
    ]
    for raw, expected in cases:
        got = book_from_title(raw)
        check(f"{raw[:26]!r} → {expected!r}", got == expected, f"得到 {got!r}")

    print("\n[用户自定义过滤]")
    from rc import capture

    capture.set_user_blocklist(["知乎", "Bilibili"])
    check("自定义词命中", book_from_title("知乎问题 - Google Chrome") == "")
    check("没命中不受影响", book_from_title("The Art of the Sublime - Google Chrome") != "")
    check("大小写不敏感", book_from_title("bilibili 视频 - Microsoft Edge") == "")
    capture.set_user_blocklist([])
    check("清空后放行", book_from_title("知乎问题 - Google Chrome") != "")

    print("\n[空白对话清理]")
    tmp = HERE / ".dbtest"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    db = Store(tmp / "reading.db")
    db.start_conversation("新建标签页", "en", "", "")
    good = db.start_conversation("The Art of the Ridiculous Sublime", "en", "passage", "trans")
    db.add_message(good, "user", "你好") if hasattr(db, "add_message") else None
    before = len(db.conversations())
    removed = db.purge_empty_conversations()
    after = len(db.conversations())
    check("删除空白对话", removed >= 1, f"removed={removed}")
    check("正常对话保留", after == before - removed, f"before={before} after={after}")
    check("书单不含垃圾", all("新建标签页" not in (b.get("book") or "") for b in db.books_with_conversations()))
    shutil.rmtree(tmp, ignore_errors=True)

    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
