"""设置窗口：API Key、模型、热键、语言 / 音色 / Anki deck、数据管理。"""

from __future__ import annotations

import os
import subprocess
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from . import __version__
from .llm import SYSTEM_PROMPT as _ZH_TRANSLATE_PROMPT
from .netpolicy import validate_base_url
from .prompts_en import (
    CHAT_PERSONA_EN as _EN_CHAT_PERSONA,
    CHAT_RULES_EN as _EN_CHAT_RULES,
    SYSTEM_PROMPT_EN as _EN_TRANSLATE_PROMPT,
)
from .service import (
    CHAT_PERSONA_DEFAULT as _ZH_CHAT_PERSONA,
    CHAT_RULES_DEFAULT as _ZH_CHAT_RULES,
)
from .i18n import tr
from .uiutil import bind_defocus
from .popup import ACCENT, BG, BORDER, DIM, FONT_FAMILY, GREEN, MUTED, PANEL, RED, TEXT


def default_translate_prompt() -> str:
    from . import i18n

    return _EN_TRANSLATE_PROMPT if i18n.LANGUAGE == "en" else _ZH_TRANSLATE_PROMPT


def default_chat_persona() -> str:
    from . import i18n

    return _EN_CHAT_PERSONA if i18n.LANGUAGE == "en" else _ZH_CHAT_PERSONA


def default_chat_rules() -> str:
    from . import i18n

    return _EN_CHAT_RULES if i18n.LANGUAGE == "en" else _ZH_CHAT_RULES


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


class SettingsWindow:
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

        self._build_ai_page()
        self._build_hotkey_page()
        self._build_ui_page()
        self._build_dict_page()
        self._build_language_page()
        self._build_records_page()
        self._build_anki_page()
        self._build_about_page()
        self._build_prompts_page()

    def _build_ai_page(self) -> None:
        outer = self._page_bodies["ai"]
        self._section(outer, "模型与连接")
        grid = tk.Frame(outer, bg=PANEL)
        grid.pack(fill="x", pady=(4, 12))
        grid.columnconfigure(1, weight=1)

        api = self.config.api
        self.var_key = tk.StringVar(value=self.config.api_key)
        self.var_base = tk.StringVar(value=api.get("base_url", "https://api.deepseek.com/v1"))
        self.var_model = tk.StringVar(value=api.get("model", "deepseek-chat"))

        self._field(grid, 0, "API Key", self.var_key, show="•")
        self._field(grid, 1, "服务地址", self.var_base)
        self._field(grid, 2, "模型", self.var_model)

        key_error = self.config.api_key_error
        if key_error:
            tk.Label(
                grid,
                text=key_error,
                bg=PANEL, fg=RED, font=(FONT_FAMILY, 8), anchor="w", justify="left",
                wraplength=520,
            ).grid(row=3, column=0, columnspan=3, sticky="ew", padx=12, pady=(0, 4))

        tk.Label(
            grid,
            text="自定义服务地址会把选中的文本和 API Key 发送到该服务器；远程地址必须使用 HTTPS。",
            bg=PANEL, fg=MUTED, font=(FONT_FAMILY, 8), anchor="w", justify="left",
        ).grid(row=4, column=0, columnspan=3, sticky="ew", padx=12, pady=(0, 4))

        row = tk.Frame(grid, bg=PANEL)
        row.grid(row=5, column=0, columnspan=2, sticky="ew", padx=12, pady=(4, 10))
        self.test_label = tk.Label(
            row, text="", bg=PANEL, fg=MUTED, font=(FONT_FAMILY, 9), anchor="w"
        )
        self.test_label.pack(side="left")
        self._button(row, "测试连接", self.test_api).pack(side="right")
        self._button(
            row, "去创建 Key", lambda: _open("https://platform.deepseek.com/api_keys")
        ).pack(side="right", padx=(0, 8))

    def _build_hotkey_page(self) -> None:
        outer = self._page_bodies["general"]
        self._section(outer, "热键与划词")
        hot = tk.Frame(outer, bg=PANEL)
        hot.pack(fill="x", pady=(4, 12))
        self.var_hotkey = tk.StringVar(value=self.config.get("hotkey", "ctrl+alt+t"))
        self.var_settings_hotkey = tk.StringVar(
            value=self.config.get("settings_hotkey", "ctrl+alt+s")
        )
        self._field(hot, 0, "划词翻译", self.var_hotkey)
        self._field(hot, 1, "打开面板", self.var_settings_hotkey)

        hot_btns = tk.Frame(hot, bg=PANEL)
        hot_btns.grid(row=2, column=0, columnspan=4, sticky="w", padx=12, pady=(4, 10))
        self._button(hot_btns, "划词按钮设置…", self.open_selection_settings).pack(side="left")
        self._button(hot_btns, "原版配色…", self.open_entry_colors).pack(side="left", padx=(8, 0))
        tk.Label(
            hot_btns,
            text="拖选后自动出现「译」按钮，可关、可换颜色和透明度",
            bg=PANEL,
            fg=DIM,
            font=(FONT_FAMILY, 8),
        ).pack(side="left", padx=(10, 0))

    def _build_ui_page(self) -> None:
        outer = self._page_bodies["general"]
        self._section(outer, "主界面")
        ui_row = tk.Frame(outer, bg=BG)
        ui_row.pack(fill="x", pady=(0, 6))
        tk.Label(
            ui_row, text="界面语言", bg=BG, fg=DIM, font=(FONT_FAMILY, 9)
        ).pack(side="left")
        self.var_ui_lang = tk.StringVar(
            value="中文" if str(self.config.get("ui_lang", "zh")) == "zh" else "English"
        )
        ui_box = tk.OptionMenu(ui_row, self.var_ui_lang, "中文", "English")
        ui_box.configure(
            bg=PANEL, fg=TEXT, activebackground=PANEL, activeforeground=TEXT,
            relief="flat", highlightthickness=0, font=(FONT_FAMILY, 9), width=12,
            anchor="w",
        )
        ui_box["menu"].configure(
            bg=PANEL, fg=TEXT, activebackground=ACCENT, activeforeground="#10131a"
        )
        ui_box.pack(side="left", padx=(8, 0))
        tk.Label(
            ui_row, text="切换后会自动重启并应用", bg=BG, fg=DIM,
            font=(FONT_FAMILY, 8),
        ).pack(side="left", padx=(10, 0))

        beh = tk.Frame(outer, bg=PANEL)
        beh.pack(fill="x", pady=(4, 12))
        self.var_follow_book = tk.BooleanVar(
            value=bool(self.config.get("auto_follow_book", False))
        )
        tk.Checkbutton(
            beh,
            text="自动跟随当前书籍（在阅读器里换书时跟着切；关掉则手动切换）",
            variable=self.var_follow_book,
            bg=PANEL,
            fg=TEXT,
            selectcolor="#2f3440",
            activebackground=PANEL,
            activeforeground=TEXT,
            font=(FONT_FAMILY, 9),
            anchor="w",
        ).grid(row=0, column=0, columnspan=4, sticky="w", padx=10, pady=(8, 2))

        self.var_quit_on_close = tk.BooleanVar(
            value=bool(self.config.get("quit_on_panel_close", True))
        )
        tk.Checkbutton(
            beh,
            text="按 Esc / 右上角 ✕ 直接退出程序（不勾则隐藏到托盘，可从托盘打开）",
            variable=self.var_quit_on_close,
            bg=PANEL,
            fg=TEXT,
            selectcolor="#2f3440",
            activebackground=PANEL,
            activeforeground=TEXT,
            font=(FONT_FAMILY, 9),
            anchor="w",
        ).grid(row=1, column=0, columnspan=4, sticky="w", padx=10, pady=(0, 6))

        book_row = tk.Frame(beh, bg=PANEL)
        book_row.grid(row=2, column=0, columnspan=4, sticky="w", padx=12, pady=(0, 10))
        tk.Label(
            book_row, text="按书名过滤", bg=PANEL, fg=DIM, font=(FONT_FAMILY, 8)
        ).pack(side="left")
        self._button(book_row, "书名过滤…", self.open_book_filter).pack(
            side="left", padx=(8, 0)
        )
        tk.Label(
            book_row,
            text="只对匹配的书名启用翻译（可配置多个关键词）",
            bg=PANEL,
            fg=DIM,
            font=(FONT_FAMILY, 8),
        ).pack(side="left", padx=(10, 0))

    def _build_dict_page(self) -> None:
        outer = self._page_bodies["langdict"]
        self._section(outer, "词典与发音")
        dict_row = tk.Frame(outer, bg=BG)
        dict_row.pack(fill="x", pady=(0, 6))
        self._button(dict_row, "词典设置…", self.open_dictionary_settings).pack(side="left")
        tk.Label(
            dict_row,
            text="添加本地 MDX/MDD 词典、调整查询顺序",
            bg=BG,
            fg=DIM,
            font=(FONT_FAMILY, 8),
        ).pack(side="left", padx=(10, 0))

        audio_row = tk.Frame(outer, bg=BG)
        audio_row.pack(fill="x", pady=(2, 6))
        tk.Label(
            audio_row, text="发音来源", bg=BG, fg=DIM, font=(FONT_FAMILY, 9)
        ).pack(side="left")
        _audio_labels = {
            "dict_first": "词典音频优先（没有就用 TTS）",
            "tts": "只用系统 TTS",
            "dict_only": "只用词典音频",
        }
        self._audio_label_to_key = {v: k for k, v in _audio_labels.items()}
        _current_audio = _audio_labels.get(
            self.config.get("audio_source", "dict_first"), _audio_labels["dict_first"]
        )
        self.var_audio_source = tk.StringVar(value=tr(_current_audio))
        audio_box = tk.OptionMenu(
            audio_row,
            self.var_audio_source,
            *[tr(v) for v in _audio_labels.values()],
        )
        audio_box.configure(
            bg=PANEL, fg=TEXT, activebackground=PANEL, activeforeground=TEXT,
            relief="flat", highlightthickness=0, font=(FONT_FAMILY, 9), width=26, anchor="w",
        )
        audio_box["menu"].configure(
            bg=PANEL, fg=TEXT, activebackground=ACCENT, activeforeground="#10131a"
        )
        audio_box.pack(side="left", padx=(8, 0))

        install_row = tk.Frame(outer, bg=BG)
        install_row.pack(fill="x", pady=(0, 6))
        self._button(
            install_row, "安装/管理系统语音…",
            lambda: _open("ms-settings:speech"),
        ).pack(side="left")
        self._button(install_row, "刷新音色", self._load_voices).pack(
            side="left", padx=(8, 0)
        )
        tk.Label(
            install_row,
            text="这里列出 SAPI 和 OneCore 两套音色；新语言请在 Windows 设置 → 语音 里添加后点「刷新」",
            bg=BG, fg=DIM, font=(FONT_FAMILY, 8),
        ).pack(side="left", padx=(10, 0))

    def _build_language_page(self) -> None:
        outer = self._page_bodies["langdict"]
        self._section(outer, "语言与音色")
        self.lang_table = tk.Frame(outer, bg=PANEL)
        self.lang_table.pack(fill="x", pady=(4, 6))
        self._voice_names: list[str] = []
        self.lang_vars: dict[str, tuple[tk.StringVar, tk.StringVar]] = {}
        self._voice_boxes: list[tuple[tk.OptionMenu, tk.StringVar]] = []
        self._deck_boxes: list = []
        self._deck_menus: list = []
        self._deck_names: list[str] = []

        lang_btns = tk.Frame(outer, bg=BG)
        lang_btns.pack(fill="x", pady=(0, 4))
        self._button(lang_btns, "+ 添加语言…", self.add_language).pack(side="left")
        tk.Label(
            lang_btns,
            text="任何语言都能加；词典在「词典与发音 → 词典设置」里挂",
            bg=BG, fg=DIM, font=(FONT_FAMILY, 8),
        ).pack(side="left", padx=(10, 0))

        lock_row = tk.Frame(outer, bg=BG)
        lock_row.pack(fill="x", pady=(0, 8))
        self.var_lang_delete_lock = tk.BooleanVar(
            value=bool(self.config.get("lang_delete_lock", True))
        )
        tk.Checkbutton(
            lock_row,
            text="删除语言前的保险：有生词或书籍时禁止删除（关掉则只弹提示）",
            variable=self.var_lang_delete_lock,
            bg=BG, fg=TEXT, selectcolor="#2f3440",
            activebackground=BG, activeforeground=TEXT,
            font=(FONT_FAMILY, 9), anchor="w",
        ).pack(side="left")
        self.lang_status = tk.Label(
            outer, text="", bg=BG, fg=MUTED, font=(FONT_FAMILY, 8), anchor="w"
        )
        self.lang_status.pack(fill="x", pady=(0, 6))

        outer = self._page_bodies["anki"]
        self._section(outer, "Anki 牌组")
        self.deck_table = tk.Frame(outer, bg=PANEL)
        self.deck_table.pack(fill="x", pady=(4, 6))
        self._rebuild_language_tables()

        hint = tk.Frame(outer, bg=BG)
        hint.pack(fill="x", pady=(0, 8))
        self._button(hint, "刷新 Anki 牌组", self._load_decks).pack(side="left")
        self.deck_status = tk.Label(
            hint, text="直接输入牌组名即可（不存在会自动新建）；点 ▾ 可从 Anki 现有牌组里选。",
            bg=BG, fg=DIM, font=(FONT_FAMILY, 8),
        )
        self.deck_status.pack(side="left", padx=(10, 0))

        skip_row = tk.Frame(outer, bg=BG)
        skip_row.pack(fill="x", pady=(0, 6))
        self.var_skip_anki = tk.BooleanVar(
            value=bool(self.config.get("anki_skip_existing", True))
        )
        tk.Checkbutton(
            skip_row,
            text="跳过 Anki 牌组里已存在的单词（不同笔记类型也算，避免重复添加）",
            variable=self.var_skip_anki,
            bg=BG,
            fg=TEXT,
            selectcolor="#2f3440",
            activebackground=BG,
            activeforeground=TEXT,
            font=(FONT_FAMILY, 9),
            anchor="w",
        ).pack(side="left")

        rich_row = tk.Frame(outer, bg=BG)
        rich_row.pack(fill="x", pady=(0, 4))
        self.var_dict2anki = tk.BooleanVar(
            value=bool(self.config.get("anki_en_dict2anki", True))
        )
        tk.Checkbutton(
            rich_row,
            text="英语用 Dict2Anki 模板同步（多义项 + 例句 + 音频，字段更全）",
            variable=self.var_dict2anki,
            bg=BG,
            fg=TEXT,
            selectcolor="#2f3440",
            activebackground=BG,
            activeforeground=TEXT,
            font=(FONT_FAMILY, 9),
            anchor="w",
        ).pack(side="left")

        card_row = tk.Frame(outer, bg=BG)
        card_row.pack(fill="x", pady=(0, 10))
        self._button(card_row, "卡片模板…", self.open_anki_cards).pack(side="left")
        tk.Label(
            card_row,
            text="自定义字段映射、Front/Back 模板与 CSS；启用后英语不再走 Dict2Anki",
            bg=BG, fg=DIM, font=(FONT_FAMILY, 8),
        ).pack(side="left", padx=(10, 0))

    def _build_records_page(self) -> None:
        outer = self._page_bodies["general"]
        self._section(outer, "记录")
        records = tk.Frame(outer, bg=PANEL)
        records.pack(fill="x", pady=(4, 12))
        rec_row = tk.Frame(records, bg=PANEL)
        rec_row.pack(fill="x", padx=12, pady=(8, 4))
        self._button(rec_row, "对话记录…", self.open_chat_history).pack(side="left")
        self._button(rec_row, "翻译记录…", self.open_translation_history).pack(
            side="left", padx=(8, 0)
        )
        data_row = tk.Frame(records, bg=PANEL)
        data_row.pack(fill="x", padx=12, pady=(0, 8))
        self._button(data_row, "打开数据目录", self._open_data).pack(side="left")
        self.data_label = tk.Label(
            records, text="", bg=PANEL, fg=MUTED, font=(FONT_FAMILY, 8), anchor="w"
        )
        self.data_label.pack(fill="x", padx=12, pady=(0, 8))

    def _build_anki_page(self) -> None:
        outer = self._page_bodies["anki"]
        self._section(outer, "生词导出")
        export_row = tk.Frame(outer, bg=PANEL)
        export_row.pack(fill="x", pady=(4, 8))
        row_inner = tk.Frame(export_row, bg=PANEL)
        row_inner.pack(fill="x", padx=12, pady=8)
        self._button(row_inner, "导出全部生词 CSV", self._export).pack(side="left")
        self._button(row_inner, "同步全部生词到 Anki", self._push).pack(
            side="left", padx=(8, 0)
        )
        self.stats = tk.Label(
            export_row, text="", bg=PANEL, fg=MUTED, font=(FONT_FAMILY, 8),
            anchor="w", justify="left",
        )
        self.stats.pack(fill="x", padx=12, pady=(0, 8))

    def _build_about_page(self) -> None:
        outer = self._page_bodies["about"]
        about = tk.Frame(outer, bg=PANEL)
        about.pack(fill="x", pady=(4, 12))
        tk.Label(
            about, text=f"Interpres v{__version__}", bg=PANEL, fg=TEXT,
            font=(FONT_FAMILY, 11, "bold"), anchor="w",
        ).pack(fill="x", padx=12, pady=(12, 4))
        tk.Label(
            about,
            text="个人阅读工具，不是商业产品。源码、文档和发布包都在 GitHub。",
            bg=PANEL, fg=DIM, font=(FONT_FAMILY, 9), anchor="w",
        ).pack(fill="x", padx=12, pady=(0, 8))
        link_row = tk.Frame(about, bg=PANEL)
        link_row.pack(fill="x", padx=12, pady=(0, 12))
        self._button(
            link_row, "打开 GitHub 发布页",
            lambda: _open("https://github.com/yaobude-1/interpres-reading-companion/releases"),
        ).pack(side="left")
        self._button(
            link_row, "源代码",
            lambda: _open("https://github.com/yaobude-1/interpres-reading-companion"),
        ).pack(side="left", padx=(8, 0))
        tk.Label(
            about, text="MIT License · 第三方组件许可见 THIRD_PARTY_NOTICES.md",
            bg=PANEL, fg=DIM, font=(FONT_FAMILY, 8), anchor="w",
        ).pack(fill="x", padx=12, pady=(0, 12))

    def _build_prompts_page(self) -> None:
        outer = self._page_bodies["ai"]
        self._section(outer, "翻译与对话")
        passage_row = tk.Frame(outer, bg=PANEL)
        passage_row.pack(fill="x", pady=(4, 4))
        tk.Label(
            passage_row, text="对话原文上限", bg=PANEL, fg=DIM,
            font=(FONT_FAMILY, 9), width=14, anchor="w",
        ).pack(side="left", padx=(12, 4), pady=8)
        self.var_chat_passage = tk.StringVar(
            value=str(self.config.get("chat_passage_chars", 0))
        )
        tk.Entry(
            passage_row, textvariable=self.var_chat_passage, width=8,
            bg=PANEL, fg=TEXT, insertbackground=TEXT, relief="flat",
            font=(FONT_FAMILY, 9),
        ).pack(side="left", ipady=3)
        tk.Label(
            passage_row,
            text="对话时最多引用多少字原文；0 = 不限制。越小越省 token、越快",
            bg=PANEL, fg=DIM, font=(FONT_FAMILY, 8),
        ).pack(side="left", padx=(10, 0))

        speed_row = tk.Frame(outer, bg=BG)
        speed_row.pack(fill="x", pady=(4, 4))
        tk.Label(
            speed_row, text="流式输出速度（字/秒）", bg=BG, fg=DIM,
            font=(FONT_FAMILY, 9),
        ).pack(side="left")
        self.var_stream_speed = tk.StringVar(
            value=str(self.config.get("stream_speed", 60))
        )
        tk.Entry(
            speed_row, textvariable=self.var_stream_speed, width=6,
            bg=PANEL, fg=TEXT, insertbackground=TEXT, relief="flat",
            font=(FONT_FAMILY, 9),
        ).pack(side="left", padx=(8, 0), ipady=3)
        tk.Label(
            speed_row, text="越大越快；译文和对话都按这个速度显示", bg=BG, fg=DIM,
            font=(FONT_FAMILY, 8),
        ).pack(side="left", padx=(8, 0))

        preview_row = tk.Frame(outer, bg=BG)
        preview_row.pack(fill="x", pady=(0, 10))
        self.stream_preview = tk.Label(
            preview_row,
            text="",
            bg=PANEL,
            fg=MUTED,
            font=(FONT_FAMILY, 9),
            anchor="w",
            justify="left",
            padx=10,
            pady=6,
        )
        self.stream_preview.pack(fill="x")
        self._preview_job = None
        self._preview_text = "这段文字会按你设置的速度逐字出现，用来感受快慢。改成 30 就慢一倍，改成 120 就快一倍。"
        self.var_stream_speed.trace_add("write", lambda *_a: self._restart_stream_preview())
        self.win.after(250, self._restart_stream_preview)

        tk.Label(
            outer, text="翻译提示词（系统提示）", bg=BG, fg=DIM,
            font=(FONT_FAMILY, 9), anchor="w",
        ).pack(fill="x", pady=(4, 2))
        self.prompt_translate = tk.Text(
            outer, height=9, bg=PANEL, fg=TEXT, insertbackground=TEXT,
            relief="flat", wrap="word", font=(FONT_FAMILY, 8), padx=8, pady=6,
        )
        self.prompt_translate.pack(fill="x")
        self.prompt_translate.insert(
            "1.0", str(self.config.get("prompt_translate_system") or "")
        )
        row1 = tk.Frame(outer, bg=BG)
        row1.pack(fill="x", pady=(2, 8))
        self._button(
            row1, "填入默认", lambda: self._fill_prompt(self.prompt_translate, default_translate_prompt())
        ).pack(side="left")
        self._button(
            row1, "清空（用默认）", lambda: self._clear_prompt(self.prompt_translate)
        ).pack(side="left", padx=(6, 0))
        tk.Label(
            row1, text="必须保留 JSON 结构说明，否则翻译结果无法解析", bg=BG,
            fg=DIM, font=(FONT_FAMILY, 8),
        ).pack(side="left", padx=(8, 0))

        tk.Label(
            outer, text="对话人设（可用 {book} 占位）", bg=BG, fg=DIM,
            font=(FONT_FAMILY, 9), anchor="w",
        ).pack(fill="x", pady=(4, 2))
        self.prompt_persona = tk.Text(
            outer, height=3, bg=PANEL, fg=TEXT, insertbackground=TEXT,
            relief="flat", wrap="word", font=(FONT_FAMILY, 8), padx=8, pady=6,
        )
        self.prompt_persona.pack(fill="x")
        self.prompt_persona.insert(
            "1.0", str(self.config.get("prompt_chat_persona") or "")
        )
        row2 = tk.Frame(outer, bg=BG)
        row2.pack(fill="x", pady=(2, 8))
        self._button(
            row2, "填入默认", lambda: self._fill_prompt(self.prompt_persona, default_chat_persona())
        ).pack(side="left")
        self._button(
            row2, "清空（用默认）", lambda: self._clear_prompt(self.prompt_persona)
        ).pack(side="left", padx=(6, 0))

        tk.Label(
            outer, text="对话回答要求", bg=BG, fg=DIM,
            font=(FONT_FAMILY, 9), anchor="w",
        ).pack(fill="x", pady=(4, 2))
        self.prompt_rules = tk.Text(
            outer, height=4, bg=PANEL, fg=TEXT, insertbackground=TEXT,
            relief="flat", wrap="word", font=(FONT_FAMILY, 8), padx=8, pady=6,
        )
        self.prompt_rules.pack(fill="x")
        self.prompt_rules.insert("1.0", str(self.config.get("prompt_chat_rules") or ""))
        row3 = tk.Frame(outer, bg=BG)
        row3.pack(fill="x", pady=(2, 10))
        self._button(
            row3, "填入默认", lambda: self._fill_prompt(self.prompt_rules, default_chat_rules())
        ).pack(side="left")
        self._button(
            row3, "清空（用默认）", lambda: self._clear_prompt(self.prompt_rules)
        ).pack(side="left", padx=(6, 0))

        # 语音列表要调用 PowerShell，放到后台，避免卡住界面渲染
        self.win.after(200, self._load_voices)
        self.win.after(250, self._load_decks)
        self._loads_applied = {"voices": False, "decks": False}
        self.win.after(300, self._check_background_loads)

        # 窗口高度按内容自适应，并居中，避免超出屏幕把底部按钮挤出去
        self.win.update_idletasks()
        sw, sh = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
        height = min(900, sh - 90)
        x = max(20, (sw - 660) // 2)
        y = max(20, (sh - height) // 2)
        self.win.geometry(f"660x{height}+{x}+{y}")
    # ------------------------------------------------------------------ 语言表
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
                text=f"{entry.get('zh_label', code)}  {code}",
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
                text=f"{entry.get('zh_label', code)}  {code}",
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
        self._set_lang_status(f"已添加语言：{dialog.result['zh_label']}")

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
        self._set_lang_status(f"已保存语言：{dialog.result['zh_label']}")

    def delete_language(self, code: str) -> None:
        languages = self.config.data.get("languages") or {}
        entry = languages.get(code) or {}
        name = entry.get("zh_label") or code
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
    def test_api(self) -> None:
        try:
            self._apply_to_config(save=False)
        except ValueError as exc:
            self.test_label.configure(text=str(exc), fg=RED)
            return
        self.test_label.configure(text="测试中…", fg=MUTED)
        self.win.update_idletasks()

        def run():
            result = self.service.test_api()

            def done():
                if result.get("ok"):
                    self.test_label.configure(text=f"连接正常 · {result.get('reply', '')}", fg=GREEN)
                else:
                    self.test_label.configure(text=result.get("error", "失败")[:80], fg=RED)

            self.win.after(0, done)

        import threading

        threading.Thread(target=run, daemon=True).start()

    def save(self) -> None:
        try:
            self._apply_to_config(save=True)
        except ValueError as exc:
            self.test_label.configure(text=str(exc), fg=RED)
            return
        self.on_saved()
        self._refresh_stats()
        self.test_label.configure(text="已保存", fg=GREEN)

    def _apply_to_config(self, save: bool) -> None:
        api = self.config.api
        api["base_url"] = validate_base_url(
            self.var_base.get().strip() or "https://api.deepseek.com/v1"
        )
        api["api_key"] = ""  # 实际密钥通过 set_api_key 加密后写入
        self.config.set_api_key(self.var_key.get().strip())
        api["model"] = self.var_model.get().strip() or "deepseek-chat"
        if save:
            self.config.data["hotkey"] = self.var_hotkey.get().strip() or "ctrl+alt+t"
            self.config.data["settings_hotkey"] = (
                self.var_settings_hotkey.get().strip() or "ctrl+alt+s"
            )
            self.config.data["anki_skip_existing"] = bool(self.var_skip_anki.get())
            if hasattr(self, "var_dict2anki"):
                self.config.data["anki_en_dict2anki"] = bool(self.var_dict2anki.get())
            if hasattr(self, "prompt_translate"):
                self.config.data["prompt_translate_system"] = self._prompt_value(
                    self.prompt_translate, default_translate_prompt()
                )
                self.config.data["prompt_chat_persona"] = self._prompt_value(
                    self.prompt_persona, default_chat_persona()
                )
                self.config.data["prompt_chat_rules"] = self._prompt_value(
                    self.prompt_rules, default_chat_rules()
                )
            if hasattr(self, "var_ui_lang"):
                self.config.data["ui_lang"] = (
                    "zh" if self.var_ui_lang.get() == "中文" else "en"
                )
            if hasattr(self, "var_lang_delete_lock"):
                self.config.data["lang_delete_lock"] = bool(
                    self.var_lang_delete_lock.get()
                )
            if hasattr(self, "var_stream_speed"):
                try:
                    value = int(self.var_stream_speed.get().strip() or 60)
                except ValueError:
                    value = 60
                self.config.data["stream_speed"] = max(5, min(400, value))
            self.config.data["auto_follow_book"] = bool(self.var_follow_book.get())
            try:
                self.config.data["chat_passage_chars"] = max(
                    0, int(self.var_chat_passage.get().strip() or 0)
                )
            except ValueError:
                self.config.data["chat_passage_chars"] = 0
            self.config.data["quit_on_panel_close"] = bool(self.var_quit_on_close.get())
            _audio_value = self.var_audio_source.get()
            self.config.data["audio_source"] = self._audio_label_to_key.get(
                _audio_value,
                {
                    "Dictionary audio first (fallback to TTS)": "dict_first",
                    "System TTS only": "tts",
                    "Dictionary audio only": "dict_only",
                }.get(_audio_value, "dict_first"),
            )
            languages = self.config.data.get("languages") or {}
            languages_now = self.config.data.get("languages") or {}
            for code, (voice_var, deck_var) in self.lang_vars.items():
                if code not in languages_now:
                    continue
                if code in languages:
                    engine = (languages[code].get("tts_engine") or "system").lower()
                    if engine == "system":
                        languages[code]["tts_voice"] = voice_var.get()
                    languages[code]["deck"] = deck_var.get()
            self.config.save()
        self._snapshot = self._form_snapshot()

    def _form_snapshot(self) -> dict:
        prompts = ()
        if hasattr(self, "prompt_translate"):
            prompts = (
                self._prompt_value(self.prompt_translate, default_translate_prompt()),
                self._prompt_value(self.prompt_persona, default_chat_persona()),
                self._prompt_value(self.prompt_rules, default_chat_rules()),
            )
        langs = tuple(
            sorted(
                (code, voice.get(), deck.get())
                for code, (voice, deck) in self.lang_vars.items()
            )
        )
        return {
            "key": self.var_key.get().strip(),
            "base": self.var_base.get().strip(),
            "model": self.var_model.get().strip(),
            "hotkey": self.var_hotkey.get().strip(),
            "settings_hotkey": self.var_settings_hotkey.get().strip(),
            "skip": bool(self.var_skip_anki.get()),
            "dict2anki": bool(getattr(self, "var_dict2anki", tk.BooleanVar(value=False)).get()),
            "prompts": prompts,
            "ui_lang": self.var_ui_lang.get(),
            "follow": bool(self.var_follow_book.get()),
            "quit": bool(self.var_quit_on_close.get()),
            "audio": self.var_audio_source.get(),
            "stream": self.var_stream_speed.get().strip(),
            "chat": self.var_chat_passage.get().strip(),
            "lang_lock": bool(getattr(self, "var_lang_delete_lock", tk.BooleanVar(value=True)).get()),
            "langs": langs,
        }

    def _is_dirty(self) -> bool:
        return getattr(self, "_snapshot", None) != self._form_snapshot()

    def _on_ui_lang_changed(self, *_args) -> None:
        if self._lang_guard or not hasattr(self, "_snapshot"):
            return
        new = "zh" if self.var_ui_lang.get() == "中文" else "en"
        old = "zh" if str(self.config.get("ui_lang", "zh")) == "zh" else "en"
        if new == old:
            return
        # 切语言没有弹窗：直接保存当前所有设置并重启
        self.save()
        if self.on_restart is None:
            self._set_hint("语言已保存，重启后生效")
            return
        self.on_restart()

    def _set_hint(self, text: str) -> None:
        try:
            self.test_label.configure(text=text, fg=MUTED)
        except tk.TclError:
            pass

    def _refresh_stats(self) -> None:
        if not hasattr(self, "stats"):
            return
        total = self.service.store.word_count()
        langs = []
        for code in (self.config.data.get("languages") or {}):
            n = self.service.store.word_count(code)
            if n:
                entry = self.config.language(code)
                langs.append(f"{entry.get('zh_label', code)} {n}")
        detail = "，".join(langs) if langs else "还没有生词"
        self.stats.configure(text=f"共 {total} 个生词（{detail}）\nAnki 状态检测中… · 数据目录 {self.config.data_dir}")

        # 连 Anki 端口可能要等一两秒，绝不能放在界面线程里
        def probe() -> None:
            ok = self.service.anki.ping()
            text = "Anki 已连接" if ok else "Anki 未运行（同步时会自动导出 CSV）"
            self.win.after(0, lambda: self._set_stats_text(f"共 {total} 个生词（{detail}）\n{text} · 数据目录 {self.config.data_dir}"))

        import threading

        threading.Thread(target=probe, daemon=True).start()

    def _set_stats_text(self, text: str) -> None:
        try:
            if self.stats.winfo_exists():
                self.stats.configure(text=text)
        except tk.TclError:
            pass

    def _open_data(self) -> None:
        _open(str(self.config.data_dir))

    def open_selection_settings(self) -> None:
        from .selection_settings import SelectionSettings

        SelectionSettings(self.win, self.config, self._selection_saved)

    def open_book_filter(self) -> None:
        from .book_settings import BookFilterSettings

        BookFilterSettings(self.win, self.config, self.on_saved)

    def open_entry_colors(self) -> None:
        from .entry_settings import EntryColorSettings

        EntryColorSettings(self.win, self.config, self.on_saved)

    def open_anki_cards(self) -> None:
        from .anki_card_settings import AnkiCardSettings

        AnkiCardSettings(self.win, self.config, self.service.anki)

    def open_dictionary_settings(self) -> None:
        from .dictionary_settings import DictionarySettings

        DictionarySettings(self.win, self.config, self.service.dicts, self.on_saved)

    def open_chat_history(self) -> None:
        from .chat_ui import ChatHistoryWindow

        window = getattr(self, "_chat_win", None)
        if window is not None and window.win.winfo_exists():
            window.show()
            return
        self._chat_win = ChatHistoryWindow(self.win, self.service)
        self._chat_win.show()

    def open_translation_history(self) -> None:
        from rc.translation_ui import TranslationWindow

        window = getattr(self, "_trans_win", None)
        if window is not None and window.win.winfo_exists():
            window.show()
            return
        self._trans_win = TranslationWindow(self.win, self.service)
        self._trans_win.show()

    def open_vocab(self) -> None:
        from .vocab_ui import VocabWindow

        window = getattr(self, "_vocab_win", None)
        if window is not None and window.win.winfo_exists():
            window.show()
            return
        self._vocab_win = VocabWindow(
            self.win, self.service, self.config, on_change=self._refresh_stats
        )
        self._vocab_win.show()

    def _selection_saved(self) -> None:
        self.on_saved()

    def _export(self) -> None:
        result = self.service.export_vocab(None)
        label = getattr(self, "stats", None) or getattr(self, "data_label", None) or self.test_label
        label.configure(text=f"已导出 {result['count']} 条 → {result['path']}", fg=GREEN)

    def _push(self) -> None:
        langs = [c for c in (self.config.data.get("languages") or {}) if self.service.store.word_count(c)]
        label = getattr(self, "stats", None) or getattr(self, "data_label", None) or self.test_label
        if not langs:
            label.configure(text="没有可同步的生词", fg=MUTED)
            return
        import threading

        label.configure(text="正在同步所有生词…", fg=MUTED)
        self._push_ready = False
        self._push_text = ""

        def run():
            lines = []
            for lang in langs:
                try:
                    result = self.service.push_anki(lang)
                    line = f"{lang}: 新增 {result.get('added', 0)}，重复 {result.get('duplicated', 0)}"
                    if result.get("skipped"):
                        line += f"，已存在 {result['skipped']}"
                    lines.append(line)
                except Exception as exc:  # noqa: BLE001
                    lines.append(f"{lang}: {exc}")
            self._push_text = "；".join(lines)
            self._push_ready = True

        threading.Thread(target=run, daemon=True).start()
        self._poll_push(0)

    def _poll_push(self, tries: int) -> None:
        try:
            if not self.win.winfo_exists():
                return
        except tk.TclError:
            return
        if not getattr(self, "_push_ready", False):
            if tries < 600:
                self.win.after(100, lambda: self._poll_push(tries + 1))
            return
        label = getattr(self, "stats", None) or getattr(self, "data_label", None) or self.test_label
        try:
            label.configure(text=getattr(self, "_push_text", "")[:100], fg=MUTED)
        except tk.TclError:
            pass

    def _quit(self) -> None:
        if self.close():
            self.on_quit()

    def close(self) -> bool:
        if self._is_dirty():
            answer = messagebox.askyesnocancel(
                "未保存的设置",
                "有未保存的修改。\n\n"
                "是：保存并关闭\n"
                "否：不保存\n"
                "取消：继续编辑",
                parent=self.win,
                default=messagebox.YES,
            )
            if answer is None:
                return False
            if answer:
                self.save()
        try:
            self.win.destroy()
        except tk.TclError:
            pass
        return True

    def show(self) -> None:
        self.win.deiconify()
        self.win.lift()
        self._refresh_stats()
        try:
            self.win.focus_force()
        except tk.TclError:
            pass


def _style_menu(widget: tk.OptionMenu) -> None:
    widget.configure(
        bg=PANEL, fg=TEXT, activebackground=PANEL, activeforeground=TEXT, relief="flat",
        highlightthickness=0, font=(FONT_FAMILY, 9), anchor="w",
    )
    widget["menu"].configure(bg=PANEL, fg=TEXT, activebackground=ACCENT, activeforeground="#10131a")


def _open(target: str) -> None:
    try:
        os.startfile(target)  # type: ignore[attr-defined]
    except Exception:
        try:
            subprocess.Popen(["explorer", target])
        except Exception:
            pass
