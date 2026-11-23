"""Service mixins share this annotated base.

Declaring the attributes here (instead of relying on implicit `self.store` etc.)
keeps the dependency surface visible to readers and to static analysers, without
changing runtime behaviour: these are annotations only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from .anki import Anki
    from .config import Config
    from .dictmanager import DictionaryManager
    from .llm import Translator
    from .store import Store
    from .tts import TTS
    from .user_lang import UserLangData


class ServiceBase:
    """Attributes set up by :meth:`rc.service.Service.__init__`."""

    config: Config
    data_dir: Path
    store: Store
    translator: Translator
    tts: TTS
    anki: Anki
    dicts: DictionaryManager
    user_lang: UserLangData
