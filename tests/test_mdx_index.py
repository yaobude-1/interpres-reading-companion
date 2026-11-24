"""MDX sidecar index and fuzzy cache correctness."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from rc.fuzzy import build_index  # noqa: E402
from rc.index_paths import sidecar  # noqa: E402
from rc.mdx_index import MdxIndex  # noqa: E402
from tmputil import local_temp  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


def main() -> int:
    with local_temp("mdx-index-") as tmp:
        os.environ["INTERPRES_INDEX_DIR"] = str(Path(tmp) / "indexes")
        path = Path(tmp) / "dict.mdx"
        path.write_bytes(b"x" * 32)
        calls = 0

        def keys():
            nonlocal calls
            calls += 1
            return iter(
                [
                    ("alpha", 10),
                    ("Alpha", 20),
                    ("amō", 30),
                    ("beta", 40),
                ]
            )

        index = MdxIndex.open_or_build(
            path, keys, lambda key: key.replace("ō", "o")
        )
        check("built index", index is not None)
        assert index is not None
        check("entry count", index.entry_count == 4, str(index.entry_count))
        check("exact case", index.find_exact("Alpha") == 20)
        check("folded first", index.find_folded("alpha") == 10)
        check("alias exact", index.find_exact("amo") == 30)
        check("alias folded", index.find_folded("amo") == 30)
        check("prefix", index.prefix("alp", 5) == ["alpha", "Alpha"])
        check("offsets", list(index.offsets) == [10, 20, 30, 40])
        check("keys view", list(index.iter_keys())[0] == ("alpha", 10))
        index.close()
        check("built once", calls == 1, str(calls))

        # A second open must use the sidecar, not re-parse keys.
        reopened = MdxIndex.open_or_build(
            path, keys, lambda key: key.replace("ō", "o")
        )
        check("reopened cache", reopened is not None and calls == 1)
        assert reopened is not None
        check("cache exact", reopened.find_exact("beta") == 40)
        reopened.close()

        # Changing the source invalidates the cache.
        time.sleep(0.01)
        path.write_bytes(b"y" * 33)
        rebuilt = MdxIndex.open_or_build(
            path, keys, lambda key: key.replace("ō", "o")
        )
        check("rebuilt after change", rebuilt is not None and calls == 2)
        assert rebuilt is not None
        rebuilt.close()

        # Fuzzy cache: first build writes a sidecar, second load reuses it.
        source = Path(tmp) / "fuzzy.mdx"
        source.write_bytes(b"z" * 16)

        class FakeMdx:
            def __init__(self) -> None:
                self.path = source
                self._keys = [("alpha", 1), ("beta", 2), ("gamma", 3)]

        class FakeDictionary:
            def __init__(self) -> None:
                self._mdx = FakeMdx()

        first = FakeDictionary()
        first_index = build_index(first)
        check("fuzzy built", first_index is not None and len(first_index) == 3)
        second = FakeDictionary()
        second_index = build_index(second)
        check("fuzzy loaded", second_index is not None and len(second_index) == 3)
        check(
            "fuzzy cache exists",
            sidecar(source, ".rcfuzzy").exists(),
        )

    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
