"""Application: save word, Anki push, pronunciation, term locking."""

from __future__ import annotations

import logging
import threading
import tkinter as tk

log = logging.getLogger("rc")


class MediaMixin:
    def save_word(self, data: dict) -> dict:
        result = self.service.add_vocab(**data)
        return result

    def push_anki(self, lang: str) -> None:
        def worker() -> None:
            try:
                result = self.service.push_anki(lang)
                msg = f"Anki：新增 {result.get('added', 0)} 张，重复 {result.get('duplicated', 0)} 张"
                if result.get("skipped"):
                    msg += f"，已存在跳过 {result['skipped']} 个"
                if result.get("failed"):
                    msg += f"，失败 {len(result['failed'])} 张"
            except Exception as exc:  # noqa: BLE001
                msg = f"Anki 同步失败：{exc}"
            self.events.put(("toast", msg))

        threading.Thread(target=worker, daemon=True).start()

    def speak(self, text: str, lang: str, audio_key: str = "", dict_id: str = "") -> None:
        source = str(self.config.get("audio_source", "dict_first"))

        def worker() -> None:
            log.info("发音请求 lang=%r source=%r", lang, source)
            try:
                if source == "tts":
                    self.service.speak(text, lang)
                    return
                if audio_key and self.service.play_dictionary_audio(lang, audio_key, dict_id):
                    return
                if source == "dict_only":
                    self.events.put(("toast", "这个词没有本地音频"))
                    return
                self.service.speak(text, lang)
            except Exception as exc:  # noqa: BLE001
                log.exception("发音失败 lang=%r", lang)
                msg = str(exc)
                if "音色" in msg:
                    self.events.put(("toast", msg[:120]))
                    return
                if "语音" in msg or "Speak" in msg or "0x8004503A" in msg:
                    self.events.put(
                        (
                            "toast",
                            "系统没有可用的语音：设置 → 时间和语言 → 语音 → 添加语音",
                        )
                    )
                else:
                    self.events.put(("toast", f"发音失败：{msg[:40]}"))

        threading.Thread(target=worker, daemon=True).start()

    def lock_term(self, book: str, source: str, lang: str) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("加入术语表")
        dialog.configure(bg="#1b1d24")
        dialog.geometry("380x170")
        dialog.attributes("-topmost", True)

        tk.Label(dialog, text=f"为《{book or '当前书'}》固定译法", bg="#1b1d24", fg="#e6e9ef",
                 font=("Microsoft YaHei UI", 10)).pack(padx=16, pady=(14, 4), anchor="w")
        row = tk.Frame(dialog, bg="#23262f")
        row.pack(fill="x", padx=16)
        src = tk.Entry(row, bg="#23262f", fg="#e6e9ef", insertbackground="#e6e9ef",
                       relief="flat", font=("Microsoft YaHei UI", 10))
        src.insert(0, source)
        src.pack(side="left", fill="x", expand=True, padx=6, pady=6)
        tk.Label(row, text="→", bg="#23262f", fg="#9aa5b1").pack(side="left")
        dst = tk.Entry(row, bg="#23262f", fg="#e6e9ef", insertbackground="#e6e9ef",
                       relief="flat", font=("Microsoft YaHei UI", 10))
        dst.pack(side="left", fill="x", expand=True, padx=6, pady=6)

        def submit() -> None:
            term_src = src.get().strip()
            term_dst = dst.get().strip()
            if not term_src or not term_dst:
                return
            self.service.add_term(book, term_src, term_dst, lang)
            dialog.destroy()
            self.toast(f"已加入术语表：{term_src} → {term_dst}")

        btn = tk.Label(dialog, text="保存", bg="#7aa2f7", fg="#10131a", padx=16, pady=5,
                       cursor="hand2", font=("Microsoft YaHei UI", 9))
        btn.pack(pady=12)
        btn.bind("<Button-1>", lambda _e: submit())
        dialog.bind("<Return>", lambda _e: submit())
        dst.focus_set()

    # ------------------------------------------------------------------ 设置
