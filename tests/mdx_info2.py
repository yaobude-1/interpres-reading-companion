"""临时探测：逐字节看 key block info 的结构。"""

import struct
import zlib

P = (
    r"D:\Downloads\Compressed\Longman Dictionary of Contemporary English 6th ed. "
    r"Summer Edition (MDX)\朗文当代高级英语辞典 第6版 夏日清凉版 V3.2\朗文当代高级英语词典6th.mdx"
)

data = open(P, "rb").read(200000)
size = struct.unpack(">I", data[:4])[0]
meta = 4 + size + 4
nk, ne, info_decomp, info_comp, kb_size = struct.unpack(">QQQQQ", data[meta : meta + 40])
info_start = meta + 44
info = zlib.decompressobj().decompress(data[info_start + 8 : info_start + 8 + info_comp])
print("info len:", len(info))
print("first 96 bytes:")
for i in range(0, 96, 16):
    print(f"  {i:3d}:", info[i : i + 16].hex(" "))

# 尝试：entries(8) head_size(2) tail_size(2) comp(8) decomp(8) head tail
pos = 0
for i in range(3):
    entries = struct.unpack(">Q", info[pos : pos + 8])[0]
    hsize = struct.unpack(">H", info[pos + 8 : pos + 10])[0]
    tsize = struct.unpack(">H", info[pos + 10 : pos + 12])[0]
    comp = struct.unpack(">Q", info[pos + 12 : pos + 20])[0]
    decomp = struct.unpack(">Q", info[pos + 20 : pos + 28])[0]
    head = info[pos + 28 : pos + 28 + hsize]
    tail = info[pos + 28 + hsize : pos + 28 + hsize + tsize]
    pos += 28 + hsize + tsize
    print(f"block {i}: entries={entries} head={head!r} tail={tail!r} comp={comp} decomp={decomp} -> pos={pos}")
