"""First-run onboarding.

A short, desktop-native welcome: identity, theme choice, default folders,
key shortcuts, optional OCR/TTS enablement, reading defaults. No account,
no network, no forced telemetry — skippable at every step.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QListWidget, QListWidgetItem, QPushButton, QStackedWidget,
    QVBoxLayout, QWidget, QLineEdit,
)

from veyrion_workspace import APP_NAME, APP_TAGLINE, __version__
from veyrion_workspace.ui.icons import pixmap
from veyrion_workspace.ui.theme import THEMES
from veyrion_workspace.ui.widgets import HelpLabel


class OnboardingDialog(QDialog):
    def __init__(self, parent, settings) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Welcome to {APP_NAME}")
        self.setMinimumSize(640, 480)
        self.settings = settings

        lay = QVBoxLayout(self)
        self._stack = QStackedWidget()
        lay.addWidget(self._stack, 1)

        self._stack.addWidget(self._page_welcome())
        self._stack.addWidget(self._page_theme())
        self._stack.addWidget(self._page_folders())
        self._stack.addWidget(self._page_shortcuts())
        self._stack.addWidget(self._page_features())

        nav = QHBoxLayout()
        self._back = QPushButton("Back")
        self._next = QPushButton("Continue")
        self._next.setObjectName("accentButton")
        self._skip = QPushButton("Skip setup")
        self._skip.clicked.connect(self._finish)
        nav.addWidget(self._skip)
        nav.addStretch(1)
        nav.addWidget(self._back)
        nav.addWidget(self._next)
        lay.addLayout(nav)

        self._back.clicked.connect(self._go_back)
        self._next.clicked.connect(self._go_next)
        self._update_buttons()

    # ------------------------------------------------------------------ pages
    def _page_welcome(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addStretch(1)
        icon_label = QLabel()
        icon_label.setPixmap(pixmap("app", "#C7522A", 72))
        icon_label.setAlignment(Qt.AlignCenter)
        lay.addWidget(icon_label)
        title = QLabel(APP_NAME)
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignCenter)
        lay.addWidget(title)
        tag = QLabel(APP_TAGLINE)
        tag.setAlignment(Qt.AlignCenter)
        f = tag.font()
        try:
            f.setLetterSpacing(QFont.AbsoluteSpacing, 2.5)
        except Exception:
            pass
        tag.setFont(f)
        tag.setObjectName("dimLabel")
        lay.addWidget(tag)
        body = QLabel(
            f"Version {__version__}\n\n"
            "One workspace for reading, editing, annotating, and organizing "
            "every document on your computer.\n\n"
            "Everything runs locally — no account, no cloud, no tracking.")
        body.setAlignment(Qt.AlignCenter)
        body.setWordWrap(True)
        lay.addWidget(body)
        lay.addStretch(2)
        return page

    def _page_theme(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(QLabel("<b>Choose how Veyrion looks</b>"))
        self._theme_combo = QComboBox()
        self._theme_combo.addItems(list(THEMES.keys()))
        self._theme_combo.setCurrentText(
            self.settings.get("appearance", "theme", "light"))
        lay.addWidget(self._theme_combo)
        lay.addWidget(HelpLabel(
            "You can switch themes anytime in Settings > Appearance, or "
            "toggle dark mode from the command palette (Ctrl+K)."))
        lay.addStretch(1)
        return page

    def _page_folders(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(QLabel("<b>Where are your documents?</b>"))
        lay.addWidget(HelpLabel(
            "Add folders to build your library automatically. You can also "
            "do this later — or simply drag files into the window."))
        self._folder_list = QListWidget()
        lay.addWidget(self._folder_list, 1)
        row = QHBoxLayout()
        add = QPushButton("Add folder…")
        remove = QPushButton("Remove")
        add.clicked.connect(self._add_folder)
        remove.clicked.connect(self._remove_folder)
        row.addWidget(add)
        row.addWidget(remove)
        row.addStretch(1)
        lay.addLayout(row)
        return page

    def _page_shortcuts(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(QLabel("<b>Shortcuts worth knowing</b>"))
        tips = [
            ("Ctrl+K", "Command palette — every action, searchable"),
            ("Ctrl+O", "Open document"),
            ("Ctrl+F", "Find in document"),
            ("Ctrl+S / Ctrl+Shift+S", "Save / Save as"),
            ("Ctrl+B", "Bookmark current page"),
            ("Ctrl+Shift+H", "Highlight tool"),
            ("F9 / F5 / F11", "Focus mode / Presentation / Fullscreen"),
            ("Ctrl+Mouse wheel", "Zoom"),
        ]
        form = QFormLayout()
        for key, action in tips:
            key_label = QLabel(f"<b>{key}</b>")
            key_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            form.addRow(key_label, QLabel(action))
        lay.addLayout(form)
        lay.addStretch(1)
        return page

    def _page_features(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(QLabel("<b>Optional features</b>"))
        self._ocr_check = QCheckBox("Enable OCR (uses Tesseract when installed)")
        self._ocr_check.setChecked(True)
        self._index_check = QCheckBox(
            "Index documents for instant full-text search (recommended)")
        self._index_check.setChecked(True)
        self._tts_check = QCheckBox("Enable read-aloud (text-to-speech)")
        self._tts_check.setChecked(True)
        self._vim_check = QCheckBox("Vim-style navigation keys")
        self._vim_check.setChecked(False)
        mode = QComboBox()
        mode.addItems(["single", "continuous", "two-page", "two-cover"])
        mode.setCurrentText(self.settings.get("reading", "pdf_mode",
                                              "continuous"))
        self._mode_combo = mode
        lay.addWidget(self._ocr_check)
        lay.addWidget(self._index_check)
        lay.addWidget(self._tts_check)
        lay.addWidget(self._vim_check)
        row = QHBoxLayout()
        row.addWidget(QLabel("Default PDF mode:"))
        row.addWidget(mode)
        row.addStretch(1)
        lay.addLayout(row)
        from veyrion_workspace.core.ocr.ocr import tesseract_available
        if not tesseract_available():
            lay.addWidget(HelpLabel(
                "Tesseract isn't installed yet. OCR will prompt with "
                "install instructions when you first use it — everything "
                "else works without it."))
        lay.addStretch(1)
        return page

    # ------------------------------------------------------------------ flow
    def _add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose folder")
        if folder:
            self._folder_list.addItem(folder)

    def _remove_folder(self) -> None:
        row = self._folder_list.currentRow()
        if row >= 0:
            self._folder_list.takeItem(row)

    def _go_next(self) -> None:
        idx = self._stack.currentIndex()
        if idx == self._stack.count() - 1:
            self._finish()
            return
        self._stack.setCurrentIndex(idx + 1)
        self._update_buttons()

    def _go_back(self) -> None:
        idx = self._stack.currentIndex()
        self._stack.setCurrentIndex(max(0, idx - 1))
        self._update_buttons()

    def _update_buttons(self) -> None:
        last = self._stack.currentIndex() == self._stack.count() - 1
        self._next.setText("Finish" if last else "Continue")
        self._back.setEnabled(self._stack.currentIndex() > 0)

    def _finish(self) -> None:
        s = self.settings
        s.set("appearance", "theme", self._theme_combo.currentText())
        folders = [self._folder_list.item(i).text()
                   for i in range(self._folder_list.count())]
        s.set("general", "watch_folders", folders)
        s.set("general", "first_run_complete", True)
        s.set("reading", "pdf_mode", self._mode_combo.currentText())
        s.set("keyboard", "vim_mode", self._vim_check.isChecked())
        s.set("ocr", "enabled", self._ocr_check.isChecked())
        choices = {
            "index": self._index_check.isChecked(),
            "tts": self._tts_check.isChecked(),
            "ocr": self._ocr_check.isChecked(),
        }
        s.set("general", "onboarding_choices", choices)
        s.save()
        self.accept()
