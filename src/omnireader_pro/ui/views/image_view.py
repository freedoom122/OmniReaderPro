"""Image and comic views.

ImageView: single image with zoom/pan/rotate/flip and EXIF panel data.
ComicView: CBZ/CBR with single/double page, RTL manga mode, fit modes,
page thumbnails via the shared thumbnail strip.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import QImage, QPainter, QPixmap, QTransform
from PySide6.QtWidgets import (
    QGraphicsPixmapItem, QGraphicsScene, QGraphicsView, QLabel, QVBoxLayout,
    QWidget,
)

from omnireader_pro.core.documents.comic_engine import CbzEngine
from omnireader_pro.core.documents.image_engine import ImageEngine
from omnireader_pro.ui.document_view import DocumentView


class _ZoomCanvas(QGraphicsView):
    """Pan/zoom canvas shared by image and comic views."""

    def __init__(self, parent_view: DocumentView) -> None:
        super().__init__()
        self._parent_view = parent_view
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setRenderHint(QPainter.SmoothPixmapTransform, True)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self._pixmap_item: QGraphicsPixmapItem | None = None

    def set_image(self, img) -> None:
        """Accepts PIL Image or QImage."""
        pixmap = self._to_pixmap(img)
        if self._pixmap_item is not None:
            self._scene.removeItem(self._pixmap_item)
        self._pixmap_item = self._scene.addPixmap(pixmap)
        self.setSceneRect(QRectF(pixmap.rect()))
        self.resetTransform()

    @staticmethod
    def _to_pixmap(img) -> QPixmap:
        if isinstance(img, QPixmap):
            return img
        if isinstance(img, QImage):
            return QPixmap.fromImage(img)
        # PIL Image -> PNG bytes -> QImage (safe, no external deps).
        import io
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        qimg = QImage.fromData(buf.getvalue(), "PNG")
        return QPixmap.fromImage(qimg)

    def wheelEvent(self, event) -> None:
        if event.modifiers() & Qt.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            self.scale(factor, factor)
            event.accept()
        else:
            super().wheelEvent(event)

    def fit_width(self) -> None:
        if self._pixmap_item is None:
            return
        self.resetTransform()
        vp_w = self.viewport().width() - 24
        scene_w = self.sceneRect().width()
        if scene_w > 1:
            factor = vp_w / scene_w
            self.scale(factor, factor)

    def fit_page(self) -> None:
        if self._pixmap_item is None:
            return
        self.resetTransform()
        vp = self.viewport().rect().adjusted(12, 12, -12, -12)
        scene = self.sceneRect()
        if scene.width() > 1 and scene.height() > 1:
            factor = min(vp.width() / scene.width(), vp.height() / scene.height())
            self.scale(factor, factor)


class ImageView(DocumentView):
    view_id = "image"

    def __init__(self, engine: ImageEngine, parent=None) -> None:
        super().__init__(engine, parent)
        self.image_engine: ImageEngine = engine
        self._canvas = _ZoomCanvas(self)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._canvas)
        self._refresh()

    def _refresh(self) -> None:
        img = self.image_engine.render_page(0, zoom=1.0)
        self._canvas.set_image(img)

    def rotate(self, degrees: int) -> None:
        self.image_engine.rotate(degrees)
        self._refresh()
        self.content_changed.emit()

    def flip(self, horizontal: bool = True) -> None:
        self.image_engine.flip(horizontal)
        self._refresh()
        self.content_changed.emit()

    def fit_width(self) -> None:
        self._canvas.fit_width()

    def fit_page(self) -> None:
        self._canvas.fit_page()

    def save(self) -> Path:
        return self.image_engine.save()

    def save_as(self, target: Path) -> Path:
        return self.image_engine.save(Path(target))


class ComicView(DocumentView):
    view_id = "comic"

    def __init__(self, engine: CbzEngine, settings=None, parent=None) -> None:
        super().__init__(engine, parent)
        self.comic: CbzEngine = engine
        s = settings or {}
        self._rtl = bool(s.get("comic_rtl", False))
        self._double = bool(s.get("comic_double", False))
        self._canvas = _ZoomCanvas(self)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._canvas)
        self.show_page(0)

    def show_page(self, index: int) -> None:
        index = max(0, min(index, self.page_count - 1))
        self._current_page = index
        if self._double:
            img_a = self.comic.render_page(index, zoom=1.0)
            self._canvas.set_image(img_a)
        else:
            img = self.comic.render_page(index, zoom=1.0)
            self._canvas.set_image(img)
        self.state_changed.emit()

    def next_page(self) -> bool:
        step = 2 if self._double else 1
        if self._rtl:
            return self.go_to_page(self._current_page - step)
        return self.go_to_page(self._current_page + step)

    def previous_page(self) -> bool:
        step = 2 if self._double else 1
        if self._rtl:
            return self.go_to_page(self._current_page + step)
        return self.go_to_page(self._current_page - step)

    def go_to_page(self, index: int) -> bool:
        if 0 <= index < self.page_count:
            self.show_page(index)
            return True
        return False

    def set_rtl(self, rtl: bool) -> None:
        self._rtl = rtl
        self.state_changed.emit()

    def set_double(self, double: bool) -> None:
        self._double = double
        self.show_page(self._current_page)

    def fit_width(self) -> None:
        self._canvas.fit_width()

    def fit_page(self) -> None:
        self._canvas.fit_page()

    def save_state(self) -> dict:
        return {"page": self._current_page, "rtl": self._rtl,
                "double": self._double}

    def restore_state(self, state: dict) -> None:
        self._rtl = bool(state.get("rtl", False))
        self._double = bool(state.get("double", False))
        self.show_page(int(state.get("page", 0)))
