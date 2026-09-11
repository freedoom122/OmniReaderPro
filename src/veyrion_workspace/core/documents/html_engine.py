"""HTML file engine: sanitized local HTML viewing + text extraction."""
from __future__ import annotations

from pathlib import Path

from veyrion_workspace.core.documents.base import (
    Capability, DocumentEngine, DocumentMetadata, PageInfo, TocEntry,
)
from veyrion_workspace.core.documents.epub_engine import html_to_text, sanitize_html_for_display


class HtmlEngine(DocumentEngine):
    def __init__(self, path: Path) -> None:
        super().__init__(path)
        raw = path.read_bytes()
        try:
            self._html = raw.decode("utf-8")
        except UnicodeDecodeError:
            self._html = raw.decode("cp1252", errors="replace")
        self._text = html_to_text(self._html)

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
        import re
        m = re.search(r"<title[^>]*>(.*?)</title>", self._html,
                      re.IGNORECASE | re.DOTALL)
        if m:
            md.title = m.group(1).strip() or self.path.stem
        md.word_count = len(self._text.split())
        return md

    def page_text(self, index: int) -> str:
        start = index * 4000
        return self._text[start:start + 4000]

    def html(self) -> str:
        return sanitize_html_for_display(self._html)

    def save(self, target: Path | None = None) -> Path:
        target = Path(target) if target else self.path
        target.write_text(self._html, encoding="utf-8")
        self.modified = False
        return target
