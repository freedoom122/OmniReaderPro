"""Presentation mode: fullscreen page display with timer, laser pointer,
and subtle transitions."""
from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QImage, QKeyEvent, QPainter, QPixmap
from PySide6.QtWidgets import (
    QLabel, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
)

from omnireader_pro.ui.icons import pixmap


class PresentationWindow(QMainWindow):
    """Frameless fullscreen presentation surface."""

    def __init__(self, parent, view) -> None:
        super().__init__(parent)
        self.view_ref = view
        self._page = view.current_page
        self._laser = False
        self._laser_pos = None
        self._start_time = time.time()
        self._transition = "fade"

        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_DeleteOnClose)

        self._canvas = QLabel()
        self._canvas.setAlignment(Qt.AlignCenter)
        self._canvas.setStyleSheet("background: #101010;")
        self.setCentralWidget(self._canvas)

        self._hud = QLabel(self)
        self._hud.setStyleSheet(
            "color: #E8E4DB; background: rgba(20,18,15,0.82);"
            "border-radius: 6px; padding: 6px 12px; font-size: 11pt;")
        self._hud.hide()

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        self._render_page()

    # ------------------------------------------------------------------ pages
    def _render_page(self) -> None:
        engine = self.view_ref.engine
        try:
            pix = engine.render_page(self._page, zoom=1.0)
            if hasattr(pix, "tobytes"):
                img = QImage(pix.samples, pix.width, pix.height, pix.stride,
                             QImage.Format.Format_RGB888)
                pm = QPixmap.fromImage(img)
            else:
                import io
                buf = io.BytesIO()
                pix.save(buf, format="PNG")
                pm = QPixmap.fromImage(QImage.fromData(buf.getvalue(), "PNG"))
            scaled = pm.scaled(self.size(), Qt.KeepAspectRatio,
                               Qt.SmoothTransformation)
            self._canvas.setPixmap(scaled)
        except Exception:
            pass
        self._show_hud()

    def _tick(self) -> None:
        self._show_hud()

    def _show_hud(self) -> None:
        total = self.view_ref.page_count
        elapsed = int(time.time() - self._start_time)
        mm, ss = divmod(elapsed, 60)
        self._hud.setText(f"{self._page + 1} / {total}   ·   {mm:02d}:{ss:02d}")
        self._hud.adjustSize()
        self._hud.move(24, self.height() - self._hud.height() - 24)
        self._hud.show()
        QTimer.singleShot(2600, self._hud.hide)

    # ------------------------------------------------------------------ events
    def resizeEvent(self, event) -> None:
        self._render_page()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if key in (Qt.Key_Right, Qt.Key_Space, Qt.Key_PageDown):
            self._next()
        elif key in (Qt.Key_Left, Qt.Key_PageUp, Qt.Key_Backspace):
            self._prev()
        elif key in (Qt.Key_Escape, Qt.Key_F5):
            self.close()
        elif key == Qt.Key_L:
            self._laser = not self._laser
            if self._laser:
                self.setCursor(Qt.BlankCursor)
            else:
                self.unsetCursor()
        event.accept()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._next()

    def mouseMoveEvent(self, event) -> None:
        if self._laser:
            self._laser_pos = event.position().toPoint()
            self._canvas.update()

    def _next(self) -> None:
        if self._page < self.view_ref.page_count - 1:
            self._page += 1
            self._render_page()

    def _prev(self) -> None:
        if self._page > 0:
            self._page -= 1
            self._render_page()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self._laser and self._laser_pos is not None:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(Qt.NoPen)
            painter.setBrush(Qt.red)
            painter.setOpacity(0.85)
            painter.drawEllipse(self._laser_pos, 6, 6)
            painter.setOpacity(0.25)
            painter.drawEllipse(self._laser_pos, 12, 12)
            painter.end()

    def closeEvent(self, event) -> None:
        # Sync the main view to the last presented page.
        try:
            self.view_ref.go_to_page(self._page)
        except Exception:
            pass
        event.accept()
