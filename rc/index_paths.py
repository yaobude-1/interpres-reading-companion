"""Central location for generated dictionary index caches.

Index caches are implementation detail, not user content.  Keep them out of
the dictionary folders and under the app data directory instead.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path


def cache_dir() -> Path:
    override = os.environ.get("INTERPRES_INDEX_DIR")
    candidates = [Path(override)] if override else []
    candidates += [
        Path.home() / ".reading-companion" / "dict-index",
        Path(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir())
        / "Interpres"
        / "dict-index",
        Path(tempfile.gettempdir()) / "Interpres" / "dict-index",
    ]
    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate
        except OSError:
            continue
    return Path(tempfile.gettempdir()) / "Interpres" / "dict-index"


def sidecar(source: str | Path, suffix: str) -> Path:
    path = Path(source)
    try:
        key = os.path.normcase(str(path.resolve()))
    except OSError:
        key = os.path.normcase(str(path.absolute()))
    digest = hashlib.sha1(key.encode("utf-8", "replace")).hexdigest()[:20]
    return cache_dir() / f"{digest}{suffix}"
