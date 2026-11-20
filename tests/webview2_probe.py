"""探针：用 ctypes 在 Tk 窗口里嵌入 WebView2，渲染一段 HTML。

只验证可行性，不接入主程序。
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

LOADER = r"C:\Program Files\WSL\wslsettings\WebView2Loader.dll"

ole32 = ctypes.windll.ole32
user32 = ctypes.windll.user32


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]

    @classmethod
    def from_string(cls, text: str) -> "GUID":
        text = text.strip("{}")
        parts = text.split("-")
        data1 = int(parts[0], 16)
        data2 = int(parts[1], 16)
        data3 = int(parts[2], 16)
        rest = parts[3] + parts[4]
        data4 = (ctypes.c_ubyte * 8)(*[int(rest[i : i + 2], 16) for i in range(0, 16, 2)])
        return cls(data1, data2, data3, data4)


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


IID_IUNKNOWN = GUID.from_string("00000000-0000-0000-C000-000000000046")
ENV_IID = GUID.from_string("B96D755E-0319-4E92-A296-23436F46A1FC")
CONTROLLER_IID = GUID.from_string("4D00C0D1-9434-4EB6-8078-8697A560334F")
WEBVIEW_IID = GUID.from_string("76ECEACB-0462-4D94-AC83-423E6A8A9B9F")
ENV_HANDLER_IID = GUID.from_string("AC64C3D0-DAE0-4F5C-8B5A-0E8A6A6D0E7A")
CTRL_HANDLER_IID = GUID.from_string("6C4819F3-C9B7-4260-8127-C9F5BDE7F68C")

HRESULT = ctypes.c_long
LPVOID = ctypes.c_void_p

QI_FN = ctypes.WINFUNCTYPE(HRESULT, LPVOID, ctypes.POINTER(GUID), ctypes.POINTER(LPVOID))
ADDREF_FN = ctypes.WINFUNCTYPE(wintypes.ULONG, LPVOID)
RELEASE_FN = ctypes.WINFUNCTYPE(wintypes.ULONG, LPVOID)


def vtable(methods):
    """把方法函数列表变成 COM vtable 指针。"""
    array = (ctypes.c_void_p * len(methods))()
    for index, fn in enumerate(methods):
        array[index] = ctypes.cast(fn, ctypes.c_void_p).value
    return array


class ComBase:
    """最小的 COM 对象：引用计数 + QueryInterface。"""

    def __init__(self) -> None:
        self.refs = 0
        self._keep = []
        self._qi = QI_FN(self._query_interface)
        self._addref = ADDREF_FN(self._add_ref)
        self._release = RELEASE_FN(self._release)
        self._methods = [self._qi, self._addref, self._release]

    def _query_interface(self, this, riid, out):
        out[0] = this  # 一律返回自己，够用
        self.refs += 1
        return 0

    def _add_ref(self, this):
        self.refs += 1
        return self.refs

    def _release(self, this):
        self.refs -= 1
        return self.refs

    def pointer(self):
        self._array = vtable(self._methods)
        self._vtbl_ptr = ctypes.cast(self._array, LPVOID)
        return ctypes.cast(ctypes.byref(self._vtbl_ptr), LPVOID)


class EnvironmentHandler(ComBase):
    def __init__(self, on_env, hwnd):
        super().__init__()
        self.on_env = on_env
        self.hwnd = hwnd
        self._invoke = ctypes.WINFUNCTYPE(HRESULT, LPVOID, HRESULT, LPVOID)(self._do_invoke)
        self._methods.append(self._invoke)

    def _do_invoke(self, this, hr, env):
        print("env handler hr:", hr, "env:", bool(env))
        if hr == 0 and env:
            self.on_env(env)
        return 0


class ControllerHandler(ComBase):
    def __init__(self, on_controller):
        super().__init__()
        self.on_controller = on_controller
        self._invoke = ctypes.WINFUNCTYPE(HRESULT, LPVOID, HRESULT, LPVOID)(self._do_invoke)
        self._methods.append(self._invoke)

    def _do_invoke(self, this, hr, controller):
        print("controller handler hr:", hr, "ctrl:", bool(controller))
        if hr == 0 and controller:
            self.on_controller(controller)
        return 0


def call(ptr, index, proto, *args):
    """按 vtable 下标调用方法。"""
    if not ptr:
        raise RuntimeError("null pointer")
    vtbl = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))
    func = proto(vtbl.contents[index])
    return func(ptr, *args)


def main() -> int:
    import tkinter as tk

    loader = ctypes.WinDLL(LOADER)
    create_env = loader.CreateCoreWebView2EnvironmentWithOptions
    create_env.restype = HRESULT
    create_env.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, LPVOID, LPVOID]

    ole32.CoInitialize(None)

    root = tk.Tk()
    root.geometry("900x600+100+100")
    frame = tk.Frame(root, bg="black")
    frame.pack(fill="both", expand=True)
    root.update()
    hwnd = int(frame.winfo_id())

    state = {}

    def on_controller(controller):
        state["controller"] = controller
        rect = RECT(0, 0, frame.winfo_width(), frame.winfo_height())
        call(controller, 6, ctypes.WINFUNCTYPE(HRESULT, LPVOID, RECT), rect)  # put_Bounds
        call(controller, 4, ctypes.WINFUNCTYPE(HRESULT, LPVOID, wintypes.BOOL), wintypes.BOOL(1))  # put_IsVisible
        webview = LPVOID()
        call(controller, 25, ctypes.WINFUNCTYPE(HRESULT, LPVOID, ctypes.POINTER(LPVOID)), ctypes.byref(webview))  # get_CoreWebView2
        state["webview"] = webview
        html = "<html><body style='background:#111;color:#eee;font:16px sans-serif'><h1>WebView2 OK</h1><p>嵌入式渲染测试</p></body></html>"
        hr_nav = call(webview, 59, ctypes.WINFUNCTYPE(HRESULT, LPVOID, wintypes.LPCWSTR), wintypes.LPCWSTR(html))  # NavigateToString
        print("webview ready:", bool(webview.value), "NavigateToString hr:", hr_nav)

    def on_env(env):
        state["env"] = env
        handler = ControllerHandler(on_controller)
        state["ctrl_handler"] = handler
        hr = call(env, 3, ctypes.WINFUNCTYPE(HRESULT, LPVOID, ctypes.c_void_p, LPVOID), ctypes.c_void_p(hwnd), handler.pointer())
        print("CreateCoreWebView2Controller hr:", hr)

    def start():
        handler = EnvironmentHandler(on_env, hwnd)
        state["env_handler"] = handler
        import os
        data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".webview2")
        os.makedirs(data_dir, exist_ok=True)
        hr = create_env(None, data_dir, None, handler.pointer())
        print("CreateEnvironment hr:", hr)

    root.after(300, start)
    def shot():
        from pathlib import Path

        from PIL import ImageGrab

        out = Path(__file__).resolve().parent / "shots" / "webview2_probe.png"
        ImageGrab.grab().save(out)
        print("shot saved", out)

    root.after(2500, shot)
    root.after(4000, root.destroy)
    root.mainloop()
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
