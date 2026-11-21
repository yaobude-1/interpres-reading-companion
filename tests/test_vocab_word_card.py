"""回归：双击生词本里的单词会弹出卡片（有词典 / 无词典两条路径）。"""

from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from rc.config import Config  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


def pump(root, predicate, timeout: float = 3.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        root.update()
        if predicate():
            return True
        time.sleep(0.02)
    root.update()
    return predicate()


def label_texts(widget) -> list[str]:
    out: list[str] = []
    for child in widget.winfo_children():
        try:
            text = child.cget("text")
        except Exception:  # noqa: BLE001
            text = ""
        if text:
            out.append(str(text))
        out.extend(label_texts(child))
    return out


def main() -> int:
    data = HERE / ".vocabcard"
    shutil.rmtree(data, ignore_errors=True)
    data.mkdir(parents=True)

    cfg = Config(data)
    cfg.data["dictionaries"] = {}
    cfg.data["server_port"] = 18791
    cfg.save()

    from app import Application

    app = Application(cfg, enable_hotkeys=False)
    svc = app.service
    svc.add_vocab(
        lang="en",
        word="ephemeral",
        lemma="ephemeral",
        reading="ɪˈfemərəl",
        pos="adj.",
        meaning="短暂的",
        sentence="Fashion is by nature ephemeral.",
        book="Test Book",
    )

    app.open_panel()
    app.root.update()
    app.panel._show_tab("vocab")
    app.root.update()
    panel = app.panel._ensure_vocab_panel()
    app.root.update()

    class Event:
        y = 0
        x_root = 300
        y_root = 300

    rows = panel.word_tree.get_children()
    check("生词表有行", bool(rows), str(rows))
    check("双击事件已绑定", bool(panel.word_tree.bind("<Double-1>")), "")

    print("\n[无词典：保存信息卡片]")
    bbox = panel.word_tree.bbox(rows[0])
    Event.y = bbox[1] + 2 if bbox else 20
    panel._open_word(Event())
    shown = pump(app.root, lambda: app.popup.visible)
    check("浮窗出现", shown)
    check("标题是生词", app.popup.title.cget("text") == "生词", app.popup.title.cget("text"))
    texts = label_texts(app.popup.body)
    check("显示单词", "ephemeral" in texts, str(texts[:8]))
    check("显示保存的释义", any("短暂的" in t for t in texts), str(texts[:8]))
    check("显示例句", any("Fashion" in t for t in texts), str(texts[:8]))
    app.popup.hide()

    print("\n[有词典：词典卡片]")
    fake = {
        "lang": "en",
        "source": "Test Dictionary",
        "entry": {
            "word": "ephemeral",
            "lang": "en",
            "phonetic": "ɪˈfemərəl",
            "senses": [{"pos": "adj.", "definition": "lasting a very short time"}],
            "matched": "ephemeral",
        },
    }
    original_lookup = svc.lookup_all
    svc.lookup_all = lambda word, lang_hint=None: [fake]
    try:
        app.show_word_card(panel.words[0], (320, 320))
    finally:
        svc.lookup_all = original_lookup
    shown = pump(app.root, lambda: app.popup.visible)
    check("词典卡片出现", shown)
    check(
        "标题是查词",
        app.popup.title.cget("text") == "查词",
        app.popup.title.cget("text"),
    )
    texts = label_texts(app.popup.body)
    check("显示词典释义", any("lasting" in t for t in texts), str(texts[:8]))
    app.popup.hide()

    app.shutdown()
    shutil.rmtree(data, ignore_errors=True)
    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
