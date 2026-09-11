"""Document engine abstraction.

Every supported format is exposed through a DocumentEngine. The UI never
touches format libraries directly; it asks engines for pages, text, outline,
and capabilities. Engines are lazily loaded so a missing optional dependency
(e.g. Tesseract) degrades gracefully instead of crashing the app.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Iterator, Optional

logger = logging.getLogger("veyrion.documents")


class DocumentError(Exception):
    """User-presentable document error."""


class EncryptedDocumentError(DocumentError):
    """Document requires a password."""


class CorruptDocumentError(DocumentError):
    """Document structure is damaged beyond opening."""


@dataclass
class PageInfo:
    index: int = 0
    width: float = 0.0
    height: float = 0.0
    rotation: int = 0
    label: str = ""


@dataclass
class TocEntry:
    title: str = ""
    page: int = 0
    level: int = 0
    anchor: str = ""


@dataclass
class DocumentMetadata:
    title: str = ""
    author: str = ""
    subject: str = ""
    keywords: str = ""
    creator: str = ""
    producer: str = ""
    created: str = ""
    modified: str = ""
    page_count: int = 0
    word_count: int = 0
    char_count: int = 0
    language: str = ""
    encrypted: bool = False
    has_acroform: bool = False
    signed: bool = False
    scanned: bool = False
    extra: dict = field(default_factory=dict)


class Capability(str, Enum):
    RENDER = "render"
    TEXT = "text"
    SEARCH_IN_DOC = "search_in_doc"
    TOC = "toc"
    ANNOTATE_PDF = "annotate_pdf"
    EDIT_PAGES = "edit_pages"
    SAVE = "save"
    FORMS = "forms"
    IMAGES = "images"
    THUMBNAIL = "thumbnail"


class DocumentEngine:
    """Base class for all document engines."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.opened_at = time.time()
        self.modified = False

    # -- lifecycle ---------------------------------------------------------
    def close(self) -> None:
        pass

    def save(self, target: Optional[Path] = None) -> Path:
        """Save to ``target`` (or in place). Returns the saved path."""
        raise NotImplementedError(f"{type(self).__name__} cannot save")

    # -- info ---------------------------------------------------------------
    @property
    def capabilities(self) -> set[Capability]:
        return set()

    @property
    def page_count(self) -> int:
        return 0

    def page_info(self, index: int) -> PageInfo:
        return PageInfo(index=index)

    def metadata(self) -> DocumentMetadata:
        return DocumentMetadata(page_count=self.page_count)

    def toc(self) -> list[TocEntry]:
        return []

    # -- content ---------------------------------------------------------
    def page_text(self, index: int) -> str:
        return ""

    def iter_text(self) -> Iterator[tuple[int, str]]:
        for i in range(self.page_count):
            yield i, self.page_text(i)

    def search(self, query: str, *, case_sensitive: bool = False,
               whole_word: bool = False, regex: bool = False,
               max_results: int = 500) -> list[dict]:
        """Search inside the document; returns [{page, text, start, end}]."""
        import re as _re
        results: list[dict] = []
        flags = 0 if case_sensitive else _re.IGNORECASE
        try:
            if regex:
                pattern = _re.compile(query, flags)
            elif whole_word:
                pattern = _re.compile(_re.escape(query) + r"\b", flags)
            else:
                pattern = _re.compile(_re.escape(query), flags)
        except _re.error as e:
            raise DocumentError(f"Invalid search expression: {e}") from e

        for page_idx, text in self.iter_text():
            for m in pattern.finditer(text):
                start = max(0, m.start() - 60)
                end = min(len(text), m.end() + 60)
                results.append({
                    "page": page_idx,
                    "text": text,
                    "start": m.start(),
                    "end": m.end(),
                    "context": text[start:end].replace("\n", " "),
                    "match": m.group(0),
                })
                if len(results) >= max_results:
                    return results
        return results

    # -- rendering ------------------------------------------------------
    def render_page(self, index: int, zoom: float = 1.0, rotation: int = 0):
        """Render a page to a QImage-compatible object (QImage or PIL Image)."""
        raise NotImplementedError(f"{type(self).__name__} cannot render")

    def render_thumbnail(self, index: int, size: int = 128):
        pix = self.render_page(index, zoom=1.0)
        return _scale_image(pix, size)

    def extract_page_image(self, index: int):
        return None

    # -- editing ------------------------------------------------------
    def rotate_page(self, index: int, degrees: int = 90) -> None:
        raise DocumentError("Page rotation is not supported for this format")

    def delete_pages(self, indices: list[int]) -> None:
        raise DocumentError("Page deletion is not supported for this format")

    def add_annotation(self, **kwargs) -> str:
        raise DocumentError("Annotations are not supported for this format")

    def update_annotation(self, uuid: str, **kwargs) -> None:
        pass

    def remove_annotation(self, uuid: str) -> None:
        pass

    def annotations(self) -> list[dict]:
        return []

    def word_count(self) -> int:
        total = 0
        for _, text in self.iter_text():
            total += len(text.split())
        return total


def _scale_image(img, size: int):
    """Best-effort thumbnail scaling for QImage or PIL images."""
    if img is None:
        return None
    try:
        # PySide6 QImage
        return img.scaled(size, size, getattr(img, "KeepAspectRatio", None) or 1,
                          getattr(img, "SmoothTransformation", None) or 1)
    except AttributeError:
        pass
    try:
        from PIL import Image
        if isinstance(img, Image.Image):
            img.thumbnail((size, size), Image.LANCZOS)
            return img
    except ImportError:
        pass
    return img


def estimate_reading_minutes(word_count: int, wpm: int = 220) -> float:
    return word_count / max(1, wpm)


def human_page_label(index: int, info: Optional[PageInfo] = None) -> str:
    if info and info.label:
        return info.label
    return str(index + 1)
