"""UIA helper: script parses, and failure paths do not crash."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from rc import uia_context  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


def main() -> int:
    print("\n[UIA 脚本]")
    script = ROOT / "rc" / "uia_context.ps1"
    check("脚本存在", script.exists(), str(script))

    shell = shutil.which("powershell") or shutil.which("pwsh")
    if shell is None:
        check("找到 PowerShell", False)
    else:
        # 只解析语法，不执行脚本内容；避免依赖真实窗口
        command = (
            "$errors = $null; "
            f"[System.Management.Automation.Language.Parser]::ParseFile('{script}', "
            "[ref]$null, [ref]$errors) | Out-Null; "
            "if ($errors.Count) { $errors | ForEach-Object { $_.Message }; exit 1 }"
        )
        proc = subprocess.run(
            [shell, "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            text=True,
            timeout=60,
        )
        check(
            "PowerShell 语法解析通过",
            proc.returncode == 0,
            (proc.stdout or "") + (proc.stderr or ""),
        )

    print("\n[失败路径]")
    check("hwnd=0 返回 unsupported", uia_context.read_context(0).get("reason") == "unsupported")
    missing = HERE / ".uidata" / f"missing-{os.getpid()}.ps1"
    missing.parent.mkdir(parents=True, exist_ok=True)
    with mock.patch.object(uia_context, "script_path", return_value=missing):
        result = uia_context.read_context(1234)
    check("脚本缺失返回 script-missing", result.get("reason") == "script-missing")

    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
