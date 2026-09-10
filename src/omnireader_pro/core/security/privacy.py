"""Metadata privacy tools: inspect and strip EXIF / XMP / document metadata."""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("omnireader.privacy")


def inspect_metadata(path: Path) -> dict[str, str]:
    """Return all discoverable metadata as a flat name->value map."""
    path = Path(path)
    ext = path.suffix.lower()
    out: dict[str, str] = {}
    try:
        if ext == ".pdf":
            import fitz
            doc = fitz.open(str(path))
            for key, value in (doc.metadata or {}).items():
                if value:
                    out[key] = str(value)
            try:
                xml = doc.get_xml_metadata()
                if xml:
                    out["XMP metadata"] = f"{len(xml)} bytes present"
            except Exception:
                pass
            doc.close()
        elif ext in (".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"):
            from PIL import Image
            from PIL.ExifTags import TAGS
            with Image.open(path) as im:
                exif = im.getexif()
                for tag_id, value in exif.items():
                    out[TAGS.get(tag_id, f"Tag{tag_id}")] = str(value)[:200]
                info = im.info or {}
                for key in ("icc_profile", "exif", "xmp", "XML:com.adobe.xmp"):
                    if key in info:
                        out[f"embedded {key}"] = f"{len(info[key])} bytes present"
        elif ext == ".docx":
            import docx
            d = docx.Document(str(path))
            cp = d.core_properties
            for attr in ("author", "title", "subject", "keywords",
                         "last_modified_by", "comments", "category",
                         "created", "modified", "revision"):
                value = getattr(cp, attr, None)
                if value:
                    out[attr] = str(value)
        elif ext == ".epub":
            from omnireader_pro.core.documents.epub_engine import EpubEngine
            eng = EpubEngine(path)
            md = eng.metadata()
            for attr in ("title", "author", "subject", "publisher", "language"):
                value = getattr(md, attr, "")
                if value:
                    out[attr] = str(value)
            eng.close()
    except Exception as e:
        logger.debug("metadata inspect failed: %s", e)
    return out


def strip_metadata(path: Path, target: Path) -> Path:
    """Write a metadata-cleaned copy to ``target`` (original untouched)."""
    path, target = Path(path), Path(target)
    ext = path.suffix.lower()
    if ext == ".pdf":
        import fitz
        doc = fitz.open(str(path))
        doc.set_metadata({})
        try:
            doc.del_xml_metadata()
        except Exception:
            pass
        doc.save(str(target), garbage=4, deflate=True)
        doc.close()
        return target
    if ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"):
        from PIL import Image
        with Image.open(path) as im:
            clean = Image.new(im.mode, im.size)
            clean.putdata(list(im.getdata()))
            fmt = ext.lstrip(".").upper()
            if fmt == "JPG":
                fmt = "JPEG"
            if fmt == "JPEG" and clean.mode not in ("RGB", "L"):
                clean = clean.convert("RGB")
            clean.save(str(target), format=fmt)
        return target
    if ext == ".docx":
        import docx
        d = docx.Document(str(path))
        cp = d.core_properties
        cp.author = ""
        cp.last_modified_by = ""
        cp.comments = ""
        cp.keywords = ""
        cp.subject = ""
        import io
        buf = io.BytesIO()
        d.save(buf)
        target.write_bytes(buf.getvalue())
        return target
    raise ValueError(f"Metadata stripping is not available for {ext} files")
