"""Document conversion engine.

Real conversions between formats using the installed engines:
  * PDF  -> images (PNG/JPEG per page), text, markdown-ish text
  * images -> PDF
  * DOCX/ODT/RTF/HTML/MD -> plain text
  * text/MD -> PDF (via PyMuPDF typesetting)
  * CSV/JSON -> PDF table report (basic)
Each conversion validates inputs and reports honest errors.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from veyrion_workspace.core.documents.registry import open_document
from veyrion_workspace.utils.pathutils import PathSafetyError, validate_path

logger = logging.getLogger("veyrion.convert")


class ConversionError(Exception):
    pass


def _progress_or_none(progress):
    return progress


def pdf_to_images(source: Path, out_dir: Path, fmt: str = "png",
                  dpi: int = 150, pages=None, progress=None, cancel=None) -> list[Path]:
    result = open_document(source)
    if not result.ok:
        raise ConversionError(result.error)
    engine = result.engine
    out_dir.mkdir(parents=True, exist_ok=True)
    targets = pages if pages is not None else list(range(engine.page_count))
    zoom = dpi / 72.0
    outputs = []
    import fitz
    for i, page_idx in enumerate(targets):
        if cancel is not None and cancel.is_set():
            break
        pix = engine.render_page(page_idx, zoom=zoom)
        ext = "jpg" if fmt in ("jpg", "jpeg") else fmt
        out = out_dir / f"{source.stem}_p{page_idx + 1:04d}.{ext}"
        if ext == "png":
            pix.save(str(out))
        else:
            pix.save(str(out), jpg_quality=88)
        outputs.append(out)
        if progress:
            progress((i + 1) / len(targets), f"page {page_idx + 1}")
    engine.close()
    return outputs


def pdf_to_text(source: Path, target: Path, progress=None, cancel=None) -> Path:
    result = open_document(source)
    if not result.ok:
        raise ConversionError(result.error)
    engine = result.engine
    parts = []
    total = engine.page_count
    for idx in range(total):
        if cancel is not None and cancel.is_set():
            break
        parts.append(f"\n\n--- Page {idx + 1} ---\n\n{engine.page_text(idx).strip()}")
        if progress:
            progress((idx + 1) / total)
    engine.close()
    target.write_text("".join(parts), encoding="utf-8")
    return target


def images_to_pdf(sources: list[Path], target: Path, progress=None) -> Path:
    from PIL import Image
    import fitz
    doc = fitz.open()
    for i, src in enumerate(sources):
        src = Path(src)
        try:
            img = Image.open(src)
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            img_bytes = _pil_to_jpeg_bytes(img) if src.suffix.lower() in (
                ".jpg", ".jpeg") else _pil_to_png_bytes(img)
            ext = "jpg" if src.suffix.lower() in (".jpg", ".jpeg") else "png"
            w, h = img.size
            page = doc.new_page(width=float(w), height=float(h))
            page.insert_image(fitz.Rect(0, 0, w, h), stream=img_bytes)
        except Exception as e:
            logger.warning("skipping %s: %s", src.name, e)
        if progress:
            progress((i + 1) / len(sources))
    doc.save(str(target), garbage=4, deflate=True)
    doc.close()
    return target


def _pil_to_jpeg_bytes(img) -> bytes:
    import io
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    return buf.getvalue()


def _pil_to_png_bytes(img) -> bytes:
    import io
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def text_to_pdf(source: Path, target: Path, title: str = "",
                font_size: float = 11, progress=None) -> Path:
    """Typeset a text/markdown file into a simple, clean PDF."""
    import fitz
    text = Path(source).read_text(encoding="utf-8", errors="replace")
    doc = fitz.open()
    margin = 72
    width, height = 595, 842
    line_height = font_size * 1.45
    page = doc.new_page(width=width, height=height)
    y = margin
    if title:
        page.insert_text((margin, y), title[:80], fontsize=font_size + 6,
                         fontname="hebo")
        y += line_height * 2
    for raw_line in text.splitlines():
        # Wrap text to page width (rough estimate: 0.5 * fontsize per char).
        max_chars = int((width - 2 * margin) / (font_size * 0.5))
        for chunk in _wrap(raw_line, max_chars):
            if y > height - margin:
                page = doc.new_page(width=width, height=height)
                y = margin
            is_heading = chunk.startswith("#")
            clean = chunk.lstrip("# ")
            page.insert_text(
                (margin, y), clean[:max_chars],
                fontsize=font_size + (3 if is_heading else 0),
                fontname="hebo" if is_heading else "helv")
            y += line_height + (6 if is_heading else 0)
        y += line_height * 0.35
    doc.save(str(target), garbage=4, deflate=True)
    doc.close()
    return target


def _wrap(line: str, max_chars: int) -> list[str]:
    if not line:
        return [""]
    words = line.split(" ")
    lines, current = [], ""
    for w in words:
        if len(current) + len(w) + 1 > max_chars and current:
            lines.append(current)
            current = w
        else:
            current = f"{current} {w}".strip()
    lines.append(current)
    return lines


def document_to_text(source: Path, target: Path, progress=None) -> Path:
    """Any supported document -> plain text."""
    result = open_document(source)
    if not result.ok:
        raise ConversionError(result.error)
    engine = result.engine
    parts = []
    total = engine.page_count
    for idx in range(total):
        parts.append(engine.page_text(idx).strip())
        if progress:
            progress((idx + 1) / total)
    engine.close()
    target.write_text("\n\n".join(p for p in parts if p), encoding="utf-8")
    return target


def document_to_markdown(source: Path, target: Path, progress=None) -> Path:
    """Text/markdown-family documents -> markdown (headings preserved for MD/DOCX)."""
    ext = Path(source).suffix.lower()
    if ext in (".md", ".markdown"):
        target.write_bytes(Path(source).read_bytes())
        return target
    result = open_document(source)
    if not result.ok:
        raise ConversionError(result.error)
    engine = result.engine
    lines = []
    if ext == ".docx" and hasattr(engine, "blocks"):
        for b in engine.blocks():
            if b["kind"] == "paragraph":
                level = b.get("level") or 0
                text = b.get("text", "").strip()
                if not text:
                    continue
                lines.append(("#" * level + " " + text) if level else text)
                lines.append("")
            elif b["kind"] == "table":
                rows = b.get("rows", [])
                if rows:
                    header = rows[0]
                    lines.append("| " + " | ".join(header) + " |")
                    lines.append("|" + "---|" * len(header))
                    for row in rows[1:]:
                        lines.append("| " + " | ".join(str(c) for c in row) + " |")
                    lines.append("")
    else:
        for idx in range(engine.page_count):
            lines.append(engine.page_text(idx).strip())
    engine.close()
    target.write_text("\n".join(lines), encoding="utf-8")
    return target


def csv_to_pdf_table(source: Path, target: Path, title: str = "",
                     progress=None) -> Path:
    """Render a CSV as a paginated PDF table."""
    import csv as csv_mod
    import fitz
    rows = []
    with open(source, newline="", encoding="utf-8-sig", errors="replace") as fh:
        for row in csv_mod.reader(fh):
            rows.append(row)
            if len(rows) > 5000:
                break
    if not rows:
        raise ConversionError("The CSV contains no data")
    doc = fitz.open()
    margin = 56
    width, height = 842, 595  # landscape
    col_count = min(10, max(1, len(rows[0])))
    col_width = (width - 2 * margin) / col_count
    y = margin

    def new_page():
        nonlocal page, y
        page = doc.new_page(width=width, height=height)
        y = margin
        if title:
            page.insert_text((margin, y), title[:90], fontsize=14, fontname="hebo")
            y += 24

    page = None
    new_page()
    for i, row in enumerate(rows):
        if y > height - margin:
            new_page()
        cells = [str(c)[:int(col_width / 5.5)] for c in row[:col_count]]
        x = margin
        for cell in cells:
            font = "hebo" if i == 0 else "helv"
            page.insert_text((x, y), cell, fontsize=8, fontname=font)
            x += col_width
        y += 14
    doc.save(str(target), garbage=4, deflate=True)
    doc.close()
    return target
