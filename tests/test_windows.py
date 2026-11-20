"""复现：手动输入窗口反复开合是否产生多余窗口。"""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from rc.config import Config  # noqa: E402


def toplevels(root: tk.Tk) -> list[str]:
    out = []
    for child in root.winfo_children():
        out.append(f"{child.winfo_class()}#{child.winfo_id()}")
    return out


def main() -> int:
    data = HERE / ".wincheck"
    cfg = Config(data)
    cfg.data["api"].update({"base_url": "http://127.0.0.1:18778/v1", "api_key": "k", "model": "m"})
    cfg.save()

    from app import Application

    app = Application(cfg, enable_hotkeys=False)
    log = []

    def step(n: int) -> None:
        app.popup.show_input((400, 300), f"text {n}")
        app.root.update()
        log.append(
            f"open#{n}: toplevels={toplevels(app.root)} body_kids={len(app.popup.body.winfo_children())}"
        )
        app.popup.hide()
        app.root.update()
        log.append(f"close#{n}: toplevels={toplevels(app.root)}")

    for i in range(1, 4):
        app.root.after(300 * i, lambda i=i: step(i))

    def finish() -> None:
        (HERE / "wincheck.txt").write_text("\n".join(log), encoding="utf-8")
        app.shutdown()

    app.root.after(1600, finish)
    app.run()
    print((HERE / "wincheck.txt").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
