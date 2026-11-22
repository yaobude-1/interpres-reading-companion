"""Settings window: the per-page builders split out of `_build`."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from . import __version__
from .i18n import tr
from .settings_common import (
    default_chat_persona,
    default_chat_rules,
    default_translate_prompt,
    open_target as _open,
)
from .theme import (
    ACCENT,
    BG,
    DIM,
    FONT_FAMILY,
    MUTED,
    PANEL,
    RED,
    TEXT,
)
from .theme import BORDER_SOFT, ON_ACCENT


class SettingsPagesMixin:
    def _build_ai_section(self) -> None:
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

    def _build_hotkey_section(self) -> None:
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

    def _build_ui_section(self) -> None:
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
            bg=PANEL, fg=TEXT, activebackground=ACCENT, activeforeground=ON_ACCENT
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
            selectcolor=BORDER_SOFT,
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
            selectcolor=BORDER_SOFT,
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

    def _build_dict_section(self) -> None:
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
            bg=PANEL, fg=TEXT, activebackground=ACCENT, activeforeground=ON_ACCENT
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

    def _build_language_section(self) -> None:
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
            bg=BG, fg=TEXT, selectcolor=BORDER_SOFT,
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
            selectcolor=BORDER_SOFT,
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
            selectcolor=BORDER_SOFT,
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

    def _build_records_section(self) -> None:
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

    def _build_anki_section(self) -> None:
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

    def _build_about_section(self) -> None:
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

    def _build_appearance_section(self) -> None:
        outer = self._page_bodies["appearance"]
        appearance = self.config.get("appearance") or {}
        theme = str(appearance.get("theme") or "dark")
        accent = str(appearance.get("accent") or "blue")
        self._section(outer, "主题")
        tk.Label(
            outer,
            text="主题和强调色保存后需要重启才会生效；尺寸和透明度在下次打开窗口时生效。",
            bg=BG, fg=DIM, font=(FONT_FAMILY, 8), anchor="w", justify="left",
        ).pack(fill="x", pady=(0, 6))

        theme_row = tk.Frame(outer, bg=PANEL)
        theme_row.pack(fill="x", pady=(0, 6))
        tk.Label(
            theme_row, text="主题", bg=PANEL, fg=DIM, font=(FONT_FAMILY, 9),
            width=10, anchor="w",
        ).pack(side="left", padx=(12, 4), pady=8)
        self.var_theme = tk.StringVar(value=theme)
        for text, value in (("深色", "dark"), ("浅色", "light")):
            tk.Radiobutton(
                theme_row, text=text, variable=self.var_theme, value=value,
                bg=PANEL, fg=TEXT, selectcolor=PANEL, activebackground=PANEL,
                activeforeground=TEXT, font=(FONT_FAMILY, 9),
                highlightthickness=0, bd=0,
            ).pack(side="left", padx=(0, 10))

        accent_row = tk.Frame(outer, bg=PANEL)
        accent_row.pack(fill="x", pady=(0, 6))
        tk.Label(
            accent_row, text="强调色", bg=PANEL, fg=DIM, font=(FONT_FAMILY, 9),
            width=10, anchor="w",
        ).pack(side="left", padx=(12, 4), pady=8)
        self._accent_labels = {"blue": "蓝", "green": "绿", "purple": "紫", "orange": "橙"}
        self._accent_keys = {v: k for k, v in self._accent_labels.items()}
        self.var_accent_label = tk.StringVar(
            value=self._accent_labels.get(accent, "蓝")
        )
        accent_box = tk.OptionMenu(
            accent_row, self.var_accent_label, *self._accent_labels.values()
        )
        accent_box.configure(
            bg=BG, fg=TEXT, activebackground=PANEL, activeforeground=TEXT,
            relief="flat", highlightthickness=0, font=(FONT_FAMILY, 9),
            width=6, anchor="w",
        )
        accent_box["menu"].configure(
            bg=PANEL, fg=TEXT, activebackground=ACCENT, activeforeground=ON_ACCENT
        )
        accent_box.pack(side="left", padx=(0, 8))

        self._section(outer, "浮窗")
        self.var_popup_width = tk.StringVar(
            value=str(self.config.get("popup_width", 560))
        )
        self.var_popup_max = tk.StringVar(
            value=str(round(float(self.config.get("popup_max_height_ratio", 0.72)) * 100))
        )
        width_row = tk.Frame(outer, bg=PANEL)
        width_row.pack(fill="x", pady=(0, 6))
        tk.Label(
            width_row, text="宽度（px）", bg=PANEL, fg=DIM, font=(FONT_FAMILY, 9),
            width=12, anchor="w",
        ).pack(side="left", padx=(12, 4), pady=8)
        tk.Entry(
            width_row, textvariable=self.var_popup_width, width=8, bg=BG, fg=TEXT,
            insertbackground=TEXT, relief="flat", font=(FONT_FAMILY, 9),
        ).pack(side="left", ipady=3)
        tk.Label(
            width_row, text="420–900", bg=PANEL, fg=DIM, font=(FONT_FAMILY, 8)
        ).pack(side="left", padx=(8, 0))

        height_row = tk.Frame(outer, bg=PANEL)
        height_row.pack(fill="x", pady=(0, 6))
        tk.Label(
            height_row, text="最大高度（%）", bg=PANEL, fg=DIM, font=(FONT_FAMILY, 9),
            width=12, anchor="w",
        ).pack(side="left", padx=(12, 4), pady=8)
        tk.Entry(
            height_row, textvariable=self.var_popup_max, width=8, bg=BG, fg=TEXT,
            insertbackground=TEXT, relief="flat", font=(FONT_FAMILY, 9),
        ).pack(side="left", ipady=3)
        tk.Label(
            height_row, text="50–95", bg=PANEL, fg=DIM, font=(FONT_FAMILY, 8)
        ).pack(side="left", padx=(8, 0))

        self.var_popup_opacity = tk.DoubleVar(
            value=float(appearance.get("popup_opacity", 1.0))
        )
        opacity_row = tk.Frame(outer, bg=PANEL)
        opacity_row.pack(fill="x", pady=(0, 6))
        tk.Label(
            opacity_row, text="不透明度", bg=PANEL, fg=DIM, font=(FONT_FAMILY, 9),
            width=12, anchor="w",
        ).pack(side="left", padx=(12, 4), pady=8)
        tk.Scale(
            opacity_row, from_=0.6, to=1.0, resolution=0.05, orient="horizontal",
            variable=self.var_popup_opacity, showvalue=True, length=220,
            bg=BG, fg=TEXT, troughcolor=BORDER_SOFT, highlightthickness=0,
            activebackground=ACCENT,
        ).pack(side="left")

        self._section(outer, "主界面")
        self.var_panel_opacity = tk.DoubleVar(
            value=float(appearance.get("panel_opacity", 1.0))
        )
        panel_row = tk.Frame(outer, bg=PANEL)
        panel_row.pack(fill="x", pady=(0, 6))
        tk.Label(
            panel_row, text="不透明度", bg=PANEL, fg=DIM, font=(FONT_FAMILY, 9),
            width=12, anchor="w",
        ).pack(side="left", padx=(12, 4), pady=8)
        tk.Scale(
            panel_row, from_=0.7, to=1.0, resolution=0.05, orient="horizontal",
            variable=self.var_panel_opacity, showvalue=True, length=220,
            bg=BG, fg=TEXT, troughcolor=BORDER_SOFT, highlightthickness=0,
            activebackground=ACCENT,
        ).pack(side="left")

        btns = tk.Frame(outer, bg=BG)
        btns.pack(fill="x", pady=(8, 4))
        self._button(btns, "保存并重启", self._appearance_save_restart).pack(side="left")

    def _prompt_text(self, parent, height: int) -> tk.Text:
        """带竖向滚动条的提示词输入框。"""
        wrap = tk.Frame(parent, bg=PANEL)
        wrap.pack(fill="x")
        text = tk.Text(
            wrap, height=height, bg=PANEL, fg=TEXT, insertbackground=TEXT,
            relief="flat", wrap="word", font=(FONT_FAMILY, 8), padx=8, pady=6,
        )
        scroll = ttk.Scrollbar(
            wrap, orient="vertical", command=text.yview, style="Vertical.TScrollbar"
        )
        text.configure(yscrollcommand=scroll.set)
        text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        text.bind(
            "<MouseWheel>",
            lambda event: (text.yview_scroll(int(-event.delta / 120), "units"), "break")[1],
        )
        return text

    def _build_prompts_section(self) -> None:
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
            text="对话时最多引用多少字原文；默认 4000，0 = 不限制。越小越省 token、越快",
            bg=PANEL, fg=DIM, font=(FONT_FAMILY, 8),
        ).pack(side="left", padx=(10, 0))

        auto_row = tk.Frame(outer, bg=BG)
        auto_row.pack(fill="x", pady=(0, 6))
        self.var_chat_auto_context = tk.BooleanVar(
            value=bool(self.config.get("chat_auto_context", True))
        )
        tk.Checkbutton(
            auto_row,
            text="自动读取选中文字所在段落（Edge/Chrome 可用；其他阅读器可手动补充）",
            variable=self.var_chat_auto_context,
            bg=BG, fg=TEXT, selectcolor=PANEL, activebackground=BG,
            activeforeground=TEXT, font=(FONT_FAMILY, 9), anchor="w",
            highlightthickness=0, bd=0,
        ).pack(anchor="w", padx=12, pady=(2, 2))

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
        self.prompt_translate = self._prompt_text(outer, 9)
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
            row1, text="留空使用默认（纯译文或 JSON 均可）", bg=BG, fg=DIM,
            font=(FONT_FAMILY, 8),
        ).pack(side="left", padx=(8, 0))

        tk.Label(
            outer, text="对话人设（可用 {book} 占位）", bg=BG, fg=DIM,
            font=(FONT_FAMILY, 9), anchor="w",
        ).pack(fill="x", pady=(4, 2))
        self.prompt_persona = self._prompt_text(outer, 3)
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
        self.prompt_rules = self._prompt_text(outer, 4)
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
