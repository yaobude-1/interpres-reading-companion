"""验证法语/拉丁词典的解析效果。"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from rc.dictionary import Dictionary  # noqa: E402

FR = r"D:\Downloads\Oxford_Hachette_French_English_Refined.mdx"
LA = (
    r"D:\桌面\Oxford Latin Dictionary (mdx & dsl)\Oxford Latin Dictionary (MDX)"
    r"\Oxford Latin Dictionary\Oxford Latin Dictionary.mdx"
)


def show(dictionary: Dictionary, words: list[str]) -> None:
    print(f"\n===== {dictionary.name} =====")
    print("能力:", dictionary.capabilities())
    for word in words:
        entry = dictionary.lookup(word)
        print(f"\n[{word}]")
        if not entry:
            print("  没找到")
            continue
        print(f"  词头: {entry.word} | 音标: {entry.phonetic} | 词性: {entry.pos}")
        for i, sense in enumerate(entry.senses[:3], 1):
            print(f"  {i}. {sense.definition_cn or sense.definition}")
            if sense.example:
                print(f"     例: {sense.example}")
            if sense.example_cn:
                print(f"     译: {sense.example_cn}")


def main() -> int:
    fr = Dictionary(FR)
    show(fr, ["temps", "aimer"])
    fr.close()

    la = Dictionary(LA)
    show(la, ["amo", "puella", "amor"])
    la.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
