"""回归：保存过的主面板几何信息必须真的被应用。

原来恢复代码放在 MainPanel 创建之前，AttributeError 被 `except Exception: pass`
吞掉，用户的窗口尺寸/位置每次启动都丢。
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from app import restore_panel_geometry  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


class FakeWin:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def geometry(self, value: str) -> None:
        self.calls.append(value)


class FakePanel:
    def __init__(self) -> None:
        self.win = FakeWin()


class FakeConfig:
    def __init__(self, value) -> None:
        self.value = value

    def get(self, key, default=None):
        return self.value


def main() -> int:
    print("\n[面板几何恢复]")

    panel = FakePanel()
    restore_panel_geometry(FakeConfig("900x700+10+20"), panel)
    check("恢复已保存的几何", panel.win.calls == ["900x700+10+20"], str(panel.win.calls))

    empty = FakePanel()
    restore_panel_geometry(FakeConfig(""), empty)
    check("没有保存值时不动窗口", empty.win.calls == [], str(empty.win.calls))

    missing = FakePanel()
    restore_panel_geometry(FakeConfig(None), missing)
    check("None 也不报错", missing.win.calls == [], str(missing.win.calls))

    class BrokenWin:
        def geometry(self, value: str) -> None:
            raise RuntimeError("bad geometry")

    class BrokenPanel:
        win = BrokenWin()

    try:
        restore_panel_geometry(FakeConfig("1x1"), BrokenPanel())
        raised = False
    except Exception:
        raised = True
    check("几何无效时不抛给主流程", not raised)

    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
