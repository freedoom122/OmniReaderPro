"""MOBI/AZW/AZW3 engine.

Parses the PalmDOC/MOBI container, decompresses the text records, and
extracts readable HTML from the MOBI header. A pragmatic best-effort
implementation: supports uncompressed, PalmDOC (LZ77), and HUFF/CDIC is
detected and rejected with a clear message (AZW3/KF8 uses HUFF/CDIC).
"""
from __future__ import annotations

import html as html_mod
import logging
import struct
from pathlib import Path

from omnireader_pro.core.documents.base import (
    Capability, CorruptDocumentError, DocumentEngine, DocumentMetadata,
    PageInfo,
)

logger = logging.getLogger("omnireader.mobi")


def _palmdoc_decompress(data: bytes) -> bytes:
    """LZ77 decompression used by PalmDOC and MOBI text records."""
    out = bytearray()
    i = 0
    n = len(data)
    while i < n:
        c = data[i]
        i += 1
        if c == 0:
            out.append(c)
        elif c <= 8:
            out.extend(data[i:i + c])
            i += c
        elif c <= 0x7F:
            out.append(c)
        elif c <= 0xBF:
            c = (c << 8) | data[i]
            i += 1
            distance = (c >> 3) & 0x7FF
            length = (c & 7) + 3
            for _ in range(length):
                out.append(out[-distance])
        else:  # 0xC0-0xFF: space + ascii char
            out.append(0x20)
            out.append(c ^ 0x80)
    return bytes(out)


class MobiEngine(DocumentEngine):
    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self._raw = path.read_bytes()
        self._parse()

    def _parse(self) -> None:
        raw = self._raw
        if len(raw) < 132 or raw[60:68] != b"BOOKMOBI":
            raise CorruptDocumentError(
                "This file is not a valid MOBI/AZW e-book.")
        try:
            num_records = struct.unpack(">H", raw[76:78])[0]
        except struct.error:
            raise CorruptDocumentError("MOBI header is damaged.")
        if num_records < 1 or 78 + num_records * 8 > len(raw):
            raise CorruptDocumentError("MOBI record table is damaged.")
        offsets = []
        for i in range(num_records):
            off = struct.unpack(">I", raw[78 + i * 8:82 + i * 8])[0]
            offsets.append(off)
        self._record0 = raw[offsets[0]:offsets[1] if len(offsets) > 1 else len(raw)]
        # MOBI header lives at offset 16 in record 0.
        if len(self._record0) < 16 + 4:
            raise CorruptDocumentError("MOBI header too short.")
        mobi_header_len = struct.unpack(
            ">I", self._record0[20:24])[0] if len(self._record0) >= 24 else 0
        encryption = struct.unpack(
            ">H", self._record0[12:14])[0] if len(self._record0) >= 14 else 0
        if encryption != 0:
            raise CorruptDocumentError(
                "This MOBI is DRM-protected and cannot be opened.")
        # Compression type at offset 0 of record 0.
        compression = struct.unpack(">H", self._record0[0:2])[0]
        if compression == 2:
            self._compress = "palmdoc"
        elif compression == 1:
            self._compress = "none"
        elif compression == 17480:  # 'DH' -> HUFF/CDIC (AZW3/KF8)
            raise CorruptDocumentError(
                "HUFF/CDIC compressed MOBI (AZW3/KF8) text extraction is "
                "not supported; convert the book to EPUB first.")
        else:
            raise CorruptDocumentError(
                f"Unknown MOBI compression type {compression}.")
        # Text length: first 4096-ish records are text.
        self._text_record_count = struct.unpack(
            ">I", self._record0[8:12])[0] if len(self._record0) >= 12 else 0
        self._records = offsets
        self._extract_text()
        self._extract_metadata()

    def _extract_text(self) -> None:
        count = min(self._text_record_count,
                    len(self._records) - 1)
        chunks = []
        for i in range(1, count):
            start = self._records[i]
            end = self._records[i + 1] if i + 1 < len(self._records) else len(self._raw)
            rec = self._raw[start:end]
            if self._compress == "palmdoc":
                try:
                    rec = _palmdoc_decompress(rec)
                except Exception:
                    pass
            chunks.append(rec.decode("cp1252", errors="replace"))
        html = "".join(chunks)
        # Trim to <html> body content.
        lower = html.lower()
        if "<html" in lower:
            html = html[lower.index("<html"):]
        from omnireader_pro.core.documents.epub_engine import html_to_text
        self._text = html_to_text(html)

    def _extract_metadata(self) -> None:
        self._meta = {}
        try:
            # EXTH header may hold title/author (best effort).
            rec0 = self._record0
            mobi_len = struct.unpack(">I", rec0[20:24])[0]
            exth_off = 16 + mobi_len
            if rec0[exth_off:exth_off + 4] == b"EXTH":
                count = struct.unpack(">I", rec0[exth_off + 8:exth_off + 12])[0]
                p = exth_off + 12
                for _ in range(count):
                    rtype, rlen = struct.unpack(
                        ">II", rec0[p:p + 8])
                    value = rec0[p + 8:p + rlen].decode("cp1252", errors="replace")
                    if rtype == 100:
                        self._meta.setdefault("author", value)
                    elif rtype == 503:
                        self._meta.setdefault("title", value)
                    p += rlen
        except Exception:
            pass

    @property
    def capabilities(self) -> set:
        return {Capability.TEXT, Capability.SEARCH_IN_DOC, Capability.THUMBNAIL}

    @property
    def page_count(self) -> int:
        return max(1, -(-len(self._text) // 4000))

    def page_info(self, index: int) -> PageInfo:
        return PageInfo(index=index, width=612, height=792)

    def metadata(self) -> DocumentMetadata:
        md = DocumentMetadata(page_count=self.page_count)
        md.title = self._meta.get("title") or self.path.stem
        md.author = self._meta.get("author", "")
        md.word_count = len(self._text.split())
        return md

    def page_text(self, index: int) -> str:
        start = index * 4000
        return self._text[start:start + 4000]
