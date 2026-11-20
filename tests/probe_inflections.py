"""探针：法/拉词典里，变位形式是否能直接查到或指向原形。"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from rc.config import Config  # noqa: E402
from rc.dictionary import Dictionary  # noqa: E402

WORDS = {
    "fr": ["parlait", "furent", "aime", "aimer", "choses", "fait", "vais", "suis"],
    "la": ["puellae", "amavit", "fecerunt", "est", "amo", "amare", "puella", "regis"],
}


def main() -> int:
    cfg = Config()
    dicts = cfg.data.get("dictionaries") or {}
    for lang, words in WORDS.items():
        paths = dicts.get(lang) or {}
        mdx = paths.get("mdx")
        if not mdx:
            print(f"[{lang}] 没配置词典")
            continue
        dic = Dictionary(mdx, paths.get("mdd"))
        print(f"\n[{lang}] {Path(mdx).name}")
        for word in words:
            raw = dic._mdx.lookup(word)
            if not raw:
                print(f"  {word:12} -> 无词条")
                continue
            html = raw[1] if isinstance(raw, tuple) else raw
            if isinstance(html, bytes):
                html = html.decode("utf-8", "replace")
            note = ""
            for marker in ("→", "->", "see ", "radical", "infinitif"):
                if marker in html:
                    note = f"含 {marker!r}"
                    break
            print(f"  {word:12} -> 有词条（{len(html)} 字节）{note}")
            print("       ", html[:150].replace("\n", " "))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
