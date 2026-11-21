"""从当前前台窗口取选中文字。

做法是最通用的那一种：模拟一次 Ctrl+C，然后读剪贴板。
只要阅读器能复制文字（SumatraPDF、Calibre、Thorium、Edge、Kindle PC 版……）就能用。
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import time

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

CF_UNICODETEXT = 13
KEYEVENTF_KEYUP = 0x0002

VK_CONTROL = 0x11
VK_MENU = 0x12  # Alt
VK_SHIFT = 0x10
VK_C = 0x43

user32.GetClipboardData.restype = wt.HANDLE
user32.GetClipboardData.argtypes = [wt.UINT]
user32.OpenClipboard.argtypes = [wt.HWND]
user32.CloseClipboard.restype = wt.BOOL
user32.EmptyClipboard.restype = wt.BOOL
user32.SetClipboardData.argtypes = [wt.UINT, wt.HANDLE]
user32.SetClipboardData.restype = wt.HANDLE
kernel32.GlobalAlloc.argtypes = [wt.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wt.HGLOBAL
kernel32.GlobalLock.argtypes = [wt.HGLOBAL]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [wt.HGLOBAL]
kernel32.GlobalUnlock.restype = wt.BOOL
kernel32.GlobalFree.argtypes = [wt.HGLOBAL]
kernel32.GlobalFree.restype = wt.HGLOBAL
kernel32.GlobalSize.argtypes = [wt.HGLOBAL]
kernel32.GlobalSize.restype = ctypes.c_size_t
user32.EnumClipboardFormats.argtypes = [wt.UINT]
user32.EnumClipboardFormats.restype = wt.UINT
user32.CountClipboardFormats.restype = wt.INT
user32.GetClipboardSequenceNumber.restype = wt.DWORD


def _open_clipboard(retries: int = 6) -> bool:
    for _ in range(retries):
        if user32.OpenClipboard(None):
            return True
        time.sleep(0.03)
    return False


def snapshot_clipboard() -> list[tuple[int, bytes]]:
    """保存剪贴板的文本/文件/图片（全局内存格式），用于取词后还原。"""
    if not _open_clipboard():
        return []
    result: list[tuple[int, bytes]] = []
    try:
        fmt = 0
        while True:
            fmt = int(user32.EnumClipboardFormats(fmt))
            if not fmt:
                break
            handle = user32.GetClipboardData(fmt)
            if not handle:
                continue
            size = int(kernel32.GlobalSize(handle))
            if size <= 0:
                continue  # CF_BITMAP 等 GDI 句柄不是全局内存格式
            ptr = kernel32.GlobalLock(handle)
            if not ptr:
                continue
            try:
                result.append((fmt, ctypes.string_at(ptr, size)))
            finally:
                kernel32.GlobalUnlock(handle)
        return result
    finally:
        user32.CloseClipboard()


def restore_clipboard(snapshot: list[tuple[int, bytes]]) -> bool:
    if not snapshot or not _open_clipboard():
        return False
    try:
        user32.EmptyClipboard()
        for fmt, data in snapshot:
            handle = kernel32.GlobalAlloc(0x0042, len(data))
            if not handle:
                continue
            ptr = kernel32.GlobalLock(handle)
            if not ptr:
                kernel32.GlobalFree(handle)
                continue
            try:
                ctypes.memmove(ptr, data, len(data))
            finally:
                kernel32.GlobalUnlock(handle)
            if not user32.SetClipboardData(fmt, handle):
                kernel32.GlobalFree(handle)
        return True
    finally:
        user32.CloseClipboard()


def clipboard_sequence() -> int:
    return int(user32.GetClipboardSequenceNumber())


def read_clipboard() -> str | None:
    for _ in range(6):
        if not user32.OpenClipboard(None):
            time.sleep(0.03)
            continue
        try:
            handle = user32.GetClipboardData(CF_UNICODETEXT)
            if not handle:
                return None
            ptr = kernel32.GlobalLock(handle)
            if not ptr:
                return None
            try:
                return ctypes.wstring_at(ptr)
            finally:
                kernel32.GlobalUnlock(handle)
        finally:
            user32.CloseClipboard()
    return None


def write_clipboard(text: str) -> bool:
    """把文本写回剪贴板；失败返回 False，不抛异常。"""
    try:
        raw = (text or "").encode("utf-16-le") + b"\x00\x00"
        handle = kernel32.GlobalAlloc(0x0042, len(raw))  # GMEM_MOVEABLE | GMEM_ZEROINIT
        if not handle:
            return False
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            kernel32.GlobalFree(handle)
            return False
        try:
            ctypes.memmove(ptr, raw, len(raw))
        finally:
            kernel32.GlobalUnlock(handle)
        for _ in range(6):
            if user32.OpenClipboard(None):
                break
            time.sleep(0.03)
        else:
            kernel32.GlobalFree(handle)
            return False
        try:
            user32.EmptyClipboard()
            if user32.SetClipboardData(CF_UNICODETEXT, handle):
                handle = None  # 成功后系统接管内存
                return True
            return False
        finally:
            user32.CloseClipboard()
            if handle:
                kernel32.GlobalFree(handle)
    except Exception:
        return False


def send_copy() -> None:
    """向当前前台窗口发 Ctrl+C。"""
    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    user32.keybd_event(VK_C, 0, 0, 0)
    time.sleep(0.02)
    user32.keybd_event(VK_C, 0, KEYEVENTF_KEYUP, 0)
    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)


def foreground_title() -> str:
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return ""
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value.strip()


def foreground_hwnd() -> int:
    """当前前台窗口句柄；留给 UI Automation 读选区上下文。"""
    return int(user32.GetForegroundWindow() or 0)


def cursor_pos() -> tuple[int, int]:
    point = wt.POINT()
    user32.GetCursorPos(ctypes.byref(point))
    return int(point.x), int(point.y)


def grab_selection(timeout: float = 0.9) -> tuple[str | None, str]:
    """返回 (选中的文字或 None, 窗口标题)。"""
    title = foreground_title()
    before = clipboard_sequence()
    previous = read_clipboard()
    snapshot = snapshot_clipboard()
    send_copy()

    deadline = time.time() + timeout
    text: str | None = None
    copied_seq = 0
    while time.time() < deadline:
        if clipboard_sequence() != before:
            copied_seq = clipboard_sequence()
            text = read_clipboard()
            break
        time.sleep(0.03)

    if not text:
        return None, title
    # 把用户原来的剪贴板换回去；若期间用户自己又复制了别的内容，就不要覆盖
    if copied_seq and clipboard_sequence() == copied_seq:
        if snapshot:
            restore_clipboard(snapshot)
        elif previous is not None:
            write_clipboard(previous)
    # 有些应用复制出来的内容和剪贴板里旧内容一样，seq 仍会变，这里不需要额外处理
    if previous is not None and text == previous and not text.strip():
        return None, title
    return text, title


_BROWSER_SUFFIXES = (
    " - google chrome",
    " - microsoft edge",
    " - mozilla firefox",
    " - firefox",
    " - opera",
    " - opera gx",
    " - chromium",
    " - brave",
    " - vivaldi",
    " - 360安全浏览器",
    " - 360极速浏览器",
    " - qq浏览器",
    " - 搜狗浏览器",
    " - 百度浏览器",
    " - 猎豹浏览器",
    " - 世界之窗浏览器",
    " - edge",
)

_READER_SUFFIXES = (
    " - sumatrapdf",
    " - adobe acrobat reader",
    " - adobe acrobat",
    " - adobe reader",
    " - foxit reader",
    " - foxit pdf reader",
    " - 福昕阅读器",
    " - calibre",
    " - calibre ebook viewer",
    " - thorium reader",
    " - kindle",
    " - 微信读书",
    " - 多看阅读",
    " - koodo reader",
    " - aquile reader",
)

_PROFILE_SUFFIXES = (
    " - 个人",
    " - 访客",
    " - 工作",
    " - 工作区",
    " - 默认",
    " - profile 1",
    " - person 1",
)

# 浏览器内部页面 / 无意义标题：这些永远不算书
_JUNK_TITLES = {
    "新建标签页",
    "新标签页",
    "新分页",
    "新建选项卡",
    "新选项卡",
    "新标签",
    "起始页",
    "主页",
    "首页",
    "about:blank",
    "new tab",
    "new tab page",
    "设置",
    "历史记录",
    "下载",
    "书签",
    "书签管理器",
    "扩展程序",
    "关于",
    "检查更新",
    "更新",
    "开发者工具",
    "任务管理器",
    "登录",
    "注册",
    "个人资料",
    "收藏夹",
    "阅读清单",
    "打印预览",
    "空白页",
}


_user_blocklist: tuple[str, ...] = ()


def set_user_blocklist(items) -> None:
    """用户自定义的书名过滤词（窗口标题包含即忽略）。"""
    global _user_blocklist
    _user_blocklist = tuple(
        str(item).strip().casefold() for item in (items or []) if str(item).strip()
    )


def user_blocklist() -> tuple[str, ...]:
    return _user_blocklist


def _blocked_by_user(title: str) -> bool:
    if not _user_blocklist:
        return False
    lowered = title.casefold()
    return any(word in lowered for word in _user_blocklist)


def _strip_suffix(title: str, suffixes: tuple[str, ...]) -> str:
    changed = True
    while changed:
        changed = False
        lowered = title.lower()
        for suffix in suffixes:
            if lowered.endswith(suffix):
                title = title[: -len(suffix)].strip()
                changed = True
                break
    return title


def book_from_title(title: str, exe: str = "") -> str:
    """从窗口标题猜书名；浏览器内部页面/无意义标题返回空字符串。"""
    original = title or ""
    if not title:
        return ""
    title = title.strip()

    # 去掉 "X - Google Chrome"、"- 个人" 这类尾巴
    title = _strip_suffix(title, _BROWSER_SUFFIXES)
    title = _strip_suffix(title, _PROFILE_SUFFIXES)

    # 阅读器："书名 - SumatraPDF" 形式，去掉尾巴后整段就是书名
    reader_title = _strip_suffix(title, _READER_SUFFIXES)
    if reader_title != title:
        title = reader_title
    else:
        # 其他程序：取分隔符前的主标题
        for sep in (" - ", " — ", " – ", " | "):
            if sep in title:
                title = title.split(sep)[0]
                break
    title = title.strip()

    if title.casefold() in _JUNK_TITLES:
        return ""
    if _blocked_by_user(title) or _blocked_by_user(original):
        return ""

    # 纯网址 / 纯符号也不要
    if title.lower().startswith(("http://", "https://", "file://", "about:", "chrome://", "edge://", "view-source:")):
        return ""

    for ext in (".pdf", ".epub", ".mobi", ".azw3", ".djvu", ".txt", ".fb2", ".cbz"):
        if title.lower().endswith(ext):
            title = title[: -len(ext)]

    title = title.strip(" -—–|\t")
    if len(title) < 2:
        return ""
    if not any(ch.isalnum() for ch in title):
        return ""
    return title
