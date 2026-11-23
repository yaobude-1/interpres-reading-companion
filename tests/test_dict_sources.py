"""面板查词：来源栏并列所有词典，并标出匹配等级。"""

from __future__ import annotations

import shutil
import sys
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


def label_texts(widget) -> list[str]:
    out: list[str] = []
    for child in widget.winfo_children():
        try:
            text = str(child.cget("text"))
        except Exception:  # noqa: BLE001
            text = ""
        if text:
            out.append(text)
        out.extend(label_texts(child))
    return out


def main() -> int:
    data = HERE / ".dictsources"
    shutil.rmtree(data, ignore_errors=True)
    data.mkdir(parents=True)
    cfg = Config(data)
    cfg.data["server_port"] = 18793
    cfg.save()

    from app import Application

    app = Application(cfg, enable_hotkeys=False)
    app.open_panel()
    app.root.update()
    panel = app.panel
    panel._show_tab("dict")
    app.root.update()

    accent = {
        "lang": "fr",
        "source": "Oxford Hachette",
        "entry": {
            "word": "créer",
            "lang": "fr",
            "phonetic": "kʁe.e",
            "senses": [{"pos": "vtr", "definition": "to create"}],
            "match": "accent",
            "matched": "créer",
        },
    }
    redirect = {
        "lang": "en",
        "source": "Longman",
        "entry": {
            "word": "c",
            "lang": "en",
            "senses": [{"pos": "n.", "definition": "版权"}],
            "match": "redirect",
            "matched": "cre",
            "redirect": "c",
        },
    }
    original = app.service.lookup_all
    app.service.lookup_all = lambda word, lang_hint=None, context="panel": [accent, redirect]
    try:
        print("\n[重音匹配 + 重定向]")
        panel.dict_input.delete(0, "end")
        panel.dict_input.insert(0, "creer")
        panel._lookup_dict(sync=True)
        app.root.update()
        texts = label_texts(panel.dict_result)
        check("来源栏出现重音匹配", any("重音匹配" in t for t in texts), str(texts[:8]))
        check("来源栏出现重定向", any("重定向" in t for t in texts), str(texts[:8]))
        check("默认选中最佳匹配", any("créer" == t for t in texts), str(texts[:6]))
        chip = next((t for t in texts if "重定向" in t), "")
        check("重定向 chip 带来源", "Longman" in chip, chip)

        print("\n[同等级：两个精确]")
        exact_en = {
            "lang": "en",
            "source": "Longman",
            "entry": {
                "word": "pain",
                "lang": "en",
                "senses": [{"pos": "noun", "definition": "疼痛"}],
                "match": "exact",
                "matched": "pain",
            },
        }
        exact_fr = {
            "lang": "fr",
            "source": "Oxford Hachette",
            "entry": {
                "word": "pain",
                "lang": "fr",
                "senses": [{"pos": "nm", "definition": "面包"}],
                "match": "exact",
                "matched": "pain",
            },
        }
        app.service.lookup_all = lambda word, lang_hint=None, context="panel": [exact_en, exact_fr]
        panel.dict_input.delete(0, "end")
        panel.dict_input.insert(0, "pain")
        panel._lookup_dict(sync=True)
        app.root.update()
        texts = label_texts(panel.dict_result)
        chips = [t for t in texts if "精确" in t]
        check("两个精确 chip 都在", len(chips) >= 2, str(texts[:8]))
        check(
            "两个来源都在",
            any("Longman" in t for t in chips) and any("Oxford" in t for t in chips),
            str(chips),
        )
    finally:
        app.service.lookup_all = original
        app.shutdown()
        shutil.rmtree(data, ignore_errors=True)

    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
