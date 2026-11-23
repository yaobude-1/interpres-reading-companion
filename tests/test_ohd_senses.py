"""OHD（牛津-阿歇特）解析：每个义项必须带自己的词性，不能被第一个 nm 吞掉。"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from rc.dictionary import DictEntry, Dictionary  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


HTML = """
<article class="ohd-entry ohd-fr-en"><div class="ohd-body"><div>
  <div class="ohd-pos-block">
    <div class="ohd-pos-heading"><span class="ohd-part-number"><b>I. </b></span>
      <span><i class="ohd-pos">nm</i></span></div>
    <div class="ohd-pos-content"><div class="ohd-example-list">
      <blockquote class="ohd-example"><span class="ohd-example-mark"><b>• </b></span>
        <div class="ohd-example-content"><span><b class="ohd-phrase">au sortir de </b></span>
          <span>at the end of</span></div></blockquote>
    </div></div>
  </div>
  <div class="ohd-pos-block">
    <div class="ohd-pos-heading"><span class="ohd-part-number"><b>II. </b></span>
      <span><i class="ohd-pos">vtr</i></span></div>
    <div class="ohd-pos-content ohd-sense-list">
      <blockquote class="ohd-sense"><span class="ohd-sense-no"><b>1. </b></span>
        <div class="ohd-sense-content"><span><i class="ohd-cue">(promener) </i></span>
          <span>to take [sb] out</span></span>
          <div class="ohd-example-list"><blockquote class="ohd-example">
            <div class="ohd-example-content ohd-example-list">
              <span class="ohd-example-source">~ un malade</span>
              <span class="ohd-example-target">to take a patient out</span>
            </div></blockquote></div>
        </div></blockquote>
      <blockquote class="ohd-sense"><span class="ohd-sense-no"><b>2. </b></span>
        <div class="ohd-sense-content"><span>(inviter) to take [sb] out</span></div>
      </blockquote>
    </div>
  </div>
</div></div></article>
"""


def main() -> int:
    dictionary = Dictionary.__new__(Dictionary)  # 只测解析，不打开 MDX
    entry = DictEntry()
    dictionary._parse_oxford_hachette(entry, HTML)

    print("\n[OHD 词性分组]")
    check("entry.pos 是第一个词性", entry.pos == "nm", entry.pos)
    check("义项数", len(entry.senses) == 3, str(len(entry.senses)))
    check(
        "词性顺序",
        [sense.pos for sense in entry.senses] == ["nm", "vtr", "vtr"],
        str([sense.pos for sense in entry.senses]),
    )
    check(
        "nm 短语区有空义项",
        "au sortir de" in entry.senses[0].definition
        and "at the end of" in entry.senses[0].definition,
        entry.senses[0].definition,
    )
    check(
        "vtr 义项不挂到 nm",
        entry.senses[1].pos == "vtr" and entry.senses[2].pos == "vtr",
        str(entry.senses[1:].copy()),
    )
    check("vtr 例句", entry.senses[1].example == "~ un malade", entry.senses[1].example)

    print("\n失败项：", fails if fails else "无")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
