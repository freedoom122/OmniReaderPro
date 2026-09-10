"""View factory: map an opened engine to the right DocumentView widget."""
from __future__ import annotations

import logging

from omnireader_pro.core.documents.registry import OpenResult
from omnireader_pro.ui.document_view import DocumentView

logger = logging.getLogger("omnireader.viewfactory")


def create_view(result: OpenResult, settings=None) -> DocumentView | None:
    """Build the appropriate view for an opened document engine."""
    engine = result.engine
    fmt = result.format_name
    try:
        if fmt == "PDF":
            from omnireader_pro.ui.views.pdf_view import PdfView
            return PdfView(engine)
        if fmt == "EPUB":
            from omnireader_pro.ui.views.epub_view import EpubView
            s = settings.section("reading") if settings else {}
            return EpubView(engine, s)
        if fmt in ("MOBI/AZW",):
            from omnireader_pro.ui.views.text_view import TextDocView
            return TextDocView(engine, settings)
        if fmt == "CBZ" or fmt == "CBR":
            from omnireader_pro.ui.views.image_view import ComicView
            s = settings.section("reading") if settings else {}
            return ComicView(engine, s)
        if fmt == "Image":
            from omnireader_pro.ui.views.image_view import ImageView
            return ImageView(engine)
        if fmt == "DOCX":
            from omnireader_pro.ui.views.office_view import DocxView
            return DocxView(engine)
        if fmt in ("ODT", "RTF", "PPTX", "XLSX", "DOC (legacy)"):
            from omnireader_pro.ui.views.office_view import (
                OdtView, PptxView, RtfView, XlsxView,
            )
            return {
                "ODT": OdtView, "RTF": RtfView, "PPTX": PptxView,
                "XLSX": XlsxView,
            }.get(fmt, RtfView)(engine)
        if fmt == "HTML":
            from omnireader_pro.ui.views.text_view import TextDocView
            return TextDocView(engine, settings)
        # Default: text-family view
        from omnireader_pro.ui.views.text_view import TextDocView
        return TextDocView(engine, settings)
    except Exception:
        logger.exception("view creation failed for %s", fmt)
        return None
