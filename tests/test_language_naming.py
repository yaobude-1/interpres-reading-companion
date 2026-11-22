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

    print("\n[英文界面文案完整]")
    for zh, en in (
        ("浮窗", "Popup"),
        ("动画", "Animations"),
        ("界面淡入淡出", "Fade animations"),
        ("数据目录", "Data folder"),
        ("还没有生词", "No words yet"),
        ("编辑语言", "Edit language"),
        ("添加语言", "Add language"),
        ("Anki 已连接", "Anki connected"),
        ("Anki 状态检测中…", "Checking Anki…"),
        (
            "Anki 未运行（同步时会自动导出 CSV）",
            "Anki is not running (CSV is exported automatically on sync)",
        ),
        ("中文名（可留空）", "Chinese name (optional)"),
    ):
        check(f"{zh} → {en}", i18n.tr(zh) == en, i18n.tr(zh))
    check(
        "生词统计行按英文格式",
        i18n.tr("共 7 个生词（English 5, Français 2）")
        == "7 words (English 5, Français 2)",
        i18n.tr("共 7 个生词（English 5, Français 2）"),
    )

    print("\n[词典映射界面英文化]")
    for zh, en in (
        ("词典映射（高级）", "Dictionary mapping (advanced)"),
        ("词典映射…", "Dictionary mapping…"),
        ("已有映射", "Saved mappings"),
        ("保存并重载", "Save and reload"),
        ("插入模板", "Insert template"),
        ("本地词典设置", "Local dictionary settings"),
        ("文件不存在", "File not found"),
        ("MDX 词典", "MDX dictionary"),
        ("所有文件", "All files"),
        ("移动…", "Move to…"),
        ("移动到…", "Move to…"),
    ):
        check(f"{zh} → {en}", i18n.tr(zh) == en, i18n.tr(zh))
    check(
        "选择词典的标题",
        i18n.tr("选择 it 的 MDX 词典") == "Choose the MDX dictionary for it",
        i18n.tr("选择 it 的 MDX 词典"),
    )
    check("读取失败", i18n.tr("读取失败：boom") == "Read failed: boom", i18n.tr("读取失败：boom"))
    check("缺少字段", i18n.tr("缺少字段：id") == "Missing field: id", i18n.tr("缺少字段：id"))
    check(
        "保存并重载状态",
        i18n.tr("已保存并重载：x.json（命中匹配规则才生效）")
        == "Saved and reloaded: x.json (takes effect when the match rule hits)",
        i18n.tr("已保存并重载：x.json（命中匹配规则才生效）"),
    )
    from rc.dict_profiles import template

    check("英文模板名", template()["name"] == "My dictionary", template()["name"])
    i18n.set_language("zh")
    check("中文模板名", template()["name"] == "我的词典", template()["name"])
    i18n.set_language("en")

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

    i18n.install()

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
        check("英文标签列宽", ld._label_width() == 24, str(ld._label_width()))
        zh_label = dlg.entry_zh.master.winfo_children()[0]
        check(
            "中文名标签完整显示",
            str(zh_label.cget("text")) == "Chinese name (optional)"
            and int(str(zh_label.cget("width"))) >= 20,
            f"{zh_label.cget('text')!r} width={zh_label.cget('width')}",
        )
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
