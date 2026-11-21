"""语言管理对话框：添加/编辑语言，以及删除前的确认。"""

from __future__ import annotations

import re
import threading
import tkinter as tk
from tkinter import messagebox

from . import i18n
from .i18n import tr
from .popup import ACCENT, BG, DIM, FONT_FAMILY, PANEL, TEXT


class LanguageDialog:
    """添加或编辑一门语言。结果放在 result 里。"""

    def __init__(
        self,
        parent,
        voices: list[str],
        code: str = "",
        entry: dict | None = None,
        edit: bool = False,
        edge_provider=None,
    ) -> None:
        self.result: dict | None = None
        self.edit = edit
        self._code = code
        self.edge_provider = edge_provider
        self._edge_choices: list[dict] | None = None
        self._edge_loading = False
        entry = entry or {}
        self.win = tk.Toplevel(parent)
        self.win.title("编辑语言" if edit else "添加语言")
        self.win.configure(bg=BG)
        self.win.resizable(False, False)
        self.win.transient(parent)
        self.win.grab_set()

        outer = tk.Frame(self.win, bg=BG)
        outer.pack(fill="both", expand=True, padx=16, pady=14)

        def row(label: str) -> tk.Entry:
            frame = tk.Frame(outer, bg=BG)
            frame.pack(fill="x", pady=4)
            tk.Label(
                frame, text=label, bg=BG, fg=DIM, font=(FONT_FAMILY, 9),
                width=12, anchor="w",
            ).pack(side="left")
            widget = tk.Entry(
                frame, bg=PANEL, fg=TEXT, insertbackground=TEXT,
                relief="flat", font=(FONT_FAMILY, 9),
            )
            widget.pack(side="left", fill="x", expand=True, ipady=4)
            return widget

        self.entry_code = row("代码")
        self.entry_code.insert(0, code)
        if edit:
            self.entry_code.configure(state="disabled")

        self.entry_zh = row("中文名（可留空）")
        self.entry_zh.insert(0, str(entry.get("zh_label") or ""))
        self.entry_label = row("本地名")
        self.entry_label.insert(0, str(entry.get("label") or ""))

        engine_frame = tk.Frame(outer, bg=BG)
        engine_frame.pack(fill="x", pady=4)
        tk.Label(
            engine_frame, text="引擎", bg=BG, fg=DIM, font=(FONT_FAMILY, 9),
            width=12, anchor="w",
        ).pack(side="left")
        self.engine_var = tk.StringVar(value=str(entry.get("tts_engine") or "system"))
        self.engine_box = tk.OptionMenu(
            engine_frame, self.engine_var, "system", "edge", "command"
        )
        self.engine_box.configure(
            bg=PANEL, fg=TEXT, activebackground=PANEL, activeforeground=TEXT,
            relief="flat", highlightthickness=0, font=(FONT_FAMILY, 9), anchor="w",
        )
        self.engine_box["menu"].configure(
            bg=PANEL, fg=TEXT, activebackground=ACCENT, activeforeground="#10131a"
        )
        self.engine_box.pack(side="left")
        tk.Label(
            engine_frame, text="系统语音 / Edge 在线 / 自定义命令", bg=BG, fg=DIM,
            font=(FONT_FAMILY, 8),
        ).pack(side="left", padx=(8, 0))

        engine_area = tk.Frame(outer, bg=BG)
        engine_area.pack(fill="x")

        voice_frame = tk.Frame(engine_area, bg=BG)
        voice_frame.pack(fill="x", pady=4)
        self.voice_title = tk.Label(
            voice_frame, text="音色", bg=BG, fg=DIM, font=(FONT_FAMILY, 9),
            width=12, anchor="w",
        )
        self.voice_title.pack(side="left")
        self.voice_var = tk.StringVar(value=str(entry.get("tts_voice") or tr("（自动匹配）")))
        options = [tr("（自动匹配）")] + list(voices)
        self.voice_box = tk.OptionMenu(voice_frame, self.voice_var, *options)
        self.voice_box.configure(
            bg=PANEL, fg=TEXT, activebackground=PANEL, activeforeground=TEXT,
            relief="flat", highlightthickness=0, font=(FONT_FAMILY, 9), anchor="w",
        )
        self.voice_box["menu"].configure(
            bg=PANEL, fg=TEXT, activebackground=ACCENT, activeforeground="#10131a"
        )
        self.voice_box.pack(side="left", fill="x", expand=True)

        edge_frame = tk.Frame(engine_area, bg=BG)
        tk.Label(
            edge_frame, text="Edge 音色", bg=BG, fg=DIM, font=(FONT_FAMILY, 9),
            width=12, anchor="w",
        ).pack(side="left")
        self.edge_var = tk.StringVar(value=str(entry.get("tts_voice") or ""))
        self.edge_entry = tk.Entry(
            edge_frame, textvariable=self.edge_var, bg=PANEL, fg=TEXT,
            insertbackground=TEXT, relief="flat", font=(FONT_FAMILY, 9),
        )
        self.edge_entry.pack(side="left", fill="x", expand=True, ipady=4)
        self.edge_pick = tk.Label(
            edge_frame, text="选择…", bg=PANEL, fg=ACCENT, font=(FONT_FAMILY, 8),
            cursor="hand2", padx=8, pady=4,
        )
        self.edge_pick.pack(side="left", padx=(4, 0))
        self.edge_pick.bind("<Button-1>", lambda _e: self._pick_edge_voice())
        self.edge_pick.bind("<Enter>", lambda _e: self.edge_pick.configure(fg=TEXT))
        self.edge_pick.bind("<Leave>", lambda _e: self.edge_pick.configure(fg=ACCENT))

        cmd_frame = tk.Frame(engine_area, bg=BG)
        tk.Label(
            cmd_frame, text="命令", bg=BG, fg=DIM, font=(FONT_FAMILY, 9),
            width=12, anchor="w",
        ).pack(side="left")
        self.cmd_var = tk.StringVar(value=str(entry.get("tts_command") or ""))
        self.cmd_entry = tk.Entry(
            cmd_frame, textvariable=self.cmd_var, bg=PANEL, fg=TEXT,
            insertbackground=TEXT, relief="flat", font=(FONT_FAMILY, 9),
        )
        self.cmd_entry.pack(side="left", fill="x", expand=True, ipady=4)

        self.engine_hint = tk.Label(
            outer, text="", bg=BG, fg=DIM, font=(FONT_FAMILY, 8), anchor="w",
            justify="left", wraplength=400,
        )
        self.engine_hint.pack(fill="x", pady=(0, 4))

        def sync_engine(*_args) -> None:
            engine = self.engine_var.get()
            for frame in (voice_frame, edge_frame, cmd_frame):
                frame.pack_forget()
            if engine == "edge":
                edge_frame.pack(fill="x", pady=4)
                self.engine_hint.configure(
                    text="Edge 在线音色：如 fr-FR-DeniseNeural；留空按语言自动选。需要联网。"
                )
            elif engine == "command":
                cmd_frame.pack(fill="x", pady=4)
                self.engine_hint.configure(
                    text="命令模板，用 {text_file} {out_file} {lang} {voice} 占位；"
                    "命令要把 wav 写到 {out_file}。"
                )
            else:
                voice_frame.pack(fill="x", pady=4)
                self.engine_hint.configure(text="使用 Windows 已安装的 SAPI / OneCore 音色。")

        self.engine_var.trace_add("write", sync_engine)
        sync_engine()

        self.entry_deck = row("Anki 牌组")
        self.entry_deck.insert(0, str(entry.get("deck") or ""))
        tk.Label(
            outer,
            text="牌组留空会自动用 Reading::<名称>；音色留空则按语言自动匹配",
            bg=BG, fg=DIM, font=(FONT_FAMILY, 8),
        ).pack(fill="x", pady=(0, 6))

        btns = tk.Frame(outer, bg=BG)
        btns.pack(fill="x", pady=(6, 0))

        save_btn = tk.Label(
            btns, text="保存", bg=ACCENT, fg="#10131a", font=(FONT_FAMILY, 9),
            padx=16, pady=5, cursor="hand2",
        )
        save_btn.pack(side="right")
        save_btn.bind("<Button-1>", lambda _e: self._save())
        cancel_btn = tk.Label(
            btns, text="取消", bg=PANEL, fg=TEXT, font=(FONT_FAMILY, 9),
            padx=16, pady=5, cursor="hand2",
        )
        cancel_btn.pack(side="right", padx=(0, 8))
        cancel_btn.bind("<Button-1>", lambda _e: self.win.destroy())
        self.win.bind("<Escape>", lambda _e: self.win.destroy())
        self.win.bind("<Return>", lambda _e: self._save())
        if edit:
            self.entry_zh.focus_set()
        else:
            self.entry_code.focus_set()
        self.win.update_idletasks()
        parent_x = parent.winfo_rootx()
        parent_y = parent.winfo_rooty()
        width = max(self.win.winfo_reqwidth(), 400)
        height = max(self.win.winfo_reqheight(), 340)
        self.win.geometry(f"{width}x{height}+{parent_x + 120}+{parent_y + 100}")


    def _save(self) -> None:
        """收集表单并写进 self.result；英文界面允许中文名留空。"""
        code_value = self._code if self.edit else self.entry_code.get().strip().lower()
        zh = self.entry_zh.get().strip()
        label_value = self.entry_label.get().strip() or zh or code_value
        engine = self.engine_var.get().strip() or "system"
        if engine == "edge":
            voice = self.edge_var.get().strip()
        elif engine == "command":
            voice = ""
        else:
            voice = self.voice_var.get().strip()
            if voice in ("（自动匹配）", tr("（自动匹配）")):
                voice = ""
        command = self.cmd_var.get().strip() if engine == "command" else ""
        deck = self.entry_deck.get().strip() or f"Reading::{label_value or code_value}"
        if not re.fullmatch(r"[a-z]{2,8}(-[a-z]{2,8})?", code_value or ""):
            messagebox.showinfo(
                "语言代码", "代码用 2~8 位小写字母，例如 it、ja、ru、pt-BR。",
                parent=self.win,
            )
            return
        if not zh:
            if i18n.LANGUAGE != "en":
                messagebox.showinfo("中文名", "中文名不能为空。", parent=self.win)
                return
            # 英文界面允许只填本地名；中文名兜底成同一个显示名
            zh = label_value
        self.result = {
            "code": code_value,
            "label": label_value,
            "zh_label": zh,
            "target": "zh-CN",
            "tts_voice": voice,
            "tts_engine": engine,
            "tts_command": command,
            "deck": deck,
        }
        self.win.destroy()

    def _pick_edge_voice(self) -> None:
        if self.edge_provider is None:
            return
        if self._edge_choices is not None:
            self._show_edge_menu()
            return
        if self._edge_loading:
            return
        self._edge_loading = True
        self.edge_pick.configure(text="加载中…")
        code = (self.entry_code.get().strip().lower() or "en")

        def run() -> None:
            try:
                self._edge_choices = list(self.edge_provider(code) or [])
            except Exception:
                self._edge_choices = []
            self._edge_loading = False

        threading.Thread(target=run, daemon=True).start()
        self._poll_edge_choices(0)

    def _poll_edge_choices(self, tries: int) -> None:
        if self._edge_loading:
            if tries < 150 and self.win.winfo_exists():
                self.win.after(100, lambda: self._poll_edge_choices(tries + 1))
            return
        self.edge_pick.configure(text="选择…")
        if self._edge_choices:
            self._show_edge_menu()
        else:
            messagebox.showinfo(
                "Edge 音色", "没取到在线音色列表（可能没联网）。可以直接手动输入音色名。",
                parent=self.win,
            )

    def _show_edge_menu(self) -> None:
        menu = tk.Menu(
            self.win, tearoff=0, bg=PANEL, fg=TEXT,
            activebackground=ACCENT, activeforeground="#10131a",
            font=(FONT_FAMILY, 9),
        )

        def choose(value: str) -> None:
            self.edge_var.set(value)

        menu.add_command(label="（自动匹配）", command=lambda: choose(""))
        for voice in self._edge_choices or []:
            name = voice.get("name", "")
            gender = voice.get("gender", "")
            label = f"{name} · {gender}" if gender else name
            menu.add_command(label=label, command=lambda n=name: choose(n))
        try:
            menu.tk_popup(
                self.edge_pick.winfo_rootx(),
                self.edge_pick.winfo_rooty() + self.edge_pick.winfo_height(),
            )
        finally:
            menu.grab_release()


class ConfirmDeleteDialog:
    """删除语言的确认框，可选「以后不再提示」。"""

    def __init__(self, parent, title: str, text: str, show_check: bool = True) -> None:
        self.confirmed = False
        self.suppress = False
        self.win = tk.Toplevel(parent)
        self.win.title(title)
        self.win.configure(bg=BG)
        self.win.resizable(False, False)
        self.win.transient(parent)
        self.win.grab_set()

        outer = tk.Frame(self.win, bg=BG)
        outer.pack(fill="both", expand=True, padx=18, pady=14)
        tk.Label(
            outer, text=text, bg=BG, fg=TEXT, font=(FONT_FAMILY, 9),
            justify="left", anchor="w", wraplength=380,
        ).pack(fill="x")
        self.var_suppress = tk.BooleanVar(value=False)
        if show_check:
            tk.Checkbutton(
                outer, text="以后不再提示", variable=self.var_suppress,
                bg=BG, fg=DIM, selectcolor="#2f3440", activebackground=BG,
                activeforeground=TEXT, font=(FONT_FAMILY, 9), anchor="w",
            ).pack(fill="x", pady=(10, 0))
        btns = tk.Frame(outer, bg=BG)
        btns.pack(fill="x", pady=(12, 0))

        def confirm() -> None:
            self.confirmed = True
            self.suppress = bool(self.var_suppress.get())
            self.win.destroy()

        yes = tk.Label(
            btns, text="删除", bg="#8b3a3a", fg=TEXT, font=(FONT_FAMILY, 9),
            padx=16, pady=5, cursor="hand2",
        )
        yes.pack(side="right")
        yes.bind("<Button-1>", lambda _e: confirm())
        no = tk.Label(
            btns, text="取消", bg=PANEL, fg=TEXT, font=(FONT_FAMILY, 9),
            padx=16, pady=5, cursor="hand2",
        )
        no.pack(side="right", padx=(0, 8))
        no.bind("<Button-1>", lambda _e: self.win.destroy())
        self.win.bind("<Escape>", lambda _e: self.win.destroy())
        self.win.update_idletasks()
        parent_x = parent.winfo_rootx()
        parent_y = parent.winfo_rooty()
        width = max(self.win.winfo_reqwidth(), 380)
        height = max(self.win.winfo_reqheight(), 180)
        self.win.geometry(f"{width}x{height}+{parent_x + 140}+{parent_y + 110}")
