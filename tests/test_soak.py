"""长跑泄漏测试：反复开关弹窗/原版窗口，观察句柄、内存、控件数。"""

from __future__ import annotations

import ctypes
import json
import shutil
import subprocess
import sys
import tempfile
import time
import tkinter as tk
from ctypes import wintypes
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from rc.config import Config  # noqa: E402

kernel32 = ctypes.windll.kernel32
psapi = ctypes.windll.psapi

kernel32.GetCurrentProcess.restype = wintypes.HANDLE
kernel32.GetProcessHandleCount.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
kernel32.GetProcessHandleCount.restype = wintypes.BOOL
psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
psapi.GetProcessMemoryInfo.restype = wintypes.BOOL


class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
        ("PrivateUsage", ctypes.c_size_t),
    ]


def handles() -> int:
    count = wintypes.DWORD()
    kernel32.GetProcessHandleCount(kernel32.GetCurrentProcess(), ctypes.byref(count))
    return int(count.value)


def private_mb() -> float:
    counters = PROCESS_MEMORY_COUNTERS()
    counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
    psapi.GetProcessMemoryInfo(
        kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb
    )
    return counters.PrivateUsage / 1048576


def widget_count(widget) -> int:
    total = 1
    for child in widget.winfo_children():
        total += widget_count(child)
    return total


def edge_procs() -> int:
    """只数我们自己配置目录下的 Edge 进程，用户自己的浏览器不算。"""
    script = (
        "$p = Get-CimInstance Win32_Process -Filter \"Name='msedge.exe'\"; "
        "($p | Where-Object { $_.CommandLine -like '*interpres-edge-profile*' }).Count"
    )
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
    ).stdout.strip()
    try:
        return int(out or 0)
    except ValueError:
        return 0


def temp_html_count() -> int:
    return len(list(Path(tempfile.gettempdir()).glob("rc-entry-*.html")))


def main() -> int:
    real = Path.home() / ".reading-companion" / "config.json"
    data = json.loads(real.read_text(encoding="utf-8")) if real.exists() else {}
    dicts = data.get("dictionaries") or {}

    tmp = HERE / "soaktmp"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    cfg = Config(tmp)
    cfg.data["dictionaries"] = dicts
    cfg.data["server_port"] = 18840
    cfg.save()
    from rc.service import Service

    svc = Service(cfg)
    entry = svc.lookup_word("seek", "en")
    if not entry and (dicts.get("fr") or {}).get("mdx"):
        entry = svc.lookup_word("fermer", "fr")
    if not entry:
        print("没有可用词条，跳过弹窗测试")
        shutil.rmtree(tmp, ignore_errors=True)
        return 0

    from app import Application

    app = Application(cfg, enable_hotkeys=False)
    app.root.update()
    word = entry.get("query") or entry.get("word") or "seek"

    # 预热：第一次显示会把弹窗控件建起来，从那之后才算基线
    app.popup.show_dictionary(entry, (300, 200), word)
    app.root.update()
    app.popup.hide()
    app.root.update()
    for stale in Path(tempfile.gettempdir()).glob("rc-entry-*.html"):
        try:
            stale.unlink()
        except OSError:
            pass

    base_handles = handles()
    base_mem = private_mb()
    base_widgets = widget_count(app.root)
    print(f"基线：句柄 {base_handles}，私有内存 {base_mem:.1f} MB，控件 {base_widgets}")

    print("\n[弹窗开关 200 次]")
    print(" 次  | 句柄 | 内存MB | 控件")
    for i in range(1, 201):
        app.popup.show_dictionary(entry, (300, 200), word)
        app.root.update()
        app.popup.hide()
        if i % 50 == 0:
            app.root.update()
            print(
                f" {i:3d} | {handles():4d} | {private_mb():6.1f} | {widget_count(app.root)}"
            )

    after_handles = handles()
    after_mem = private_mb()
    after_widgets = widget_count(app.root)
    print(
        f"增量：句柄 +{after_handles - base_handles}，"
        f"内存 +{after_mem - base_mem:.1f} MB，控件 {base_widgets}→{after_widgets}"
    )

    fail = False
    if after_handles - base_handles > 400:
        print("  FAIL 句柄增长过多")
        fail = True
    if after_mem - base_mem > 120:
        print("  FAIL 内存增长过多")
        fail = True
    if after_widgets != base_widgets:
        print("  FAIL 控件数变了（有控件泄漏）")
        fail = True

    print("\n[原版窗口开关 20 次]")
    base_edge = edge_procs()
    base_temp = temp_html_count()
    from rc.htmlview import EntryViewer, wait_attached

    html = svc.entry_html(word, entry.get("lang") or "en")
    viewer = EntryViewer(app.root)
    # 预热一次：第一次启动 Edge 会额外开后台进程/线程，从第二次起算基线
    viewer.show(html, word)
    wait_attached(viewer, 10.0)
    viewer.close()
    app.root.update()
    time.sleep(1.0)
    base_edge = edge_procs()
    base_temp = temp_html_count()
    after_handles = handles()
    for i in range(1, 21):
        viewer.show(html, word)
        wait_attached(viewer, 10.0)
        viewer.close()
        app.root.update()
        time.sleep(0.3)
        print(f" {i:2d} | 我们的 Edge {edge_procs()} | 临时 {temp_html_count()} | 句柄 {handles()}")
    print(
        f"增量：Edge {base_edge}→{edge_procs()}，临时 {base_temp}→{temp_html_count()}，"
        f"句柄 {after_handles}→{handles()}"
    )
    if edge_procs() - base_edge > 2:
        print("  FAIL Edge 进程数增长")
        fail = True
    if temp_html_count() > base_temp:
        print("  FAIL 临时文件增长")
        fail = True

    app.shutdown()
    try:
        app.root.destroy()
    except tk.TclError:
        pass
    shutil.rmtree(tmp, ignore_errors=True)
    print("\n结论：", "有问题" if fail else "无泄漏迹象")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
