"""Single-image engine (PNG/JPG/WEBP/BMP/TIFF/GIF/SVG first frame)."""
from __future__ import annotations

import logging
from pathlib import Path

from veyrion_workspace.core.documents.base import (
    Capability, CorruptDocumentError, DocumentEngine, DocumentMetadata,
    PageInfo,
)

logger = logging.getLogger("veyrion.image")


class ImageEngine(DocumentEngine):
    def __init__(self, path: Path) -> None:
        super().__init__(path)
        from PIL import Image
        try:
            self._img = Image.open(str(path))
            self._img.load()
        except Exception:
            raise CorruptDocumentError("This image could not be decoded.")
        self._rotation = 0
        self._flip_h = False
        self._flip_v = False

    @property
    def capabilities(self) -> set:
        return {Capability.RENDER, Capability.THUMBNAIL}

    @property
    def page_count(self) -> int:
        return 1

    def page_info(self, index: int) -> PageInfo:
        w, h = self._img.size
        if self._rotation % 180 == 90:
            w, h = h, w
        return PageInfo(index=0, width=float(w), height=float(h))

    def metadata(self) -> DocumentMetadata:
        md = DocumentMetadata(page_count=1)
        md.title = self.path.stem
        md.extra = {
            "format": self._img.format or "",
            "mode": self._img.mode,
            "size": f"{self._img.width} x {self._img.height}",
            "exif": self._exif_summary(),
        }
        return md

    def _exif_summary(self) -> dict:
        try:
            exif = self._img.getexif()
            out = {}
            for tag_id, value in list(exif.items())[:30]:
                name = self._exif_tag_name(tag_id)
                out[name] = str(value)[:120]
            return out
        except Exception:
            return {}

    @staticmethod
    def _exif_tag_name(tag_id: int) -> str:
        from PIL.ExifTags import TAGS
        return TAGS.get(tag_id, f"Tag{tag_id}")

    def rotate(self, degrees: int) -> None:
        self._rotation = (self._rotation + degrees) % 360
        self.modified = True

    def flip(self, horizontal: bool) -> None:
        if horizontal:
            self._flip_h = not self._flip_h
        else:
            self._flip_v = not self._flip_v
        self.modified = True

    def render_page(self, index: int, zoom: float = 1.0, rotation: int = 0):
        img = self._img
        total_rot = (self._rotation + rotation) % 360
        if total_rot:
            img = img.rotate(-total_rot, expand=True)
        if self._flip_h:
            img = img.transpose(getattr(img, "FLIP_LEFT_RIGHT"))
        if self._flip_v:
            img = img.transpose(getattr(img, "FLIP_TOP_BOTTOM"))
        if zoom != 1.0:
            img = img.resize((max(1, int(img.width * zoom)),
                              max(1, int(img.height * zoom))))
        return img

    def save(self, target: Path | None = None) -> Path:
        target = Path(target) if target else self.path
        img = self.render_page(0, zoom=1.0)
        fmt = target.suffix.lstrip(".").upper()
        if fmt == "JPG":
            fmt = "JPEG"
        save_kw = {}
        if fmt == "JPEG" and img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        img.save(str(target), format=fmt or None, **save_kw)
        self.modified = False
        return target
