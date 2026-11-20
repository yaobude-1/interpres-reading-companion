"""截图：生词本管理窗口。"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

import tkinter as tk  # noqa: E402

from PIL import ImageGrab  # noqa: E402

from rc.config import Config  # noqa: E402

OUT = HERE / "shots"
WORDS = [
    ("en", "ephemeral", "ephemeral", "/ɪˈfemərəl/", "形容词", "短暂的，转瞬即逝的", "Sapiens", "The beauty of the moment was ephemeral."),
    ("en", "sanguine", "sanguine", "/ˈsæŋɡwɪn/", "形容词", "乐观的，充满希望的", "Sapiens", "He remained sanguine about the outcome."),
    ("fr", "spleen", "spleen", "/splɛn/", "名词", "忧郁，烦闷（波德莱尔笔下的典型情绪）", "Les Fleurs du mal", "Le spleen n'est pas une maladie."),
    ("la", "amo", "amo, amare, amavi, amatum", "", "动词", "爱，喜爱", "Confessiones", "Amo te, Domine."),
    ("la", "puella", "puella, puellae, f", "", "名词", "女孩，少女", "Confessiones", "Puella in horto ambulat."),
    ("en", "quixotic", "quixotic", "/kwɪkˈsɒtɪk/", "形容词", "不切实际的，堂吉诃德式的", "Sapiens", "A quixotic plan."),
]


def main() -> int:
    OUT.mkdir(exist_ok=True)
    data = HERE / ".uidata"
    cfg = Config(data)
    cfg.save()
    from rc.service import Service

    service = Service(cfg)
    for lang, word, lemma, reading, pos, meaning, book, sentence in WORDS:
        service.add_vocab(
            lang=lang, word=word, lemma=lemma, reading=reading, pos=pos,
            meaning=meaning, book=book, sentence=sentence,
        )

    from rc.vocab_ui import VocabWindow

    root = tk.Tk()
    root.withdraw()
    win = VocabWindow(root, service, cfg)
    root.after(900, lambda: ImageGrab.grab().save(OUT / "vocab.png"))
    root.after(1600, root.destroy)
    root.mainloop()
    _ = win
    service.store.close()
    import shutil

    shutil.rmtree(data, ignore_errors=True)
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
