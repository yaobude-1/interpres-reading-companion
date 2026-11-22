"""UIA 真实链路契约测试（不需要 Edge）。

评审 F-4：真实 `powershell.exe -> UIAutomationClient -> TextPattern -> JSON`
这条路径过去在 CI 从未执行（`test_uia_script.py` 在 Python 侧就短路了，
`test_uia_live.py` 是 opt-in）。

这里用 PowerShell 起一个 WPF RichTextBox —— 在 UIA 里是 ControlType=Document，
带 TextPattern 和真实选区 —— 作为被读窗口，验证：

1. 正向：`read_context` 通过真实脚本读出 app / selection / paragraph；
2. 失败契约：timeout / spawn / no-output / bad-json / 非 dict JSON 都返回
   `ok=False` 且 reason 正确。

WPF 不可用时跳过（不影响 CI 其它用例）。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import types
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from rc import uia_context  # noqa: E402

TARGET = HERE / "uia_contract_target.ps1"
TITLE = "Interpres UIA Contract Target"
MARKER = "quick brown fox jumps over the lazy dog"
REQUIRED_KEYS = {"ok", "reason", "app", "selection", "paragraph"}

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _start_target(hwnd_file: Path) -> subprocess.Popen:
    return subprocess.Popen(
        [
            "powershell.exe",
            "-STA",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(TARGET),
            "-HwndFile",
            str(hwnd_file),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def check_real_chain() -> int:
    """返回非 0 表示环境不满足、应跳过。"""
    work = HERE / ".uidata" / f"uia-contract-{os.getpid()}"
    work.mkdir(parents=True, exist_ok=True)
    hwnd_file = work / "hwnd.txt"
    proc = _start_target(hwnd_file)
    try:
        deadline = time.time() + 30
        status = ""
        while time.time() < deadline:
            status = _read(hwnd_file)
            if status:
                break
            time.sleep(0.3)
        if not status:
            check("WPF 测试窗口启动", False, "等待 HWND 文件超时")
            return 0
        if status.startswith("SKIP:"):
            print("  skip  WPF 不可用：" + status[5:].strip()[:120])
            return 0
        if status.startswith("ERROR:"):
            check("WPF 测试窗口启动", False, status[6:].strip()[:200])
            return 0

        hwnd = int(status)
        check("拿到测试窗口 HWND", hwnd != 0, status)

        # UIA 首次连接需要一点时间，允许短轮询。
        info: dict = {}
        deadline = time.time() + 20
        while time.time() < deadline:
            info = uia_context.read_context(hwnd, timeout=20)
            if info.get("ok"):
                break
            time.sleep(0.5)

        check("真实链路返回 dict", isinstance(info, dict), str(info))
        check("契约字段齐全", REQUIRED_KEYS <= set(info), str(sorted(info)))
        check("ok=True", info.get("ok") is True, str(info))
        check("app 是目标窗口标题", info.get("app") == TITLE, repr(info.get("app")))
        check("selection 非空", bool((info.get("selection") or "").strip()), repr(info.get("selection")))
        check("paragraph 含标记文本", MARKER in (info.get("paragraph") or ""), repr(info.get("paragraph"))[:160])
        print("  info " + json.dumps(info, ensure_ascii=False)[:300])
    finally:
        try:
            proc.kill()
        except OSError:
            pass
        shutil.rmtree(work, ignore_errors=True)
    return 0


def _fake(stdout: bytes) -> types.SimpleNamespace:
    return types.SimpleNamespace(stdout=stdout, returncode=1)


def check_failure_paths() -> None:
    print("\n[失败契约]")
    cases = [
        (
            "timeout 返回 reason=timeout",
            {"side_effect": subprocess.TimeoutExpired(["powershell.exe"], 1)},
            lambda r: r == {"ok": False, "reason": "timeout"},
        ),
        (
            "spawn OSError 返回 reason=spawn:…",
            {"side_effect": OSError("boom")},
            lambda r: r.get("ok") is False and str(r.get("reason", "")).startswith("spawn:"),
        ),
        (
            "无输出返回 reason=no-output",
            {"return_value": _fake(b"  \n")},
            lambda r: r.get("ok") is False and r.get("reason") == "no-output",
        ),
        (
            "坏 JSON 返回 reason=bad-json",
            {"return_value": _fake(b"not json\n")},
            lambda r: r.get("ok") is False and r.get("reason") == "bad-json",
        ),
        (
            "非 dict JSON 返回 reason=bad-json",
            {"return_value": _fake(b"[1, 2]\n")},
            lambda r: r.get("ok") is False and r.get("reason") == "bad-json",
        ),
    ]
    for name, patcher, ok in cases:
        with mock.patch.object(uia_context.subprocess, "run", **patcher):
            result = uia_context.read_context(1234, timeout=1)
        check(name, ok(result), str(result))


def main() -> int:
    if os.name != "nt":
        print("skip: not Windows")
        return 0
    if not TARGET.exists():
        check("WPF 测试脚本存在", False, str(TARGET))
        return 1

    print("\n[真实链路]")
    check_real_chain()
    check_failure_paths()

    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
