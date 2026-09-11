"""Format detection and engine factory.

Opens any supported file by extension, returns a ready DocumentEngine, and
translates engine exceptions into user-presentable errors.
"""
from __future__ import annotations

import logging
from pathlib import Path

from veyrion_workspace.core.documents.base import (
    Capability, CorruptDocumentError, DocumentEngine, DocumentError,
    DocumentMetadata, EncryptedDocumentError, PageInfo,
)
from veyrion_workspace.utils.pathutils import SUPPORTED_EXTENSIONS

logger = logging.getLogger("veyrion.registry")

PDF_EXTS = {".pdf"}
EPUB_EXTS = {".epub"}
TEXT_EXTS = {".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".xml", ".log"}
HTML_EXTS = {".html", ".htm"}
OFFICE_EXTS = {".docx", ".odt", ".rtf", ".pptx", ".xlsx"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif"}
COMIC_EXTS = {".cbz", ".cbr"}
MOBI_EXTS = {".mobi", ".azw", ".azw3"}
LEGACY_EXTS = {".doc"}
DJVU_XPS_EXTS = {".djvu", ".xps", ".oxps", ".chm"}


class OpenResult:
    def __init__(self, engine=None, error: str = "", needs_password: bool = False,
                 format_name: str = "") -> None:
        self.engine = engine
        self.error = error
        self.needs_password = needs_password
        self.format_name = format_name

    @property
    def ok(self) -> bool:
        return self.engine is not None


def describe_format(path: Path) -> str:
    ext = path.suffix.lower()
    return SUPPORTED_EXTENSIONS.get(ext, ext.lstrip(".").upper() + " file")


def open_document(path: Path, password: str = "") -> OpenResult:
    """Factory: detect format and instantiate the right engine."""
    path = Path(path)
    ext = path.suffix.lower()

    if not path.exists():
        return OpenResult(error=f"The file does not exist: {path.name}")
    if path.stat().st_size == 0:
        return OpenResult(error=f"The file is empty: {path.name}")

    try:
        if ext in PDF_EXTS:
            from veyrion_workspace.core.documents.pdf_engine import PdfEngine
            try:
                return OpenResult(PdfEngine(path, password), format_name="PDF")
            except EncryptedDocumentError:
                return OpenResult(needs_password=True, format_name="PDF",
                                  error="Password required")
        if ext in EPUB_EXTS:
            from veyrion_workspace.core.documents.epub_engine import EpubEngine
            return OpenResult(EpubEngine(path), format_name="EPUB")
        if ext in MOBI_EXTS:
            from veyrion_workspace.core.documents.mobi_engine import MobiEngine
            return OpenResult(MobiEngine(path), format_name="MOBI/AZW")
        if ext in COMIC_EXTS:
            if ext == ".cbz":
                from veyrion_workspace.core.documents.comic_engine import CbzEngine
                return OpenResult(CbzEngine(path), format_name="CBZ")
            from veyrion_workspace.core.documents.comic_engine import CbrEngine
            return OpenResult(CbrEngine(path), format_name="CBR")
        if ext in IMAGE_EXTS:
            from veyrion_workspace.core.documents.image_engine import ImageEngine
            return OpenResult(ImageEngine(path), format_name="Image")
        if ext in OFFICE_EXTS:
            return _open_office(path, ext)
        if ext in TEXT_EXTS:
            from veyrion_workspace.core.documents.text_engine import TextEngine
            return OpenResult(TextEngine(path), format_name="Text")
        if ext in HTML_EXTS:
            from veyrion_workspace.core.documents.html_engine import HtmlEngine
            return OpenResult(HtmlEngine(path), format_name="HTML")
        if ext in LEGACY_EXTS:
            return _open_legacy_doc(path)
        if ext in DJVU_XPS_EXTS:
            return OpenResult(
                error=f"{describe_format(path)} requires an external converter "
                      f"(e.g. convert via the Tools > Convert menu with "
                      f"MuPDF/Calibre installed). The format is recognized "
                      f"but this build cannot render it natively.")

        # Unknown extension: try text sniffing as a last resort.
        try:
            head = path.read_bytes()[:512]
            if head and all(b in (9, 10, 13) or 32 <= b < 127 or b >= 0xC0
                            for b in head):
                from veyrion_workspace.core.documents.text_engine import TextEngine
                return OpenResult(TextEngine(path), format_name="Text")
        except OSError:
            pass
        return OpenResult(
            error=f"Veyrion cannot open {ext.upper() or 'this'} files. "
                  f"Supported formats: PDF, EPUB, MOBI, CBZ, images, "
                  f"DOCX, ODT, RTF, TXT, MD, HTML, CSV, JSON, XLSX, PPTX.")
    except EncryptedDocumentError:
        return OpenResult(needs_password=True, format_name=describe_format(path),
                          error="Password required")
    except DocumentError as e:
        return OpenResult(error=str(e), format_name=describe_format(path))
    except MemoryError:
        return OpenResult(error="The file is too large to open with available memory.",
                          format_name=describe_format(path))
    except Exception as e:
        logger.exception("open failed for %s", path.name)
        return OpenResult(
            error=f"The document could not be opened ({type(e).__name__}).",
            format_name=describe_format(path))


def _open_office(path: Path, ext: str) -> OpenResult:
    from veyrion_workspace.core.documents.office_engine import (
        DocxEngine, OdtEngine, PptxEngine, RtfEngine, XlsxEngine,
    )
    try:
        if ext == ".docx":
            return OpenResult(DocxEngine(path), format_name="DOCX")
        if ext == ".odt":
            return OpenResult(OdtEngine(path), format_name="ODT")
        if ext == ".rtf":
            return OpenResult(RtfEngine(path), format_name="RTF")
        if ext == ".pptx":
            return OpenResult(PptxEngine(path), format_name="PPTX")
        if ext == ".xlsx":
            return OpenResult(XlsxEngine(path), format_name="XLSX")
    except ImportError as e:
        return OpenResult(error=f"Office support module missing: {e}")
    except DocumentError:
        raise
    except Exception as e:
        logger.exception("office open failed")
        return OpenResult(error=f"The office document could not be parsed "
                                f"({type(e).__name__}).")
    return OpenResult(error="Unsupported office format")


def _open_legacy_doc(path: Path) -> OpenResult:
    """Legacy .doc: extract the readable text stream heuristically."""
    try:
        data = path.read_bytes()
        if not data.startswith(b"\xd0\xcf\x11\xe0"):
            raise CorruptDocumentError("This is not a valid legacy Word file.")
        text = _extract_doc_text(data)
        if not text.strip():
            return OpenResult(error="No readable text found in this .doc file.")
        from veyrion_workspace.core.documents.text_engine import TextEngine
        tmp = TextEngine.__new__(TextEngine)
        from veyrion_workspace.core.documents.base import DocumentEngine
        DocumentEngine.__init__(tmp, path)
        tmp._text = text
        tmp._encoding = "cp1252"
        tmp._pages = tmp._paginate()
        tmp.modified = False
        return OpenResult(tmp, format_name="DOC (legacy)")
    except DocumentError:
        raise
    except Exception:
        return OpenResult(
            error="Legacy .doc support is limited. Convert to DOCX for "
                  "full editing.")


def _extract_doc_text(data: bytes) -> str:
    """Best-effort text extraction from OLE2 .doc Word binary streams."""
    try:
        import olefile  # optional
    except ImportError:
        olefile = None

    if olefile:
        try:
            import io
            ole = olefile.OleFileIO(io.BytesIO(data))
            if ole.exists("WordDocument"):
                stream = ole.openstream("WordDocument").read()
                # crude: pull runs of printable cp1252
                import re
                chunks = re.findall(rb"[\x20-\x7e\r\n\t]{16,}", stream)
                text = b" ".join(chunks).decode("cp1252", errors="replace")
                return text
        except Exception:
            pass

    # Fallback: scan whole file for text runs.
    import re
    chunks = re.findall(rb"[\x20-\x7e\r\n\t]{24,}", data)
    return b" ".join(chunks).decode("cp1252", errors="replace")
