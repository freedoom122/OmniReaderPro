"""Office document engines: DOCX (editable), ODT, RTF, PPTX, XLSX.

DOCX is loaded with python-docx into a lightweight paragraph/table model,
editable, and saved back preserving the original package so styles and
parts not exposed in the model survive the round-trip.
"""
from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Optional

from omnireader_pro.core.documents.base import (
    Capability, DocumentEngine, DocumentError, DocumentMetadata, PageInfo,
    TocEntry,
)
from omnireader_pro.utils.safeio import atomic_copy

logger = logging.getLogger("omnireader.office")


class DocxEngine(DocumentEngine):
    """DOCX via python-docx with heading outline and paragraph editing."""

    def __init__(self, path: Path) -> None:
        super().__init__(path)
        import docx
        self._docx = docx
        self._doc = docx.Document(str(path))
        self._load()

    def _load(self) -> None:
        self._blocks: list[dict] = []
        for para in self._doc.paragraphs:
            style = para.style.name if para.style else "Normal"
            level = 0
            if style.startswith("Heading"):
                try:
                    level = int(style.split()[-1])
                except ValueError:
                    level = 1
            elif style == "Title":
                level = 1
            runs_info = [
                {"text": r.text, "bold": bool(r.bold), "italic": bool(r.italic),
                 "underline": bool(r.underline)}
                for r in para.runs
            ]
            self._blocks.append({
                "kind": "paragraph", "style": style, "level": level,
                "text": para.text, "runs": runs_info,
            })
        for table in self._doc.tables:
            rows = []
            for row in table.rows:
                rows.append([cell.text for cell in row.cells])
            self._blocks.append({"kind": "table", "rows": rows})

    @property
    def capabilities(self) -> set:
        return {Capability.TEXT, Capability.SEARCH_IN_DOC, Capability.SAVE,
                Capability.TOC, Capability.THUMBNAIL}

    @property
    def page_count(self) -> int:
        # DOCX has no fixed pages; paginate for the viewer by ~350 words.
        words = sum(len(b.get("text", "").split()) for b in self._blocks
                    if b["kind"] == "paragraph")
        return max(1, -(-words // 350))

    def page_info(self, index: int) -> PageInfo:
        return PageInfo(index=index, width=612, height=792)

    def metadata(self) -> DocumentMetadata:
        cp = self._doc.core_properties
        words = sum(len(b.get("text", "").split()) for b in self._blocks
                    if b["kind"] == "paragraph")
        md = DocumentMetadata(page_count=max(1, -(-words // 350)))
        title = cp.title or ""
        if not title:
            # Fall back to the first heading so titles are useful even when
            # the DOCX core properties were never filled in.
            for b in self._blocks:
                if b["kind"] == "paragraph" and b.get("level"):
                    title = b.get("text", "")[:80]
                    break
        md.title = title
        md.author = cp.author or ""
        md.subject = cp.subject or ""
        md.keywords = cp.keywords or ""
        text = "\n".join(b.get("text", "") for b in self._blocks
                         if b["kind"] == "paragraph")
        md.word_count = len(text.split())
        md.char_count = len(text)
        md.extra = {"last_modified_by": cp.last_modified_by or "",
                    "revision": cp.revision or 0}
        return md

    def toc(self) -> list:
        entries = []
        page = 0
        words = 0
        for b in self._blocks:
            if b["kind"] == "paragraph":
                words += len(b.get("text", "").split())
                page = words // 350
                if b.get("level"):
                    entries.append(TocEntry(
                        title=b.get("text", "")[:80] or "(untitled)",
                        page=page, level=b["level"]))
        return entries

    def blocks(self) -> list:
        return self._blocks

    def set_block_text(self, index: int, text: str) -> None:
        b = self._blocks[index]
        if b["kind"] != "paragraph":
            raise DocumentError("Only paragraphs can be edited")
        b["text"] = text
        b["runs"] = [{"text": text, "bold": False, "italic": False,
                      "underline": False}]
        b["edited"] = True
        self.modified = True

    def page_text(self, index: int) -> str:
        # Approximate pagination: 350 words per page.
        words_per_page = 350
        text = "\n".join(b.get("text", "") for b in self._blocks
                         if b["kind"] == "paragraph")
        words = text.split()
        chunk = words[index * words_per_page:(index + 1) * words_per_page]
        return " ".join(chunk)

    def save(self, target: Optional[Path] = None) -> Path:
        target = Path(target) if target else self.path
        # Write edited paragraph text back into run structure.
        paras = [p for p in self._doc.paragraphs]
        for i, b in enumerate(self._blocks):
            if b["kind"] != "paragraph" or not b.get("edited"):
                continue
            if i >= len(paras):
                break
            para = paras[i]
            if para.runs:
                para.runs[0].text = b["text"]
                for r in para.runs[1:]:
                    r.text = ""
            else:
                para.add_run(b["text"])
        import io
        buf = io.BytesIO()
        self._doc.save(buf)
        atomic_copy_needed = target != self.path
        if atomic_copy_needed:
            target.write_bytes(buf.getvalue())
        else:
            from omnireader_pro.utils.safeio import atomic_write_bytes
            atomic_write_bytes(target, buf.getvalue())
        self.modified = False
        return target


class RtfEngine(DocumentEngine):
    """RTF: strip control words into plain text; save as RTF or TXT."""

    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self._raw = path.read_bytes()
        self._text = self._strip_rtf(self._raw.decode("latin-1", errors="replace"))

    @staticmethod
    def _strip_rtf(data: str) -> str:
        # Remove groups, control words, and escaped chars (best effort).
        data = re.sub(r"\{\\\*[^{}]*\}", "", data)          # {\*\...} destinations
        data = re.sub(r"\\'([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), data)
        data = re.sub(r"\\par[d]?\s?", "\n", data)
        data = re.sub(r"\\tab\s?", "\t", data)
        data = re.sub(r"\\[a-zA-Z]+-?\d*\s?", "", data)
        data = data.replace("{", "").replace("}", "")
        return data

    @property
    def capabilities(self) -> set:
        return {Capability.TEXT, Capability.SEARCH_IN_DOC, Capability.SAVE,
                Capability.THUMBNAIL}

    @property
    def page_count(self) -> int:
        return max(1, -(-len(self._text) // 4000))

    def page_info(self, index: int) -> PageInfo:
        return PageInfo(index=index, width=612, height=792)

    def metadata(self) -> DocumentMetadata:
        md = DocumentMetadata(page_count=self.page_count)
        md.title = self.path.stem
        md.word_count = len(self._text.split())
        return md

    def page_text(self, index: int) -> str:
        start = index * 4000
        return self._text[start:start + 4000]

    def full_text(self) -> str:
        return self._text

    def save(self, target: Optional[Path] = None) -> Path:
        target = Path(target) if target else self.path
        target.write_text(self._text, encoding="utf-8")
        self.modified = False
        return target


class OdtEngine(DocumentEngine):
    """ODT text extraction via odfpy."""

    def __init__(self, path: Path) -> None:
        super().__init__(path)
        from odf.opendocument import load
        from odf import text as odf_text, teletype
        self._doc = load(str(path))
        self._teletype = teletype
        self._odf_text = odf_text
        paras = self._doc.getElementsByType(odf_text.P) + \
            self._doc.getElementsByType(odf_text.H)
        self._paras = [teletype.extractText(p) for p in paras]

    @property
    def capabilities(self) -> set:
        return {Capability.TEXT, Capability.SEARCH_IN_DOC, Capability.THUMBNAIL}

    @property
    def page_count(self) -> int:
        return max(1, -(-len(self._paras) // 30))

    def page_info(self, index: int) -> PageInfo:
        return PageInfo(index=index, width=612, height=792)

    def metadata(self) -> DocumentMetadata:
        md = DocumentMetadata(page_count=self.page_count)
        try:
            meta = self._doc.meta
            from odf import dc
            titles = meta.getElementsByType(dc.Title)
            creators = meta.getElementsByType(dc.Creator)
            md.title = self._teletype.extractText(titles[0]) if titles else self.path.stem
            md.author = self._teletype.extractText(creators[0]) if creators else ""
        except Exception:
            md.title = self.path.stem
        md.word_count = len(" ".join(self._paras).split())
        return md

    def page_text(self, index: int) -> str:
        chunk = self._paras[index * 30:(index + 1) * 30]
        return "\n".join(chunk)


class PptxEngine(DocumentEngine):
    """PPTX slide extraction via python-pptx."""

    def __init__(self, path: Path) -> None:
        super().__init__(path)
        from pptx import Presentation
        self._prs = Presentation(str(path))
        self._slides: list[str] = []
        for slide in self._prs.slides:
            parts = []
            for shape in slide.shapes:
                if shape.has_text_frame:
                    for para in shape.text_frame.paragraphs:
                        t = "".join(r.text for r in para.runs)
                        if t.strip():
                            parts.append(t)
            self._slides.append("\n".join(parts))

    @property
    def capabilities(self) -> set:
        return {Capability.TEXT, Capability.SEARCH_IN_DOC, Capability.THUMBNAIL}

    @property
    def page_count(self) -> int:
        return len(self._slides)

    def page_info(self, index: int) -> PageInfo:
        return PageInfo(index=index, width=960, height=540)

    def metadata(self) -> DocumentMetadata:
        md = DocumentMetadata(page_count=self.page_count)
        md.title = self.path.stem
        try:
            cp = self._prs.core_properties
            md.title = cp.title or self.path.stem
            md.author = cp.author or ""
        except Exception:
            pass
        return md

    def page_text(self, index: int) -> str:
        return self._slides[index] if 0 <= index < len(self._slides) else ""


class XlsxEngine(DocumentEngine):
    """XLSX via openpyxl; each sheet becomes a 'page' of TSV text."""

    def __init__(self, path: Path) -> None:
        super().__init__(path)
        from openpyxl import load_workbook
        self._wb = load_workbook(str(path), data_only=True, read_only=True)
        self._sheets = list(self._wb.sheetnames)

    @property
    def capabilities(self) -> set:
        return {Capability.TEXT, Capability.SEARCH_IN_DOC, Capability.THUMBNAIL}

    @property
    def page_count(self) -> int:
        return len(self._sheets)

    def page_info(self, index: int) -> PageInfo:
        return PageInfo(index=index, width=792, height=612)

    def metadata(self) -> DocumentMetadata:
        md = DocumentMetadata(page_count=self.page_count)
        md.title = self.path.stem
        md.extra = {"sheets": self._sheets}
        return md

    def page_text(self, index: int) -> str:
        name = self._sheets[index]
        ws = self._wb[name]
        rows = []
        for row in ws.iter_rows(values_only=True):
            if any(v is not None for v in row):
                rows.append("\t".join("" if v is None else str(v) for v in row))
        return "\n".join(rows[:5000])

    def close(self) -> None:
        try:
            self._wb.close()
        except Exception:
            pass
