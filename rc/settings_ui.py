"""设置窗口：API Key、模型、热键、语言 / 音色 / Anki deck、数据管理。"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, ttk

from . import __version__
from .i18n import lang_display_name, tr
from .settings_actions import SettingsActionsMixin
from .settings_pages import SettingsPagesMixin
from .uiutil import bind_defocus
from .popup import ACCENT, BG, BORDER, DIM, FONT_FAMILY, GREEN, MUTED, PANEL, RED, TEXT


VOICE_SAMPLES = {
    "en": "This is a test of the selected voice.",
    "it": "Ciao, questo è un test della voce selezionata.",
    "ja": "こんにちは、これは選択した音声のテストです。",
    "ru": "Привет, это проверка выбранного голоса.",
    "de": "Hallo, das ist ein Test der ausgewählten Stimme.",
    "es": "Hola, esta es una prueba de la voz seleccionada.",
    "pt": "Olá, este é um teste da voz selecionada.",
    "fr": "Ceci est un test de la voix sélectionnée.",
    "la": "Haec est probatio vocis selectae.",
}


COLOR_ROWS = [
    ("sense", "义项号"),
    ("pos", "词性"),
    ("label", "标签"),
    ("example", "例句"),
    ("section", "部分号"),
    ("text", "正文"),
    ("bg", "背景"),
]


class SettingsWindow(SettingsPagesMixin, SettingsActionsMixin):
    def __init__(self, root: tk.Tk, service, on_saved, on_quit, on_restart=None) -> None:
        self.root = root
        self.service = service
        self.config = service.config
        self.on_saved = on_saved
        self.on_quit = on_quit
        self.on_restart = on_restart
        self._lang_guard = False

        self.win = tk.Toplevel(root)
        self.win.withdraw()
        self.win.title("Interpres · 设置")
        self.win.configure(bg=BG)
        self.win.geometry("640x720")
        self.win.minsize(560, 560)
        self.win.attributes("-topmost", True)
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self._build()
        bind_defocus(self.win)
        self.win.update_idletasks()
        self.win.deiconify()
        self.win.after(100, lambda: self.win.attributes("-topmost", False))
        self._snapshot = self._form_snapshot()
        self.var_ui_lang.trace_add("write", self._on_ui_lang_changed)

    # ------------------------------------------------------------------ 构建
    def _make_page(self, key: str, title: str) -> None:
        page = tk.Frame(self._page_host, bg=BG)
        canvas = tk.Canvas(page, bg=BG, highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(page, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        body = tk.Frame(canvas, bg=BG)
        window_id = canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind(
            "<Configure>",
            lambda _e, c=canvas: c.configure(scrollregion=c.bbox("all")),
        )
        canvas.bind(
            "<Configure>",
            lambda e, c=canvas, w=window_id: c.itemconfigure(w, width=e.width),
        )
        inner = tk.Frame(body, bg=BG)
        inner.pack(fill="both", expand=True, padx=20, pady=(6, 16))
        self._page_title(inner, title)
        self._pages[key] = page
        self._page_bodies[key] = inner
        self._page_canvases[key] = canvas
        self._page_windows[key] = window_id

    def _page_title(self, parent, text: str) -> None:
        tk.Label(
            parent, text=text, bg=BG, fg=TEXT,
            font=(FONT_FAMILY, 14, "bold"), anchor="w",
        ).pack(fill="x", pady=(2, 8))

    def _show_page(self, key: str) -> None:
        for page in self._pages.values():
            page.pack_forget()
        page = self._pages.get(key)
        if page is not None:
            page.pack(fill="both", expand=True)
            canvas = self._page_canvases.get(key)
            if canvas is not None:
                self._active_canvas = canvas
                # 切页回到顶部，避免上一页的滚动位置或空白残留
                try:
                    canvas.update_idletasks()
                    body = self._page_bodies[key]
                    window_id = self._page_windows[key]
                    canvas.coords(window_id, 0, 0)
                    canvas.configure(
                        scrollregion=(0, 0, canvas.winfo_width(), body.winfo_reqheight())
                    )
                    canvas.yview_moveto(0)
                except (tk.TclError, KeyError):
                    pass
        for name, btn in self._nav_buttons.items():
            active = name == key
            btn.configure(
                bg=PANEL if active else "#10131a",
                fg=TEXT if active else DIM,
            )

    def _on_wheel(self, event) -> None:
        canvas = getattr(self, "_active_canvas", None)
        if canvas is None:
            return
        try:
            if not canvas.winfo_exists():
                return
            # 内容不足一屏时完全禁止滚动，避免顶部出现空白
            bbox = canvas.bbox("all")
            if not bbox or bbox[3] <= canvas.winfo_height():
                canvas.yview_moveto(0)
                return
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            # 不允许滚出内容范围，避免顶部出现空白
            first, _last = canvas.yview()
            if first < 0:
                canvas.yview_moveto(0)
        except tk.TclError:
            pass

    def _build(self) -> None:
        self._setup_ttk()
        self.win.geometry("920x720")
        self.win.minsize(820, 600)

        main = tk.Frame(self.win, bg=BG)
        main.pack(fill="both", expand=True)
        bottom = tk.Frame(self.win, bg=BG)
        bottom.pack(side="bottom", fill="x", padx=16, pady=(0, 10))
        self._button(bottom, "保存", self.save, primary=True).pack(side="right")
        self._button(bottom, "关闭", self.close).pack(side="right", padx=(0, 8))
        self._button(bottom, "退出程序", self._quit).pack(side="left")

        side = tk.Frame(main, bg="#10131a", width=190)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        content = tk.Frame(main, bg=BG)
        content.pack(side="left", fill="both", expand=True)

        head = tk.Frame(content, bg=BG)
        head.pack(fill="x", padx=(14, 0), pady=(10, 4))
        tk.Label(
            head, text="设置", bg=BG, fg=TEXT,
            font=(FONT_FAMILY, 15, "bold"), anchor="w",
        ).pack(side="left")
        tk.Label(
            head, text=f"Interpres v{__version__}", bg=BG, fg=DIM,
            font=(FONT_FAMILY, 8), anchor="w",
        ).pack(side="left", padx=(10, 0))

        self._page_host = tk.Frame(content, bg=BG)
        self._page_host.pack(fill="both", expand=True, padx=(10, 0), pady=(0, 4))
        self._pages: dict[str, tk.Frame] = {}
        self._page_bodies: dict[str, tk.Frame] = {}
        self._page_canvases: dict[str, tk.Canvas] = {}
        self._page_windows: dict[str, int] = {}
        self._nav_buttons: dict[str, tk.Label] = {}

        pages = (
            ("ai", "连接与 AI"),
            ("general", "通用"),
            ("langdict", "语言、词典与发音"),
            ("anki", "Anki"),
            ("about", "关于"),
        )
        for key, label in pages:
            btn = tk.Label(
                side, text=label, bg="#10131a", fg=DIM,
                font=(FONT_FAMILY, 10), anchor="w", padx=16, pady=9,
                cursor="hand2",
            )
            btn.pack(fill="x", pady=1)
            btn.bind("<Button-1>", lambda _e, k=key: self._show_page(k))
            self._nav_buttons[key] = btn
            self._make_page(key, label)

        self.win.bind("<MouseWheel>", self._on_wheel, add="+")
        self._show_page("ai")

        self._build_ai_section()
        self._build_hotkey_section()
        self._build_ui_section()
        self._build_dict_section()
        self._build_language_section()
        self._build_records_section()
        self._build_anki_section()
        self._build_about_section()
        self._build_prompts_section()

    def _rebuild_language_tables(self) -> None:
        self.lang_vars = {}
        languages = self.config.data.get("languages") or {}
        for code, entry in languages.items():
            self.lang_vars[code] = (
                tk.StringVar(value=entry.get("tts_voice", "")),
                tk.StringVar(value=entry.get("deck", "")),
            )
        self._fill_language_table()
        self._fill_deck_table()

    def _fill_language_table(self) -> None:
        table = self.lang_table
        for child in table.winfo_children():
            child.destroy()
        table.columnconfigure(1, weight=2)
        self._voice_boxes = []
        for col, text in enumerate(["语种", "音色", ""]):
            tk.Label(
                table, text=text, bg=PANEL, fg=DIM, font=(FONT_FAMILY, 8), anchor="w"
            ).grid(row=0, column=col, sticky="w", padx=12, pady=(8, 2))

        languages = self.config.data.get("languages") or {}
        for idx, (code, entry) in enumerate(languages.items(), start=1):
            voice_var, _deck_var = self.lang_vars[code]
            tk.Label(
                table,
                text=f"{lang_display_name(entry, code)}  {code}",
                bg=PANEL, fg=TEXT, font=(FONT_FAMILY, 9), anchor="w",
            ).grid(row=idx, column=0, sticky="w", padx=12, pady=3)

            cell = tk.Frame(table, bg=PANEL)
            cell.grid(row=idx, column=1, sticky="ew", padx=6, pady=3)
            engine = (entry.get("tts_engine") or "system").strip().lower()
            if engine == "edge":
                shown = "Edge · " + (voice_var.get() or "自动")
            elif engine == "command":
                shown = "自定义命令"
            else:
                shown = self._voice_display(voice_var.get())
            voice_label = tk.Label(
                cell, text=shown, bg=PANEL, fg=TEXT,
                font=(FONT_FAMILY, 9), anchor="w", padx=4, pady=2, cursor="hand2",
            )
            voice_label.pack(side="left", fill="x", expand=True)
            if engine == "system":
                voice_label.bind(
                    "<Button-1>",
                    lambda _e, v=voice_var, lb=voice_label: self._show_voice_menu(v, lb),
                )
                self._voice_boxes.append((voice_label, voice_var))
            else:
                voice_label.bind(
                    "<Button-1>", lambda _e, c=code: self.edit_language(c)
                )
            voice_label.bind("<Enter>", lambda _e, lb=voice_label: lb.configure(fg=ACCENT))
            voice_label.bind("<Leave>", lambda _e, lb=voice_label: lb.configure(fg=TEXT))

            tools = tk.Frame(table, bg=PANEL)
            tools.grid(row=idx, column=2, sticky="e", padx=(4, 10), pady=3)
            self._row_action(
                tools, "试听", lambda c=code: self.preview_voice(c), ACCENT
            ).pack(side="left")
            self._row_action(
                tools, "编辑", lambda c=code: self.edit_language(c), ACCENT
            ).pack(side="left")
            self._row_action(
                tools, "删除", lambda c=code: self.delete_language(c), "#ff8f8f"
            ).pack(side="left")

    def _fill_deck_table(self) -> None:
        table = self.deck_table
        for child in table.winfo_children():
            child.destroy()
        table.columnconfigure(1, weight=2)
        self._deck_boxes = []
        self._deck_menus = []
        for col, text in enumerate(["语种", "Anki 牌组", ""]):
            tk.Label(
                table, text=text, bg=PANEL, fg=DIM, font=(FONT_FAMILY, 8), anchor="w"
            ).grid(row=0, column=col, sticky="w", padx=12, pady=(8, 2))
        languages = self.config.data.get("languages") or {}
        for idx, (code, entry) in enumerate(languages.items(), start=1):
            _voice_var, deck_var = self.lang_vars[code]
            tk.Label(
                table,
                text=f"{lang_display_name(entry, code)}  {code}",
                bg=PANEL, fg=TEXT, font=(FONT_FAMILY, 9), anchor="w",
            ).grid(row=idx, column=0, sticky="w", padx=12, pady=3)
            cell = tk.Frame(table, bg=PANEL)
            cell.grid(row=idx, column=1, sticky="ew", padx=6, pady=3)
            deck_entry = tk.Entry(
                cell, textvariable=deck_var, bg=PANEL, fg=TEXT,
                insertbackground=TEXT, relief="flat", font=(FONT_FAMILY, 9),
            )
            deck_entry.pack(side="left", fill="x", expand=True, ipady=3, padx=(4, 0))
            deck_pick = tk.Label(
                cell, text="▾", bg=PANEL, fg=DIM,
                font=(FONT_FAMILY, 11), cursor="hand2", padx=6,
            )
            deck_pick.pack(side="right")
            deck_menu = tk.Menu(
                self.win, tearoff=0, bg=PANEL, fg=TEXT,
                activebackground=ACCENT, activeforeground="#10131a",
                font=(FONT_FAMILY, 9),
            )
            deck_pick.bind(
                "<Button-1>",
                lambda _e, m=deck_menu, v=deck_var, w=deck_pick: self._show_deck_menu(m, v, w),
            )
            self._deck_boxes.append(deck_entry)
            self._deck_menus.append(deck_menu)
            tools = tk.Frame(table, bg=PANEL)
            tools.grid(row=idx, column=2, sticky="e", padx=(4, 10), pady=3)
            self._row_action(
                tools, "编辑", lambda c=code: self.edit_language(c), ACCENT
            ).pack(side="left")

    def add_language(self) -> None:
        from .language_dialog import LanguageDialog

        dialog = LanguageDialog(
            self.win, self._voice_names, edge_provider=self._edge_voice_provider
        )
        self.win.wait_window(dialog.win)
        if not dialog.result:
            return
        code = dialog.result["code"]
        if code in (self.config.data.get("languages") or {}):
            messagebox.showinfo(
                "添加语言", f"「{code}」已经存在了。", parent=self.win
            )
            return
        self.service.set_language(code, dialog.result)
        self._rebuild_language_tables()
        self._set_lang_status(f"已添加语言：{lang_display_name(dialog.result, code)}")

    def edit_language(self, code: str) -> None:
        from .language_dialog import LanguageDialog

        entry = (self.config.data.get("languages") or {}).get(code) or {}
        dialog = LanguageDialog(
            self.win, self._voice_names, code=code, entry=entry, edit=True,
            edge_provider=self._edge_voice_provider,
        )
        self.win.wait_window(dialog.win)
        if not dialog.result:
            return
        self.service.set_language(code, dialog.result)
        self._rebuild_language_tables()
        self._set_lang_status(f"已保存语言：{lang_display_name(dialog.result, code)}")

    def delete_language(self, code: str) -> None:
        languages = self.config.data.get("languages") or {}
        entry = languages.get(code) or {}
        name = lang_display_name(entry, code)
        words, books = self.service.language_size(code)
        has_data = words > 0 or books > 0
        if has_data and bool(self.config.get("lang_delete_lock", True)):
            self._set_lang_status(
                f"已开启删除保险：{name} 还有 {words} 个生词、{books} 本书，不能删", error=True
            )
            messagebox.showinfo(
                "删除语言",
                f"「{name}」还有 {words} 个生词、{books} 本书。\n\n"
                "「删除保险」处于开启状态，所以不能删除。\n"
                "可以先清理数据，或到设置里关闭保险（会改为只提示）。",
                parent=self.win,
            )
            return
        if has_data and bool(self.config.get("lang_delete_warn", True)):
            from .language_dialog import ConfirmDeleteDialog

            dialog = ConfirmDeleteDialog(
                self.win,
                "删除语言",
                f"「{name}」还有 {words} 个生词、{books} 本书。\n"
                "删除后语言配置消失，生词本和书籍数据会保留（变成未分组）。\n\n确定删除？",
                show_check=True,
            )
            self.win.wait_window(dialog.win)
            if not dialog.confirmed:
                return
            if dialog.suppress:
                self.config.data["lang_delete_warn"] = False
                self.config.save()
        self.service.remove_language(code)
        self._rebuild_language_tables()
        self._set_lang_status(f"已删除语言：{name}")

    def _set_lang_status(self, text: str, error: bool = False) -> None:
        try:
            self.lang_status.configure(
                text=text[:100], fg="#ff8080" if error else GREEN
            )
        except Exception:
            pass

    def _restart_stream_preview(self) -> None:
        """按当前输入的速度，重新把示例文字“写”一遍。"""
        job = getattr(self, "_preview_job", None)
        if job:
            try:
                self.win.after_cancel(job)
            except Exception:
                pass
        self._preview_job = None
        try:
            speed = int(self.var_stream_speed.get().strip() or 60)
        except Exception:
            speed = 60
        speed = max(5, min(400, speed))
        self._preview_index = 0
        try:
            self.stream_preview.configure(text="")
        except Exception:
            return
        self._preview_tick(speed)

    def _preview_tick(self, speed: int) -> None:
        self._preview_job = None
        try:
            if not self.stream_preview.winfo_exists():
                return
        except Exception:
            return
        text = tr(getattr(self, "_preview_text", ""))
        index = getattr(self, "_preview_index", 0)
        if index >= len(text):
            return
        step = max(1, int(speed * 0.033))
        index = min(len(text), index + step)
        self._preview_index = index
        try:
            self.stream_preview.configure(text=text[:index])
        except Exception:
            return
        if index < len(text):
            self._preview_job = self.win.after(33, lambda: self._preview_tick(speed))

    def _fill_prompt(self, widget, text: str) -> None:
        widget.delete("1.0", "end")
        widget.insert("1.0", text)

    def _clear_prompt(self, widget) -> None:
        widget.delete("1.0", "end")

    def _prompt_value(self, widget, default: str) -> str:
        value = widget.get("1.0", "end-1c").strip()
        return "" if value == default.strip() else value

    def preview_voice(self, code: str) -> None:
        """用当前选中的音色念一句示例。"""
        voice = self.lang_vars[code][0].get()
        text = VOICE_SAMPLES.get(code, "This is a test of the selected voice.")
        self.test_label.configure(text="试听中…", fg=MUTED)

        self._preview_ready = False
        self._preview_result = ("", "", MUTED)

        def run() -> None:
            try:
                engine = self.service.tts.engine_for(code)
                if engine == "system":
                    self.service.tts.speak_with(text, voice)
                    label = voice or "系统默认音色"
                else:
                    self.service.speak(text, code)
                    label = "Edge 在线音色" if engine == "edge" else "自定义命令"
                self._preview_result = (f"试听：{label}", "", GREEN)
            except Exception as exc:  # noqa: BLE001
                import logging

                logging.getLogger("tts").exception("试听失败")
                msg = str(exc)[:60]
                self._preview_result = ("", f"试听失败：{msg}", RED)
            self._preview_ready = True

        threading.Thread(target=run, daemon=True).start()
        self._poll_preview(0)

    def _poll_preview(self, tries: int) -> None:
        try:
            if not self.win.winfo_exists():
                return
        except tk.TclError:
            return
        if not getattr(self, "_preview_ready", False):
            if tries < 600:
                self.win.after(100, lambda: self._poll_preview(tries + 1))
            return
        ok_text, err_text, color = self._preview_result
        try:
            self.test_label.configure(text=err_text or ok_text, fg=color)
        except tk.TclError:
            pass

    def _load_voices(self) -> None:
        import threading

        self._voices_ready = False
        self._voices_result: list[str] = []

        def run() -> None:
            try:
                self._voices_result = [v["name"] for v in self.service.tts.voices()]
            except Exception:
                self._voices_result = []
            self._voices_ready = True

        threading.Thread(target=run, daemon=True).start()

    def _check_background_loads(self) -> None:
        """主线程轮询后台数据，加载好了就应用（避免线程里碰 Tk）。"""
        try:
            if not self.win.winfo_exists():
                return
        except tk.TclError:
            return
        applied = getattr(self, "_loads_applied", {})
        wait = False
        if not applied.get("voices"):
            if getattr(self, "_voices_ready", False):
                if getattr(self, "_voices_result", None):
                    self._apply_voices(self._voices_result)
                applied["voices"] = True
            else:
                wait = True
        if not applied.get("decks"):
            if getattr(self, "_decks_ready", False):
                self._apply_decks(getattr(self, "_decks_result", []))
                applied["decks"] = True
            else:
                wait = True
        self._loads_applied = applied
        if wait:
            self.win.after(150, self._check_background_loads)

    def _poll_voices(self, tries: int) -> None:
        try:
            if not self.win.winfo_exists():
                return
        except tk.TclError:
            return
        if not getattr(self, "_voices_ready", False):
            if tries < 150:
                self.win.after(100, lambda: self._poll_voices(tries + 1))
            return
        if self._voices_result:
            self._apply_voices(self._voices_result)

    def _row_action(self, parent, text, command, hover_fg):
        label = tk.Label(
            parent, text=text, bg=PANEL, fg=DIM, font=(FONT_FAMILY, 8),
            cursor="hand2", padx=4,
        )
        label.bind("<Button-1>", lambda _e: command())
        label.bind("<Enter>", lambda _e: label.configure(fg=hover_fg))
        label.bind("<Leave>", lambda _e: label.configure(fg=DIM))
        return label

    def _edge_voice_provider(self, lang: str) -> list[dict]:
        try:
            return self.service.tts.edge_voice_choices(lang)
        except Exception:
            return []

    def _voice_display(self, name: str) -> str:
        name = (name or "").strip()
        if not name:
            return tr("（自动匹配）")
        return name if len(name) <= 22 else name[:21] + "…"

    def _show_voice_menu(self, var, label) -> None:
        menu = tk.Menu(
            self.win, tearoff=0, bg=PANEL, fg=TEXT,
            activebackground=ACCENT, activeforeground="#10131a",
            font=(FONT_FAMILY, 9),
        )

        def choose(value: str) -> None:
            var.set(value)
            label.configure(text=self._voice_display(value))

        menu.add_command(label="（自动匹配）", command=lambda: choose(""))
        for name in getattr(self, "_voice_names", []):
            menu.add_command(label=name, command=lambda n=name: choose(n))
        try:
            menu.tk_popup(
                label.winfo_rootx(), label.winfo_rooty() + label.winfo_height()
            )
        finally:
            menu.grab_release()

    def _apply_voices(self, voices: list[str]) -> None:
        self._voice_names = list(voices)
        for label, var in getattr(self, "_voice_boxes", []):
            try:
                label.configure(text=self._voice_display(var.get()))
            except tk.TclError:
                continue

    def _section(self, parent, text: str) -> None:
        tk.Label(
            parent, text=text, bg=BG, fg=ACCENT, font=(FONT_FAMILY, 9, "bold"), anchor="w"
        ).pack(fill="x", pady=(6, 0))

    def _setup_ttk(self) -> None:
        style = ttk.Style(self.win)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "TCombobox",
            fieldbackground=PANEL,
            background=PANEL,
            foreground=TEXT,
            arrowcolor=MUTED,
            bordercolor=BORDER,
            lightcolor=PANEL,
            darkcolor=PANEL,
            insertcolor=TEXT,
        )
        self.win.option_add("*TCombobox*Listbox.background", PANEL)
        self.win.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.win.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        self.win.option_add("*TCombobox*Listbox.selectForeground", "#10131a")

    def _show_deck_menu(self, menu, var, widget) -> None:
        menu.delete(0, "end")
        names = list(getattr(self, "_deck_names", []) or [])
        if not names:
            menu.add_command(label="（还没读取到 Anki 牌组）", state="disabled")
        for name in names:
            menu.add_command(label=name, command=lambda n=name: var.set(n))
        try:
            menu.tk_popup(widget.winfo_rootx(), widget.winfo_rooty() + widget.winfo_height())
        finally:
            menu.grab_release()

    def _load_decks(self) -> None:
        self._decks_ready = False
        self._decks_result: list[str] = []

        def run() -> None:
            try:
                self._decks_result = list(self.service.anki.deck_names() or [])
            except Exception:
                self._decks_result = []
            self._decks_ready = True

        threading.Thread(target=run, daemon=True).start()

    def _poll_decks(self, tries: int) -> None:
        try:
            if not self.win.winfo_exists():
                return
        except tk.TclError:
            return
        if not getattr(self, "_decks_ready", False):
            if tries < 150:
                self.win.after(100, lambda: self._poll_decks(tries + 1))
            return
        self._apply_decks(self._decks_result)

    def _apply_decks(self, decks: list[str]) -> None:
        try:
            if not self.deck_status.winfo_exists():
                return
        except tk.TclError:
            return
        if not decks:
            self.deck_status.configure(text="没连上 Anki（未运行？），可以直接手输牌组名", fg=RED)
            return
        self.deck_status.configure(text=f"已从 Anki 读取 {len(decks)} 个牌组（也可以直接改名）", fg=MUTED)
        self._deck_names = list(decks)
        for box in list(self._deck_boxes):
            try:
                current = box.get()
            except tk.TclError:
                current = ""
            if current and current not in self._deck_names:
                self._deck_names.insert(0, current)

    def _field(self, parent, row: int, label: str, var: tk.StringVar, show: str = "") -> None:
        tk.Label(
            parent, text=label, bg=PANEL, fg=DIM, font=(FONT_FAMILY, 9), anchor="w", width=14
        ).grid(row=row, column=0, sticky="w", padx=(12, 4), pady=6)
        entry = tk.Entry(
            parent,
            textvariable=var,
            bg="#1b1e26",
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            highlightthickness=1,
            highlightbackground="#2c313c",
            highlightcolor=ACCENT,
            font=(FONT_FAMILY, 9),
            show=show,
        )
        entry.grid(row=row, column=1, sticky="ew", padx=(0, 12), pady=6)

    def _button(self, parent, text: str, command, primary: bool = False) -> tk.Label:
        bg = ACCENT if primary else PANEL
        fg = "#10131a" if primary else TEXT
        label = tk.Label(
            parent,
            text=text,
            bg=bg,
            fg=fg,
            font=(FONT_FAMILY, 9),
            padx=12,
            pady=5,
            cursor="hand2",
        )
        label.bind("<Button-1>", lambda _e: command())
        label.bind("<Enter>", lambda _e: label.configure(bg="#8ab4ff" if primary else "#313643"))
        label.bind("<Leave>", lambda _e: label.configure(bg=bg))
        return label

    # ------------------------------------------------------------------ 动作
def _style_menu(widget: tk.OptionMenu) -> None:
    widget.configure(
        bg=PANEL, fg=TEXT, activebackground=PANEL, activeforeground=TEXT, relief="flat",
        highlightthickness=0, font=(FONT_FAMILY, 9), anchor="w",
    )
    widget["menu"].configure(bg=PANEL, fg=TEXT, activebackground=ACCENT, activeforeground="#10131a")
