"""词典映射编辑器：让用户用 JSON + XPath 适配任意 MDX 的词条结构。"""

from __future__ import annotations

import json
import re
import tkinter as tk
from pathlib import Path

from .dict_profiles import TEMPLATE
from .popup import ACCENT, BG, DIM, FONT_FAMILY, GREEN, MUTED, PANEL, RED, TEXT
from .theme import ON_ACCENT


class DictProfileEditor:
    def __init__(self, root: tk.Tk, config, manager) -> None:
        self.root = root
        self.config = config
        self.manager = manager
        self.dir = Path(config.data_dir) / "dict_profiles"
        self.dir.mkdir(parents=True, exist_ok=True)

        self.win = tk.Toplevel(root)
        self.win.title("词典映射（高级）")
        self.win.configure(bg=BG)
        self.win.geometry("780x600")
        self.win.transient(root)
        self.win.grab_set()

        outer = tk.Frame(self.win, bg=BG)
        outer.pack(fill="both", expand=True, padx=16, pady=12)
        tk.Label(
            outer, text="词典映射", bg=BG, fg=TEXT,
            font=(FONT_FAMILY, 14, "bold"), anchor="w",
        ).pack(fill="x")
        tk.Label(
            outer,
            text=(
                "用 JSON 里的 XPath 告诉程序：词头、音标、词性、义项、例句在 HTML 的哪里。\n"
                "match.contains 必须填词条 HTML 里独有的一段文字；保存后自动重载词典。\n"
                "留空或解析失败会自动回退到内置解析，不会把词典弄坏。"
            ),
            bg=BG, fg=DIM, font=(FONT_FAMILY, 9), anchor="w", justify="left",
            wraplength=720,
        ).pack(fill="x", pady=(2, 8))

        list_row = tk.Frame(outer, bg=BG)
        list_row.pack(fill="x", pady=(0, 6))
        tk.Label(list_row, text="已有映射", bg=BG, fg=DIM, font=(FONT_FAMILY, 9)).pack(side="left")
        self.var_existing = tk.StringVar(value="")
        self.existing = tk.OptionMenu(list_row, self.var_existing, "")
        self.existing.configure(
            bg=PANEL, fg=TEXT, activebackground=PANEL, activeforeground=TEXT,
            relief="flat", highlightthickness=0, font=(FONT_FAMILY, 9), width=34,
            anchor="w",
        )
        self.existing["menu"].configure(
            bg=PANEL, fg=TEXT, activebackground=ACCENT, activeforeground=ON_ACCENT
        )
        self.existing.pack(side="left", padx=(8, 0))
        self.var_existing.trace_add("write", lambda *_: self._load_selected())
        self._reload_list()

        self.text = tk.Text(
            outer, height=18, bg=PANEL, fg=TEXT, insertbackground=TEXT,
            relief="flat", font=("Consolas", 9), wrap="none", padx=8, pady=6,
        )
        self.text.pack(fill="both", expand=True)
        self.text.insert("1.0", json.dumps(TEMPLATE, ensure_ascii=False, indent=2))

        self.status = tk.Label(outer, text="", bg=BG, fg=MUTED, font=(FONT_FAMILY, 9), anchor="w")
        self.status.pack(fill="x", pady=(6, 0))

        bar = tk.Frame(outer, bg=BG)
        bar.pack(fill="x", pady=(6, 0))
        self._button(bar, "保存并重载", self.save, primary=True).pack(side="right")
        self._button(bar, "打开配置目录", self._open_dir).pack(side="right", padx=(0, 8))
        self._button(bar, "插入模板", self._insert_template).pack(side="left")
        self._button(bar, "关闭", self.win.destroy).pack(side="left", padx=(8, 0))

    # ------------------------------------------------------------------ 工具
    def _button(self, parent, text, command, primary=False):
        label = tk.Label(
            parent, text=text, bg=ACCENT if primary else PANEL,
            fg=ON_ACCENT if primary else TEXT, font=(FONT_FAMILY, 9),
            padx=12, pady=4, cursor="hand2",
        )
        label.bind("<Button-1>", lambda _e: command())
        return label

    def _set_status(self, text: str, color=MUTED) -> None:
        try:
            self.status.configure(text=text, fg=color)
        except tk.TclError:
            pass

    def _paths(self) -> list[Path]:
        return sorted(self.dir.glob("*.json"))

    def _reload_list(self) -> None:
        names = ["（新建模板）"] + [p.name for p in self._paths()]
        self._profile_files = {p.name: p for p in self._paths()}
        menu = self.existing["menu"]
        menu.delete(0, "end")
        for name in names:
            menu.add_command(
                label=name,
                command=lambda n=name: self.var_existing.set("" if n.startswith("（") else n),
            )
        self.var_existing.set("")

    def _load_selected(self) -> None:
        name = self.var_existing.get().strip()
        path = self._profile_files.get(name)
        if not path:
            return
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as exc:
            self._set_status(f"读取失败：{exc}", RED)
            return
        self.text.delete("1.0", "end")
        self.text.insert("1.0", content)
        self._set_status(f"已载入 {name}")

    def _insert_template(self) -> None:
        self.text.delete("1.0", "end")
        self.text.insert("1.0", json.dumps(TEMPLATE, ensure_ascii=False, indent=2))
        self._set_status("已插入模板，改完再保存")

    def _open_dir(self) -> None:
        try:
            import os

            os.startfile(str(self.dir))
        except Exception:
            self._set_status(f"配置目录：{self.dir}")

    def save(self) -> None:
        raw = self.text.get("1.0", "end-1c").strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            self._set_status(f"JSON 语法错误：第 {exc.lineno} 行 {exc.msg}", RED)
            return
        if not isinstance(data, dict):
            self._set_status("JSON 顶层必须是对象", RED)
            return
        for key in ("id", "name", "senses", "definition", "match"):
            if not data.get(key):
                self._set_status(f"缺少字段：{key}", RED)
                return
        profile_id = re.sub(r"[^a-z0-9_-]+", "-", str(data["id"]).strip().lower()).strip("-")
        if not profile_id:
            self._set_status("id 只能包含小写字母、数字、- 和 _", RED)
            return
        data["id"] = profile_id
        path = self.dir / f"{profile_id}.json"
        try:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as exc:
            self._set_status(f"写入失败：{exc}", RED)
            return
        try:
            self.manager.reload()
        except Exception as exc:  # noqa: BLE001
            self._set_status(f"已保存，但重载失败：{exc}", RED)
            return
        self._reload_list()
        self._set_status(f"已保存并重载：{path.name}（命中匹配规则才生效）", GREEN)
