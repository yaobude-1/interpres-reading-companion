"""单实例锁。

端口占用检查在 Windows 上靠不住：http.server 默认带 SO_REUSEADDR，
多个进程可以同时 bind 同一个端口。这里改用内核命名互斥体，
进程一退出（哪怕崩溃）系统就会自动释放，不会残留。
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

ERROR_ALREADY_EXISTS = 183

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
_kernel32.CreateMutexW.restype = wintypes.HANDLE
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.CloseHandle.restype = wintypes.BOOL


class SingleInstance:
    """with SingleInstance() as lock: if not lock.acquired: ..."""

    def __init__(self, name: str = "Local\\ReadingCompanion") -> None:
        import os

        self.name = os.environ.get("RC_INSTANCE_NAME") or name
        self.handle: int | None = None
        self.acquired = False
        # CreateMutexW 成功时不会清零上次错误，先手动清掉，避免把旧错误误判成「已存在」
        ctypes.set_last_error(0)
        handle = _kernel32.CreateMutexW(None, False, name)
        if not handle:
            # 打不开（例如对方以更高权限运行）就不拦，让程序照常启动
            self.acquired = True
            return
        if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
            _kernel32.CloseHandle(handle)
            self.acquired = False
            return
        self.handle = handle
        self.acquired = True

    def release(self) -> None:
        if self.handle:
            _kernel32.CloseHandle(self.handle)
            self.handle = None

    def __enter__(self) -> "SingleInstance":
        return self

    def __exit__(self, *exc) -> None:
        self.release()
