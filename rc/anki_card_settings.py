"""Anki 卡片自定义：字段映射 + Front/Back/CSS。"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox

from .anki import (
    CUSTOM_SOURCES,
    DEFAULT_BACK,
    DEFAULT_FRONT,
    CSS as DEFAULT_CSS,
    FIELDS,
    MODEL_NAME,
)
from .popup import ACCENT, BG, DIM, FONT_FAMILY, GREEN, MUTED, PANEL, RED, TEXT
from .theme import BORDER_SOFT, ON_ACCENT, SCROLL_THUMB, SCROLL_TRACK


class AnkiCardSettings:
    def __init__(self, root, config, anki) -> None:
        self.root = root
        self.config = config
        self.anki = anki
        saved = dict(config.get("anki_custom") or {})
        self.saved = saved
        self.models: list[str] = [MODEL_NAME]
        self.model_fields: dict[str, list[str]] = {MODEL_NAME: list(FIELDS)}
        self.mapping_vars: dict[str, tk.StringVar] = {}

        self.win = tk.Toplevel(root)
        self.win.title("Anki 卡片设置")
        self.win.configure(bg=BG)
        self.win.geometry("860x720")
        self.win.minsize(760, 600)
        self.win.transient(root)
        self.win.grab_set()

        bar = tk.Frame(self.win, bg=BG)
        bar.pack(side="bottom", fill="x", padx=16, pady=(0, 10))
        main = tk.Frame(self.win, bg=BG)
        main.pack(fill="both", expand=True)

        canvas = tk.Canvas(main, bg=BG, highlightthickness=0, bd=0)
        scrollbar = tk.Scrollbar(
            main, orient="vertical", command=canvas.yview,
            bg=SCROLL_THUMB, troughcolor=SCROLL_TRACK, activebackground=ACCENT,
        )
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y", padx=(0, 6))

        outer = tk.Frame(canvas, bg=BG)
        window_id = canvas.create_window((0, 0), window=outer, anchor="nw")

        def _on_outer(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas(event):
            canvas.itemconfigure(window_id, width=event.width)

        outer.bind("<Configure>", _on_outer)
        canvas.bind("<Configure>", _on_canvas)

        def _wheel(event):
            try:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except tk.TclError:  # 控件可能已销毁，刻意忽略
                pass

        self.win.bind("<MouseWheel>", _wheel, add="+")

        tk.Label(
            outer, text="Anki 卡片", bg=BG, fg=TEXT,
            font=(FONT_FAMILY, 14, "bold"), anchor="w",
        ).pack(fill="x")
        tk.Label(
            outer,
            text=(
                "字段映射把这里生成的内容放进你选择的笔记类型；Front/Back/CSS 仅对内置 "
                "Interpres 模型生效（也可同步到你自己的模型，会影响已有卡片）。\n"
                "启用后，英语也不再走 Dict2Anki。"
            ),
            bg=BG, fg=DIM, font=(FONT_FAMILY, 9), anchor="w", justify="left",
            wraplength=820,
        ).pack(fill="x", pady=(2, 8))

        head = tk.Frame(outer, bg=BG)
        head.pack(fill="x", pady=(0, 6))
        self.var_enabled = tk.BooleanVar(value=bool(saved.get("enabled")))
        tk.Checkbutton(
            head, text="启用自定义卡片", variable=self.var_enabled,
            bg=BG, fg=TEXT, selectcolor=BORDER_SOFT, activebackground=BG,
            activeforeground=TEXT, font=(FONT_FAMILY, 9), anchor="w",
        ).pack(side="left")

        tk.Label(head, text="笔记类型", bg=BG, fg=DIM, font=(FONT_FAMILY, 9)).pack(
            side="left", padx=(16, 6)
        )
        self.var_model = tk.StringVar(value=str(saved.get("model") or MODEL_NAME))
        self.model_box = tk.OptionMenu(head, self.var_model, MODEL_NAME)
        self.model_box.configure(
            bg=PANEL, fg=TEXT, activebackground=PANEL, activeforeground=TEXT,
            relief="flat", highlightthickness=0, font=(FONT_FAMILY, 9), width=28,
            anchor="w",
        )
        self.model_box["menu"].configure(
            bg=PANEL, fg=TEXT, activebackground=ACCENT, activeforeground=ON_ACCENT
        )
        self.model_box.pack(side="left")
        self.var_model.trace_add("write", lambda *_: self._on_model_change())
        tk.Label(
            head, text="（连不上 Anki 时用内置 Interpres 字段）", bg=BG, fg=DIM,
            font=(FONT_FAMILY, 8),
        ).pack(side="left", padx=(8, 0))

        map_box = tk.LabelFrame(
            outer, text="字段映射（目标字段 → 内容来源）", bg=PANEL, fg=TEXT,
            font=(FONT_FAMILY, 9), bd=0, padx=8, pady=6,
        )
        map_box.pack(fill="x", pady=(0, 8))
        self.map_frame = tk.Frame(map_box, bg=PANEL)
        self.map_frame.pack(fill="x")

        self.status = tk.Label(outer, text="", bg=BG, fg=MUTED, font=(FONT_FAMILY, 8))
        self.status.pack(fill="x")

        # 模板编辑
        editors = tk.Frame(outer, bg=BG)
        editors.pack(fill="both", expand=True, pady=(4, 0))
        self.front_text = self._editor(editors, "Front 模板", DEFAULT_FRONT, 5)
        self.back_text = self._editor(editors, "Back 模板", DEFAULT_BACK, 5)
        self.css_text = self._editor(editors, "CSS", DEFAULT_CSS, 7)

        self.var_sync = tk.BooleanVar(value=bool(saved.get("sync_templates", True)))
        tk.Checkbutton(
            outer, text="保存/同步时把模板与 CSS 推到 Anki（已有卡片会重新渲染）",
            variable=self.var_sync, bg=BG, fg=TEXT, selectcolor=BORDER_SOFT,
            activebackground=BG, activeforeground=TEXT, font=(FONT_FAMILY, 9),
            anchor="w",
        ).pack(fill="x", pady=(4, 0))

        self._button(bar, "保存", self.save, primary=True).pack(side="right")
        self._button(bar, "取消", self.win.destroy).pack(side="right", padx=(0, 8))
        self._button(bar, "填入默认模板", self._fill_defaults).pack(side="left")

        self._fill_editors(saved)
        self._build_mapping()
        self._set_status("正在从 Anki 读取字段…")
        self._load_models()

    # ------------------------------------------------------------------ UI
    def _editor(self, parent, label, default, height):
        tk.Label(
            parent, text=label, bg=BG, fg=DIM, font=(FONT_FAMILY, 8), anchor="w"
        ).pack(fill="x", pady=(4, 0))
        text = tk.Text(
            parent, height=height, bg=PANEL, fg=TEXT, insertbackground=TEXT,
            relief="flat", font=("Consolas", 8), wrap="word", padx=6, pady=4,
        )
        text.pack(fill="both", expand=True)
        text.insert("1.0", default)
        return text

    def _button(self, parent, text, command, primary=False):
        label = tk.Label(
            parent, text=text, bg=ACCENT if primary else PANEL,
            fg=ON_ACCENT if primary else TEXT, font=(FONT_FAMILY, 9),
            padx=14, pady=5, cursor="hand2",
        )
        label.bind("<Button-1>", lambda _e: command())
        return label

    def _set_status(self, text: str, color=MUTED) -> None:
        try:
            self.status.configure(text=text, fg=color)
        except tk.TclError:  # 控件可能已销毁，刻意忽略
            pass

    # ------------------------------------------------------------------ 数据
    def _fill_editors(self, saved: dict) -> None:
        values = (
            (self.front_text, saved.get("front") or DEFAULT_FRONT),
            (self.back_text, saved.get("back") or DEFAULT_BACK),
            (self.css_text, saved.get("css") or DEFAULT_CSS),
        )
        for widget, value in values:
            widget.delete("1.0", "end")
            widget.insert("1.0", value)

    def _fill_defaults(self) -> None:
        for widget, value in (
            (self.front_text, DEFAULT_FRONT),
            (self.back_text, DEFAULT_BACK),
            (self.css_text, DEFAULT_CSS),
        ):
            widget.delete("1.0", "end")
            widget.insert("1.0", value)
        self._set_status("已填入内置默认模板")

    def _load_models(self) -> None:
        self._models_ready = False

        def work() -> None:
            try:
                self.models = self.anki.model_names() or [MODEL_NAME]
            except Exception:
                self.models = [MODEL_NAME]
            if MODEL_NAME not in self.models:
                self.models.append(MODEL_NAME)
            self._models_ready = True

        threading.Thread(target=work, daemon=True).start()
        self._poll_models(0)

    def _poll_models(self, tries: int) -> None:
        if not getattr(self, "_models_ready", False):
            if tries < 60 and self.win.winfo_exists():
                self.win.after(100, lambda: self._poll_models(tries + 1))
            return
        menu = self.model_box["menu"]
        menu.delete(0, "end")
        for name in self.models:
            menu.add_command(label=name, command=lambda n=name: self.var_model.set(n))
        if self.var_model.get() not in self.models:
            self.var_model.set(MODEL_NAME)
        self._on_model_change()
        model = self.var_model.get() or MODEL_NAME
        if model in self.model_fields:
            self._set_status("已读取字段", GREEN)

    def _on_model_change(self) -> None:
        model = self.var_model.get() or MODEL_NAME
        if model in self.model_fields:
            self._build_mapping()
            self._set_status(
                f"已就绪：{len(self.model_fields[model])} 个字段", GREEN
            )
            return
        self._fields_loading = True
        self._set_status(f"正在从 Anki 读取「{model}」的字段…")

        def work() -> None:
            try:
                fields = self.anki.model_fields(model) or list(FIELDS)
            except Exception:
                fields = list(FIELDS)
            self.model_fields[model] = fields
            self._fields_loading = False

        threading.Thread(target=work, daemon=True).start()
        self._poll_fields(0)

    def _poll_fields(self, tries: int) -> None:
        if getattr(self, "_fields_loading", False):
            if tries < 60 and self.win.winfo_exists():
                self.win.after(100, lambda: self._poll_fields(tries + 1))
            return
        self._build_mapping()
        model = self.var_model.get() or MODEL_NAME
        fields = self.model_fields.get(model) or list(FIELDS)
        self._set_status(f"已读取 {len(fields)} 个字段", GREEN)

    def _build_mapping(self) -> None:
        for child in self.map_frame.winfo_children():
            child.destroy()
        model = self.var_model.get() or MODEL_NAME
        fields = self.model_fields.get(model) or list(FIELDS)
        saved_map = self.saved.get("fields") or {}
        self.mapping_vars = {}
        for index, field in enumerate(fields):
            tk.Label(
                self.map_frame, text=field, bg=PANEL, fg=TEXT,
                font=(FONT_FAMILY, 9), anchor="w", width=16,
            ).grid(row=index, column=0, sticky="w", padx=(4, 8), pady=2)
            default = saved_map.get(field) or (
                field if field in CUSTOM_SOURCES else ""
            )
            var = tk.StringVar(value=default or "（不填）")
            box = tk.OptionMenu(
                self.map_frame, var, "（不填）", *CUSTOM_SOURCES
            )
            box.configure(
                bg=PANEL, fg=TEXT, activebackground=PANEL, activeforeground=TEXT,
                relief="flat", highlightthickness=0, font=(FONT_FAMILY, 9),
                width=18, anchor="w",
            )
            box["menu"].configure(
                bg=PANEL, fg=TEXT, activebackground=ACCENT, activeforeground=ON_ACCENT
            )
            box.grid(row=index, column=1, sticky="w", pady=2)
            self.mapping_vars[field] = var

    # ------------------------------------------------------------------ 保存
    def save(self) -> None:
        model = self.var_model.get() or MODEL_NAME
        fields = {}
        for target, var in self.mapping_vars.items():
            source = var.get()
            if source and source != "（不填）":
                fields[target] = source
        data = {
            "enabled": bool(self.var_enabled.get()),
            "model": model,
            "fields": fields,
            "front": self.front_text.get("1.0", "end-1c"),
            "back": self.back_text.get("1.0", "end-1c"),
            "css": self.css_text.get("1.0", "end-1c"),
            "sync_templates": bool(self.var_sync.get()),
        }
        self.config.data["anki_custom"] = data
        self.config.save()
        self._set_status("已保存；下次同步 Anki 时生效", GREEN)
        if (
            data["enabled"]
            and data["sync_templates"]
            and model != MODEL_NAME
        ):
            if not messagebox.askyesno(
                "覆盖模板",
                f"「{model}」是你自己的笔记类型。\n\n"
                "继续只会替换它的第一个模板的 Front/Back/CSS，其他模板保留；"
                "已有卡片仍会重渲染。\n"
                "确定同步吗？",
                parent=self.win,
            ):
                data["sync_templates"] = False
                self.config.data["anki_custom"] = data
                self.config.save()
        if data["enabled"] and data["sync_templates"]:
            try:
                self.anki.update_custom_templates(
                    model, data["front"], data["back"], data["css"]
                )
                self._set_status("已保存并同步模板/CSS 到 Anki", GREEN)
            except Exception as exc:  # noqa: BLE001
                self._set_status(
                    f"已保存；模板同步失败（Anki 未运行？）：{exc}", RED
                )
        messagebox.showinfo(
            "Anki 卡片",
            "自定义卡片设置已保存。\n\n"
            f"笔记类型：{model}\n"
            f"字段映射：{len(fields)} 个\n"
            "英语将不再走 Dict2Anki。",
            parent=self.win,
        )
