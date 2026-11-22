"""最小动画工具：缓动端点、禁用时同步落值、取消后不再回调。"""

from __future__ import annotations

import sys
import time
import tkinter as tk
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from rc import anim  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


class FakeWindow:
    """记录 alpha 与 after 队列，用来在无 GUI 的情况下测试 fade。"""

    def __init__(self) -> None:
        self.alpha: float | None = None
        self.jobs: dict[str, tuple] = {}
        self._seq = 0

    def attributes(self, name: str, value=None) -> None:
        if name == "-alpha":
            self.alpha = float(value)

    def after(self, ms: int, func=None, *args):
        self._seq += 1
        key = str(self._seq)
        self.jobs[key] = (func, args)
        return key

    def after_cancel(self, job_id: str) -> None:
        self.jobs.pop(str(job_id), None)

    def winfo_exists(self) -> int:
        return 1


def main() -> int:
    print("\n[测试环境自动关动画]")
    check("tests 目录下自动关闭", anim._under_tests() is True)
    check("初始 enabled 为 False", anim.enabled is False, str(anim.enabled))

    print("\n[缓动]")
    check("ease_out(0)=0", anim.ease_out(0) == 0.0, repr(anim.ease_out(0)))
    check("ease_out(1)=1", abs(anim.ease_out(1) - 1.0) < 1e-9)
    values = [anim.ease_out(i / 10) for i in range(11)]
    check("单调不减", all(b >= a for a, b in zip(values, values[1:], strict=False)))
    check("越界钳制", anim.ease_out(-5) == 0.0 and anim.ease_out(5) == 1.0)

    old = anim.enabled
    try:
        print("\n[禁用时同步落值]")
        anim.enabled = False
        win = FakeWindow()
        done: list[bool] = []
        cancel = anim.fade(win, 0.0, 0.8, 200, on_done=lambda: done.append(True))
        check("直接落到终值", win.alpha == 0.8, str(win.alpha))
        check("完成回调立即执行", done == [True], str(done))
        check("不排定时任务", win.jobs == {}, str(win.jobs))
        cancel()

        print("\n[启用时可取消]")
        anim.enabled = True
        win = FakeWindow()
        cancel = anim.fade(win, 0.0, 1.0, 200)
        check("排了首帧", len(win.jobs) == 1, str(win.jobs))
        job_id = next(iter(win.jobs))
        first = win.jobs[job_id][0]
        cancel()
        check("取消后清空任务", win.jobs == {}, str(win.jobs))
        first()  # 取消后即使首帧被调用，也不应再排任务
        check("取消后不再排任务", win.jobs == {}, str(win.jobs))

        print("\n[真实 Tk 窗口淡入]")
        root = tk.Tk()
        root.withdraw()
        try:
            top = tk.Toplevel(root)
            top.attributes("-alpha", 0.0)
            done: list[bool] = []
            anim.fade(top, 0.0, 0.7, 120, on_done=lambda: done.append(True))
            deadline = time.time() + 3.0
            while time.time() < deadline and not done:
                root.update()
                time.sleep(0.01)
            check(
                "淡入到达终值",
                abs(float(top.attributes("-alpha")) - 0.7) < 0.02,
                str(top.attributes("-alpha")),
            )
            check("完成回调触发", done == [True], str(done))
            top.destroy()
        finally:
            root.destroy()
    finally:
        anim.enabled = old

    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
