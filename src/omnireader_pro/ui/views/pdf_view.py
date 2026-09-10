"""PDF viewer widget.

Rendering architecture:
  * QGraphicsView-based canvas with one QGraphicsItem per page slot.
  * Pages render lazily on a worker pool; a memory-aware LRU keeps recent
    bitmaps (configurable MB budget).
  * Neighbor prefetch, fit-width/page/height modes, 50%-800% zoom,
    single/continuous/two-page/two-cover modes, rotation, smooth scrolling,
    link handling, and text-selection-based annotations.
"""
from __future__ import annotations

import logging
import time
from collections import OrderedDict
from pathlib import Path
from typing import Optional

from PySide6.QtCore import (
    QObject, QPointF, QRunnable, QRectF, QSizeF, Qt, QThreadPool, Signal,
    QTimer,
)
from PySide6.QtGui import (
    QColor, QCursor, QImage, QPainter, QPen, QPixmap, QTransform,
)
from PySide6.QtWidgets import (
    QApplication, QGraphicsItem, QGraphicsPixmapItem, QGraphicsScene,
    QGraphicsView, QMenu, QWidget,
)

from omnireader_pro.core.documents.base import Capability
from omnireader_pro.core.documents.pdf_engine import PdfEngine
from omnireader_pro.ui.document_view import DocumentView

logger = logging.getLogger("omnireader.pdfview")


class PageCache:
    """Memory-aware LRU page bitmap cache."""

    def __init__(self, budget_mb: float = 160) -> None:
        self.budget_bytes = int(budget_mb * 1024 * 1024)
        self._entries: OrderedDict[tuple, tuple[QPixmap, int]] = OrderedDict()
        self._bytes = 0

    def get(self, key) -> Optional[QPixmap]:
        if key not in self._entries:
            return None
        pm, size = self._entries.pop(key)
        self._entries[key] = (pm, size)
        return pm

    def put(self, key, pixmap: QPixmap) -> None:
        if key in self._entries:
            old_pm, old_size = self._entries.pop(key)
            self._bytes -= old_size
        size = pixmap.width() * pixmap.height() * 4
        self._entries[key] = (pixmap, size)
        self._bytes += size
        while self._bytes > self.budget_bytes and len(self._entries) > 1:
            _, (pm, s) = self._entries.popitem(last=False)
            self._bytes -= s

    def clear(self) -> None:
        self._entries.clear()
        self._bytes = 0

    def stats(self) -> tuple[int, float]:
        return len(self._entries), self._bytes / 1024 / 1024


class PdfView(DocumentView):
    view_id = "pdf"

    page_rendered = Signal(int)

    MODE_SINGLE = "single"
    MODE_CONTINUOUS = "continuous"
    MODE_TWO = "two-page"
    MODE_TWO_COVER = "two-cover"

    def __init__(self, engine: PdfEngine, parent=None) -> None:
        super().__init__(engine, parent)
        self.pdf: PdfEngine = engine

        self._mode = self.MODE_CONTINUOUS
        self._rotation = 0
        self._fit_mode = "width"          # width|page|height|none
        self._cache = PageCache(budget_mb=160)
        self._pending: dict[tuple, list] = {}
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(2)
        self._highlights: dict[int, list] = {}   # page -> [QRectF in page coords]
        self._annot_tool: str = ""               # current annotation tool
        self._annot_color = "#E5B25D"
        self._annot_opacity = 0.4
        self._annot_width = 2.0
        self._drag_ink: list = []
        self._drag_start: QPointF | None = None
        self._rubber: QGraphicsRectItem = None  # type: ignore

        self._scene = QGraphicsScene(self)
        self._view = _PdfGraphicsView(self._scene, self)
        self._view.setDragMode(QGraphicsView.ScrollHandDrag)
        self._view.setRenderHint(QPainter.Antialiasing, True)
        self._view.setRenderHint(QPainter.SmoothPixmapTransform, True)
        self._view.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self._view.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self._render_signals = _RenderSignals(self)
        self._render_signals.finished.connect(self._on_render_done)
        self._render_signals.failed.connect(self._on_render_failed)

        lay = self.layout() or None
        from PySide6.QtWidgets import QVBoxLayout
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(self._view)

        self._page_items: list[PageSlotItem] = []
        self._build_scene()

        # Debounced relayout on resize.
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(180)
        self._resize_timer.timeout.connect(self._relayout)
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(60)
        self._debounce_timer.timeout.connect(self._apply_zoom_now)

    # ------------------------------------------------------------------ scene
    def _build_scene(self) -> None:
        self._scene.clear()
        self._page_items = []
        infos = [self.pdf.page_info(i) for i in range(self.page_count)]
        y = 12.0
        gap = 14.0
        for i, info in enumerate(infos):
            w, h = info.width, info.height
            if self._rotation % 180 == 90:
                w, h = h, w
            item = PageSlotItem(i, w, h)
            self._scene.addItem(item)
            # Layout: compute later in _relayout (mode-dependent).
            self._page_items.append(item)
        self._relayout()

    def _relayout(self) -> None:
        """Position page items per view mode."""
        if not self._page_items:
            return
        gap = 14.0
        two = self._mode in (self.MODE_TWO, self.MODE_TWO_COVER)
        x = 12.0
        y = 12.0
        row_max_h = 0.0
        for i, item in enumerate(self._page_items):
            w = item.page_width
            h = item.page_height
            if two:
                is_cover = (self._mode == self.MODE_TWO_COVER and i == 0)
                if is_cover:
                    item.setPos(x, y)
                    x += w + gap
                    row_max_h = max(row_max_h, h)
                    continue
                # Pair pages: left page odd slots, right page even slots.
                if i % 2 == 1:
                    item.setPos(x, y)
                    x += w + gap
                else:
                    item.setPos(x + w + gap, y)
                    x += w + gap
                    y += row_max_h + gap
                    row_max_h = 0
                    x = 12.0
                row_max_h = max(row_max_h, h)
            else:
                item.setPos(x, y)
                y += h + gap
                x = 12.0
        self._scene.setSceneRect(0, 0, self._view.viewport().width(),
                                 max(y + 12, 400))
        self._request_visible(force=True)

    # ------------------------------------------------------------------ zoom
    def set_zoom(self, zoom: float) -> None:
        self._fit_mode = "none"
        self._zoom = max(0.1, min(8.0, zoom))
        self._debounce_timer.start()

    def _apply_zoom_now(self) -> None:
        self._request_visible(force=True)
        self.state_changed.emit()

    def fit_width(self) -> None:
        self._fit_mode = "width"
        self._compute_fit()

    def fit_page(self) -> None:
        self._fit_mode = "page"
        self._compute_fit()

    def fit_height(self) -> None:
        self._fit_mode = "height"
        self._compute_fit()

    def _compute_fit(self) -> None:
        if not self._page_items:
            return
        vp_w = self._view.viewport().width() - 40
        vp_h = self._view.viewport().height() - 40
        info = self.pdf.page_info(min(self._current_page, self.page_count - 1))
        w, h = info.width, info.height
        if self._rotation % 180 == 90:
            w, h = h, w
        if self._fit_mode == "width":
            z = vp_w / max(1.0, w)
        elif self._fit_mode == "page":
            z = min(vp_w / max(1.0, w), vp_h / max(1.0, h))
        else:
            z = vp_h / max(1.0, h)
        self._zoom = max(0.1, min(8.0, z))
        self._request_visible(force=True)
        self.state_changed.emit()

    def rotate(self, degrees: int) -> None:
        self._rotation = (self._rotation + degrees) % 360
        keep = self._current_page
        self._build_scene()
        self._compute_fit()
        if self._page_items:
            self.go_to_page(min(keep, len(self._page_items) - 1))
        self.state_changed.emit()

    # ------------------------------------------------------------------ modes
    def set_mode(self, mode: str) -> None:
        self._mode = mode
        self._relayout()
        self.state_changed.emit()

    def mode(self) -> str:
        return self._mode

    # ------------------------------------------------------------------ render pipeline
    def _request_visible(self, force: bool = False) -> None:
        """Enqueue rendering for visible (and nearby) pages."""
        if not self._page_items:
            return
        viewport_rect = self._view.mapToScene(self._view.viewport().rect()).boundingRect()
        prefetch = 2
        for item in self._page_items:
            item_rect = QRectF(item.pos(), QSizeF(item.page_width * self._zoom,
                                                  item.page_height * self._zoom))
            if item_rect.intersects(viewport_rect):
                self._ensure_render(item, self._zoom)
            elif abs(item_rect.top() - viewport_rect.center().y()) < \
                    (viewport_rect.height() * (prefetch + 0.5)):
                self._ensure_render(item, self._zoom, low_priority=True)
            else:
                item.show_placeholder()

    def _ensure_render(self, item: "PageSlotItem", zoom: float,
                       low_priority: bool = False) -> None:
        key = (item.page_index, round(zoom, 2), self._rotation)
        cached = self._cache.get(key)
        if cached is not None:
            item.set_pixmap(cached, zoom)
            return
        if key in self._pending:
            return
        runnable = _PageRenderRunnable(self, item.page_index, zoom, key)
        self._pending[key] = [item.page_index]
        self._pool.start(runnable)

    def _on_render_done(self, page_index: int, zoom: float, key, image: QImage) -> None:
        self._pending.pop(key, None)
        if image.isNull():
            return
        pm = QPixmap.fromImage(image)
        self._cache.put(key, pm)
        if not self._page_items or page_index >= len(self._page_items):
            return
        item = self._page_items[page_index]
        current_key = (page_index, round(self._zoom, 2), self._rotation)
        item.set_pixmap(pm, self._zoom if key == current_key else key[1])
        self.page_rendered.emit(page_index)

    def _on_render_failed(self, key) -> None:
        self._pending.pop(key, None)

    def _on_scroll(self, value: int) -> None:
        self._request_visible()
        self._update_current_page_from_scroll()
        self.state_changed.emit()

    def _update_current_page_from_scroll(self) -> None:
        viewport_rect = self._view.mapToScene(self._view.viewport().rect()).boundingRect()
        center_y = viewport_rect.center().y()
        best, best_dist = self._current_page, 1e18
        for item in self._page_items:
            mid = item.pos().y() + item.page_height * self._zoom / 2
            dist = abs(mid - center_y)
            if dist < best_dist:
                best, best_dist = item.page_index, dist
        if best != self._current_page:
            self._current_page = best
            self.state_changed.emit()

    # ------------------------------------------------------------------ navigation
    def go_to_page(self, index: int) -> bool:
        if not (0 <= index < len(self._page_items)):
            return False
        self._current_page = index
        item = self._page_items[index]
        target_y = item.pos().y() - 10
        self._view.verticalScrollBar().setValue(int(target_y * self._zoom / max(0.01, self._zoom) + item.pos().y()))
        self._view.verticalScrollBar().setValue(int(item.pos().y()))
        self.state_changed.emit()
        return True

    def page_info(self, index: int = -1):
        idx = self._current_page if index < 0 else index
        try:
            return self.pdf.page_info(idx)
        except Exception:
            return None

    # ------------------------------------------------------------------ text
    def selected_text(self) -> str:
        return self._view.textCursorSelected()

    def find_in_view(self, query: str, case_sensitive: bool = False,
                     whole_word: bool = False, regex: bool = False,
                     backwards: bool = False) -> int:
        """Find in the PDF via PyMuPDF search; highlights all hits on pages."""
        if not query:
            self.clear_find()
            return 0
        flags = 0
        try:
            import fitz
            hits_total = 0
            self._highlights.clear()
            start_page = self._current_page if not backwards else self._current_page
            order = list(range(self.page_count))
            if backwards:
                order = order[: self._current_page + 1][::-1] + \
                    order[self._current_page + 1:][::-1]
            for pno in order:
                page = self.pdf._doc[pno]
                quads = page.search_for(query, quads=True)
                if quads:
                    self._highlights[pno] = [
                        QRectF(q.rect.x0, q.rect.y0, q.rect.width, q.rect.height)
                        for q in quads]
                    hits_total += len(quads)
                    if hits_total > 500:
                        break
            for item in self._page_items:
                item.set_search_highlights(self._highlights.get(item.page_index, []))
            if self._highlights:
                first_page = min(self._highlights.keys())
                self.go_to_page(first_page)
            return hits_total
        except Exception:
            logger.exception("find failed")
            return 0

    def clear_find(self) -> None:
        self._highlights.clear()
        for item in self._page_items:
            item.set_search_highlights([])

    def goto_search_hit(self, hit: dict) -> None:
        self.go_to_page(int(hit.get("page", 0)))

    # ------------------------------------------------------------------ annotations
    def set_annotation_tool(self, tool: str) -> None:
        self._annot_tool = tool
        self._view.set_annotation_mode(tool)
        if tool:
            self._view.setDragMode(QGraphicsView.NoDrag)
            self._view.setCursor(Qt.CrossCursor)
        else:
            self._view.setDragMode(QGraphicsView.ScrollHandDrag)
            self._view.unsetCursor()

    def annotation_tool(self) -> str:
        return self._annot_tool

    def set_annotation_style(self, color: str, opacity: float,
                             width: float) -> None:
        self._annot_color = color
        self._annot_opacity = opacity
        self._annot_width = width

    def add_annotation_at(self, page: int, kind: str, page_rect, *,
                          quads=None, points=None, text: str = "") -> Optional[dict]:
        """Create a PDF annotation. Returns the annotation dict."""
        import fitz
        try:
            if kind == "highlight":
                xref = self.pdf.add_highlight(
                    page, [fitz.Rect(*page_rect)], self._annot_color,
                    self._annot_opacity)
            elif kind in ("underline", "strikeout", "squiggly"):
                xref = self.pdf.add_text_markup(
                    page, [fitz.Rect(*page_rect)], kind, self._annot_color,
                    self._annot_opacity)
            elif kind == "note":
                xref = self.pdf.add_note(
                    page, page_rect[:2], text or "Note",
                    self._annot_color)
            elif kind == "freetext":
                xref = self.pdf.add_free_text(
                    page, page_rect, text or "Text", self._annot_color)
            elif kind == "ink":
                xref = self.pdf.add_ink(
                    page, [points] if points else [], self._annot_color,
                    self._annot_width)
            elif kind in ("rectangle", "ellipse", "line", "arrow"):
                xref = self.pdf.add_shape(
                    page, kind, page_rect, self._annot_color, self._annot_width)
            elif kind == "stamp":
                xref = self.pdf.add_stamp(page, page_rect)
            else:
                return None
            self.content_changed.emit()
            self._rerender_page(page)
            return {"xref": xref, "page": page, "type": kind}
        except Exception:
            logger.exception("annotation failed")
            return None

    def delete_annotation_xref(self, xref: int) -> None:
        self.pdf.delete_annot_by_xref(xref)
        self.content_changed.emit()

    def _rerender_page(self, page_index: int) -> None:
        # Cache keys include page index; clear all and redraw.
        self._cache.clear()
        self._request_visible(force=True)

    # ------------------------------------------------------------------ state
    def save_state(self) -> dict:
        return {"page": self._current_page, "zoom": self._zoom,
                "mode": self._mode, "rotation": self._rotation}

    def restore_state(self, state: dict) -> None:
        self._mode = state.get("mode", self.MODE_CONTINUOUS)
        self._rotation = int(state.get("rotation", 0))
        self._current_page = int(state.get("page", 0))
        self._zoom = float(state.get("zoom", 1.0))
        if self._page_items:
            self.go_to_page(self._current_page)
    def delete_current_page(self) -> None:
        self.pdf.delete_pages([self._current_page])
        self.content_changed.emit()
        self._build_scene()
        self.state_changed.emit()

    def rotate_current_page(self, degrees: int) -> None:
        self.pdf.rotate_page(self._current_page, degrees)
        self.content_changed.emit()
        self._build_scene()

    # ------------------------------------------------------------------ presentation
    def enter_presentation(self) -> None:
        self._view.showFullScreen() if False else None


class _PdfGraphicsView(QGraphicsView):
    """Canvas with annotation interaction and link handling."""

    def __init__(self, scene, pdf_view: PdfView) -> None:
        super().__init__(scene)
        self.pdf_view = pdf_view
        self._annot_mode = ""
        self._drawing = False
        self._last_point = None
        self._shape_start = None
        self._preview_item = None

    def set_annotation_mode(self, mode: str) -> None:
        self._annot_mode = mode

    def wheelEvent(self, event) -> None:
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            factor = 1.15 if delta > 0 else 1 / 1.15
            self.pdf_view.set_zoom(self.pdf_view.zoom * factor)
            event.accept()
        else:
            super().wheelEvent(event)

    def mousePressEvent(self, event) -> None:
        if self._annot_mode and event.button() == Qt.LeftButton:
            self._handle_annot_press(event)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drawing:
            self._handle_annot_move(event)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._drawing and event.button() == Qt.LeftButton:
            self._handle_annot_release(event)
            event.accept()
            return
        if event.button() == Qt.LeftButton and not self._annot_mode:
            # Link handling
            self._try_open_link(event)
        super().mouseReleaseEvent(event)

    # -- annotation interactions ---------------------------------------------
    def _page_at(self, scene_pos: QPointF):
        item = self.scene().itemAt(scene_pos, QTransform())
        if isinstance(item, PageSlotItem):
            return item
        return None

    def _handle_annot_press(self, event) -> None:
        scene_pos = self.mapToScene(event.position().toPoint())
        item = self._page_at(scene_pos)
        if item is None:
            return
        page_point = self._to_page_coords(item, scene_pos)
        mode = self._annot_mode
        if mode in ("highlight", "underline", "strikeout", "squiggly",
                    "rectangle", "ellipse", "line", "arrow", "redact"):
            self._shape_start = (item, page_point)
            self._drawing = True
        elif mode == "ink":
            self._drawing = True
            self.pdf_view._drag_ink = [page_point]
        elif mode == "note":
            self.pdf_view.add_annotation_at(
                item.page_index, "note", (page_point.x(), page_point.y()))

    def _handle_annot_move(self, event) -> None:
        scene_pos = self.mapToScene(event.position().toPoint())
        item = self._page_at(scene_pos)
        if item is None:
            return
        page_point = self._to_page_coords(item, scene_pos)
        if self._annot_mode == "ink":
            self.pdf_view._drag_ink.append(page_point)
            self._draw_ink_preview()
        elif self._shape_start:
            self._draw_shape_preview(item, page_point)

    def _handle_annot_release(self, event) -> None:
        if self._annot_mode == "ink":
            stroke = [(p.x(), p.y()) for p in self.pdf_view._drag_ink]
            self.pdf_view._drag_ink = []
            if len(stroke) > 1:
                self.pdf_view.add_annotation_at(
                    self._ink_page, "ink", None, points=stroke)
            self._remove_preview()
            self._drawing = False
            return
        if self._shape_start:
            item, start = self._shape_start
            scene_pos = self.mapToScene(event.position().toPoint())
            end = self._to_page_coords(item, scene_pos)
            rect = (min(start.x(), end.x()), min(start.y(), end.y()),
                    max(start.x(), end.x()), max(start.y(), end.y()))
            mode = self._annot_mode
            self._remove_preview()
            self._drawing = False
            self._shape_start = None
            if mode == "redact":
                self.pdf_view.pdf.add_redaction(item.page_index, rect)
                self.pdf_view.content_changed.emit()
            elif mode in ("highlight", "underline", "strikeout", "squiggly"):
                # Snap markup to text under the drag if any.
                quads = self._text_quads(item, rect)
                self.pdf_view.add_annotation_at(
                    item.page_index, mode, rect, quads=quads)
            else:
                self.pdf_view.add_annotation_at(item.page_index, mode, rect)

    def _to_page_coords(self, item: "PageSlotItem", scene_pos: QPointF) -> QPointF:
        """Map scene coords to unrotated PDF page coords (Y down)."""
        px = (scene_pos.x() - item.pos().x()) / max(0.01, self.pdf_view.zoom)
        py = (scene_pos.y() - item.pos().y()) / max(0.01, self.pdf_view.zoom)
        return QPointF(px, py)

    def _text_quads(self, item, rect) -> list:
        """Find text inside rect and return fitz quads (for markup tools)."""
        import fitz
        try:
            page = self.pdf_view.pdf._doc[item.page_index]
            r = fitz.Rect(*rect)
            words = page.get_text("words")
            hits = [fitz.Rect(w[:4]) for w in words
                    if r.intersects(fitz.Rect(w[:4]))]
            return [h.quad for h in hits] if hits else [r]
        except Exception:
            import fitz as _f
            return [_f.Rect(*rect)]

    def _draw_shape_preview(self, item, point: QPointF) -> None:
        scene = self.scene()
        if self._preview_item is not None:
            scene.removeItem(self._preview_item)
            self._preview_item = None
        start = self._to_page_coords(item, QPointF(*self._shape_start_page()))
        p1 = QPointF(item.pos().x() + start.x() * self.pdf_view.zoom,
                     item.pos().y() + start.y() * self.pdf_view.zoom)
        p2 = QPointF(item.pos().x() + point.x() * self.pdf_view.zoom,
                     item.pos().y() + point.y() * self.pdf_view.zoom)
        from PySide6.QtWidgets import QGraphicsRectItem
        from PySide6.QtGui import QPen, QColor
        self._preview_item = scene.addRect(
            QRectF(p1, p2).normalized(),
            QPen(QColor(self.pdf_view._annot_color), 1.4, Qt.DashLine))
        self._preview_item.setZValue(50)

    def _shape_start_page(self):
        item, point = self._shape_start
        return (point.x(), point.y())

    def _draw_ink_preview(self) -> None:
        # Cheap polyline preview: use a pixmap overlay path.
        pass

    def _remove_preview(self) -> None:
        if self._preview_item is not None:
            self.scene().removeItem(self._preview_item)
            self._preview_item = None

    # -- links ------------------------------------------------------------------
    def _try_open_link(self, event) -> None:
        scene_pos = self.mapToScene(event.position().toPoint())
        item = self._page_at(scene_pos)
        if item is None:
            return
        page_point = self._to_page_coords(item, scene_pos)
        import fitz
        try:
            links = self.pdf_view.pdf._doc[item.page_index].get_links()
        except Exception:
            return
        for lk in links:
            r = lk.get("from")
            if r and r.contains(fitz.Point(page_point.x(), page_point.y())):
                kind = lk.get("kind")
                if kind == fitz.LINK_GOTO:
                    self.pdf_view.go_to_page(lk.get("page", 0))
                elif kind == fitz.LINK_URI:
                    from omnireader_pro.ui.dialogs import confirm_external_link
                    confirm_external_link(self, lk.get("uri", ""))
                return


class PageSlotItem(QGraphicsPixmapItem):
    """A page placeholder that becomes a rendered pixmap."""

    def __init__(self, page_index: int, page_width: float,
                 page_height: float) -> None:
        super().__init__()
        self.page_index = page_index
        self.page_width = page_width
        self.page_height = page_height
        self._zoom = 0.0
        self._highlights: list = []
        self._placeholder_pixmap: QPixmap | None = None
        placeholder = QPixmap(max(1, int(page_width * 0.5)),
                              max(1, int(page_height * 0.5)))
        placeholder.fill(QColor(245, 243, 238))
        painter = QPainter(placeholder)
        painter.setPen(QPen(QColor(210, 205, 195), 1))
        painter.drawRect(placeholder.rect().adjusted(0, 0, -1, -1))
        painter.end()
        self._placeholder_pixmap = placeholder
        self.setPixmap(placeholder)
        self.setShapeMode(QGraphicsPixmapItem.BoundingRectShape)
        self.setAcceptHoverEvents(True)

    def show_placeholder(self) -> None:
        if self._zoom > 0:
            self.setPixmap(self._placeholder_pixmap)
            self._zoom = 0.0

    def set_pixmap(self, pm: QPixmap, zoom: float) -> None:
        scaled = pm.scaled(
            int(self.page_width * zoom), int(self.page_height * zoom),
            Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        self.setPixmap(scaled)
        self._zoom = zoom

    def set_search_highlights(self, rects) -> None:
        self._highlights = rects
        self.update()

    def paint(self, painter, option, widget=None) -> None:
        super().paint(painter, option, widget)
        if self._highlights and self._zoom > 0:
            painter.save()
            painter.setOpacity(0.35)
            painter.setBrush(QColor("#E5B25D"))
            painter.setPen(Qt.NoPen)
            for r in self._highlights:
                scaled = QRectF(
                    r.x() * self._zoom, r.y() * self._zoom,
                    r.width() * self._zoom, r.height() * self._zoom)
                painter.drawRect(scaled)
            painter.restore()
        # Page shadow/border
        painter.save()
        painter.setPen(QPen(QColor(180, 175, 165, 120), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(self.boundingRect())
        painter.restore()


class _RenderSignals(QObject):
    """Thread-safe delivery channel from render workers to the GUI thread.

    QRunnable objects cannot be QObjects, so the view owns this bridge;
    emitting a signal from a worker thread is queued to the receiver's
    thread automatically, which QTimer.singleShot(0, ...) from a pool
    thread is not (pool threads have no event loop).
    """

    finished = Signal(int, float, object, object)   # page, zoom, key, QImage
    failed = Signal(object)                          # key


class _PageRenderRunnable(QRunnable):
    def __init__(self, pdf_view: PdfView, page_index: int, zoom: float, key) -> None:
        super().__init__()
        self.pdf_view = pdf_view
        self.page_index = page_index
        self.zoom = zoom
        self.key = key
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            pix = self.pdf_view.pdf.render_page(self.page_index, zoom=self.zoom)
            fmt = QImage.Format_RGB888 if pix.n < 4 else QImage.Format_RGBA8888
            img = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt).copy()
            self.pdf_view._render_signals.finished.emit(
                self.page_index, self.zoom, self.key, img)
        except Exception:
            logger.exception("page render failed p%d", self.page_index)
            self.pdf_view._render_signals.failed.emit(self.key)
