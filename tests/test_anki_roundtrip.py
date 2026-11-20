"""Anki 真实往返：加词 → 同步 → 核对卡片 → 判重 → 删卡重同步 → 清理。

用法：先打开 Anki（装好 AnkiConnect），再运行。
测试牌组是 InterpresTest，结束时删掉，不会留在收藏里。
"""

from __future__ import annotations

import shutil
import sys
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from rc import anki as anki_mod  # noqa: E402
from rc.config import Config  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


def main() -> int:
    client = anki_mod.Anki()
    try:
        if not client.ping():
            print("Anki 没开（或 AnkiConnect 没装），跳过。")
            return 0
    except Exception as exc:  # noqa: BLE001
        print(f"连不上 Anki：{exc}")
        return 0

    tag = "rc-test-" + uuid.uuid4().hex[:6]
    deck = "InterpresTest"
    words = [
        (f"{tag}-alpha", "测试甲"),
        (f"{tag}-beta", "测试乙"),
        (f"{tag}-gamma", "测试丙"),
    ]

    tmp = HERE / "ankitmp"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    cfg = Config(tmp)
    cfg.data["languages"]["en"]["deck"] = deck
    cfg.save()

    from rc.service import Service

    svc = Service(cfg)
    for word, meaning in words:
        svc.add_vocab(
            lang="en",
            word=word,
            lemma=word,
            reading="/t/",
            pos="n.",
            meaning=meaning,
            dict_meaning=meaning,
        )
    print(f"生词本里加了 {len(words)} 个测试词（{tag}）")

    def set_synced(value: int, only_word: str | None = None) -> None:
        with svc.store._lock:
            if only_word:
                svc.store._conn.execute(
                    "UPDATE vocab SET synced = ? WHERE word = ?", (value, only_word)
                )
            else:
                svc.store._conn.execute(
                    "UPDATE vocab SET synced = ? WHERE word LIKE ?", (value, tag + "%")
                )
            svc.store._conn.commit()

    print("\n[第一次同步]")
    result1 = svc.push_anki("en")
    print("  ", result1)
    check("新增 3 张", result1.get("added", 0) == 3, str(result1))

    notes = client._invoke(
        "findNotes", query=f'deck:"{deck}" "Word:{tag}-alpha"'
    ) or []
    check("Anki 里查到 alpha 卡片", len(notes) == 1, str(notes))
    if notes:
        info = client._invoke("notesInfo", notes=notes)[0]
        fields = info.get("fields") or {}
        check("卡片 Word 字段正确", tag + "-alpha" in (fields.get("Word") or {}).get("value", ""))
        check("卡片 Meaning 字段正确", "测试甲" in (fields.get("Meaning") or {}).get("value", ""))

    print("\n[判重：重置同步标记后再推一次]")
    set_synced(0)
    result2 = svc.push_anki("en")
    print("  ", result2)
    check("不重复加卡", result2.get("added", 0) == 0, str(result2))
    check("识别为已存在", (result2.get("skipped", 0) + result2.get("duplicated", 0)) >= 3, str(result2))

    print("\n[删掉一张卡再同步]")
    target = client._invoke("findNotes", query=f'deck:"{deck}" "Word:{tag}-beta"') or []
    if target:
        client._invoke("deleteNotes", notes=target)
    set_synced(0, tag + "-beta")
    result3 = svc.push_anki("en")
    print("  ", result3)
    check("删掉的那张补回来了", result3.get("added", 0) == 1, str(result3))

    print("\n[清理]")
    try:
        client._invoke("deleteDecks", decks=[deck], cardsToo=True)
        print(f"  已删测试牌组 {deck}")
    except Exception as exc:  # noqa: BLE001
        print(f"  清理失败，请手动删掉牌组 {deck}：{exc}")

    svc.store.close() if hasattr(svc.store, "close") else None
    shutil.rmtree(tmp, ignore_errors=True)
    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
