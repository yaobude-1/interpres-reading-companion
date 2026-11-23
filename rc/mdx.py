"""MDX/MDD 词典读取（纯标准库）。

支持的布局（MDX 2.0，未加密）：

    header:      size(4) + UTF-16LE 属性文本(size 字节) + checksum(4)
    key header:  num_key_blocks(8) + num_entries(8) + info_decomp(8)
                 + info_comp(8) + key_block_size(8) + checksum(4)
    key info:    type(4) + checksum(4) + zlib(info_comp - 8)，解压后每块一条：
                 entries(8) + head_len(2) + head + 0x00
                 + tail_len(2) + tail + 0x00 + comp(8) + decomp(8)
    key blocks:  依次 [type(4) + checksum(4) + zlib(comp - 8)]
                 解压后是 [offset(8) + key + 0x00] 序列
    record info: num_blocks(8) + num_entries(8) + info_size(8) + data_size(8)
                 + 每块 comp(8) + decomp(8)
    record blocks: 依次 [type(4) + checksum(4) + zlib(comp - 8)]

只读，不写。
"""

from __future__ import annotations

import bisect
import html as html_lib
import logging
import re
import struct
import threading
import zlib
from pathlib import Path

from .lzo import decompress as _lzo_decompress

log = logging.getLogger("rc")


class MDXError(RuntimeError):
    pass


_MACRON_TABLE = {ord(c): ord(p) for c, p in zip("āēīōūȳĀĒĪŌŪȲ", "aeiouyAEIOUY", strict=True)}
_MACRON_TABLE[0x0304] = None  # 组合长音符号直接删掉


def _parse_header(raw: bytes) -> dict:
    text = raw.decode("utf-16le", "ignore").strip("\x00")
    return dict(re.findall(r'(\w+)\s*=\s*"([^"]*)"', text))


class MDX:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._fh = self.path.open("rb")
        self._lock = threading.RLock()
        self.attrs = self._read_header()
        declared = (self.attrs.get("Encoding") or "").strip().upper()
        if declared:
            self.encoding = declared
        elif self.path.suffix.lower() == ".mdd":
            self.encoding = "UTF-16"  # MDD 的键默认是 UTF-16LE
        else:
            self.encoding = "UTF-8"
        self._unit = 2 if "UTF-16" in self.encoding else 1
        self.encrypted = str(self.attrs.get("Encrypted", "0")).lower()
        version = self.attrs.get("GeneratedByEngineVersion") or ""
        if self.encrypted in ("2", "3", "yes"):
            raise MDXError("这本词典带加密锁（Encrypted=2），需要注册码，暂不支持")
        if self.encrypted in ("1",):
            raise MDXError("这本词典加密了记录块（Encrypted=1），暂不支持")
        try:
            self._version_number = float(version or "2.0")
        except ValueError:
            self._version_number = 2.0
        self._legacy = self._version_number < 2.0
        if self._legacy and not version.startswith("1."):
            raise MDXError(f"不认识的 MDX 版本：{version}")
        self.version = version or "2.0"
        self._keys: list[tuple[str, int]] = []
        self._key_index: dict[str, int] = {}
        self._exact_index: dict[str, int] = {}
        self._record_blocks: list[tuple[int, int, int]] = []
        self._record_start = 0
        self._cache: dict[int, bytes] = {}
        self._read_header_offset()
        self._read_key_info()
        self._read_keys()
        self._read_record_info()

    # ------------------------------------------------------------------ 头部
    def _read_header(self) -> dict:
        f = self._fh
        f.seek(0)
        size = struct.unpack(">I", f.read(4))[0]
        return _parse_header(f.read(size))

    def _read_header_offset(self) -> None:
        self._fh.seek(0)
        size = struct.unpack(">I", self._fh.read(4))[0]
        self._meta_at = 4 + size + 4  # 头部文本 + 4 字节校验

    # -------------------------------------------------------------- key 索引
    def _read_key_info(self) -> None:
        f = self._fh
        f.seek(self._meta_at)
        if self._legacy:
            (
                self.num_key_blocks,
                self.num_entries,
                self._info_comp,
                self.key_block_size,
            ) = struct.unpack(">IIII", f.read(16))
            self._info_at = self._meta_at + 16
            f.seek(self._info_at)
            info = f.read(self._info_comp)
            pos = 0
            self._key_blocks: list[tuple[int, int]] = []
            for _ in range(self.num_key_blocks):
                _entries = struct.unpack(">I", info[pos : pos + 4])[0]
                pos += 4
                head_len = info[pos]
                pos += 1
                pos += head_len * self._unit
                tail_len = info[pos]
                pos += 1
                pos += tail_len * self._unit
                comp, decomp = struct.unpack(">II", info[pos : pos + 8])
                pos += 8
                self._key_blocks.append((comp, decomp))
            return

        (
            self.num_key_blocks,
            self.num_entries,
            info_decomp,
            info_comp,
            self.key_block_size,
        ) = struct.unpack(">QQQQQ", f.read(40))
        self._info_comp = info_comp
        f.read(4)  # 校验
        self._info_at = self._meta_at + 44
        f.seek(self._info_at)
        prefix = f.read(8)
        if prefix[:4] != b"\x02\x00\x00\x00":
            raise MDXError("词条索引格式不认识（压缩类型不是 zlib）")
        raw = f.read(info_comp - 8)
        info = zlib.decompress(raw)
        if len(info) != info_decomp:
            raise MDXError("词条索引长度不符")

        pos = 0
        self._key_blocks: list[tuple[int, int]] = []
        for _ in range(self.num_key_blocks):
            _entries = struct.unpack(">Q", info[pos : pos + 8])[0]
            pos += 8
            head_len = struct.unpack(">H", info[pos : pos + 2])[0]
            pos += 2 + head_len * self._unit + self._unit  # 首词 + 结尾 0
            tail_len = struct.unpack(">H", info[pos : pos + 2])[0]
            pos += 2 + tail_len * self._unit + self._unit  # 尾词 + 结尾 0
            comp, decomp = struct.unpack(">QQ", info[pos : pos + 16])
            pos += 16
            self._key_blocks.append((comp, decomp))

    def _read_keys(self) -> None:
        f = self._fh
        f.seek(self._info_at + self._key_block_meta_size())
        unit = self._unit
        width = 4 if self._legacy else 8
        for comp, decomp in self._key_blocks:
            block = f.read(comp)
            data = _inflate_block(block, decomp if self._legacy else None)
            pos = 0
            while pos + width + unit <= len(data):
                if width == 4:
                    offset = struct.unpack(">I", data[pos : pos + 4])[0]
                else:
                    offset = struct.unpack(">Q", data[pos : pos + 8])[0]
                pos += width
                if unit == 2:
                    end = pos
                    while end + 1 < len(data) and not (data[end] == 0 and data[end + 1] == 0):
                        end += 2
                    key = data[pos:end].decode("utf-16le", "replace")
                    pos = end + 2
                else:
                    end = data.find(b"\x00", pos)
                    if end < 0:
                        break
                    key = data[pos:end].decode(self.encoding, "replace")
                    pos = end + 1
                self._keys.append((key, offset))
        self.entry_count = len(self._keys)
        for i, (key, _offset) in enumerate(self._keys):
            self._key_index.setdefault(key.lower(), i)
            self._exact_index.setdefault(key, i)
        # 拉丁语词典的键带长音符号（amō），补一个去掉长音符号的别名
        for i, (key, _offset) in enumerate(self._keys):
            plain = key.translate(_MACRON_TABLE)
            if plain != key:
                self._key_index.setdefault(plain.lower(), i)
                self._exact_index.setdefault(plain, i)
        self._offsets = sorted({offset for _key, offset in self._keys})

    def _key_block_meta_size(self) -> int:
        # info 段总长 = info_comp（含 8 字节前缀）
        return self._info_comp

    @property
    def info_comp(self) -> int:
        return self._info_comp

    # ------------------------------------------------------------ record 索引
    def _read_record_info(self) -> None:
        f = self._fh
        start = self._info_at + self.info_comp + sum(c for c, _d in self._key_blocks)
        f.seek(start)
        if self._legacy:
            num_blocks, _num_entries, info_size, _data_size = struct.unpack(
                ">IIII", f.read(16)
            )
            blocks = []
            acc = 0
            for _ in range(num_blocks):
                comp, decomp = struct.unpack(">II", f.read(8))
                blocks.append((comp, decomp, acc))
                acc += decomp
            self._record_blocks = blocks
            self._record_start = f.tell()
            self._record_total = acc
            return

        num_blocks, _num_entries, info_size, _data_size = struct.unpack(
            ">QQQQ", f.read(32)
        )
        blocks = []
        acc = 0
        for _ in range(num_blocks):
            comp, decomp = struct.unpack(">QQ", f.read(16))
            blocks.append((comp, decomp, acc))
            acc += decomp
        self._record_blocks = blocks
        self._record_start = f.tell()
        self._record_total = acc

    # ------------------------------------------------------------------ 读取
    def _read_record(self, offset: int) -> bytes:
        # MDX 只有一个文件句柄；翻译会并发查词，seek/read 必须串行。
        with self._lock:
            return self._read_record_locked(offset)

    def _read_record_locked(self, offset: int) -> bytes:
        if not self._record_blocks or offset < 0 or offset >= self._record_total:
            raise MDXError("记录偏移越界")
        index = 0
        for i, (_comp, _decomp, start) in enumerate(self._record_blocks):
            if start <= offset:
                index = i
            else:
                break
        if index not in self._cache:
            f = self._fh
            f.seek(self._record_start)
            for i, (comp, decomp, _start) in enumerate(self._record_blocks):
                if i == index:
                    self._cache.clear()
                    self._cache[index] = _inflate_block(
                        f.read(comp), decomp if self._legacy else None
                    )
                    break
                f.seek(comp, 1)
        data = self._cache[index]
        local = offset - self._record_blocks[index][2]
        # 记录长度由下一个记录的偏移决定（MDD 的音频里也有 0x00，不能靠找 0 截断）
        nxt = bisect.bisect_right(self._offsets, offset)
        if nxt < len(self._offsets):
            end = self._offsets[nxt] - self._record_blocks[index][2]
        else:
            end = len(data)
        end = min(end, len(data))
        return data[local:end].rstrip(b"\x00")

    # ------------------------------------------------------------------ 查询
    def _lookup_raw(self, key: str) -> str | None:
        # 先按大小写精确匹配（'AI' 和 'ai' 可能是不同的记录）
        exact = self._exact_index.get(key)
        if exact is not None:
            _key, offset = self._keys[exact]
            try:
                return self._read_record(offset).decode(self.encoding, "replace")
            except MDXError:
                return None
        for candidate in (key, key.lower(), key.capitalize(), key.upper()):
            idx = self._key_index.get(candidate.lower())
            if idx is not None:
                _key, offset = self._keys[idx]
                try:
                    return self._read_record(offset).decode(self.encoding, "replace")
                except MDXError:
                    return None
        return None

    def lookup(self, word: str) -> str | None:
        """查词，自动跟随 @@@LINK= 跳转（带环路保护）。"""
        key = (word or "").strip()
        if not key:
            return None
        text = self._lookup_raw(key)
        seen = {key}
        for _ in range(5):
            if not text:
                return None
            stripped = text.lstrip()
            if not stripped.startswith("@@@LINK="):
                return text
            target = stripped[len("@@@LINK="):].strip().strip("\r\n")
            if not target or target in seen:
                return None
            seen.add(target)
            text = self._lookup_raw(target)
        return None

    def keys_matching(self, prefix: str, limit: int = 10) -> list[str]:
        prefix = prefix.lower()
        out = []
        for key, _offset in self._keys:
            if key.lower().startswith(prefix):
                out.append(key)
                if len(out) >= limit:
                    break
        return out

    # -------------------------------------------------------------- 二进制读取
    def lookup_bytes(self, key: str) -> bytes | None:
        """按原始键取二进制记录（MDD 音频/图片用）。"""
        candidates = [
            key,
            key.replace("/", "\\"),
            "\\" + key.replace("/", "\\").lstrip("\\"),
            key.lower(),
        ]
        for candidate in candidates:
            idx = self._key_index.get(candidate.lower())
            if idx is not None:
                _key, offset = self._keys[idx]
                try:
                    return self._read_record(offset)
                except MDXError:
                    return None
        return None

    def close(self) -> None:
        try:
            self._fh.close()
        except OSError as exc:  # noqa: BLE001 - 关闭失败不影响已读数据
            log.debug("关闭词典文件失败: %s", exc)


class MDD(MDX):
    """MDD 和 MDX 结构相同，只是记录是二进制资源（音频、图片）。"""

    def lookup_audio(self, sound_key: str) -> bytes | None:
        return self.lookup_bytes(sound_key)


def _inflate_block(block: bytes, expected: int | None = None) -> bytes:
    """块结构：[type(4) + checksum(4) + payload]，type 1=LZO, 2=zlib。"""
    if len(block) < 8:
        raise MDXError("数据块太短")
    kind = struct.unpack("<I", block[:4])[0]
    body = block[8:]
    if kind == 2:
        try:
            return _decompress_capped(body)
        except zlib.error:
            return _decompress_capped(block[4:])
    if kind == 1:
        if expected is None:
            raise MDXError("LZO 块缺少解压长度")
        try:
            return _lzo_decompress(body, expected)
        except (ValueError, IndexError) as exc:
            raise MDXError(f"LZO 解压失败：{exc}") from exc
    if kind == 0:
        return body
    raise MDXError(f"不认识的压缩类型：{kind}")


def _decompress_capped(data: bytes, limit: int = 64 * 1024 * 1024) -> bytes:
    """解压单个记录块，并限制输出大小，避免恶意 MDX 造成内存耗尽。"""
    obj = zlib.decompressobj()
    out = obj.decompress(data, limit + 1)
    if len(out) > limit or obj.unconsumed_tail:
        raise MDXError("词典记录解压后过大")
    out += obj.flush()
    if len(out) > limit:
        raise MDXError("词典记录解压后过大")
    return out


TAG_RE = re.compile(r"<[^>]+>")
BLOCK_TAGS = re.compile(r"</(p|div|tr|li|h\d)>|<br\s*/?>", re.I)
SPACE_RE = re.compile(r"[ \t\u00a0]+")


def html_to_text(html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    # 先把换行标签变成 \n，再剥其它标签；注意 \b，否则会把 <br> 当成 <b> 删掉
    text = BLOCK_TAGS.sub("\n", text)
    text = re.sub(r"(?i)</?(span|a|b|i|strong|em|font|sup|sub|u)\b[^>]*>", "", text)
    text = TAG_RE.sub(" ", text)
    text = html_lib.unescape(text)
    text = SPACE_RE.sub(" ", text)
    lines = [ln.strip() for ln in text.split("\n")]
    return "\n".join(ln for ln in lines if ln)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("用法: python -m rc.mdx <词典.mdx> <单词>")
        raise SystemExit(1)
    dictionary = MDX(sys.argv[1])
    print("条目数:", dictionary.entry_count, "| 编码:", dictionary.encoding)
    html = dictionary.lookup(sys.argv[2])
    if not html:
        print("没找到：", sys.argv[2])
        print("相近词：", dictionary.keys_matching(sys.argv[2][:3]))
    else:
        print(html_to_text(html)[:1500])
    dictionary.close()
