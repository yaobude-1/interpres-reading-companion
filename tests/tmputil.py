"""Project-local temporary directories for tests.

The DSH/Windows sandbox can lock %TEMP%; keeping ephemeral fixtures under the
checkout makes these tests portable without changing application code.
"""

from __future__ import annotations

import shutil
import uuid
from contextlib import contextmanager
from pathlib import Path

_BASE = Path(__file__).resolve().parent / ".tmp_tests"


@contextmanager
def local_temp(prefix: str = "case-"):
    path = _BASE / (prefix + uuid.uuid4().hex[:10])
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield str(path)
    finally:
        shutil.rmtree(path, ignore_errors=True)
