"""全局热键监听。

用轮询 GetAsyncKeyState 实现，比装键盘钩子简单，也不会拖慢系统输入。
"""

from __future__ import annotations

import ctypes
import logging
import threading
import time
from collections.abc import Callable

log = logging.getLogger("rc")

user32 = ctypes.windll.user32

MODIFIERS = {
    "ctrl": 0x11,
    "control": 0x11,
    "alt": 0x12,
    "menu": 0x12,
    "shift": 0x10,
    "win": 0x5B,
}

KEYS = {
    "tab": 0x09,
    "enter": 0x0D,
    "return": 0x0D,
    "space": 0x20,
    "esc": 0x1B,
    "escape": 0x1B,
}

for _i in range(1, 25):
    KEYS[f"f{_i}"] = 0x6F + _i


def parse_combo(combo: str) -> tuple[frozenset[int], int]:
    parts = [p.strip().lower() for p in (combo or "").split("+") if p.strip()]
    if not parts:
        raise ValueError("热键不能为空")
    mods: set[int] = set()
    vk: int | None = None
    for part in parts:
        if part in MODIFIERS:
            mods.add(MODIFIERS[part])
        elif part in KEYS:
            vk = KEYS[part]
        elif len(part) == 1 and part.isalnum():
            vk = ord(part.upper())
        else:
            raise ValueError(f"不认识的热键：{part}")
    if vk is None:
        raise ValueError(f"热键需要一个主键：{combo}")
    return frozenset(mods), vk


class HotkeyWatcher(threading.Thread):
    def __init__(self, combos: dict[str, str], callback: Callable[[str], None]) -> None:
        super().__init__(daemon=True, name="hotkey")
        self._bindings: list[tuple[str, frozenset[int], int, bool]] = []
        for name, combo in combos.items():
            mods, vk = parse_combo(combo)
            self._bindings.append((name, mods, vk, False))
        self._callback = callback
        self._stop = threading.Event()

    def run(self) -> None:
        binds = self._bindings
        down = ctypes.c_short
        while not self._stop.is_set():
            for idx, (name, mods, vk, was_down) in enumerate(binds):
                active = bool(user32.GetAsyncKeyState(vk) & 0x8000)
                for mod in mods:
                    active = active and bool(user32.GetAsyncKeyState(mod) & 0x8000)
                if active and not was_down:
                    binds[idx] = (name, mods, vk, True)
                    try:
                        self._callback(name)
                    except Exception:  # noqa: BLE001 - 用户回调，异常不能带崩监听线程
                        log.exception("热键回调失败: %s", name)
                elif not active and was_down:
                    binds[idx] = (name, mods, vk, False)
            time.sleep(0.025)
        _ = down

    def stop(self) -> None:
        self._stop.set()
