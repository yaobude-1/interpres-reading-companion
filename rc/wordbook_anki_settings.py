"""按词本自定义 Anki 卡片：跟随全局 / 独立笔记类型 / 选已有类型。"""

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
from .i18n import tr
from .popup import ACCENT, BG, DIM, FONT_FAMILY, GREEN, MUTED, PANEL, RED, TEXT


class WordbookAnkiSettings:
    def __init__(self, parent, service, book: dict) -> None:
        self.service = service
        self.config = service.config
        self.book = book
        self.book_id = int(book["id"])
        saved = service.wordbook_anki(self.book_id)
        self.saved = saved
        self.mode = tk.StringVar(value=(saved.get("mode") or "inherit"))
        self.model = tk.StringVar(value=str(saved.get("model") or ""))
        self.models: list[str] = [MODEL_NAME]
        self.model_fields: dict[str, list[str]] = {MODEL_NAME: list(FIELDS)}
        self.mapping_vars: dict[str, tk.StringVar] = {}

        self.win = tk.Toplevel(parent)
        self.win.title(f"Anki 设置 · {book.get('name') or ''}")
        self.win.configure(bg=BG)
        self.win.geometry("820x700")
        self.win.minsize(720, 560)
        self.win.transient(parent)
        self.win.grab_set()

        bar = tk.Frame(self.win, bg=BG)
        bar.pack(side="bottom", fill="x", padx=16, pady=(0, 10))
        main = tk.Frame(self.win, bg=BG)
        main.pack(fill="both", expand=True)

        canvas = tk.Canvas(main, bg=BG, highlightthickness=0, bd=0)
        scroll = tk.Scrollbar(main, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y", padx=(0, 6))
        outer = tk.Frame(canvas, bg=BG)
        window_id = canvas.create_window((0, 0), window=outer, anchor="nw")
        outer.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window_id, width=e.width))
        self.win.bind(
            "<MouseWheel>",
            lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"),
            add="+",
        )

        tk.Label(
            outer, text=f"Anki 卡片 · {book.get('name') or ''}", bg=BG, fg=TEXT,
            font=(FONT_FAMILY, 14, "bold"), anchor="w",
        ).pack(fill="x")
        tk.Label(
            outer,
            text=(
                "牌组沿用词本设置里的牌组。模板属于笔记类型：\n"
                "• 跟随全局：与设置里的全局模板共用\n"
                "• 独立：自动创建「Interpres · 词本名」，模板只属于这本\n"
                "• 选已有类型：与其它使用该类型的词本共享模板"
            ),
            bg=BG, fg=DIM, font=(FONT_FAMILY, 9), anchor="w", justify="left",
            wraplength=760,
        ).pack(fill="x", pady=(2, 8))

        mode_box = tk.LabelFrame(
            outer, text="模式", bg=PANEL, fg=TEXT, font=(FONT_FAMILY, 9),
            bd=0, padx=8, pady=6,
        )
        mode_box.pack(fill="x", pady=(0, 8))
        for value, label in (
            ("inherit", "跟随全局默认（与其它词本共享）"),
            ("independent", "独立模板（自动创建 Interpres · 词本名）"),
            ("custom", "选择已有笔记类型"),
        ):
            tk.Radiobutton(
                mode_box, text=label, value=value, variable=self.mode,
                bg=PANEL, fg=TEXT, selectcolor="#2f3440", activebackground=PANEL,
                activeforeground=TEXT, font=(FONT_FAMILY, 9), anchor="w",
                command=self._on_mode_change,
            ).pack(fill="x")

        model_row = tk.Frame(outer, bg=BG)
        model_row.pack(fill="x", pady=(0, 6))
        tk.Label(model_row, text="笔记类型", bg=BG, fg=DIM, font=(FONT_FAMILY, 9)).pack(side="left")
        self.model_label = tk.Label(
            model_row, text="", bg=PANEL, fg=TEXT, font=(FONT_FAMILY, 9),
            anchor="w", padx=6, pady=3, width=36,
        )
        self.model_label.pack(side="left", padx=(8, 0))
        self.model_box = tk.OptionMenu(model_row, self.model, MODEL_NAME)
        self.model_box.configure(
            bg=PANEL, fg=TEXT, activebackground=PANEL, activeforeground=TEXT,
            relief="flat", highlightthickness=0, font=(FONT_FAMILY, 9), width=34,
            anchor="w",
        )
        self.model_box["menu"].configure(
            bg=PANEL, fg=TEXT, activebackground=ACCENT, activeforeground="#10131a"
        )
        self.model_var_trace = self.model.trace_add(
            "write", lambda *_: self._on_model_change()
        )

        self.map_box = tk.LabelFrame(
            outer, text="字段映射", bg=PANEL, fg=TEXT, font=(FONT_FAMILY, 9),
            bd=0, padx=8, pady=6,
        )
        self.map_frame = tk.Frame(self.map_box, bg=PANEL)
        self.map_frame.pack(fill="x")

        self.template_frame = tk.Frame(outer, bg=BG)
        self.front_text = self._editor(self.template_frame, "Front 模板", DEFAULT_FRONT, 5)
        self.back_text = self._editor(self.template_frame, "Back 模板", DEFAULT_BACK, 5)
        self.css_text = self._editor(self.template_frame, "CSS", DEFAULT_CSS, 6)

        self.var_sync = tk.BooleanVar(value=bool(saved.get("sync_templates", True)))
        self.sync_check = tk.Checkbutton(
            outer, text="同步模板/CSS 到 Anki（已有卡片会重新渲染）",
            variable=self.var_sync, bg=BG, fg=TEXT, selectcolor="#2f3440",
            activebackground=BG, activeforeground=TEXT, font=(FONT_FAMILY, 9),
            anchor="w",
        )
        self.sync_check.pack(fill="x", pady=(4, 0))

        self.hint = tk.Label(
            outer, text="", bg=BG, fg=MUTED, font=(FONT_FAMILY, 8),
            anchor="w", justify="left", wraplength=760,
        )
        self.hint.pack(fill="x", pady=(6, 0))

        self._button(bar, "保存", self.save, primary=True).pack(side="right")
        self._button(bar, "取消", self.win.destroy).pack(side="right", padx=(0, 8))
        self._button(bar, "填入默认模板", self._fill_defaults).pack(side="left")

        self._load_models()
        self._on_mode_change()

    # ------------------------------------------------------------------ UI
    def _editor(self, parent, label, default, height):
        tk.Label(parent, text=label, bg=BG, fg=DIM, font=(FONT_FAMILY, 8), anchor="w").pack(
            fill="x", pady=(4, 0)
        )
        text = tk.Text(
            parent, height=height, bg=PANEL, fg=TEXT, insertbackground=TEXT,
            relief="flat", font=("Consolas", 8), wrap="word", padx=6, pady=4,
        )
        text.pack(fill="x")
        text.insert("1.0", default)
        return text

    def _button(self, parent, text, command, primary=False):
        label = tk.Label(
            parent, text=text, bg=ACCENT if primary else PANEL,
            fg="#10131a" if primary else TEXT, font=(FONT_FAMILY, 9),
            padx=14, pady=5, cursor="hand2",
        )
        label.bind("<Button-1>", lambda _e: command())
        return label

    def _set_hint(self, text: str, color=MUTED):
        try:
            self.hint.configure(text=text, fg=color)
        except tk.TclError:
            pass

    def _fill_defaults(self) -> None:
        for widget, value in (
            (self.front_text, DEFAULT_FRONT),
            (self.back_text, DEFAULT_BACK),
            (self.css_text, DEFAULT_CSS),
        ):
            widget.delete("1.0", "end")
            widget.insert("1.0", value)
        self._set_hint("已填入内置默认模板")

    # ------------------------------------------------------------------ 数据
    def _load_models(self) -> None:
        self._models_ready = False

        def work() -> None:
            try:
                self.models = self.service.anki.model_names() or [MODEL_NAME]
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
            menu.add_command(label=name, command=lambda n=name: self.model.set(n))
        self._on_mode_change()

    def _independent_model(self) -> str:
        return f"Interpres · {self.book.get('name') or '词本'}"

    def _on_mode_change(self) -> None:
        mode = self.mode.get()
        if mode == "inherit":
            global_cfg = self.config.get("anki_custom") or {}
            if global_cfg.get("enabled"):
                label = f"全局自定义：{global_cfg.get('model') or 'Interpres'}"
            elif (self.book.get("lang") or "") == "en":
                label = "全局默认：英语 Dict2Anki / 其他语言 Interpres"
            else:
                label = "全局默认：Interpres"
            self.model_label.configure(text=label)
            self.model_label.pack(side="left", padx=(8, 0))
            self.model_box.pack_forget()
            self.map_box.pack_forget()
            self.template_frame.pack_forget()
            self.sync_check.pack_forget()
            self._set_hint("使用设置 →「卡片模板…」里的全局配置；要单独改就切到独立或已有类型。")
            return
        if mode == "independent":
            self.model.set(self._independent_model())
            self.model_label.pack_forget()
            self.model_box.pack(side="left", padx=(8, 0))
        else:
            self.model_label.pack_forget()
            self.model_box.pack(side="left", padx=(8, 0))
            if not self.model.get():
                self.model.set(self.models[0] if self.models else MODEL_NAME)
        self.map_box.pack(fill="x", pady=(0, 8))
        self.template_frame.pack(fill="x")
        self.sync_check.pack(fill="x", pady=(4, 0))
        if mode == "independent":
            self._set_hint(
                "独立模板只属于这本词本；首次同步会自动在 Anki 创建该笔记类型。"
            )
        else:
            self._set_hint(
                "与其它使用这个笔记类型的词本共享模板；修改会影响它们。"
            )
        self._on_model_change()

    def _on_model_change(self) -> None:
        mode = self.mode.get()
        if mode == "inherit":
            return
        model = self.model.get() or self._independent_model()
        if model in self.model_fields:
            self._build_mapping()
            return
        self._fields_loading = True

        def work() -> None:
            try:
                fields = self.service.anki.model_fields(model) or list(FIELDS)
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

    def _build_mapping(self) -> None:
        for child in self.map_frame.winfo_children():
            child.destroy()
        model = self.model.get() or self._independent_model()
        fields = self.model_fields.get(model) or list(FIELDS)
        saved_map = self.saved.get("fields") or {}
        self.mapping_vars = {}
        for index, field in enumerate(fields):
            tk.Label(
                self.map_frame, text=field, bg=PANEL, fg=TEXT,
                font=(FONT_FAMILY, 9), anchor="w", width=16,
            ).grid(row=index, column=0, sticky="w", padx=(4, 8), pady=2)
            default = saved_map.get(field) or (field if field in CUSTOM_SOURCES else "")
            var = tk.StringVar(value=default or "（不填）")
            box = tk.OptionMenu(self.map_frame, var, "（不填）", *CUSTOM_SOURCES)
            box.configure(
                bg=PANEL, fg=TEXT, activebackground=PANEL, activeforeground=TEXT,
                relief="flat", highlightthickness=0, font=(FONT_FAMILY, 9),
                width=18, anchor="w",
            )
            box["menu"].configure(
                bg=PANEL, fg=TEXT, activebackground=ACCENT, activeforeground="#10131a"
            )
            box.grid(row=index, column=1, sticky="w", pady=2)
            self.mapping_vars[field] = var

    # ------------------------------------------------------------------ 保存
    def save(self) -> None:
        mode = self.mode.get()
        if mode == "inherit":
            self.service.set_wordbook_anki(self.book_id, {"mode": "inherit"})
            self.config.save()
            self.win.destroy()
            return
        model = self.model.get().strip() or self._independent_model()
        fields = {}
        for target, var in self.mapping_vars.items():
            source = var.get()
            if source and source != "（不填）":
                fields[target] = source
        sync = bool(self.var_sync.get())
        data = {
            "mode": mode,
            "model": model,
            "fields": fields,
            "sync_templates": sync,
        }
        self.service.set_wordbook_anki(self.book_id, data)
        models = self.config.data.setdefault("anki_models", {})
        models[model] = {
            "front": self.front_text.get("1.0", "end-1c"),
            "back": self.back_text.get("1.0", "end-1c"),
            "css": self.css_text.get("1.0", "end-1c"),
        }
        self.config.save()
        if sync:
            others = 0
            for book in self.service.wordbooks():
                if int(book["id"]) == self.book_id:
                    continue
                cfg = self.service.wordbook_anki(int(book["id"]))
                if (cfg.get("mode") or "inherit") != "inherit" and (cfg.get("model") or "") == model:
                    others += 1
            if others:
                messagebox.showinfo(
                    "模板共享",
                    f"还有 {others} 本词本也使用「{model}」。\n修改模板会影响它们。",
                    parent=self.win,
                )
            try:
                self.service.anki.update_custom_templates(
                    model,
                    models[model]["front"],
                    models[model]["back"],
                    models[model]["css"],
                )
                self._set_hint("已保存并同步模板/CSS 到 Anki", GREEN)
            except Exception:
                self._set_hint("已保存；Anki 未运行，模板将在下次同步时应用", MUTED)
        self.win.destroy()
