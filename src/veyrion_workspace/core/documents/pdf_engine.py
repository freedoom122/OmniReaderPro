"""PDF engine built on PyMuPDF (fitz).

Implements rendering with rotation/crop, per-page text, outline, AcroForm
reading and filling, standard PDF annotations, page operations, redaction
with content removal, and digital signature inspection.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from veyrion_workspace.core.documents.base import (
    Capability,
    CorruptDocumentError,
    DocumentEngine,
    DocumentError,
    DocumentMetadata,
    EncryptedDocumentError,
    PageInfo,
    TocEntry,
)
from veyrion_workspace.utils.safeio import make_temp_file

logger = logging.getLogger("veyrion.pdf")

try:
    import fitz  # PyMuPDF
    HAS_FITZ = True
except ImportError:  # pragma: no cover
    fitz = None
    HAS_FITZ = False


class PdfEngine(DocumentEngine):
    def __init__(self, path: Path, password: str = "") -> None:
        if not HAS_FITZ:
            raise DocumentError("PyMuPDF is not installed; PDF support is unavailable")
        super().__init__(path)
        self._doc = None
        self._password = password
        self._open(password)

    def _open(self, password: str) -> None:
        try:
            self._doc = fitz.open(str(self.path))
        except Exception:
            raise CorruptDocumentError(
                "This PDF's internal structure appears damaged.")
        if self._doc.is_encrypted:
            if password:
                if not self._doc.authenticate(password):
                    self._doc.close()
                    raise EncryptedDocumentError("Incorrect password")
            else:
                self._doc.close()
                raise EncryptedDocumentError("Password required")

    # -- lifecycle ---------------------------------------------------------
    def close(self) -> None:
        if self._doc is not None:
            try:
                self._doc.close()
            finally:
                self._doc = None

    @property
    def page_count(self) -> int:
        return self._doc.page_count if self._doc is not None else 0

    @property
    def capabilities(self) -> set:
        caps = {Capability.RENDER, Capability.TEXT, Capability.SEARCH_IN_DOC,
                Capability.TOC, Capability.SAVE, Capability.THUMBNAIL,
                Capability.ANNOTATE_PDF, Capability.EDIT_PAGES, Capability.FORMS}
        return caps

    def needs_password(self) -> bool:
        return bool(self._doc and self._doc.needs_pass)

    # -- info ---------------------------------------------------------------
    def page_info(self, index: int) -> PageInfo:
        page = self._doc[index]
        return PageInfo(
            index=index,
            width=page.rect.width,
            height=page.rect.height,
            rotation=page.rotation,
            label=self._page_label(index),
        )

    def _page_label(self, index: int) -> str:
        try:
            labels = self._doc.get_page_labels()
            if not labels:
                return ""
            import fitz
            best = None
            for item in labels:
                if index >= item.get("startpage", 0):
                    if best is None or item["startpage"] >= best["startpage"]:
                        best = item
            if not best:
                return ""
            style = best.get("style", "D")
            prefix = best.get("prefix", "") or ""
            n = index - best.get("startpage", 0) + 1
            if style == "D":
                body = str(n)
            elif style == "r":
                body = _to_roman(n).lower()
            elif style == "R":
                body = _to_roman(n)
            elif style in ("a", "A"):
                body = _to_alpha(n, style)
            else:
                body = str(n)
            return f"{prefix}{body}"
        except Exception:
            return ""

    def metadata(self) -> DocumentMetadata:
        md = self._doc.metadata or {}
        meta = DocumentMetadata(page_count=self.page_count)
        meta.title = md.get("title", "")
        meta.author = md.get("author", "")
        meta.subject = md.get("subject", "")
        meta.keywords = md.get("keywords", "")
        meta.creator = md.get("creator", "")
        meta.producer = md.get("producer", "")
        meta.created = md.get("creationDate", "")
        meta.modified = md.get("modDate", "")
        meta.encrypted = bool(self._doc.is_encrypted)
        meta.has_acroform = bool(self._doc.is_form_pdf)
        meta.signed = self._has_signatures()
        word_total = 0
        scanned_pages = 0
        sample = min(self.page_count, 25)
        for i in range(sample):
            text = self._doc[i].get_text().strip()
            word_total += len(text.split())
            if len(text) < 10:
                scanned_pages += 1
        meta.scanned = sample > 0 and scanned_pages / sample > 0.8
        meta.word_count = word_total if sample >= self.page_count else int(
            word_total * self.page_count / sample)
        try:
            fonts = set()
            for i in range(sample):
                for f in self._doc[i].get_fonts():
                    fonts.add(f[3])
            meta.extra["fonts"] = sorted(fonts)[:40]
        except Exception:
            meta.extra["fonts"] = []
        meta.extra["images"] = self._count_images(sample)
        return meta

    def _count_images(self, sample: int) -> int:
        try:
            total = 0
            for i in range(sample):
                total += len(self._doc[i].get_images(full=True))
            if sample < self.page_count:
                total = int(total * self.page_count / sample)
            return total
        except Exception:
            return 0

    def toc(self) -> list[TocEntry]:
        entries = []
        try:
            for level, title, page in self._doc.get_toc():
                entries.append(TocEntry(
                    title=title, page=page - 1 if page > 0 else 0, level=level))
        except Exception:
            logger.debug("toc failed", exc_info=True)
        return entries

    # -- text ---------------------------------------------------------
    def page_text(self, index: int) -> str:
        if self._doc is None:
            return ""
        try:
            return self._doc[index].get_text()
        except Exception:
            return ""

    # -- rendering ------------------------------------------------------
    def render_page(self, index: int, zoom: float = 1.0, rotation: int = 0):
        page = self._doc[index]
        eff_rotation = (page.rotation + rotation) % 360
        mat = fitz.Matrix(zoom, zoom).prerotate(eff_rotation)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        return pix

    def extract_page_image(self, index: int) -> bytes:
        pix = self.render_page(index, zoom=2.0)
        return pix.tobytes("png")

    # -- annotations (standard PDF structures) ----------------------------
    def annotations(self) -> list[dict]:
        out = []
        for pno in range(self.page_count):
            for annot in self._doc[pno].annots() or []:
                out.append(self._annot_to_dict(annot, pno))
        return out

    def _annot_to_dict(self, annot, pno: int) -> dict:
        colors = annot.colors or {}
        col = colors.get("stroke") or colors.get("fill") or [0.9, 0.7, 0.35]
        return {
            "pdf_xref": annot.xref,
            "page": pno,
            "type": annot.type[1],
            "type_code": annot.type[0],
            "rect": list(annot.rect),
            "color": _rgb_to_hex(col),
            "opacity": float(getattr(annot, "opacity", 1.0) or 1.0),
            "text": (annot.info.get("content") or "").strip(),
            "author": annot.info.get("title") or "",
            "date": annot.info.get("modDate") or annot.info.get("date") or "",
        }

    def add_highlight(self, page: int, quads: list, color: str = "#E5B25D",
                      opacity: float = 0.4) -> int:
        page_obj = self._doc[page]
        annot = page_obj.add_highlight_annot(quads)
        _set_annot_color(annot, color)
        annot.set_opacity(opacity)
        annot.update()
        self.modified = True
        return annot.xref

    def add_text_markup(self, page: int, quads: list, kind: str = "underline",
                        color: str = "#C7522A", opacity: float = 1.0) -> int:
        page_obj = self._doc[page]
        if kind == "underline":
            a = page_obj.add_underline_annot(quads)
        elif kind == "strikeout":
            a = page_obj.add_strikeout_annot(quads)
        else:
            a = page_obj.add_squiggly_annot(quads)
        _set_annot_color(a, color)
        a.set_opacity(opacity)
        a.update()
        self.modified = True
        return a.xref

    def add_note(self, page: int, point, text: str, color: str = "#E5B25D",
                 author: str = "Me") -> int:
        page_obj = self._doc[page]
        annot = page_obj.add_text_annot(fitz.Point(*point), text, icon="Comment")
        _set_annot_color(annot, color)
        annot.info["title"] = author
        annot.update()
        self.modified = True
        return annot.xref

    def add_free_text(self, page: int, rect, text: str, color: str = "#C7522A",
                      font_size: float = 11) -> int:
        page_obj = self._doc[page]
        annot = page_obj.add_freetext_annot(
            fitz.Rect(*rect), text, fontsize=font_size,
            text_color=_hex_to_rgb(color), fill_color=(1, 1, 1))
        annot.set_border(width=0.5)
        annot.update()
        self.modified = True
        return annot.xref

    def add_ink(self, page: int, strokes: list, color: str = "#222222",
                width: float = 2.0) -> int:
        page_obj = self._doc[page]
        points = [[(float(x), float(y)) for (x, y) in stroke] for stroke in strokes]
        annot = page_obj.add_ink_annot(points)
        _set_annot_color(annot, color)
        annot.set_border(width=width)
        annot.update()
        self.modified = True
        return annot.xref

    def add_shape(self, page: int, kind: str, rect, color: str = "#C7522A",
                  width: float = 1.5, fill: str = "") -> int:
        page_obj = self._doc[page]
        r = fitz.Rect(*rect)
        if kind == "rectangle":
            annot = page_obj.add_rect_annot(r)
        elif kind == "ellipse":
            annot = page_obj.add_circle_annot(r)
        elif kind in ("line", "arrow"):
            p1 = fitz.Point(r.x0, r.y0)
            p2 = fitz.Point(r.x1, r.y1)
            annot = page_obj.add_line_annot(p1, p2)
            if kind == "arrow":
                annot.set_line_ends(fitz.PDF_ANNOT_LE_NONE, fitz.PDF_ANNOT_LE_CLOSED_ARROW)
            else:
                annot.set_line_ends(fitz.PDF_ANNOT_LE_NONE, fitz.PDF_ANNOT_LE_NONE)
        else:
            raise DocumentError(f"Unknown shape kind: {kind}")
        _set_annot_color(annot, color)
        annot.set_border(width=width)
        if fill and kind in ("rectangle", "ellipse"):
            annot.set_fill(_hex_to_rgb(fill))
        annot.update()
        self.modified = True
        return annot.xref

    def add_stamp(self, page: int, rect, text: str = "Reviewed") -> int:
        page_obj = self._doc[page]
        annot = page_obj.add_stamp_annot(fitz.Rect(*rect), stamp=0)
        annot.info["content"] = text
        annot.update()
        self.modified = True
        return annot.xref

    def add_link(self, page: int, rect, target_page: int) -> int:
        lk = {"kind": fitz.LINK_GOTO, "from": fitz.Rect(*rect), "page": target_page}
        page_obj = self._doc[page]
        page_obj.insert_link(lk)
        self.modified = True
        return 0

    def delete_annot_by_xref(self, xref: int) -> None:
        for pno in range(self.page_count):
            page_obj = self._doc[pno]
            for annot in page_obj.annots() or []:
                if annot.xref == xref:
                    page_obj.delete_annot(annot)
                    self.modified = True
                    return

    def update_annot_text(self, xref: int, text: str) -> None:
        for pno in range(self.page_count):
            page_obj = self._doc[pno]
            for annot in page_obj.annots() or []:
                if annot.xref == xref:
                    annot.info["content"] = text
                    annot.update()
                    self.modified = True
                    return

    # -- page operations --------------------------------------------------
    def rotate_page(self, index: int, degrees: int = 90) -> None:
        page = self._doc[index]
        page.set_rotation((page.rotation + degrees) % 360)
        self.modified = True

    def delete_pages(self, indices: list[int]) -> None:
        self._doc.delete_pages(indices)
        self.modified = True

    def duplicate_pages(self, indices: list[int]) -> None:
        for i in sorted(indices, reverse=True):
            self._doc.fullcopy_page(i, 1)
        self.modified = True

    def move_page(self, from_index: int, to_index: int) -> None:
        self._doc.move_page(from_index, to_index)
        self.modified = True

    def insert_blank_page(self, after: int, width: float = 595,
                          height: float = 842) -> None:
        self._doc.new_page(pno=after + 1, width=width, height=height)
        self.modified = True

    def insert_pages_from(self, after: int, other_pdf: Path,
                          other_range=None) -> None:
        src = fitz.open(str(other_pdf))
        if other_range:
            src.select(list(other_range))
        self._doc.insert_pdf(src, start_at=after + 1)
        src.close()
        self.modified = True

    def merge_from(self, other_pdf: Path) -> None:
        src = fitz.open(str(other_pdf))
        self._doc.insert_pdf(src)
        src.close()
        self.modified = True

    def extract_pages_to(self, indices: list[int], target: Path) -> None:
        new = fitz.open()
        for i in indices:
            new.insert_pdf(self._doc, from_page=i, to_page=i)
        new.save(str(target), garbage=4, deflate=True)
        new.close()

    def split_at(self, ranges: list, out_dir: Path,
                 base_name: str) -> list[Path]:
        out_dir.mkdir(parents=True, exist_ok=True)
        outputs = []
        for idx, (a, b) in enumerate(ranges, 1):
            part = fitz.open()
            part.insert_pdf(self._doc, from_page=a, to_page=b)
            out = out_dir / f"{base_name}_part{idx}.pdf"
            part.save(str(out), garbage=4, deflate=True)
            part.close()
            outputs.append(out)
        return outputs

    # -- metadata ------------------------------------------------------
    def set_metadata(self, title: Optional[str] = None,
                     author: Optional[str] = None, subject: Optional[str] = None,
                     keywords: Optional[str] = None) -> None:
        md = self._doc.metadata or {}
        if title is not None:
            md["title"] = title
        if author is not None:
            md["author"] = author
        if subject is not None:
            md["subject"] = subject
        if keywords is not None:
            md["keywords"] = keywords
        self._doc.set_metadata(md)
        self.modified = True

    def strip_metadata(self) -> None:
        self._doc.set_metadata({})
        try:
            self._doc.del_xml_metadata()
        except Exception:
            pass
        self.modified = True

    # -- forms ---------------------------------------------------------
    def form_fields(self) -> list[dict]:
        fields = []
        for pno in range(self.page_count):
            for w in self._doc[pno].widgets() or []:
                fields.append({
                    "page": pno, "name": w.field_name,
                    "type": w.field_type_string,
                    "value": w.field_value,
                    "choices": list(w.choice_values) if w.choice_values else [],
                    "rect": list(w.rect),
                })
        return fields

    def set_field_value(self, page: int, name: str, value) -> bool:
        for w in self._doc[page].widgets() or []:
            if w.field_name == name:
                w.field_value = value
                w.update()
                self.modified = True
                return True
        return False

    def clear_form(self) -> int:
        cleared = 0
        for pno in range(self.page_count):
            for w in self._doc[pno].widgets() or []:
                try:
                    w.field_value = False if w.field_type == fitz.PDF_WIDGET_TYPE_CHECKBOX else ""
                    w.update()
                    cleared += 1
                except Exception:
                    pass
        self.modified = True
        return cleared

    # -- redaction ------------------------------------------------------
    def add_redaction(self, page: int, rect, text: str = "") -> None:
        self._doc[page].add_redact_annot(fitz.Rect(*rect), text=(text or None))
        self.modified = True

    def apply_redactions(self) -> int:
        """Remove redacted content from all marked pages. Returns page count."""
        count = 0
        redact_type = getattr(fitz, "PDF_ANNOT_REDACT", None)
        for pno in range(self.page_count):
            page = self._doc[pno]
            try:
                redact_annots = list(page.annots(
                    types=[redact_type]) if redact_type else page.annots())
                if redact_annots:
                    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS)
                    count += 1
            except Exception:
                logger.exception("redaction failed on page %d", pno)
        self.modified = True
        return count

    def verify_redaction(self, phrases: list[str]) -> dict:
        """Reopen the saved file from disk and search for the removed phrases."""
        return verify_redaction_in_file(self.path, phrases)

    # -- signatures ------------------------------------------------------
    def _has_signatures(self) -> bool:
        try:
            return bool(self._doc.get_sig_flags())
        except Exception:
            return False

    def signature_info(self) -> list[dict]:
        """Best-effort signature listing via pypdf (no crypto verification)."""
        infos = []
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(self.path))
            fields = reader.get_fields() or {}
            for name, f in fields.items():
                if f.get("/FT") != "/Sig":
                    continue
                v = f.get("/V")
                entry = {"name": name, "signed": v is not None,
                         "signer": "", "issuer": "", "valid_from": "",
                         "valid_to": "", "intact": None}
                if v is not None:
                    try:
                        cert = v.get("/Cert")
                        if cert is not None:
                            from cryptography import x509
                            der = bytes(cert)
                            c = x509.load_der_x509_certificate(der)
                            entry["signer"] = c.subject.rfc4514_string()
                            entry["issuer"] = c.issuer.rfc4514_string()
                            entry["valid_from"] = c.not_valid_before_utc.isoformat()
                            entry["valid_to"] = c.not_valid_after_utc.isoformat()
                    except Exception:
                        logger.debug("cert parse failed", exc_info=True)
                infos.append(entry)
        except Exception:
            logger.debug("signature inspection failed", exc_info=True)
        return infos

    # -- saving ------------------------------------------------------
    def save(self, target: Optional[Path] = None) -> Path:
        target = Path(target) if target else self.path
        tmp = make_temp_file(suffix=".pdf")
        tmp.unlink()
        self._doc.save(str(tmp), garbage=3, deflate=True)
        if Path(target).resolve() == self.path.resolve():
            # Windows keeps the source open while fitz has it loaded; swap
            # the file out safely and reload the saved state.
            self._doc.close()
            try:
                os.replace(str(tmp), str(target))
            finally:
                self._open(self._password)
        else:
            os.replace(str(tmp), str(target))
        self.modified = False
        return target

    def save_incremental(self) -> Path:
        """Preserve signature validity: append-only save."""
        self._doc.save(str(self.path), incremental=True,
                       encryption=fitz.PDF_ENCRYPT_NONE)
        self.modified = False
        return self.path

    def optimize(self, out: Path, *, garbage: int = 4, linear: bool = False,
                 strip_metadata: bool = False) -> tuple:
        before = self.path.stat().st_size
        tmp = make_temp_file(suffix=".pdf")
        tmp.unlink()
        if strip_metadata:
            self.strip_metadata()
        self._doc.save(str(tmp), garbage=garbage, deflate=True,
                       clean=True, linear=linear)
        after = tmp.stat().st_size
        os.replace(str(tmp), str(out))
        return Path(out), before, after

    def to_searchable(self, ocr_result: dict) -> None:
        """Add an invisible text layer from OCR results (per page)."""
        for pno, text in ocr_result.items():
            page = self._doc[pno]
            lines = [l for l in text.splitlines() if l.strip()]
            if not lines:
                continue
            n = len(lines)
            rect = page.rect
            line_h = rect.height / n
            y = 6
            for line in lines:
                page.insert_text(
                    fitz.Point(2, y), line[:200],
                    fontsize=max(4, min(8, line_h * 0.7)),
                    fontname="helv", render_mode=3,  # invisible text
                )
                y += line_h
        self.modified = True

    def page_pixels(self, index: int, dpi: int = 300):
        """High-resolution pixmap for OCR."""
        return self.render_page(index, zoom=dpi / 72.0)


def verify_redaction_in_file(pdf_path: Path, phrases: list) -> dict:
    """Reopen a saved PDF and check whether ``phrases`` can still be found."""
    doc = fitz.open(str(pdf_path))
    report = {"pages": doc.page_count, "found": {}, "object_leaks": []}
    for phrase in phrases:
        hits = []
        for pno in range(doc.page_count):
            text = doc[pno].get_text()
            if phrase.lower() in text.lower():
                hits.append(pno)
        report["found"][phrase] = hits
    doc.close()
    raw = Path(pdf_path).read_bytes()
    for phrase in phrases:
        for encoding in (phrase.encode("utf-16-le"), phrase.encode("latin-1", "ignore")):
            if encoding and encoding in raw:
                report["object_leaks"].append(phrase)
                break
    return report


def _to_roman(num: int) -> str:
    vals = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"),
            (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX"),
            (5, "V"), (4, "IV"), (1, "I")]
    out = []
    for v, sym in vals:
        while num >= v:
            out.append(sym)
            num -= v
    return "".join(out)


def _to_alpha(num: int, style: str) -> str:
    letters = "abcdefghijklmnopqrstuvwxyz" if style == "a" else "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    out = []
    while num > 0:
        num, rem = divmod(num - 1, 26)
        out.append(letters[rem])
    return "".join(reversed(out)) or letters[0]


def _rgb_to_hex(rgb) -> str:
    if not rgb:
        return "#E5B25D"
    try:
        r, g, b = (int(round(c * 255)) for c in rgb[:3])
        return f"#{r:02x}{g:02x}{b:02x}"
    except Exception:
        return "#E5B25D"


def _hex_to_rgb(h: str):
    h = (h or "#888888").lstrip("#")
    try:
        return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    except ValueError:
        return (0.53, 0.32, 0.16)


def _set_annot_color(annot, color: str) -> None:
    try:
        annot.set_colors(stroke=_hex_to_rgb(color))
    except Exception:
        pass
