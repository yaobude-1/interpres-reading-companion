"""Settings window: save, connection test, dialogs and export actions."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from . import i18n
from .i18n import lang_display_name, tr
from .netpolicy import validate_base_url
from .settings_common import (
    default_chat_persona,
    default_chat_rules,
    default_translate_prompt,
    open_target as _open,
)
from .theme import GREEN, MUTED, RED


class SettingsActionsMixin:
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
        before = dict(self.config.get("appearance") or {})
        try:
            self._apply_to_config(save=True)
        except ValueError as exc:
            self.test_label.configure(text=str(exc), fg=RED)
            return
        self.on_saved()
        self._refresh_stats()
        after = dict(self.config.get("appearance") or {})
        theme_changed = (
            before.get("theme") != after.get("theme")
            or before.get("accent") != after.get("accent")
        )
        if theme_changed and self.on_restart:
            if messagebox.askyesno(
                "重启生效",
                "主题/强调色已保存，需要重启才能应用。现在重启吗？",
                parent=self.win,
            ):
                self.on_restart()
        self.test_label.configure(text="已保存", fg=GREEN)

    def _appearance_save_restart(self) -> None:
        """外观页的按钮：保存后直接重启，不再弹一次确认。"""
        try:
            self._apply_to_config(save=True)
        except ValueError as exc:
            self.test_label.configure(text=str(exc), fg=RED)
            return
        self.on_saved()
        if self.on_restart:
            self.on_restart()

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
            self.config.data["chat_auto_context"] = bool(
                self.var_chat_auto_context.get()
            )
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
            appearance = self.config.data.setdefault("appearance", {})
            if hasattr(self, "var_theme"):
                appearance["theme"] = self.var_theme.get()
                if hasattr(self, "var_accent_label"):
                    appearance["accent"] = self._accent_keys.get(
                        self.var_accent_label.get(), "blue"
                    )
            if hasattr(self, "var_popup_opacity"):
                appearance["popup_opacity"] = round(
                    float(self.var_popup_opacity.get()), 2
                )
                appearance["panel_opacity"] = round(
                    float(self.var_panel_opacity.get()), 2
                )
            if hasattr(self, "var_animations"):
                appearance["animations"] = bool(self.var_animations.get())
            if hasattr(self, "var_popup_width"):
                try:
                    width = int(self.var_popup_width.get().strip() or 560)
                except ValueError:
                    width = 560
                self.config.data["popup_width"] = max(420, min(900, width))
            if hasattr(self, "var_popup_max"):
                try:
                    percent = int(self.var_popup_max.get().strip() or 72)
                except ValueError:
                    percent = 72
                self.config.data["popup_max_height_ratio"] = max(
                    0.5, min(0.95, percent / 100)
                )
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
        except tk.TclError:  # 控件可能已销毁，刻意忽略
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
                langs.append(f"{lang_display_name(entry, code)} {n}")
        sep = ", " if i18n.LANGUAGE == "en" else "，"
        detail = sep.join(langs) if langs else tr("还没有生词")
        head = tr(f"共 {total} 个生词（{detail}）")
        data_label = tr("数据目录")
        self.stats.configure(
            text=f"{head}\n{tr('Anki 状态检测中…')} · {data_label} {self.config.data_dir}"
        )

        # 连 Anki 端口可能要等一两秒，绝不能放在界面线程里
        def probe() -> None:
            ok = self.service.anki.ping()
            text = tr("Anki 已连接") if ok else tr("Anki 未运行（同步时会自动导出 CSV）")
            self.win.after(
                0,
                lambda: self._set_stats_text(
                    f"{head}\n{text} · {data_label} {self.config.data_dir}"
                ),
            )

        import threading

        threading.Thread(target=probe, daemon=True).start()

    def _set_stats_text(self, text: str) -> None:
        try:
            if self.stats.winfo_exists():
                self.stats.configure(text=text)
        except tk.TclError:  # 控件可能已销毁，刻意忽略
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
        except tk.TclError:  # 控件可能已销毁，刻意忽略
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
        except tk.TclError:  # 控件可能已销毁，刻意忽略
            pass
        return True

    def show(self) -> None:
        self.win.deiconify()
        self.win.lift()
        self._refresh_stats()
        try:
            self.win.focus_force()
        except tk.TclError:  # 控件可能已销毁，刻意忽略
            pass
