"""用 Edge 的 app 模式窗口渲染 HTML，并把它嵌进 Tk 窗口。

Chromium 渲染，原版词典排版、图片、CSS 都能显示；进程退出时自动清理。
"""

from __future__ import annotations

import ctypes
import logging
import os
import subprocess
import tempfile
import time
import uuid
from ctypes import wintypes
from pathlib import Path

import tkinter as tk

log = logging.getLogger("rc")

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

user32 = ctypes.windll.user32
user32.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
user32.SetWindowLongW.restype = wintypes.LONG
user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostMessageW.restype = wintypes.BOOL
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL
user32.MoveWindow.argtypes = [
    wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.BOOL
]

GWL_STYLE = -16
WS_CHILD = 0x40000000
WS_POPUP = 0x80000000
WS_CAPTION = 0x00C00000
WS_THICKFRAME = 0x00040000
WS_SYSMENU = 0x00080000
WS_MINIMIZEBOX = 0x00020000
WS_MAXIMIZEBOX = 0x00010000
SWP_FRAMECHANGED = 0x0020
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
WM_CLOSE = 0x0010


PROFILE_DIR = Path(tempfile.gettempdir()) / "interpres-edge-profile"


def _profile_args() -> list[str]:
    """独立的浏览器配置：避免被用户已开着的 Edge 接管成普通大窗口。"""
    try:
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        return [
            f"--user-data-dir={PROFILE_DIR}",
            "--no-default-browser-check",
            "--no-first-run",
        ]
    except OSError:
        return []


def find_edge() -> str | None:
    for path in EDGE_CANDIDATES:
        if Path(path).exists():
            return path
    return None


def _find_window_by_title(needle: str) -> int:
    found: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length:
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            if needle in buf.value:
                found.append(hwnd)
        return True

    user32.EnumWindows(callback, 0)
    return found[0] if found else 0


class EntryViewer:
    """一个 Toplevel，里面嵌着 Edge 渲染的词典原版条目。"""

    def __init__(self, root: tk.Tk, on_close=None) -> None:
        self.root = root
        self.on_close = on_close
        self.proc: subprocess.Popen | None = None
        self.hwnd = 0
        self._title_h = 0
        self._marker = ""
        self._html_path: Path | None = None
        self._attach_job = None
        self._attach_tries = 0

        self.win: tk.Toplevel | None = None
        self.frame: tk.Frame | None = None
        self._build_window()

    def _build_window(self) -> None:
        self.win = tk.Toplevel(self.root)
        self.win.withdraw()
        self.win.title("原版条目")
        self.win.configure(bg="#12141a")
        self.win.geometry("640x780+120+80")
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.frame = tk.Frame(self.win, bg="#12141a")
        self.frame.pack(fill="both", expand=True)
        self.frame.bind("<Configure>", self._resize)
        self.loading = tk.Label(
            self.frame, text="正在载入原版条目…", bg="#12141a", fg="#8a8f98",
            font=("Microsoft YaHei", 10),
        )
        self.loading.place(relx=0.5, rely=0.5, anchor="center")

    def _ensure_window(self) -> None:
        """窗口被用户关掉后再打开时，重建一个。"""
        if self.win is not None:
            try:
                if self.win.winfo_exists():
                    return
            except tk.TclError:  # 控件可能已销毁，刻意忽略
                pass
        self._build_window()

    # ------------------------------------------------------------------ 显示
    def show(self, html: str, title: str = "词典条目") -> bool:
        self._ensure_window()
        edge = find_edge()
        if not edge:
            self._fallback(html)
            return False
        self.close_process()
        self._marker = f"rc-entry-{uuid.uuid4().hex[:8]}"
        doc = html.replace("<title>", f"<title>{self._marker} ", 1)
        path = Path(tempfile.gettempdir()) / f"{self._marker}.html"
        # newline="" 保留 LF：CSP 的 script-src 哈希按脚本文本计算，
        # 不能让它被 Windows 的 CRLF 转换改变。
        path.write_text(doc, encoding="utf-8", newline="")
        self._html_path = path
        try:
            self.proc = subprocess.Popen(
                [
                    edge,
                    "--app=file:///" + str(path).replace("\\", "/"),
                    "--window-size=620,720",
                    "--window-position=-10000,-10000",
                    "--disable-features=Translate,TranslateUI,msEdgeSidebarV2",
                    "--disable-background-mode",
                    *_profile_args(),
                ]
            )
        except OSError:
            self._fallback(html)
            return False
        self.win.deiconify()
        self.win.lift()
        self.win.update_idletasks()
        self._attach_tries = 0
        self._attach_job = self.root.after(80, self._attach)
        return True

    def _attach(self) -> None:
        self._attach_job = None
        try:
            if self.win is None or not self.win.winfo_exists():
                return
            self.win.update_idletasks()
        except tk.TclError:
            return
        hwnd = _find_window_by_title(self._marker)
        if not hwnd:
            self._attach_tries += 1
            if self._attach_tries >= 30:  # 约 2.4 秒还没起来就放弃
                self._fallback_browser()
                return
            self._attach_job = self.root.after(80, self._attach)
            return
        self.hwnd = hwnd
        if self.frame is None:
            return
        frame_hwnd = int(self.frame.winfo_id())
        user32.SetParent(hwnd, frame_hwnd)
        style = user32.GetWindowLongW(hwnd, GWL_STYLE)
        style &= ~(WS_POPUP | WS_CAPTION | WS_THICKFRAME | WS_SYSMENU | WS_MINIMIZEBOX | WS_MAXIMIZEBOX)
        style |= WS_CHILD
        user32.SetWindowLongW(hwnd, GWL_STYLE, style)
        user32.SetWindowPos(
            hwnd, 0, 0, 0, self.frame.winfo_width(), self.frame.winfo_height(),
            SWP_FRAMECHANGED | SWP_NOZORDER | SWP_NOACTIVATE,
        )
        # Chromium 的标题栏画在客户区里，样式去不掉，只能按固定高度裁掉。
        # 实测：100% 缩放时约 31px，125% 约 38px，150% 约 45px —— 取 32×缩放更贴合。
        try:
            scale = user32.GetDpiForWindow(hwnd) / 96.0
        except Exception:
            scale = 1.0
        self._title_h = max(1, int(round(32 * scale)))
        self._resize()
        if getattr(self, "loading", None) is not None:
            try:
                self.loading.destroy()
            except tk.TclError:  # 控件可能已销毁，刻意忽略
                pass
            self.loading = None

    def _frame_height(self, hwnd: int) -> int:
        rect = wintypes.RECT()
        client = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        user32.GetClientRect(hwnd, ctypes.byref(client))
        delta = (rect.bottom - rect.top) - client.bottom
        return max(0, delta)

    def _resize(self, _event=None) -> None:
        if not self.hwnd or self.frame is None:
            return
        # Chromium 自己画的标题栏没法用样式去掉，往上挪出可视区域即可
        offset = getattr(self, "_title_h", 0)
        user32.MoveWindow(
            self.hwnd, 0, -offset,
            self.frame.winfo_width(), self.frame.winfo_height() + offset, True,
        )

    def _fallback_browser(self) -> None:
        """内嵌失败：把条目丢给默认浏览器，同时窗口里给出说明。"""
        if getattr(self, "loading", None) is not None:
            try:
                self.loading.destroy()
            except tk.TclError:  # 控件可能已销毁，刻意忽略
                pass
            self.loading = None
        path = self._html_path
        self._html_path = None  # 保住临时文件给浏览器用
        self.close_process()
        text = tk.Text(self.frame, bg="#12141a", fg="#e8e6e3", wrap="word", relief="flat")
        text.pack(fill="both", expand=True)
        text.insert(
            "1.0",
            "内嵌渲染失败（Edge 没起来或被系统拦住了）。\n\n已尝试用默认浏览器打开这一页。",
        )
        text.configure(state="disabled")
        if path and path.exists():
            try:
                os.startfile(str(path))
            except OSError as exc:  # noqa: BLE001 - 打不开浏览器时界面已给出提示
                log.debug("打开浏览器失败: %s", exc)

    def _fallback(self, html: str) -> None:
        """没有 Edge：写到临时文件，用默认浏览器打开。"""
        marker = f"rc-entry-{uuid.uuid4().hex[:8]}"
        path = Path(tempfile.gettempdir()) / f"{marker}.html"
        try:
            path.write_text(
                html.replace("<title>", f"<title>{marker} ", 1),
                encoding="utf-8",
                newline="",
            )
        except OSError:
            path = None
        text = tk.Text(self.frame, bg="#12141a", fg="#e8e6e3", wrap="word", relief="flat")
        text.pack(fill="both", expand=True)
        text.insert(
            "1.0",
            "没找到 Microsoft Edge，无法内嵌显示原版排版。\n\n"
            + ("已尝试用默认浏览器打开这一页。" if path else ""),
        )
        text.configure(state="disabled")
        if path is not None:
            try:
                os.startfile(str(path))
            except OSError as exc:  # noqa: BLE001 - 打不开浏览器时界面已给出提示
                log.debug("打开浏览器失败: %s", exc)

    # ------------------------------------------------------------------ 清理
    def close_process(self) -> None:
        if self._attach_job is not None:
            try:
                self.root.after_cancel(self._attach_job)
            except tk.TclError:  # 控件可能已销毁，刻意忽略
                pass
            self._attach_job = None
        # 只关我们嵌进来的那个窗口：给窗口发 WM_CLOSE。
        # 不能 terminate 整个进程 —— Edge 是单实例体系，杀掉的可能就是用户正在用的浏览器。
        if self.hwnd:
            try:
                user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
            except (OSError, AttributeError) as exc:  # noqa: BLE001 - 窗口可能已关闭
                log.debug("发送关闭窗口消息失败: %s", exc)
            # 不在这里阻塞等待：窗口关闭是异步的，等它反而卡住界面
        self.hwnd = 0
        if self.proc is not None:
            # 进程可能属于共享的 Edge；后台等它退出，顺手释放进程句柄（不阻塞界面）
            proc = self.proc
            self.proc = None
            try:
                import threading

                def _reap(p) -> None:
                    try:
                        p.wait(timeout=3)
                    except Exception:
                        # 这是我们自己配置目录下的实例，杀它不会碰到用户的浏览器
                        try:
                            p.terminate()
                            p.wait(timeout=3)
                        except (OSError, subprocess.SubprocessError) as exc:  # noqa: BLE001 - 进程可能已退出
                            log.debug("结束浏览器进程失败: %s", exc)

                threading.Thread(target=_reap, args=(proc,), daemon=True).start()
            except (OSError, RuntimeError) as exc:  # noqa: BLE001 - 线程起不来不影响界面
                log.debug("启动进程回收线程失败: %s", exc)
        if self._html_path is not None:
            # Edge 可能还持有文件句柄，删不掉就留给系统清理，不报错
            for _ in range(3):
                try:
                    self._html_path.unlink()
                    break
                except OSError:
                    time.sleep(0.1)
            self._html_path = None

    def close(self) -> None:
        self.close_process()
        try:
            if self.win is not None:
                self.win.destroy()
        except tk.TclError:  # 控件可能已销毁，刻意忽略
            pass
        self.win = None
        self.frame = None
        if self.on_close:
            self.on_close()


def wait_attached(viewer: EntryViewer, timeout: float = 5.0) -> bool:
    """测试用：等窗口嵌好。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if viewer.hwnd:
            return True
        viewer.root.update()
        time.sleep(0.05)
    return bool(viewer.hwnd)
