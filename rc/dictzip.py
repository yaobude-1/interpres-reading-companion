"""Random-access reader for dictzip (``.dict.dz``) files.

Dictzip is a gzip member with an ``RA`` extra field: the uncompressed data is
split into fixed-size chunks, each chunk is an independent raw-deflate stream,
and the extra field stores each compressed chunk size.  StarDict dictionaries
use this so one article can be read without inflating the whole dictionary.
"""

from __future__ import annotations

import gzip
import logging
import struct
import threading
import zlib
from pathlib import Path

log = logging.getLogger("rc")


class DictZipError(RuntimeError):
    pass


def _skip_cstring(fh) -> None:
    while True:
        byte = fh.read(1)
        if not byte:
            raise DictZipError("dictzip header 不完整")
        if byte == b"\x00":
            return


class DictZip:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._fh = self.path.open("rb")
        self._lock = threading.RLock()
        self._cache_index = -1
        self._cache = b""
        self.chunk_length = 0
        self.chunk_count = 0
        self._sizes: list[int] = []
        self._data_start = 0
        self.total_size = 0
        try:
            self._parse_header()
        except Exception:
            self._fh.close()
            raise

    def _parse_header(self) -> None:
        f = self._fh
        fixed = f.read(10)
        if len(fixed) != 10 or fixed[:2] != b"\x1f\x8b" or fixed[2] != 8:
            raise DictZipError("不是 gzip 文件")
        flags = fixed[3]
        if not flags & 0x04:
            raise DictZipError("缺少 FEXTRA，不是 dictzip")
        xlen_raw = f.read(2)
        if len(xlen_raw) != 2:
            raise DictZipError("dictzip 头不完整")
        xlen = struct.unpack("<H", xlen_raw)[0]
        extra = f.read(xlen)
        if len(extra) != xlen:
            raise DictZipError("dictzip extra 不完整")
        ra = self._find_ra(extra)
        if ra is None or len(ra) < 6:
            raise DictZipError("缺少 RA 随机访问字段")
        version, chunk_length, chunk_count = struct.unpack("<HHH", ra[:6])
        if version != 1 or chunk_length == 0 or chunk_count == 0:
            raise DictZipError("不支持的 dictzip 版本")
        if len(ra) < 6 + chunk_count * 2:
            raise DictZipError("dictzip chunk 表不完整")
        sizes = struct.unpack("<%dH" % chunk_count, ra[6 : 6 + chunk_count * 2])
        self.chunk_length = chunk_length
        self.chunk_count = chunk_count
        self._sizes = [int(value) for value in sizes]
        # Optional gzip fields after FEXTRA (FNAME/FCOMMENT/FHCRC).
        if flags & 0x08:
            _skip_cstring(f)
        if flags & 0x10:
            _skip_cstring(f)
        if flags & 0x02:
            f.read(2)
        self._data_start = f.tell()
        self.total_size = self.chunk_count * self.chunk_length
        if self._data_start + sum(self._sizes) > self.path.stat().st_size:
            raise DictZipError("dictzip chunk 超出文件范围")

    @staticmethod
    def _find_ra(extra: bytes) -> bytes | None:
        pos = 0
        while pos + 4 <= len(extra):
            sub_id = extra[pos : pos + 2]
            length = struct.unpack("<H", extra[pos + 2 : pos + 4])[0]
            pos += 4
            data = extra[pos : pos + length]
            if len(data) != length:
                return None
            if sub_id == b"RA":
                return data
            pos += length
        return None

    def _chunk(self, index: int) -> bytes:
        if index == self._cache_index:
            return self._cache
        if index < 0 or index >= self.chunk_count:
            return b""
        offset = self._data_start + sum(self._sizes[:index])
        size = self._sizes[index]
        with self._lock:
            self._fh.seek(offset)
            raw = self._fh.read(size)
        try:
            obj = zlib.decompressobj(-15)
            data = obj.decompress(raw) + obj.flush()
        except zlib.error as exc:
            raise DictZipError(f"dictzip chunk 解压失败: {exc}") from exc
        self._cache_index = index
        self._cache = data
        return data

    def read(self, offset: int, size: int) -> bytes:
        if size <= 0 or offset < 0:
            return b""
        end = min(offset + size, self.total_size)
        if offset >= end:
            return b""
        first = offset // self.chunk_length
        last = (end - 1) // self.chunk_length
        out = bytearray()
        for index in range(first, last + 1):
            chunk = self._chunk(index)
            base = index * self.chunk_length
            start = max(0, offset - base)
            stop = min(len(chunk), end - base)
            out += chunk[start:stop]
        return bytes(out)

    def close(self) -> None:
        try:
            self._fh.close()
        except OSError:
            pass
        self._cache = b""


def open_dictzip(path: str | Path) -> DictZip | None:
    try:
        return DictZip(path)
    except (OSError, DictZipError, struct.error) as exc:
        log.debug("dictzip 读取失败 %s: %s", path, exc)
        return None


def read_fallback(path: str | Path, offset: int, size: int) -> bytes:
    try:
        with gzip.open(path, "rb") as fh:
            data = fh.read()
        return data[offset : offset + size]
    except OSError:
        return b""
