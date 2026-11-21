"""体验体检：空状态、错误路径、设置保存等，尽量不弹窗不联网。"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from rc.config import Config  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(name: str, fn) -> None:
    """跑一个断言函数：抛异常或返回 False/None 都算失败。

    注意：不能写成 `fn() or ""` 后无条件记 True——那样返回 False 的断言也会变绿。
    """
    try:
        detail = fn()
    except Exception as exc:  # noqa: BLE001
        results.append((name, False, f"{type(exc).__name__}: {exc}"))
        print(f"  FAIL {name}  {type(exc).__name__}: {exc}")
        traceback.print_exc(limit=2)
        return
    if detail is False or detail is None:
        results.append((name, False, "断言返回 False"))
        print(f"  FAIL {name}  断言返回 False")
        return
    results.append((name, True, str(detail)[:120]))
    print(f"  ok   {name}" + (f"  {detail}" if detail else ""))


def main() -> int:
    import tkinter as tk

    from rc.service import Service

    import shutil

    tmp = HERE / "uxtmp"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)
    cfg = Config(tmp)
    cfg.data["dictionaries"] = {}
    cfg.data["api"]["base_url"] = "http://127.0.0.1:18778/v1"
    cfg.data["api"]["api_key"] = "k"
    cfg.save()
    from tests import mock_openai

    mock_openai.start(18778)
    svc = Service(cfg)

    print("\n[空状态：没有配置词典]")
    check("lookup_all 不炸", lambda: len(svc.lookup_all("hello")) == 0 or "有词典")
    check("lookup_word 返回 None", lambda: svc.lookup_word("hello") is None)
    check("entry_html 返回空串", lambda: svc.entry_html("hello", "en") == "")

    print("\n[设置窗口：能建、能存]")
    root = tk.Tk()
    root.withdraw()

    def settings_flow():
        from rc.settings_ui import SettingsWindow

        win = SettingsWindow(root, svc, on_saved=lambda: None, on_quit=lambda: None)
        win.win.update_idletasks()
        win.save()  # 保存不能抛异常
        return "saved"

    check("打开并保存", settings_flow)

    def book_filter_window():
        from rc.book_settings import BookFilterSettings

        w = BookFilterSettings(root, cfg, on_saved=lambda: None)
        w.win.update_idletasks()
        w.save()
        return "saved"

    check("书名过滤窗口保存", book_filter_window)

    def color_window():
        from rc.entry_settings import EntryColorSettings

        w = EntryColorSettings(root, cfg, on_saved=lambda: None)
        w.win.update_idletasks()
        w.save()
        return "saved"

    check("配色窗口保存", color_window)

    print("\n[选词/翻译空输入]")
    def empty_translate():
        try:
            svc.translate("")
        except ValueError as exc:
            return f"友好报错: {exc}"
        return "没报错"

    check("空文本翻译给明确提示", lambda: "没有读到文字" in str(empty_translate()))
    check("超长文本不炸", lambda: svc.translate("x" * 5000) is not None or "有返回")

    print("\n[聊天]")
    def chat_empty():
        conv_id = svc.start_conversation("Book", "en", "passage", "译文")["id"]
        try:
            svc.ask(conv_id, "   ")
        except ValueError as exc:
            return str(exc)
        raise AssertionError("空问题没有报错")

    check("空消息聊天给明确提示", lambda: "问题不能为空" in chat_empty())

    print("\n[生词本/导出]")
    check("生词列表", lambda: isinstance(svc.store.list_words(), list))
    check("导出翻译", lambda: isinstance(svc.export_translations(), (str, dict)))

    root.destroy()
    shutil.rmtree(tmp, ignore_errors=True)
    failed = [name for name, ok, _ in results if not ok]
    print("\n失败项：", failed if failed else "无")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
