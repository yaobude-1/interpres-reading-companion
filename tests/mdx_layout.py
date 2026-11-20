"""临时探测：找出 MDX 头之后各结构的真实位置。"""

import struct
import zlib

P = (
    r"D:\Downloads\Compressed\Longman Dictionary of Contemporary English 6th ed. "
    r"Summer Edition (MDX)\朗文当代高级英语辞典 第6版 夏日清凉版 V3.2\朗文当代高级英语词典6th.mdx"
)

data = open(P, "rb").read(6000)
size = struct.unpack(">I", data[:4])[0]
print("header size field:", size)

for off in range(700, 1200):
    if data[off] != 0x78 or data[off + 1] not in (0x01, 0x9C, 0xDA):
        continue
    try:
        d = zlib.decompressobj()
        out = d.decompress(data[off:])
        head = out[:16]
        print(f"zlib at {off}: out={len(out)} bytes, head={head.hex(' ')}")
        if len(out) % 16 == 0 and len(out) < 100000:
            pairs = [struct.unpack(">QQ", out[i : i + 16]) for i in range(0, min(len(out), 64), 16)]
            print("   as pairs:", pairs)
    except Exception:
        pass

# 把 700~800 的字节按 4 字节一组打印，方便对齐
print("\n--- 700..820 as 8-byte BE ---")
base = size
for i in range(base, base + 120, 8):
    print(f"{i:5d}: {struct.unpack('>Q', data[i:i+8])[0]:>18}   {data[i:i+8].hex(' ')}")
