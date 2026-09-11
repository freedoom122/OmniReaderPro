"""Plain-text family engine: TXT, MD, CSV, JSON, XML, log files.

Uses chardet for encoding detection and normalizes line endings.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from veyrion_workspace.core.documents.base import (
    Capability, DocumentEngine, DocumentMetadata, PageInfo, TocEntry,
)

logger = logging.getLogger("veyrion.text")

try:
    import chardet
    HAS_CHARDET = True
except ImportError:  # pragma: no cover
    HAS_CHARDET = False


class TextEngine(DocumentEngine):
    """Whole-file text document (one 'page' per ~4000 lines for navigation)."""

    PAGE_LINES = 4000

    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self._text, self._encoding = self._read()
        self._pages: list[str] = self._paginate()
        self.modified = False

    def _read(self) -> tuple:
        data = self.path.read_bytes()
        encoding = "utf-8"
        if HAS_CHARDET:
            guess = chardet.detect(data[:65536])
            encoding = (guess.get("encoding") or "utf-8")
            if (guess.get("encoding") or "").lower() in ("ascii",):
                encoding = "utf-8"
        try:
            text = data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            text = data.decode("utf-8", errors="replace")
            encoding = "utf-8"
        return text.replace("\r\n", "\n").replace("\r", "\n"), encoding

    def _paginate(self) -> list:
        lines = self._text.split("\n")
        pages = []
        for i in range(0, len(lines), self.PAGE_LINES):
            pages.append("\n".join(lines[i:i + self.PAGE_LINES]))
        return pages or [""]

    @property
    def capabilities(self) -> set:
        return {Capability.TEXT, Capability.SEARCH_IN_DOC, Capability.SAVE,
                Capability.TOC, Capability.THUMBNAIL}

    @property
    def page_count(self) -> int:
        return len(self._pages)

    def page_info(self, index: int) -> PageInfo:
        return PageInfo(index=index, width=612, height=792, label="")

    def metadata(self) -> DocumentMetadata:
        md = DocumentMetadata(page_count=self.page_count)
        md.title = self.path.stem.replace("_", " ").replace("-", " ").title()
        words = self._text.split()
        md.word_count = len(words)
        md.char_count = len(self._text)
        md.extra = {"encoding": self._encoding}
        return md

    def toc(self) -> list:
        """Markdown heading outline."""
        ext = self.path.suffix.lower()
        if ext not in (".md", ".markdown"):
            return []
        entries = []
        in_code = False
        page = 0
        line_in_page = 0
        for line in self._text.split("\n"):
            if line.strip().startswith("```"):
                in_code = not in_code
            if not in_code and line.startswith("#"):
                level = len(line) - len(line.lstrip("#"))
                if 1 <= level <= 6:
                    entries.append(TocEntry(
                        title=line.lstrip("#").strip(), page=page, level=level))
        return entries

    def page_text(self, index: int) -> str:
        return self._pages[index] if 0 <= index < len(self._pages) else ""

    def full_text(self) -> str:
        return self._text

    def replace_full_text(self, text: str) -> None:
        self._text = text.replace("\r\n", "\n")
        self._pages = self._paginate()
        self.modified = True

    def save(self, target: Optional[Path] = None) -> Path:
        target = Path(target) if target else self.path
        target.write_text(self._text, encoding="utf-8")
        self.modified = False
        return target

    def search(self, query: str, *, case_sensitive: bool = False,
               whole_word: bool = False, regex: bool = False,
               max_results: int = 500) -> list:
        return super().search(query, case_sensitive=case_sensitive,
                              whole_word=whole_word, regex=regex,
                              max_results=max_results)
