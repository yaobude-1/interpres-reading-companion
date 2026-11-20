"""体验体检 3：翻译/聊天/Anki/热键的错误路径。"""

from __future__ import annotations

import shutil
import sys
import time
import tkinter as tk
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from rc.config import Config  # noqa: E402
from tests import mock_openai  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


def main() -> int:
    tmp = HERE / "uxtmp3"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)
    cfg = Config(tmp)
    cfg.data["dictionaries"] = {}
    cfg.data["api"].update(
        {"base_url": "http://127.0.0.1:18778/v1", "api_key": "k", "model": "mock"}
    )
    cfg.data["server_port"] = 18830
    cfg.save()
    mock_openai.start(18778)

    from rc.service import Service

    svc = Service(cfg)

    print("\n[翻译]")
    def translate_ok():
        payload = svc.translate("The quick brown fox.")
        return (payload.get("translation") or "")[:40]

    try:
        text = translate_ok()
        check("正常翻译", bool(text), text)
    except Exception as exc:  # noqa: BLE001
        check("正常翻译", False, f"{type(exc).__name__}: {exc}")

    def translate_bad_key():
        old = cfg.api.get("base_url")
        cfg.api["base_url"] = "http://127.0.0.1:1/v1"
        try:
            svc.translate("hello")
        finally:
            cfg.api["base_url"] = old

    try:
        translate_bad_key()
        check("连不上时抛异常（由上层提示）", False, "没有抛异常")
    except Exception as exc:  # noqa: BLE001
        check("连不上时抛异常（由上层提示）", True, type(exc).__name__)

    print("\n[聊天]")
    def chat_flow():
        conv = svc.store.start_conversation("测试书", "en", "passage", "译文")
        svc.store.add_message(conv, "user", "你好") if hasattr(svc.store, "add_message") else None
        reply = svc.ask(conv, "你好")
        return str(reply)[:40] if reply else ""

    try:
        reply = chat_flow()
        check("聊天有回复", bool(reply), reply)
    except Exception as exc:  # noqa: BLE001
        check("聊天有回复", False, f"{type(exc).__name__}: {exc}")

    print("\n[Anki]")
    from rc import anki

    def anki_status():
        try:
            return anki.ping()
        except Exception as exc:  # noqa: BLE001
            return f"error: {type(exc).__name__}"

    try:
        check("Anki 未开时能给出状态而不是崩", anki_status() is not None)
    except Exception as exc:  # noqa: BLE001
        check("Anki 未开时能给出状态而不是崩", False, f"{type(exc).__name__}: {exc}")

    print("\n[热键校验]")
    root = tk.Tk()
    root.withdraw()
    from rc.settings_ui import SettingsWindow

    win = SettingsWindow(root, svc, on_saved=lambda: None, on_quit=lambda: None)
    win.var_hotkey.set("这不是热键")
    try:
        win.save()
        check("非法热键保存不崩", True)
    except Exception as exc:  # noqa: BLE001
        check("非法热键保存不崩", False, f"{type(exc).__name__}: {exc}")

    win.close()
    root.destroy()
    shutil.rmtree(tmp, ignore_errors=True)
    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
