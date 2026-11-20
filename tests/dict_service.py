"""验证词典服务：结构化提取 + 真人发音。"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from rc.dictionary import Dictionary  # noqa: E402

BASE = (
    r"D:\Downloads\Compressed\Longman Dictionary of Contemporary English 6th ed. "
    r"Summer Edition (MDX)\朗文当代高级英语辞典 第6版 夏日清凉版 V3.2"
)
MDX_PATH = BASE + r"\朗文当代高级英语词典6th.mdx"
MDD_PATH = BASE + r"\朗文当代高级英语词典6th.mdd"


def main() -> int:
    dict_ = Dictionary(MDX_PATH, MDD_PATH)
    print("词典:", dict_.name, "| 词条:", dict_.entry_count)
    print("能力:", dict_.capabilities())

    for word in ("ephemeral", "sanguine", "quixotic"):
        entry = dict_.lookup(word)
        print(f"\n===== {word} =====")
        if not entry:
            print("  没找到")
            continue
        print(f"  词头: {entry.word} | 音标: /{entry.phonetic}/ | 词性: {entry.pos}")
        for i, sense in enumerate(entry.senses[:3], 1):
            print(f"  {i}. {sense.definition_cn or sense.definition}")
            if sense.example:
                print(f"     例: {sense.example}")
            if sense.example_cn:
                print(f"     译: {sense.example_cn}")
        print("  音频键:", entry.audio_keys[:2])
        if entry.audio_keys:
            data = dict_.audio(entry.audio_keys[0])
            if data:
                head = data[:4]
                kind = "ID3" if head[:3] == b"ID3" else ("MP3" if head[0] == 0xFF else "?")
                print(f"  音频: {len(data)} 字节, 格式 {kind}, 头 {head.hex()}")
            else:
                print("  音频: 没取到")

    dict_.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
