"""Language display names follow the UI language; the dialog allows no Chinese name in English."""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from rc import i18n  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


def main() -> int:
    entry = {"label": "English", "zh_label": "英语"}

    print("\n[语言显示名]")
    i18n.set_language("zh")
    check("中文界面用中文名", i18n.lang_display_name(entry, "en") == "英语")
    check("中文词本后缀", i18n.wordbook_suffix() == "词本")

    i18n.set_language("en")
    check("英文界面用本地名", i18n.lang_display_name(entry, "en") == "English")
    check("英文词本后缀", i18n.wordbook_suffix() == " wordbook")
    check(
        "缺本地名时回退中文名",
        i18n.lang_display_name({"zh_label": "英语"}, "en") == "英语",
    )
    check("两者都缺时回退代码", i18n.lang_display_name({}, "en") == "en")

    from rc.store import _default_wordbook_name

    i18n.set_language("zh")
    check("中文默认词本名", _default_wordbook_name("en") == "英语词本")
    i18n.set_language("en")
    check("英文默认词本名", _default_wordbook_name("en") == "English wordbook")
    check("未知语言用代码", _default_wordbook_name("xx") == "xx wordbook")

    print("\n[词典显示名]")
    from rc.popup_common import source_label

    check("保留原词典名", source_label("  Oxford   Hachette ") == "Oxford Hachette")
    long_name = "x" * 60
    check("过长时截断", source_label(long_name).endswith("…") and len(source_label(long_name)) == 44)

    print("\n[添加语言：英文界面可只填本地名]")
    import rc.language_dialog as ld

    shown: list[str] = []
    original = ld.messagebox.showinfo
    ld.messagebox.showinfo = lambda *a, **k: shown.append(a[1] if len(a) > 1 else "")

    root = tk.Tk()
    root.withdraw()
    try:
        dlg = ld.LanguageDialog(root, [], code="", entry={}, edit=False)
        dlg.entry_code.insert(0, "it")
        dlg.entry_label.insert(0, "Italiano")
        root.update()
        dlg._save()
        result = dlg.result or {}
        check("保存成功", bool(result), str(result))
        check("中文名兜底为本地名", result.get("zh_label") == "Italiano", str(result))
        check("牌组默认用本地名", result.get("deck") == "Reading::Italiano", str(result))
        check("没有弹校验框", shown == [], str(shown))

        i18n.set_language("zh")
        dlg2 = ld.LanguageDialog(root, [], code="", entry={}, edit=False)
        dlg2.entry_code.insert(0, "it")
        dlg2.entry_label.insert(0, "Italiano")
        root.update()
        dlg2._save()
        check("中文界面仍要求中文名", dlg2.result is None, str(dlg2.result))
    finally:
        ld.messagebox.showinfo = original
        i18n.set_language("zh")
        try:
            root.destroy()
        except Exception:  # noqa: BLE001
            pass

    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
