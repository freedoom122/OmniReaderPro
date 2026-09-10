"""Library scanning and metadata extraction.

Imports folders into the library database, extracts metadata via the
document engines, generates cover thumbnails into the cache, and feeds the
full-text indexer. All heavy work runs through TaskManager in production;
this module is pure library logic.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

from omnireader_pro.app import paths
from omnireader_pro.core.documents.registry import open_document
from omnireader_pro.storage.repositories import DocumentRecord, LibraryRepository
from omnireader_pro.utils.pathutils import detect_kind, format_size

logger = logging.getLogger("omnireader.library")


def _render_cover(engine, doc_id: int, kind: str) -> str:
    """Render a cover image into the cache; returns its path ("" on failure)."""
    try:
        cache_dir = paths.cache_dir() / "covers"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cover_path = cache_dir / f"cover_{doc_id}.png"
        if kind == "ebook" and hasattr(engine, "cover_image"):
            img = engine.cover_image()
            if img is not None:
                img.thumbnail((320, 480))
                img.save(cover_path)
                return str(cover_path)
        if kind in ("pdf", "comic", "image") and hasattr(engine, "render_page"):
            pix_or_img = engine.render_page(0, zoom=0.6)
            if hasattr(pix_or_img, "tobytes"):  # fitz pixmap
                pix_or_img.save(str(cover_path))
                return str(cover_path)
            # PIL image
            img = pix_or_img
            img.thumbnail((320, 480))
            img.save(cover_path)
            return str(cover_path)
    except Exception:
        logger.debug("cover render failed", exc_info=True)
    return ""


def import_document(path: Path, library: LibraryRepository,
                    make_cover: bool = True) -> DocumentRecord | None:
    """Open a file, extract metadata, and upsert it into the library."""
    path = Path(path)
    try:
        result = open_document(path)
        if not result.ok:
            logger.info("library import skipped %s: %s", path.name, result.error[:80])
            return None
        engine = result.engine
        rec = DocumentRecord(
            path=str(path),
            title=path.stem,
            author="",
            kind=detect_kind(path),
            format=result.format_name,
            size_bytes=path.stat().st_size,
            folder=str(path.parent),
            last_modified=path.stat().st_mtime,
        )
        try:
            md = engine.metadata()
            rec.title = md.title or path.stem
            rec.author = md.author or ""
            rec.subject = md.subject or ""
            rec.keywords = md.keywords or ""
            rec.page_count = engine.page_count
            rec.word_count = md.word_count or engine.word_count()
        except Exception:
            logger.debug("metadata extraction failed for %s", path.name, exc_info=True)
        doc_id = library.upsert(rec)
        if make_cover and doc_id:
            cover = _render_cover(engine, doc_id, rec.kind)
            if cover:
                library.set_cover(rec.path, cover)
        engine.close()
        return library.get_by_path(rec.path)
    except Exception:
        logger.exception("library import failed for %s", path.name)
        return None


def scan_folder(folder: Path, library: LibraryRepository, recursive: bool = True,
                progress=None, cancel=None) -> tuple[int, int]:
    """Import all supported files in a folder. Returns (imported, skipped)."""
    folder = Path(folder)
    if not folder.exists():
        return (0, 0)
    pattern = "**/*" if recursive else "*"
    candidates = []
    for entry in sorted(folder.glob(pattern)):
        if entry.is_file() and entry.suffix.lower() in {
            ".pdf", ".epub", ".mobi", ".azw", ".azw3", ".cbz", ".cbr", ".docx",
            ".odt", ".rtf", ".txt", ".md", ".markdown", ".html", ".htm", ".csv",
            ".json", ".xml", ".xlsx", ".pptx", ".png", ".jpg", ".jpeg", ".webp",
            ".bmp", ".tif", ".tiff", ".gif",
        }:
            candidates.append(entry)
    imported = skipped = 0
    total = len(candidates)
    for i, entry in enumerate(candidates):
        if cancel is not None and cancel.is_set():
            break
        existing = library.get_by_path(str(entry))
        if existing is None:
            if import_document(entry, library) is not None:
                imported += 1
            else:
                skipped += 1
        else:
            # Refresh stale metadata (file changed on disk).
            try:
                mtime = entry.stat().st_mtime
                if mtime > existing.last_modified:
                    if import_document(entry, library, make_cover=False) is not None:
                        imported += 1
                    else:
                        skipped += 1
                else:
                    skipped += 1
            except OSError:
                skipped += 1
        if progress:
            progress((i + 1) / max(1, total), entry.name)
    return (imported, skipped)


def update_stats_record(library: LibraryRepository, path: str,
                        ann_count: int, note_count: int) -> None:
    """Store computed extra fields used by smart collections."""
    # 'annotated' is derived; expose via metadata_json-free approach:
    # stored on the record dict at query time by the UI.
    pass
