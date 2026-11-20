"""临时探测：解析 key block info 的每条记录格式。"""

import struct
import zlib

P = (
    r"D:\Downloads\Compressed\Longman Dictionary of Contemporary English 6th ed. "
    r"Summer Edition (MDX)\朗文当代高级英语辞典 第6版 夏日清凉版 V3.2\朗文当代高级英语词典6th.mdx"
)

data = open(P, "rb").read(200000)
size = struct.unpack(">I", data[:4])[0]
print("size field:", size)
# 头部内容 size 字节，然后 4 字节校验，然后 key list meta
meta_at = 4 + size + 4
print("meta candidate at", meta_at, "bytes:", data[meta_at : meta_at + 48].hex(" "))
nk, ne, info_decomp, info_comp, kb_size = struct.unpack(">QQQQQ", data[meta_at : meta_at + 40])
print("num_key_blocks:", nk, "num_entries:", ne, "info_decomp:", info_decomp, "info_comp:", info_comp, "key_block_size:", kb_size)

# info = 4字节类型 + 4字节校验 + zlib
info_start = meta_at + 44
print("info prefix:", data[info_start : info_start + 8].hex(" "))
info = zlib.decompressobj().decompress(data[info_start + 8 : info_start + 8 + info_comp])
print("info decompressed:", len(info), "(期望", info_decomp, ")")

pos = 0
for i in range(min(nk, 4)):
    n_entries = struct.unpack(">Q", info[pos : pos + 8])[0]
    pos += 8
    head_len = struct.unpack(">H", info[pos : pos + 2])[0]
    pos += 2
    head = info[pos : pos + head_len]
    pos += head_len
    tail_len = struct.unpack(">H", info[pos : pos + 2])[0]
    pos += 2
    tail = info[pos : pos + tail_len]
    pos += tail_len
    comp = struct.unpack(">Q", info[pos : pos + 8])[0]
    pos += 8
    decomp = struct.unpack(">Q", info[pos : pos + 8])[0]
    pos += 8
    print(f"block {i}: entries={n_entries} head={head!r} tail={tail!r} comp={comp} decomp={decomp}")

print("consumed after first block:", pos, "of", len(info))
