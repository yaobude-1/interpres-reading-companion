"""临时探测：顺序解压 MDX 的各个 zlib 块，反推真实布局。"""

import struct
import zlib

P = (
    r"D:\Downloads\Compressed\Longman Dictionary of Contemporary English 6th ed. "
    r"Summer Edition (MDX)\朗文当代高级英语辞典 第6版 夏日清凉版 V3.2\朗文当代高级英语词典6th.mdx"
)

f = open(P, "rb")
size = struct.unpack(">I", f.read(4))[0]
f.seek(size)
prologue = f.read(64)
print("prologue:", prologue.hex(" "))
print("fields at +8:", struct.unpack(">QQQ", prologue[8:32]))

# 从 766 开始顺序解压
f.seek(766)
pos = 766
total_entries = 0
for block in range(200):
    f.seek(pos)
    head = f.read(2)
    if head != b"\x78\xda" and head != b"\x78\x9c" and head != b"\x78\x01":
        print(f"block {block}: not zlib at {pos}, head={head.hex()}")
        print("next 48 bytes:", f.read(46).hex(" "))
        break
    f.seek(pos)
    chunk = f.read(4 << 20)
    d = zlib.decompressobj()
    try:
        out = d.decompress(chunk)
    except Exception as exc:
        print(f"block {block}: decompress error {exc}")
        break
    consumed = len(chunk) - len(d.unused_data)
    entries = 0
    i = 0
    while i < len(out):
        _off = struct.unpack(">Q", out[i : i + 8])[0]
        i += 8
        ln = struct.unpack(">H", out[i : i + 2])[0]
        i += 2 + ln
        entries += 1
    total_entries += entries
    if block < 3 or block > 99:
        print(f"block {block}: at {pos}, out={len(out)}, consumed={consumed}, entries={entries}, tail={out[-12:].hex(' ')}")
    # 块后可能有 4 字节 adler
    next_pos = pos + consumed
    f.seek(next_pos)
    nxt = f.read(6)
    if nxt[:2] not in (b"\x78\xda", b"\x78\x9c", b"\x78\x01"):
        next_pos2 = pos + consumed + 4
        f.seek(next_pos2)
        nxt2 = f.read(6)
        if nxt2[:2] in (b"\x78\xda", b"\x78\x9c", b"\x78\x01"):
            next_pos = next_pos2
        else:
            print(f"block {block}: after block neither +0 nor +4 is zlib; bytes={nxt.hex(' ')} / {nxt2.hex(' ')}")
            pos = pos + consumed
            break
    pos = next_pos

print("total entries parsed:", total_entries, "| next pos:", pos)
f.close()
