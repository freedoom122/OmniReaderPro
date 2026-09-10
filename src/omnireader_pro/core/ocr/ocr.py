"""OCR subsystem: Tesseract-backed text recognition with caching.

Tesseract itself is an optional runtime dependency — availability is
detected at runtime and reported honestly in the UI.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from omnireader_pro.storage.database import Database

logger = logging.getLogger("omnireader.ocr")

try:
    import pytesseract
    HAS_PYTESS = True
except ImportError:  # pragma: no cover
    HAS_PYTESS = False

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:  # pragma: no cover
    HAS_PIL = False


def tesseract_available() -> bool:
    """True when both the wrapper and the engine binary are present."""
    if not HAS_PYTESS:
        return False
    exe = shutil.which("tesseract")
    if exe:
        pytesseract.pytesseract.tesseract_cmd = exe
        return True
    for candidate in (
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        str(Path.home() / "AppData" / "Local" / "Programs" / "Tesseract-OCR" / "tesseract.exe"),
        "/usr/bin/tesseract", "/usr/local/bin/tesseract",
        "/opt/homebrew/bin/tesseract",
    ):
        if Path(candidate).exists():
            pytesseract.pytesseract.tesseract_cmd = candidate
            return True
    return False


def tesseract_version() -> str:
    if not tesseract_available():
        return ""
    try:
        out = subprocess.run(
            [pytesseract.pytesseract.tesseract_cmd, "--version"],
            capture_output=True, text=True, timeout=10)
        line = (out.stdout or out.stderr).splitlines()
        return line[0] if line else "unknown"
    except Exception:
        return "unknown"


def available_languages() -> list[str]:
    if not tesseract_available():
        return []
    try:
        langs = pytesseract.get_languages(config="")
        return sorted(l for l in langs if l and l != "osd")
    except Exception:
        return ["eng"]


def image_to_text(image, lang: str = "eng") -> str:
    """Run OCR on a PIL image."""
    if not tesseract_available():
        raise RuntimeError(
            "Tesseract OCR is not installed. Install it from "
            "https://github.com/UB-Mannheim/tesseract/wiki and restart "
            "OmniReader to enable text recognition.")
    return pytesseract.image_to_string(image, lang=lang)


class OcrService:
    """Per-page OCR with database caching and searchable-PDF output."""

    def __init__(self, db: Database, engine_path: str = "") -> None:
        self._db = db
        if engine_path and Path(engine_path).exists():
            pytesseract.pytesseract.tesseract_cmd = engine_path

    def ocr_page(self, engine, page: int, lang: str = "eng",
                 dpi: int = 300, use_cache: bool = True) -> str:
        """OCR a single page of an open document engine (cached)."""
        doc_path = str(engine.path)
        if use_cache:
            row = self._db.query_one(
                "SELECT text FROM ocr_cache WHERE doc_path=? AND page=? AND lang=?",
                (doc_path, page, lang))
            if row is not None:
                return row["text"]
        if not tesseract_available():
            raise RuntimeError(
                "Tesseract OCR is not installed. Install it from "
                "https://github.com/UB-Mannheim/tesseract/wiki and restart "
                "OmniReader.")
        pix = engine.page_pixels(page, dpi=dpi)
        img = _pix_to_pil(pix)
        text = pytesseract.image_to_string(img, lang=lang)
        self._db.execute(
            "INSERT OR REPLACE INTO ocr_cache (doc_path, page, lang, text, created_at) "
            "VALUES (?,?,?,?,strftime('%s','now'))",
            (doc_path, page, lang, text))
        return text

    def ocr_document(self, engine, pages: list[int] | None = None,
                     lang: str = "eng", dpi: int = 300,
                     progress=None, cancel=None) -> dict[int, str]:
        """OCR many pages; returns {page: text}."""
        if pages is None:
            pages = list(range(engine.page_count))
        results: dict[int, str] = {}
        total = len(pages)
        for i, page in enumerate(pages):
            if cancel is not None and cancel.is_set():
                break
            results[page] = self.ocr_page(engine, page, lang=lang, dpi=dpi)
            if progress:
                progress((i + 1) / total, f"page {page + 1} of {total}")
        return results

    def make_searchable_pdf(self, engine, target: Path, pages=None,
                            lang: str = "eng", dpi: int = 200,
                            progress=None, cancel=None) -> Path:
        """OCR pages then write an invisible text layer into a new PDF."""
        ocr_results = self.ocr_document(engine, pages=pages, lang=lang,
                                        dpi=dpi, progress=progress,
                                        cancel=cancel)
        engine.to_searchable(ocr_results)
        return engine.save(Path(target))

    def clear_cache(self, doc_path: str | None = None) -> int:
        if doc_path:
            cur = self._db.execute("DELETE FROM ocr_cache WHERE doc_path=?", (doc_path,))
        else:
            cur = self._db.execute("DELETE FROM ocr_cache")
        return cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0


def _pix_to_pil(pix):
    """Convert a PyMuPDF pixmap to PIL without extra copies where possible."""
    if HAS_PIL and hasattr(pix, "width"):
        try:
            mode = "RGB" if pix.n < 4 else "RGBA"
            return Image.frombytes(mode, (pix.width, pix.height), pix.samples)
        except Exception:
            pass
    return pix
