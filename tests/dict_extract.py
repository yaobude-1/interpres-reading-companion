"""探测朗文6 词条里 释义/例句/音频 的结构。"""

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from rc.mdx import MDX, html_to_text  # noqa: E402

DICT = (
    r"D:\Downloads\Compressed\Longman Dictionary of Contemporary English 6th ed. "
    r"Summer Edition (MDX)\朗文当代高级英语辞典 第6版 夏日清凉版 V3.2\朗文当代高级英语词典6th.mdx"
)

d = MDX(DICT)
html = d.lookup("ephemeral")

print("--- def 片段 ---")
for m in list(re.finditer(r'<span class="def"[^>]*>(.{0,200}?)</span>', html))[:6]:
    print("  ", repr(html_to_text(m.group(1))[:100]))

print("--- sense 标签 ---")
for m in list(re.finditer(r'<span class="sense"[^>]*>', html))[:4]:
    print("  ", m.group(0)[:120])

print("--- 音标 ---")
m = re.search(r'<span class="pron">(.*?)</span>', html)
print("  ", html_to_text(m.group(1)) if m else None)

print("--- 词性 ---")
m = re.search(r'<span class="pos">(.*?)</span>', html)
print("  ", html_to_text(m.group(1)) if m else None)

print("--- 音频键 ---")
print("  ", re.findall(r'sound://([^"\']+)', html)[:4])

print("--- 例句(ul.exas) ---")
for m in list(re.finditer(r'<ul class="exas">(.*?)</ul>', html, re.S))[:2]:
    items = re.findall(r"<li>(.*?)</li>", m.group(1), re.S)
    for item in items[:3]:
        print("  ", html_to_text(item)[:100])

d.close()
