"""Helpers shared by the settings window and its page mixin."""

from __future__ import annotations

import logging
import os
import subprocess

from . import i18n
from .llm import SYSTEM_PROMPT as _ZH_TRANSLATE_PROMPT
from .prompts_en import (
    CHAT_PERSONA_EN as _EN_CHAT_PERSONA,
    CHAT_RULES_EN as _EN_CHAT_RULES,
    SYSTEM_PROMPT_EN as _EN_TRANSLATE_PROMPT,
)
from .service import (
    CHAT_PERSONA_DEFAULT as _ZH_CHAT_PERSONA,
    CHAT_RULES_DEFAULT as _ZH_CHAT_RULES,
)

log = logging.getLogger("rc")


def default_translate_prompt() -> str:
    return _EN_TRANSLATE_PROMPT if i18n.LANGUAGE == "en" else _ZH_TRANSLATE_PROMPT


def default_chat_persona() -> str:
    return _EN_CHAT_PERSONA if i18n.LANGUAGE == "en" else _ZH_CHAT_PERSONA


def default_chat_rules() -> str:
    return _EN_CHAT_RULES if i18n.LANGUAGE == "en" else _ZH_CHAT_RULES


def open_target(target: str) -> None:
    try:
        os.startfile(target)  # type: ignore[attr-defined]
    except Exception:
        try:
            subprocess.Popen(["explorer", target])
        except OSError as exc:  # noqa: BLE001 - 打不开目录时静默失败
            log.debug("用资源管理器打开失败: %s", exc)
