"""验证长文本自动分块翻译。"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from rc.config import Config  # noqa: E402
from rc.service import CHUNK_CHARS, Service, split_chunks  # noqa: E402
from tests import mock_openai  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


def main() -> int:
    data = HERE / ".chunk"
    shutil.rmtree(data, ignore_errors=True)
    data.mkdir(parents=True)
    mock_openai.start(18778)

    cfg = Config(data)
    cfg.data["api"].update(
        {"base_url": "http://127.0.0.1:18778/v1", "api_key": "k", "model": "mock"}
    )
    cfg.save()
    service = Service(cfg)

    print("\n[切块规则]")
    short = "A short sentence."
    check("短文本不切", len(split_chunks(short)) == 1, str(split_chunks(short)))

    paragraph = "The quick brown fox jumps over the lazy dog. " * 30
    long_text = "\n\n".join([paragraph, paragraph, paragraph])
    chunks = split_chunks(long_text)
    check("长文本被切开", len(chunks) >= 3, f"{len(chunks)} 块")
    check("每块不超限", all(len(c) <= CHUNK_CHARS for c in chunks), str([len(c) for c in chunks]))
    check("原文不丢", sum(len(c) for c in chunks) >= len(long_text) * 0.95, str(len(long_text)))

    print("\n[分段翻译 + 合并]")
    mock_openai._Handler.calls = 0
    result = service.translate(long_text, book="Long Book")
    calls = mock_openai._Handler.calls
    unique = len({c for c in chunks})
    check(
        "按块调用模型（相同块只翻一次）",
        calls == unique,
        f"calls={calls}, unique={unique}, chunks={len(chunks)}",
    )
    check("meta 记录块数", result["meta"].get("chunks") == len(chunks), str(result["meta"]))
    check("译文合并了多段", result["translation"].count("敏捷的棕色狐狸") == len(chunks),
          result["translation"][:80])
    check("生词去重", len(result["terms"]) == 3, str(len(result["terms"])))

    print("\n[分块缓存]")
    mock_openai._Handler.calls = 0
    again = service.translate(long_text, book="Long Book")
    check("第二次全部命中缓存", mock_openai._Handler.calls == 0, str(mock_openai._Handler.calls))
    check("标记为缓存", again["meta"].get("cached") is True, str(again["meta"]))

    print("\n[短文本仍是单次]")
    mock_openai._Handler.calls = 0
    short_result = service.translate("The quick brown fox.", book="Long Book")
    check("一次调用", mock_openai._Handler.calls == 1, str(mock_openai._Handler.calls))
    check("没有 chunks 字段", "chunks" not in short_result["meta"], str(short_result["meta"]))

    service.store.close()
    shutil.rmtree(data, ignore_errors=True)
    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
