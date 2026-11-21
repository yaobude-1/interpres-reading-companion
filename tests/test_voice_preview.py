"""验证音色试听：用当前选中的音色念示例句。"""

from __future__ import annotations

import shutil
import sys
import tkinter as tk
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from rc.config import Config  # noqa: E402
from rc.service import Service  # noqa: E402
from rc.settings_ui import SettingsWindow, VOICE_SAMPLES  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


def main() -> int:
    data = HERE / ".voicepreview"
    shutil.rmtree(data, ignore_errors=True)
    cfg = Config(data)
    # 固定用 system 引擎：让 preview_voice 走被 mock 的 speak_with，
    # 不依赖机器上是否装了某个 SAPI 音色、也不会去连 Edge。
    for code in ("en", "fr"):
        cfg.data.setdefault("languages", {}).setdefault(code, {})["tts_engine"] = "system"
    cfg.save()
    service = Service(cfg)

    calls: list[tuple[str, str]] = []
    service.tts.speak_with = lambda text, voice: calls.append((text, voice)) or Path("x.wav")

    root = tk.Tk()
    root.withdraw()
    window = SettingsWindow(root, service, lambda: None, lambda: None)
    root.update()

    # 选一个音色，再点试听
    window.lang_vars["en"][0].set("Microsoft Zira Desktop")
    window.lang_vars["fr"][0].set("Microsoft Hortense Desktop")
    window.preview_voice("en")
    window.preview_voice("fr")

    deadline = time.time() + 2
    while len(calls) < 2 and time.time() < deadline:
        root.update()
        time.sleep(0.02)

    check("试听了两次", len(calls) == 2, str(calls))
    if len(calls) >= 2:
        check("英语用 Zira", calls[0][1] == "Microsoft Zira Desktop", str(calls[0]))
        check("英语文本是示例句", calls[0][0] == VOICE_SAMPLES["en"], calls[0][0])
        check("法语用 Hortense", calls[1][1] == "Microsoft Hortense Desktop", str(calls[1]))
        check("法语文本是示例句", calls[1][0] == VOICE_SAMPLES["fr"], calls[1][0])

    root.destroy()
    service.store.close()
    shutil.rmtree(data, ignore_errors=True)
    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
