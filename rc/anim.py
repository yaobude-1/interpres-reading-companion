"""最小动画工具：基于 Tk ``after`` 的窗口 alpha 过渡。

只做"出现/消失"的淡入淡出，不做布局动画。用户可以在外观设置里关闭；
测试脚本（``tests/`` 下运行）或 ``RC_DISABLE_ANIM=1`` 时自动关闭，
保证现有 GUI 回归的时序确定。
"""

from __future__ import annotations

import os
import sys
import time
import tkinter as tk
from pathlib import Path
from typing import Callable

_OFF_VALUES = {"1", "true", "yes", "on"}


def _env_disabled() -> bool:
    return os.environ.get("RC_DISABLE_ANIM", "").strip().lower() in _OFF_VALUES


def _under_tests() -> bool:
    """``python tests/xxx.py`` 直接运行时返回 True。"""
    try:
        return "tests" in Path(sys.argv[0]).resolve().parts
    except OSError:
        return False


_FORCED_OFF = _env_disabled() or _under_tests()
enabled = not _FORCED_OFF


def configure(flag: bool) -> None:
    """按用户配置启用/禁用；测试或环境变量强制关闭优先。"""
    global enabled
    enabled = bool(flag) and not _FORCED_OFF


def ease_out(t: float) -> float:
    """三次缓出：起步快、收尾稳，适合 100–200ms 的短过渡。"""
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


def set_alpha(window, value: float) -> None:
    try:
        window.attributes("-alpha", max(0.0, min(1.0, value)))
    except tk.TclError:
        pass


def fade(
    window,
    start: float,
    end: float,
    ms: int = 140,
    on_done: Callable[[], None] | None = None,
) -> Callable[[], None]:
    """把 ``window`` 的 alpha 从 ``start`` 过渡到 ``end``，返回取消函数。

    取消之后不会再排下一帧，也不会再触发 ``on_done``。
    """
    cancelled = False
    job: list[str | None] = [None]

    def cancel() -> None:
        nonlocal cancelled
        cancelled = True
        job_id = job[0]
        job[0] = None
        if job_id is not None:
            try:
                window.after_cancel(job_id)
            except tk.TclError:
                pass

    if not enabled or ms <= 0:
        set_alpha(window, end)
        if on_done is not None:
            on_done()
        return cancel

    started = time.monotonic()

    def tick() -> None:
        if cancelled:
            return
        try:
            if not window.winfo_exists():
                return
        except tk.TclError:
            return
        elapsed = (time.monotonic() - started) * 1000.0
        progress = min(1.0, elapsed / ms)
        set_alpha(window, start + (end - start) * ease_out(progress))
        if progress >= 1.0:
            job[0] = None
            if on_done is not None:
                on_done()
            return
        job[0] = window.after(max(1, int(ms / 10)), tick)

    job[0] = window.after(0, tick)
    return cancel


class Fader:
    """管理单个窗口的淡入淡出；新动画开始前自动取消上一段。

    ``restart=True`` 表示窗口刚从隐藏状态出现，从 0 淡入；
    否则从当前 alpha 续上（例如旧浮窗正在淡出时来了新结果）。
    """

    def __init__(self, window, target: float = 1.0) -> None:
        self.window = window
        self.target = target
        self._cancel: Callable[[], None] | None = None

    def cancel(self) -> None:
        if self._cancel is not None:
            self._cancel()
            self._cancel = None

    def alpha(self) -> float:
        try:
            return float(self.window.attributes("-alpha"))
        except tk.TclError:
            return 0.0

    def fade_in(self, restart: bool = False, ms: int = 120) -> None:
        self.cancel()
        if restart:
            set_alpha(self.window, 0.0)
        begin = 0.0 if restart else max(0.0, self.alpha())
        if begin >= self.target - 0.01:
            set_alpha(self.window, self.target)
            return
        self._cancel = fade(self.window, begin, self.target, ms)

    def fade_out(self, ms: int = 100, on_done: Callable[[], None] | None = None) -> None:
        self.cancel()
        self._cancel = fade(self.window, self.alpha(), 0.0, ms, on_done=on_done)
