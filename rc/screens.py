"""按监视器算「可用区域」，并用它夹取悬浮窗位置。

要点：
- 多屏坐标可能是负数（左屏）或大于主屏宽度（右屏），不能只用主屏尺寸夹；
- 任务栏占掉的部分不算可用区域；
- 每个监视器 DPI 可能不同，这里只处理像素坐标，DPI 由 Tk/Win32 自己处理。
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32

MONITOR_DEFAULTTONEAREST = 2


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_ulong),
        ("rcMonitor", _RECT),
        ("rcWork", _RECT),
        ("dwFlags", ctypes.c_ulong),
    ]


try:
    user32.MonitorFromPoint.argtypes = [_POINT, wintypes.DWORD]
    user32.MonitorFromPoint.restype = wintypes.HMONITOR
    user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(_MONITORINFO)]
    user32.GetMonitorInfoW.restype = wintypes.BOOL
except Exception:  # pragma: no cover - 非 Windows 或老系统
    pass


def work_area(x: int, y: int) -> tuple[int, int, int, int]:
    """返回包含点 (x, y) 的监视器的工作区 (left, top, right, bottom)。"""
    try:
        point = _POINT(int(x), int(y))
        monitor = user32.MonitorFromPoint(point, MONITOR_DEFAULTTONEAREST)
        if monitor:
            info = _MONITORINFO()
            info.cbSize = ctypes.sizeof(_MONITORINFO)
            if user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
                rect = info.rcWork
                if rect.right > rect.left and rect.bottom > rect.top:
                    return rect.left, rect.top, rect.right, rect.bottom
    except Exception:
        pass
    # 兜底：主屏
    return 0, 0, int(user32.GetSystemMetrics(0)), int(user32.GetSystemMetrics(1))


def clamp(
    anchor: tuple[int, int],
    size: tuple[int, int],
    offset: tuple[int, int] = (14, 16),
    margin: int = 8,
) -> tuple[int, int]:
    """把「锚点 + 偏移」的窗口夹进锚点所在监视器的工作区。"""
    ax, ay = int(anchor[0]), int(anchor[1])
    width, height = max(1, int(size[0])), max(1, int(size[1]))
    left, top, right, bottom = work_area(ax, ay)
    x = ax + offset[0]
    y = ay + offset[1]
    max_x = max(left + margin, right - width - margin)
    max_y = max(top + margin, bottom - height - margin)
    x = min(max(left + margin, x), max_x)
    y = min(max(top + margin, y), max_y)
    return int(x), int(y)
