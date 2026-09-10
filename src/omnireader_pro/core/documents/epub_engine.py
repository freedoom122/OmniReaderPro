"""EPUB engine using ebooklib: spine order, per-chapter text, TOC, metadata.

Includes a defensive fallback OPF parser for real-world EPUBs that break
ebooklib's stricter reader (missing NCX, malformed spine, etc.).
"""
from __future__ import annotations

import html as html_mod
import logging
import re
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional

from omnireader_pro.core.documents.base import (
    Capability, CorruptDocumentError, DocumentEngine, DocumentError,
    DocumentMetadata, PageInfo, TocEntry,
)

logger = logging.getLogger("omnireader.epub")


class _TextExtractor(HTMLParser):
    """Extract readable text + paragraph/heading structure from XHTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0
        self._buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip_depth += 1
        elif tag in ("p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li",
                     "blockquote", "tr", "br"):
            self._flush()
            if tag.startswith("h"):
                try:
                    level = int(tag[1])
                except ValueError:
                    level = 3
                self.parts.append(f"{'#' * min(level, 6)} ")
        elif tag == "img":
            self._flush()

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip_depth:
            self._skip_depth -= 1
        elif tag in ("p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li",
                     "blockquote", "tr"):
            self._flush()

    def handle_data(self, data):
        if not self._skip_depth:
            self._buf.append(data)

    def _flush(self):
        text = "".join(self._buf).strip()
        self._buf = []
        if text:
            self.parts.append(text + "\n\n")

    def result(self) -> str:
        self._flush()
        return "".join(self.parts).strip()


def html_to_text(html: str) -> str:
    p = _TextExtractor()
    try:
        p.feed(html)
        p.close()
    except Exception:
        pass
    return p.result()


def sanitize_html_for_display(html: str) -> str:
    """Neutralize scripts, event handlers, and external resource loading."""
    html = re.sub(r"<script\b[^>]*>.*?</script>", "", html,
                  flags=re.IGNORECASE | re.DOTALL)
    html = re.sub(r"<script\b[^>]*/>", "", html, flags=re.IGNORECASE)
    html = re.sub(r"\son\w+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", "", html,
                  flags=re.IGNORECASE)
    html = re.sub(r"javascript\s*:", "blocked:", html, flags=re.IGNORECASE)
    return html


class EpubEngine(DocumentEngine):
    """EPUB 2/3 reader engine with fallback raw parsing."""

    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self._ebooklib = None
        self._epub = None
        self._book = None
        self._fallback_mode = False
        try:
            from ebooklib import epub as epub_mod
            self._epub = epub_mod
            self._ebooklib = epub_mod
            self._book = epub_mod.read_epub(str(path))
        except Exception:
            logger.info("ebooklib failed on %s; using fallback parser",
                        path.name, exc_info=True)
            self._parse_fallback()
            return
        self._spine_ids: list[str] = []
        self._items_by_id: dict = {}
        self._load_spine()
        if not self._spine_ids:
            logger.info("empty spine; using fallback parser for %s", path.name)
            self._parse_fallback()

    # ------------------------------------------------------------------ ebooklib path
    def _load_spine(self) -> None:
        ebooklib = self._ebooklib
        for item in self._book.get_items():
            self._items_by_id[item.get_id()] = item
        spine = self._book.spine if hasattr(self._book, "spine") else []
        for entry in spine:
            idref = entry[0] if isinstance(entry, (tuple, list)) else entry
            if idref in self._items_by_id:
                self._spine_ids.append(idref)
        if not self._spine_ids:
            for item in self._book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
                self._spine_ids.append(item.get_id())

    # ------------------------------------------------------------------ fallback path
    def _parse_fallback(self) -> None:
        """Minimal robust EPUB parse: manifest + spine straight from the OPF."""
        self._fallback_mode = True
        self._zip = zipfile.ZipFile(self.path)
        self._names = {n: self._zip.read(n) for n in self._zip.namelist()
                       if not n.endswith("/")}
        opf_path = self._find_opf()
        if not opf_path:
            raise CorruptDocumentError(
                "This EPUB is missing its package definition (OPF).")
        opf = self._names.get(opf_path, b"").decode("utf-8", errors="replace")
        opf_dir = "/".join(opf_path.split("/")[:-1])

        id_to_href: dict[str, str] = {}
        for m in re.finditer(
                r"<item\b[^>]*\bid=\"([^\"]+)\"[^>]*\bhref=\"([^\"]+)\"", opf):
            id_to_href[m.group(1)] = m.group(2)
        for m in re.finditer(
                r"<item\b[^>]*\bhref=\"([^\"]+)\"[^>]*\bid=\"([^\"]+)\"", opf):
            id_to_href[m.group(2)] = m.group(1)

        self._spine_hrefs: list[str] = []
        spine_m = re.search(r"<spine\b[^>]*>(.*?)</spine>", opf, re.DOTALL)
        if spine_m:
            for sm in re.finditer(r"<itemref\b[^>]*\bidref=\"([^\"]+)\"",
                                  spine_m.group(1)):
                href = id_to_href.get(sm.group(1))
                if href:
                    self._spine_hrefs.append(self._resolve(opf_dir, href))
        if not self._spine_hrefs:
            # Last resort: all XHTML files in reading-ish order.
            self._spine_hrefs = sorted(
                n for n in self._names
                if n.lower().endswith((".xhtml", ".html", ".htm")))
        self._meta_fallback = {}
        title_m = re.search(r"<dc:title[^>]*>(.*?)</dc:title>", opf, re.DOTALL)
        if title_m:
            self._meta_fallback["title"] = re.sub(r"<[^>]+>", "", title_m.group(1)).strip()
        author_m = re.search(r"<dc:creator[^>]*>(.*?)</dc:creator>", opf, re.DOTALL)
        if author_m:
            self._meta_fallback["author"] = re.sub(r"<[^>]+>", "", author_m.group(1)).strip()

    def _find_opf(self) -> str:
        container = self._names.get("META-INF/container.xml", b"").decode(
            "utf-8", errors="replace")
        m = re.search(r"full-path=\"([^\"]+)\"", container)
        if m:
            return m.group(1)
        for name in self._names:
            if name.lower().endswith(".opf"):
                return name
        return ""

    @staticmethod
    def _resolve(base_dir: str, href: str) -> str:
        if href.startswith("/"):
            return href.lstrip("/")
        if not base_dir:
            return href
        parts = (base_dir + "/" + href).split("/")
        out: list[str] = []
        for part in parts:
            if part == "..":
                if out:
                    out.pop()
            elif part not in (".", ""):
                out.append(part)
        return "/".join(out)

    # ------------------------------------------------------------------ common API
    @property
    def capabilities(self) -> set:
        return {Capability.TEXT, Capability.SEARCH_IN_DOC, Capability.TOC,
                Capability.SAVE, Capability.THUMBNAIL}

    @property
    def page_count(self) -> int:
        if self._fallback_mode:
            return len(self._spine_hrefs)
        return len(self._spine_ids)

    def page_info(self, index: int) -> PageInfo:
        return PageInfo(index=index, width=0, height=0,
                        label=self.chapter_title(index))

    def chapter_title(self, index: int) -> str:
        name = ""
        if self._fallback_mode:
            if 0 <= index < len(self._spine_hrefs):
                name = Path(self._spine_hrefs[index]).stem
        else:
            item = self._item(index)
            if item is not None:
                name = Path(item.get_name()).stem
        name = name.replace("-", " ").replace("_", " ")
        return name.title() if name else f"Section {index + 1}"

    def _item(self, index: int):
        if 0 <= index < len(self._spine_ids):
            return self._items_by_id.get(self._spine_ids[index])
        return None

    def chapter_html(self, index: int) -> str:
        raw = None
        if self._fallback_mode:
            if 0 <= index < len(self._spine_hrefs):
                raw = self._names.get(self._spine_hrefs[index])
                if raw is None:
                    # try with OEBPS prefix variants
                    for name in self._names:
                        if name.endswith(self._spine_hrefs[index]):
                            raw = self._names[name]
                            break
            if raw is None:
                return "<html><body></body></html>"
        else:
            item = self._item(index)
            if item is None:
                return "<html><body></body></html>"
            raw = item.get_content()
        content = raw.decode("utf-8", errors="replace")
        return sanitize_html_for_display(content)

    def page_text(self, index: int) -> str:
        return html_to_text(self.chapter_html(index))

    def iter_text(self):
        for i in range(self.page_count):
            yield i, self.page_text(i)

    def metadata(self) -> DocumentMetadata:
        md = DocumentMetadata(page_count=self.page_count)
        if self._fallback_mode:
            md.title = self._meta_fallback.get("title") or self.path.stem
            md.author = self._meta_fallback.get("author", "")
            words = 0
            for i in range(self.page_count):
                words += len(self.page_text(i).split())
            md.word_count = words
            return md

        def get_meta(name):
            try:
                values = self._book.get_metadata("DC", name)
                return str(values[0][0]) if values else ""
            except Exception:
                return ""

        md.title = get_meta("title") or self.path.stem
        md.author = get_meta("creator")
        md.subject = get_meta("subject")
        try:
            values = self._book.get_metadata("DC", "publisher")
            md.publisher = str(values[0][0]) if values else ""
        except Exception:
            pass
        md.language = get_meta("language")
        words = 0
        for i in range(self.page_count):
            words += len(self.page_text(i).split())
        md.word_count = words
        return md

    def toc(self) -> list:
        entries = []
        if self._fallback_mode:
            for i, href in enumerate(self._spine_hrefs):
                title_m = re.search(
                    r"<h1[^>]*>(.*?)</h1>",
                    self._names.get(href, b"").decode("utf-8", errors="replace"),
                    re.DOTALL)
                title = (re.sub(r"<[^>]+>", "", title_m.group(1)).strip()
                         if title_m else self.chapter_title(i))
                entries.append(TocEntry(title=title, page=i, level=1,
                                        anchor=href))
            return entries

        def walk(items, level=0):
            for item in items:
                if isinstance(item, (list, tuple)):
                    walk(item, level + 1)
                    continue
                try:
                    href = item.href if hasattr(item, "href") else ""
                    title = item.title if hasattr(item, "title") else str(item)
                except Exception:
                    continue
                page = self._page_for_href(href)
                entries.append(TocEntry(title=title, page=page, level=level,
                                        anchor=href))
                if hasattr(item, "children") and item.children:
                    walk(item.children, level + 1)

        try:
            walk(self._book.toc)
        except Exception:
            logger.debug("toc walk failed", exc_info=True)
        return entries

    def _page_for_href(self, href: str) -> int:
        if not href:
            return 0
        base = href.split("#")[0]
        if self._fallback_mode:
            for i, h in enumerate(self._spine_hrefs):
                if h.endswith(base):
                    return i
            return 0
        for i, sid in enumerate(self._spine_ids):
            item = self._items_by_id.get(sid)
            if item is not None and item.get_name().endswith(base):
                return i
        return 0

    def cover_image(self):
        from PIL import Image
        import io
        if self._fallback_mode:
            for name, data in self._names.items():
                if name.lower().endswith((".jpg", ".jpeg", ".png")) \
                        and "cover" in name.lower():
                    try:
                        return Image.open(io.BytesIO(data)).convert("RGB")
                    except Exception:
                        continue
            return None
        try:
            for item in self._book.get_items_of_type(self._ebooklib.ITEM_COVER):
                return Image.open(io.BytesIO(item.get_content())).convert("RGB")
        except Exception:
            pass
        try:
            for item in self._book.get_items_of_type(self._ebooklib.ITEM_IMAGE):
                return Image.open(io.BytesIO(item.get_content())).convert("RGB")
        except Exception:
            pass
        return None

    def resource(self, name: str) -> Optional[bytes]:
        if self._fallback_mode:
            if name in self._names:
                return self._names[name]
            for known in self._names:
                if known.endswith(name):
                    return self._names[known]
            return None
        for item in self._book.get_items():
            if item.get_name().endswith(name):
                return item.get_content()
        return None

    def resource_map(self) -> dict:
        if self._fallback_mode:
            return dict(self._names)
        out = {}
        for item in self._book.get_items():
            try:
                out[item.get_name()] = item.get_content()
            except Exception:
                continue
        return out

    def set_chapter_html(self, index: int, html: str) -> None:
        clean = sanitize_html_for_display(html)
        if self._fallback_mode:
            if not (0 <= index < len(self._spine_hrefs)):
                raise DocumentError("Invalid chapter index")
            self._names[self._spine_hrefs[index]] = clean.encode("utf-8")
            self.modified = True
            return
        item = self._item(index)
        if item is None:
            raise DocumentError("Invalid chapter index")
        item.set_content(clean.encode("utf-8"))
        self.modified = True

    def save(self, target: Optional[Path] = None) -> Path:
        target = Path(target) if target else self.path
        if self._fallback_mode:
            with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
                for name, data in self._names.items():
                    zf.writestr(name, data)
            self.modified = False
            return target
        self._epub.write_epub(str(target), self._book)
        self.modified = False
        return target
