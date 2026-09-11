"""Comic archive engine (CBZ) with page ordering and guarded extraction."""
from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

from veyrion_workspace.core.documents.base import (
    Capability, CorruptDocumentError, DocumentEngine, DocumentError,
    DocumentMetadata, PageInfo,
)
from veyrion_workspace.utils.pathutils import safe_filename
from veyrion_workspace.utils.safeio import make_temp_dir

logger = logging.getLogger("veyrion.comic")

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}

NATURAL_SORT_KEY = None


def natural_key(name: str):
    import re
    return [int(t) if t.isdigit() else t.lower()
            for t in re.split(r"(\d+)", name)]


class CbzEngine(DocumentEngine):
    """CBZ comic: validated extraction to app temp, lazy image loading."""

    def __init__(self, path: Path) -> None:
        super().__init__(path)
        import zipfile
        self._zip = zipfile.ZipFile(path)
        self._extract_dir: Path | None = None
        self._pages: list[Path] = []
        self._open_archive()

    def _open_archive(self) -> None:
        try:
            names = [i.filename for i in self._zip.infolist() if not i.is_dir()]
        except zipfile.BadZipFile:
            raise CorruptDocumentError("This comic archive is damaged.")
        image_names = [n for n in names
                       if Path(n).suffix.lower() in IMAGE_EXTS]
        if not image_names:
            raise DocumentError("No images found in the comic archive.")
        image_names.sort(key=natural_key)
        self._member_names = image_names

        self._extract_dir = make_temp_dir(prefix="comic_")
        for name in image_names:
            target = self._extract_dir
            for part in Path(name).parts:
                if part in ("", ".", ".."):
                    continue
                target = target / safe_filename(part)
            target.parent.mkdir(parents=True, exist_ok=True)
            with self._zip.open(name) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst, length=1 << 20)
            self._pages.append(target)

    @property
    def capabilities(self) -> set:
        return {Capability.RENDER, Capability.THUMBNAIL}

    @property
    def page_count(self) -> int:
        return len(self._pages)

    def page_info(self, index: int) -> PageInfo:
        from PIL import Image
        w, h = 800, 1200
        if 0 <= index < len(self._pages):
            try:
                with Image.open(self._pages[index]) as im:
                    w, h = im.size
            except Exception:
                pass
        return PageInfo(index=index, width=float(w), height=float(h))

    def metadata(self) -> DocumentMetadata:
        md = DocumentMetadata(page_count=self.page_count)
        md.title = self.path.stem
        md.extra = {"format": "CBZ"}
        return md

    def render_page(self, index: int, zoom: float = 1.0, rotation: int = 0):
        from PIL import Image
        img = Image.open(self._pages[index]).convert("RGB")
        if rotation:
            img = img.rotate(-rotation, expand=True)
        if zoom != 1.0:
            img = img.resize(
                (max(1, int(img.width * zoom)), max(1, int(img.height * zoom))),
                Image.LANCZOS)
        return img

    def close(self) -> None:
        try:
            self._zip.close()
        except Exception:
            pass
        if self._extract_dir and self._extract_dir.exists():
            shutil.rmtree(self._extract_dir, ignore_errors=True)
            self._extract_dir = None


class CbrEngine(CbzEngine):
    """CBR via rarfile when a RAR backend is available."""

    def __init__(self, path: Path) -> None:
        DocumentEngine.__init__(self, path)
        try:
            import rarfile
        except ImportError:
            raise DocumentError(
                "CBR support requires the 'rarfile' package and a RAR backend.")
        try:
            self._zip = rarfile.RarFile(str(path))
        except Exception as e:
            raise CorruptDocumentError(
                "This CBR archive could not be opened (is a RAR backend installed?)")
        self._extract_dir = None
        self._pages = []
        self._open_archive_cbr()

    def _open_archive_cbr(self) -> None:
        names = [i.filename for i in self._zip.infolist() if not i.is_dir()]
        image_names = [n for n in names if Path(n).suffix.lower() in IMAGE_EXTS]
        if not image_names:
            raise DocumentError("No images found in the comic archive.")
        image_names.sort(key=natural_key)
        self._extract_dir = make_temp_dir(prefix="comic_")
        for name in image_names:
            target = self._extract_dir
            for part in Path(name).parts:
                if part in ("", ".", ".."):
                    continue
                target = target / safe_filename(part)
            target.parent.mkdir(parents=True, exist_ok=True)
            with self._zip.open(name) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst, length=1 << 20)
            self._pages.append(target)
