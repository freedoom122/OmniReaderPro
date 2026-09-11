"""EPUB / HTML reader view: reflowable paginated chapters with typography
controls, themes, TOC, and safe link handling.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QLabel, QSlider, QTextBrowser,
    QToolBar, QVBoxLayout, QWidget, QSpinBox,
)

from veyrion_workspace.core.documents.epub_engine import EpubEngine
from veyrion_workspace.ui.document_view import DocumentView
from veyrion_workspace.ui.views.text_view import markdown_to_html

THEME_CSS = {
    "light": ("#FAFAF7", "#26241F", "#8A5A2B"),
    "sepia": ("#F4ECD8", "#4A3F2E", "#7A4A20"),
    "dark": ("#1D1B17", "#E8E4DB", "#D8A05C"),
    "oled": ("#000000", "#E8E4DB", "#D8A05C"),
}


class EpubView(DocumentView):
    view_id = "epub"

    def __init__(self, engine: EpubEngine, settings=None, parent=None) -> None:
        super().__init__(engine, parent)
        self.epub: EpubEngine = engine
        s = settings or {}
        self._font_family = s.get("epub_font_family", "serif")
        self._font_size = int(s.get("epub_font_size", 17))
        self._line_height = float(s.get("epub_line_height", 1.6))
        self._width = int(s.get("epub_width", 720))
        self._theme = s.get("epub_theme", "light")

        self._browser = _EpubBrowser(self)
        self._build_toolbar()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._toolbar)
        lay.addWidget(self._browser)
        self.show_chapter(0)

    # ------------------------------------------------------------------ toolbar
    def _build_toolbar(self) -> None:
        self._toolbar = QToolBar()
        self._toolbar.setMovable(False)

        prev_btn_label = QLabel("  ")
        self._chapter_combo = QComboBox()
        self._chapter_combo.currentIndexChanged.connect(self._on_chapter_selected)

        fs_label = QLabel("Aa")
        self._font_spin = QSpinBox()
        self._font_spin.setRange(10, 34)
        self._font_spin.setValue(self._font_size)
        self._font_spin.valueChanged.connect(self._on_font_changed)

        lh_label = QLabel("Line")
        self._lh_slider = QSlider(Qt.Horizontal)
        self._lh_slider.setRange(12, 26)
        self._lh_slider.setValue(int(self._line_height * 10))
        self._lh_slider.setFixedWidth(90)
        self._lh_slider.valueChanged.connect(self._on_line_height_changed)

        self._theme_combo = QComboBox()
        self._theme_combo.addItems(list(THEME_CSS.keys()))
        self._theme_combo.setCurrentText(self._theme)
        self._theme_combo.currentTextChanged.connect(self._on_theme_changed)

        self._toolbar.addWidget(QLabel(" Chapter: "))
        self._toolbar.addWidget(self._chapter_combo)
        self._toolbar.addSeparator()
        self._toolbar.addWidget(fs_label)
        self._toolbar.addWidget(self._font_spin)
        self._toolbar.addWidget(lh_label)
        self._toolbar.addWidget(self._lh_slider)
        self._toolbar.addSeparator()
        self._toolbar.addWidget(self._theme_combo)

    def refresh_chapters(self) -> None:
        self._chapter_combo.blockSignals(True)
        self._chapter_combo.clear()
        for i in range(self.page_count):
            self._chapter_combo.addItem(f"{i + 1}. {self.epub.chapter_title(i)}")
        self._chapter_combo.blockSignals(False)

    # ------------------------------------------------------------------ content
    def show_chapter(self, index: int) -> None:
        self._current_page = max(0, min(index, self.page_count - 1))
        self.refresh_chapters()
        self._chapter_combo.blockSignals(True)
        self._chapter_combo.setCurrentIndex(self._current_page)
        self._chapter_combo.blockSignals(False)
        self._render_chapter()
        self.state_changed.emit()

    def _render_chapter(self) -> None:
        html = self.epub.chapter_html(self._current_page)
        bg, fg, link = THEME_CSS.get(self._theme, THEME_CSS["light"])
        serif = ("Georgia, 'Charter', serif" if self._font_family == "serif"
                 else "'Segoe UI', sans-serif")
        style = f"""
        <style>
          body {{ background:{bg}; color:{fg}; font-family:{serif};
                 font-size:{self._font_size}pt; line-height:{self._line_height};
                 max-width:{self._width}px; margin:2em auto; padding:0 1.5em; }}
          a {{ color:{link}; }}
          img {{ max-width:100%; height:auto; }}
          blockquote {{ border-left:3px solid rgba(128,128,128,0.4);
                        margin-left:0; padding-left:14px; color:{fg}; opacity:0.8; }}
          h1,h2,h3 {{ line-height:1.25; }}
          table {{ border-collapse:collapse; }} td,th {{ padding:4px 8px;
                  border:1px solid rgba(128,128,128,0.35); }}
        </style>"""
        # Load via the resource-aware browser (serves EPUB-internal images).
        self._browser.set_engine(self.epub)
        self._browser.set_base_url(QUrl(f"or-epub://{self._current_page}/"))
        self._browser.setHtml(f"<html><head>{style}</head><body>"
                              f"{html}</body></html>")

    def _on_chapter_selected(self, index: int) -> None:
        if index >= 0:
            self.show_chapter(index)

    def _on_font_changed(self, value: int) -> None:
        self._font_size = value
        self._render_chapter()
        self.state_changed.emit()

    def _on_line_height_changed(self, value: int) -> None:
        self._line_height = value / 10.0
        self._render_chapter()
        self.state_changed.emit()

    def _on_theme_changed(self, theme: str) -> None:
        self._theme = theme
        self._render_chapter()
        self.state_changed.emit()

    # ------------------------------------------------------------------ overrides
    def go_to_page(self, index: int) -> bool:
        if 0 <= index < self.page_count:
            self.show_chapter(index)
            return True
        return False

    def page_text(self, page: int = -1) -> str:
        idx = self._current_page if page < 0 else page
        return self.epub.page_text(idx)

    def selected_text(self) -> str:
        return self._browser.textCursor().selectedText()

    def find_in_view(self, query: str, case_sensitive: bool = False,
                     whole_word: bool = False, regex: bool = False,
                     backwards: bool = False) -> int:
        found = self._browser.find(query)
        if not found:
            # Try next chapters.
            for offset in range(1, self.page_count):
                nxt = (self._current_page + offset) % self.page_count
                text = self.epub.page_text(nxt).lower()
                if query.lower() in text:
                    self.show_chapter(nxt)
                    self._browser.find(query)
                    return 1
        return 1 if found else 0

    def save_state(self) -> dict:
        return {"page": self._current_page,
                "scroll": self._browser.verticalScrollBar().value(),
                "font_size": self._font_size, "theme": self._theme,
                "line_height": self._line_height}

    def restore_state(self, state: dict) -> None:
        self._font_size = int(state.get("font_size", self._font_size))
        self._theme = state.get("theme", self._theme)
        self._line_height = float(state.get("line_height", self._line_height))
        self._font_spin.setValue(self._font_size)
        self._theme_combo.setCurrentText(self._theme)
        self._lh_slider.setValue(int(self._line_height * 10))
        self.show_chapter(int(state.get("page", 0)))
        from PySide6.QtCore import QTimer
        QTimer.singleShot(120, lambda: self._browser.verticalScrollBar().setValue(
            int(state.get("scroll", 0))))

    def set_reader_defaults(self, **kw) -> None:
        if "font_size" in kw:
            self._font_spin.setValue(int(kw["font_size"]))
        if "line_height" in kw:
            self._lh_slider.setValue(int(float(kw["line_height"]) * 10))
        if "theme" in kw:
            self._theme_combo.setCurrentText(str(kw["theme"]))


class _EpubBrowser(QTextBrowser):
    """Serves EPUB-internal resources (images) without executing scripts."""

    def __init__(self, parent: EpubView) -> None:
        super().__init__(parent)
        self._epub_view = parent
        self._engine: EpubEngine | None = None
        self._base_url: QUrl | None = None
        self.setOpenLinks(False)
        self.anchorClicked.connect(self._on_anchor)

    def set_engine(self, engine: EpubEngine) -> None:
        self._engine = engine

    def set_base_url(self, url: QUrl) -> None:
        """Remember the chapter base for resolving relative resource names."""
        self._base_url = url

    def loadResource(self, rtype, url: QUrl):
        if self._engine is None:
            return b""
        name = url.toString()
        if name.startswith("or-epub:"):
            parts = name.replace("or-epub://", "").split("/", 1)
            name = parts[1] if len(parts) > 1 else name
        data = self._engine.resource(name)
        if data:
            from PySide6.QtGui import QImage, QPixmap
            if rtype == self.document().ResourceType.ImageResource:
                img = QImage.fromData(data)
                if not img.isNull():
                    return QPixmap.fromImage(img)
            return data
        return b""

    def _on_anchor(self, url: QUrl) -> None:
        target = url.toString()
        # Internal chapter links navigate; external links get the gate.
        if target.startswith("or-epub:"):
            return
        if target.startswith("#"):
            self.scrollToAnchor(target[1:])
            return
        from veyrion_workspace.ui.dialogs import confirm_external_link
        confirm_external_link(self, target)
