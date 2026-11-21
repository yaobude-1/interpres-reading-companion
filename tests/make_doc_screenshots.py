"""生成 README 用的演示截图：临时数据目录，不含个人配置。

用法：
    python tests/make_doc_screenshots.py en   # 英文界面 + 法语→英语（英文 README 用）
    python tests/make_doc_screenshots.py zh   # 中文界面 + 英语→中文（中文 README 用）
"""

from __future__ import annotations

import shutil
import sys
import time
import tkinter as tk
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from PIL import ImageGrab  # noqa: E402

OUT = ROOT / "docs" / "screenshots"
DATA = HERE / ".docshots"


def grab(widget, name: str) -> None:
    win = widget.winfo_toplevel()
    win.update_idletasks()
    win.deiconify()
    win.lift()
    win.update()
    try:
        win.attributes("-topmost", True)
    except tk.TclError:
        pass
    win.update()
    time.sleep(0.2)
    x, y = win.winfo_rootx(), win.winfo_rooty()
    w, h = win.winfo_width(), win.winfo_height()
    ImageGrab.grab(bbox=(x, y, x + w, y + h)).save(OUT / name)
    try:
        win.attributes("-topmost", False)
    except tk.TclError:
        pass
    print("saved", name, w, h)


def main() -> int:
    mode = (sys.argv[1] if len(sys.argv) > 1 else "en").lower()
    if mode not in ("en", "zh"):
        print("usage: make_doc_screenshots.py [en|zh]")
        return 2
    suffix = "" if mode == "en" else "-zh"
    OUT.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(DATA, ignore_errors=True)
    DATA.mkdir(parents=True)

    from rc.config import Config
    from rc import i18n

    cfg = Config(DATA)
    cfg.data["ui_lang"] = mode
    # 演示内容要和界面语言一致：英文界面配“法语→英语”，中文界面配“英语→中文”。
    cfg.data["target_lang"] = "en" if mode == "en" else "zh-CN"
    cfg.data["api"].update(
        {
            "base_url": "https://api.deepseek.com/v1",
            "api_key": "sk-demo-not-a-real-key-000000",
            "model": "deepseek-chat",
        }
    )
    cfg.data["stream_cps"] = 60
    for code, name, deck in (
        ("en", "English", "Reading::English"),
        ("fr", "French", "Reading::French"),
    ):
        lang = cfg.data["languages"].setdefault(code, {})
        lang["name"] = name
        lang["label"] = name
        lang["zh_label"] = name
        lang["deck"] = deck
    cfg.save()

    i18n.set_language(mode)
    i18n.install()

    from app import Application
    from rc.anki_card_settings import AnkiCardSettings
    from rc.language_dialog import LanguageDialog

    app = Application(cfg, enable_hotkeys=False, silent=True)
    svc = app.service
    svc.store.touch_book("Demo Book", "en")
    svc.add_vocab(
        lang="en",
        word="ephemeral",
        lemma="ephemeral",
        reading="/ɪˈfemərəl/",
        pos="adj.",
        meaning="lasting for a very short time",
        sentence="Fashion is by nature ephemeral.",
        book="Demo Book",
    )
    svc.add_vocab(
        lang="en",
        word="serendipity",
        lemma="serendipity",
        reading="/ˌserənˈdɪpəti/",
        pos="n.",
        meaning="a fortunate discovery by chance",
        book="Demo Book",
    )
    svc.add_vocab(
        lang="fr",
        word="flâner",
        lemma="flâner",
        reading="/flane/",
        pos="v.",
        meaning="to stroll; to wander aimlessly",
        book="Demo Book",
    )
    svc.store.rename_default_wordbook("en", "English")
    svc.store.rename_default_wordbook("fr", "French")

    class DemoAnki:
        def model_names(self):
            return ["Interpres", "Reading Note"]

        def model_fields(self, model):
            return [
                "Word",
                "Phonetic",
                "POS",
                "Meaning",
                "Example",
                "ExampleCN",
                "Audio",
                "Book",
                "Language",
            ]

        def update_custom_templates(self, *args, **kwargs):
            pass

    state = {"step": 0}

    def next_step() -> None:
        step = state["step"]
        state["step"] += 1
        try:
            if step == 0:
                app.open_panel()
                if mode == "en":
                    source = (
                        "La mode est par nature éphémère, et le désir de nouveauté "
                        "fait avancer l'industrie."
                    )
                    translation = (
                        "Fashion is by nature ephemeral, and the desire for novelty "
                        "keeps the industry moving."
                    )
                else:
                    source = (
                        "Fashion is by nature ephemeral, and the desire for novelty "
                        "keeps the industry moving."
                    )
                    translation = "时尚本质上是短暂的，而对新奇事物的渴望让这个行业不断向前。"
                app.panel.input.insert("1.0", source)
                app.panel._finish_result(
                    {
                        "translation": translation,
                        "meta": {"elapsed_ms": 1840, "cached": False},
                    }
                )
                app.root.after(700, next_step)
            elif step == 1:
                grab(app.panel.win, f"panel-{mode}.png")
                app.panel._show_tab("vocab")
                app.root.after(700, next_step)
            elif step == 2:
                grab(app.panel.win, f"vocabulary{suffix}.png")
                app.open_settings()
                if app._settings:
                    app._settings.win.geometry("+60+30")
                app.root.after(900, next_step)
            elif step == 3:
                if app._settings:
                    grab(app._settings.win, f"settings-{mode}.png")
                dlg = LanguageDialog(app.panel.win, ["Microsoft Zira Desktop", "Microsoft David Desktop"])
                dlg.entry_code.insert(0, "it")
                dlg.entry_zh.insert(0, "意大利语")
                dlg.entry_label.insert(0, "Italiano")
                dlg.win.geometry("+720+80")
                app.root.after(800, lambda: (grab(dlg.win, f"language-dialog{suffix}.png"), dlg.win.destroy()))
                app.root.after(1500, next_step)
            elif step == 4:
                card = AnkiCardSettings(app.panel.win, cfg, DemoAnki())
                card.win.geometry("+160+40")
                app.root.after(1100, lambda: (grab(card.win, f"anki-cards{suffix}.png"), card.win.destroy()))
                app.root.after(2000, next_step)
            elif step >= 5:
                app.shutdown()
        except Exception:
            import traceback

            traceback.print_exc()
            app.shutdown()

    app.root.after(500, next_step)
    app.run()
    time.sleep(0.3)
    shutil.rmtree(DATA, ignore_errors=True)
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
