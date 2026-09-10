"""Settings application: categories, live persistence, reset per-section."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFormLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPlainTextEdit, QPushButton, QSpinBox, QStackedWidget, QVBoxLayout,
    QWidget, QLineEdit, QGroupBox,
)

from omnireader_pro.ui.theme import THEMES
from omnireader_pro.ui.widgets import HelpLabel

CATEGORIES = [
    "General", "Appearance", "Reading", "PDF", "EPUB", "Annotations",
    "OCR", "Speech", "Library", "Search", "Security", "Privacy",
    "Performance", "Keyboard", "Updates", "Data",
]


class SettingsDialog(QDialog):
    def __init__(self, parent, settings=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumSize(720, 560)
        from omnireader_pro.services.settings import Settings as _Settings
        self.settings = settings if settings is not None else (
            getattr(parent, "settings", None) or _Settings())

        lay = QVBoxLayout(self)
        body = QHBoxLayout()
        self._nav = QListWidget()
        self._nav.setFixedWidth(150)
        for cat in CATEGORIES:
            self._nav.addItem(QListWidgetItem(cat))
        body.addWidget(self._nav)
        self._stack = QStackedWidget()
        body.addWidget(self._stack, 1)
        lay.addLayout(body)

        self._pages: dict[str, QWidget] = {}
        self._builders = {
            "General": self._page_general, "Appearance": self._page_appearance,
            "Reading": self._page_reading, "PDF": self._page_pdf,
            "EPUB": self._page_epub, "Annotations": self._page_annotations,
            "OCR": self._page_ocr, "Speech": self._page_speech,
            "Library": self._page_library, "Search": self._page_search,
            "Security": self._page_security, "Privacy": self._page_privacy,
            "Performance": self._page_performance,
            "Keyboard": self._page_keyboard, "Updates": self._page_updates,
            "Data": self._page_data,
        }
        for cat in CATEGORIES:
            page = QWidget()
            v = QVBoxLayout(page)
            self._builders[cat](v)
            v.addStretch(1)
            scroll_page = page
            self._stack.addWidget(scroll_page)
            self._pages[cat] = page
        self._nav.currentRowChanged.connect(self._stack.setCurrentIndex)
        self._nav.setCurrentRow(0)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok |
                                   QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._apply)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    # -- helpers ------------------------------------------------------------
    def _add(self, layout, name, widget, section, key, tooltip=""):
        row = QHBoxLayout()
        label = QLabel(name)
        if tooltip:
            label.setToolTip(tooltip)
            widget.setToolTip(tooltip)
        row.addWidget(label)
        row.addStretch(1)
        row.addWidget(widget)
        layout.addLayout(row)
        getter = lambda: widget.isChecked() if isinstance(widget, QCheckBox) \
            else widget.currentText() if isinstance(widget, QComboBox) \
            else widget.value()
        setter = lambda v: widget.setChecked(bool(v)) if isinstance(widget, QCheckBox) \
            else widget.setCurrentText(str(v)) if isinstance(widget, QComboBox) \
            else widget.setValue(v)
        current = self.settings.get(section, key)
        if isinstance(widget, QComboBox) and current not in (None, ""):
            setter(current)
        elif current not in (None, ""):
            try:
                setter(current)
            except Exception:
                pass
        def save(*_):
            value = getter()
            if isinstance(widget, QSpinBox) or isinstance(widget, QDoubleSpinBox):
                value = float(value) if isinstance(widget, QDoubleSpinBox) else int(value)
            self.settings.set(section, key, value)
        widget.widget = widget  # self-ref safety
        if isinstance(widget, QCheckBox):
            widget.toggled.connect(save)
        elif isinstance(widget, QComboBox):
            widget.currentTextChanged.connect(save)
        elif isinstance(widget, QLineEdit):
            widget.textEdited.connect(save)
        else:
            widget.valueChanged.connect(save)
        return widget

    def _section_reset(self, layout, section: str) -> None:
        row = QHBoxLayout()
        reset = QPushButton(f"Reset {section} to defaults")
        reset.clicked.connect(lambda: (self.settings.reset_section(section),
                                       self.reject(), self.accept()))
        row.addWidget(reset)
        row.addStretch(1)
        layout.addLayout(row)

    # -- pages ---------------------------------------------------------------
    def _page_general(self, layout) -> None:
        layout.addWidget(QLabel("<b>General</b>"))
        self._add(layout, "Restore last session on startup", QCheckBox(),
                  "general", "restore_session")
        self._add(layout, "Autosave interval (seconds)",
                  self._spin(30, 3600, 10), "general", "autosave_interval_sec")
        self._add(layout, "Version history depth",
                  self._spin(1, 50, 1), "general", "version_history_depth")
        self._add(layout, "Confirm destructive actions", QCheckBox(),
                  "general", "confirm_destructive")
        self._section_reset(layout, "general")

    def _page_appearance(self, layout) -> None:
        layout.addWidget(QLabel("<b>Appearance</b>"))
        theme_combo = QComboBox()
        theme_combo.addItems(list(THEMES.keys()))
        self._add(layout, "Theme", theme_combo, "appearance", "theme")
        accent = QLineEdit(self.settings.get("appearance", "accent", ""))
        accent.setPlaceholderText("#C7522A (empty = theme default)")
        self._add(layout, "Accent color", accent, "appearance", "accent")
        self._add(layout, "Large text", QCheckBox(), "appearance", "large_text")
        self._add(layout, "Dyslexia-friendly font", QCheckBox(),
                  "appearance", "dyslexia_font")
        self._add(layout, "Reduced motion", QCheckBox(),
                  "appearance", "reduced_motion")
        self._section_reset(layout, "appearance")

    def _page_reading(self, layout) -> None:
        layout.addWidget(QLabel("<b>Reading</b>"))
        mode = QComboBox()
        mode.addItems(["single", "continuous", "two-page", "two-cover"])
        self._add(layout, "Default PDF mode", mode, "reading", "pdf_mode")
        fit = QComboBox()
        fit.addItems(["width", "page", "height", "none"])
        self._add(layout, "Default fit", fit, "reading", "fit")
        self._add(layout, "Smooth scrolling", QCheckBox(),
                  "reading", "smooth_scroll")
        self._add(layout, "Comic right-to-left (manga)", QCheckBox(),
                  "reading", "comic_rtl")
        self._add(layout, "Comic double-page", QCheckBox(),
                  "reading", "comic_double")
        self._section_reset(layout, "reading")

    def _page_pdf(self, layout) -> None:
        layout.addWidget(QLabel("<b>PDF</b>"))
        layout.addWidget(HelpLabel(
            "PDF rendering uses PyMuPDF with lazy page rendering and an "
            "LRU cache. Cache size is on the Performance page."))
        self._section_reset(layout, "pdf")

    def _page_epub(self, layout) -> None:
        layout.addWidget(QLabel("<b>EPUB</b>"))
        fam = QComboBox()
        fam.addItems(["serif", "sans"])
        self._add(layout, "Font family", fam, "reading", "epub_font_family")
        self._add(layout, "Font size (pt)", self._spin(10, 34, 1),
                  "reading", "epub_font_size")
        lh = QDoubleSpinBox()
        lh.setRange(1.0, 2.6)
        lh.setSingleStep(0.1)
        self._add(layout, "Line height", lh, "reading", "epub_line_height")
        self._add(layout, "Content width (px)", self._spin(480, 1200, 20),
                  "reading", "epub_width")
        theme = QComboBox()
        theme.addItems(["light", "sepia", "dark", "oled"])
        self._add(layout, "Reading theme", theme, "reading", "epub_theme")
        self._section_reset(layout, "reading")

    def _page_annotations(self, layout) -> None:
        layout.addWidget(QLabel("<b>Annotations</b>"))
        color = QLineEdit(self.settings.get("annotations", "default_color",
                                            "#E5B25D"))
        self._add(layout, "Default color", color, "annotations", "default_color")
        op = QDoubleSpinBox()
        op.setRange(0.1, 1.0)
        op.setSingleStep(0.1)
        self._add(layout, "Highlight opacity", op, "annotations",
                  "highlight_opacity")
        self._add(layout, "Author name", QLineEdit(), "annotations", "author")
        self._section_reset(layout, "annotations")

    def _page_ocr(self, layout) -> None:
        layout.addWidget(QLabel("<b>OCR</b>"))
        self._add(layout, "OCR enabled", QCheckBox(), "ocr", "enabled")
        lang = QComboBox()
        lang.addItems(["eng", "deu", "fra", "spa", "ita", "por", "nld", "rus"])
        lang.setEditable(True)
        self._add(layout, "Default language", lang, "ocr", "language")
        self._add(layout, "Render DPI", self._spin(150, 600, 50), "ocr", "dpi")
        from omnireader_pro.core.ocr.ocr import tesseract_available, tesseract_version
        status = (f"Engine: {tesseract_version()}" if tesseract_available()
                  else "Tesseract not installed — install from "
                       "github.com/UB-Mannheim/tesseract/wiki")
        layout.addWidget(HelpLabel(status))
        self._section_reset(layout, "ocr")

    def _page_speech(self, layout) -> None:
        layout.addWidget(QLabel("<b>Speech (read aloud)</b>"))
        rate = QDoubleSpinBox()
        rate.setRange(0.5, 3.0)
        rate.setSingleStep(0.1)
        self._add(layout, "Speed", rate, "speech", "rate")
        vol = QDoubleSpinBox()
        vol.setRange(0.0, 1.0)
        vol.setSingleStep(0.1)
        self._add(layout, "Volume", vol, "speech", "volume")
        self._section_reset(layout, "speech")

    def _page_library(self, layout) -> None:
        layout.addWidget(QLabel("<b>Library</b>"))
        view = QComboBox()
        view.addItems(["grid", "list", "compact", "table"])
        self._add(layout, "Default view", view, "library", "view")
        sort = QComboBox()
        sort.addItems(["last_opened", "title", "author", "added", "size",
                       "pages", "rating", "progress", "type"])
        self._add(layout, "Sort by", sort, "library", "sort")
        self._add(layout, "Thumbnail size", self._spin(64, 320, 8),
                  "library", "thumb_size")
        self._section_reset(layout, "library")

    def _page_search(self, layout) -> None:
        layout.addWidget(QLabel("<b>Search</b>"))
        self._add(layout, "Case sensitive by default", QCheckBox(),
                  "search", "case_sensitive")
        self._add(layout, "Whole word by default", QCheckBox(),
                  "search", "whole_word")
        self._add(layout, "Regex by default", QCheckBox(), "search", "regex")
        self._add(layout, "Fuzzy matching", QCheckBox(), "search", "fuzzy")
        self._section_reset(layout, "search")

    def _page_security(self, layout) -> None:
        layout.addWidget(QLabel("<b>Security</b>"))
        links = QComboBox()
        links.addItems(["ask", "open", "block"])
        self._add(layout, "External links", links, "security", "external_links")
        self._add(layout, "Vault auto-lock (minutes, 0 = off)",
                  self._spin(0, 120, 5), "security", "vault_autolock_min")
        layout.addWidget(HelpLabel(
            "Redaction removes underlying text and rasterizes covered "
            "images. Always use Verify Redaction for sensitive documents."))
        self._section_reset(layout, "security")

    def _page_privacy(self, layout) -> None:
        layout.addWidget(QLabel("<b>Privacy</b>"))
        self._add(layout, "Offline mode", QCheckBox(), "privacy", "offline_mode")
        self._add(layout, "Allow update checks", QCheckBox(),
                  "privacy", "allow_update_check")
        self._add(layout, "Remember document passwords", QCheckBox(),
                  "privacy", "remember_doc_passwords")
        layout.addWidget(HelpLabel(
            "OmniReader never sends telemetry. Network access only happens "
            "for features you explicitly trigger."))
        self._section_reset(layout, "privacy")

    def _page_performance(self, layout) -> None:
        layout.addWidget(QLabel("<b>Performance</b>"))
        self._add(layout, "Page cache (MB)", self._spin(32, 1024, 16),
                  "performance", "cache_page_mb")
        self._add(layout, "Prefetch pages", self._spin(0, 10, 1),
                  "performance", "prefetch")
        self._add(layout, "Thumbnail workers", self._spin(1, 8, 1),
                  "performance", "thumbnail_workers")
        self._section_reset(layout, "performance")

    def _page_keyboard(self, layout) -> None:
        layout.addWidget(QLabel("<b>Keyboard</b>"))
        self._add(layout, "Vim-style navigation (j/k/gg/G)", QCheckBox(),
                  "keyboard", "vim_mode")
        layout.addWidget(HelpLabel(
            "Shortcuts: Ctrl+O open · Ctrl+S save · Ctrl+P print · "
            "Ctrl+F find · Ctrl+K palette · F9 focus · F5 present · "
            "F11 fullscreen · Ctrl+B bookmark · Esc cancel tool."))
        self._section_reset(layout, "keyboard")

    def _page_updates(self, layout) -> None:
        layout.addWidget(QLabel("<b>Updates</b>"))
        self._add(layout, "Check for updates (manual)", QCheckBox(),
                  "privacy", "allow_update_check")
        layout.addWidget(HelpLabel(
            "Update checking is off by default and never downloads "
            "executables silently."))
        self._section_reset(layout, "privacy")

    def _page_data(self, layout) -> None:
        layout.addWidget(QLabel("<b>Data locations</b>"))
        from omnireader_pro.app import paths
        info = QPlainTextEdit()
        info.setReadOnly(True)
        info.setPlainText(
            f"Database: {paths.database_dir()}\n"
            f"Cache: {paths.cache_dir()}\n"
            f"Logs: {paths.logs_dir()}\n"
            f"Backups: {paths.backups_dir()}\n"
            f"Vault: {paths.vault_dir()}\n"
            f"Plugins: {paths.plugins_dir()}")
        info.setMaximumHeight(160)
        layout.addWidget(info)
        row = QHBoxLayout()
        logs_btn = QPushButton("Open logs folder")
        logs_btn.clicked.connect(lambda: __import__(
            "omnireader_pro.app.logging_setup",
            fromlist=["open_logs_folder"]).open_logs_folder())
        row.addWidget(logs_btn)
        row.addStretch(1)
        layout.addLayout(row)

    @staticmethod
    def _spin(lo: int, hi: int, step: int) -> QSpinBox:
        s = QSpinBox()
        s.setRange(lo, hi)
        s.setSingleStep(step)
        return s

    def _apply(self) -> None:
        self.settings.save()
        self.accept()
