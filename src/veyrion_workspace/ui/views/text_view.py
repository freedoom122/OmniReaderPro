"""Text-family view: TXT/MD/code editing with live markdown preview.

Markdown files get a split editor/preview; plain text gets a comfortable
reading/writing surface. Find/replace works on the whole buffer.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QSyntaxHighlighter, QTextCharFormat, QColor
from PySide6.QtWidgets import (
    QPlainTextEdit, QSplitter, QTextBrowser, QVBoxLayout, QWidget, QLineEdit,
    QPushButton, QHBoxLayout, QLabel,
)

from veyrion_workspace.core.documents.text_engine import TextEngine
from veyrion_workspace.ui.document_view import DocumentView
from veyrion_workspace.ui.theme import Palette


class _MarkdownHighlighter(QSyntaxHighlighter):
    """Lightweight markdown syntax highlighting."""

    def __init__(self, doc, p: Palette) -> None:
        super().__init__(doc)
        self._p = p
        heading = QTextCharFormat()
        heading.setFontWeight(QFont.Bold)
        heading.setForeground(QColor(p.accent))
        self._rules = [
            (r"^#{1,6}\s.*", heading),
            (r"\*\*[^*]+\*\*", self._bold_fmt()),
            (r"\*[^*]+\*", self._italic_fmt()),
            (r"`[^`]+`", self._code_fmt()),
            (r"^\s*[-*+] ", self._list_fmt()),
            (r"^\s*\d+\. ", self._list_fmt()),
            (r"^>\s?.*", self._quote_fmt()),
            (r"\[([^\]]+)\]\(([^)]+)\)", self._link_fmt()),
        ]

    def _bold_fmt(self):
        f = QTextCharFormat()
        f.setFontWeight(QFont.Bold)
        return f

    def _italic_fmt(self):
        f = QTextCharFormat()
        f.setFontItalic(True)
        return f

    def _code_fmt(self):
        f = QTextCharFormat()
        f.setFontFamilies(["Consolas", "monospace"])
        f.setBackground(QColor(self._p.code_bg))
        return f

    def _list_fmt(self):
        f = QTextCharFormat()
        f.setForeground(QColor(self._p.accent))
        return f

    def _quote_fmt(self):
        f = QTextCharFormat()
        f.setForeground(QColor(self._p.text_dim))
        f.setFontItalic(True)
        return f

    def _link_fmt(self):
        f = QTextCharFormat()
        f.setForeground(QColor(self._p.link))
        f.setFontUnderline(True)
        return f

    def highlightBlock(self, text: str) -> None:
        import re
        for pattern, fmt in self._rules:
            for m in re.finditer(pattern, text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)


def markdown_to_html(text: str) -> str:
    """Render markdown to HTML using markdown-it-py when available."""
    try:
        from markdown_it import MarkdownIt
        md = MarkdownIt("commonmark", {"html": False}).enable("table")
        body = md.render(text)
    except Exception:
        # Extremely defensive fallback: escape + line breaks.
        import html
        body = "<p>" + html.escape(text).replace("\n\n", "</p><p>") \
            .replace("\n", "<br>") + "</p>"
    return (
        "<html><head><meta charset='utf-8'><style>"
        "body{font-family:Georgia,serif;line-height:1.65;max-width:760px;"
        "margin:2em auto;padding:0 1.5em;}"
        "h1,h2,h3{line-height:1.25;} code{background:rgba(128,128,128,0.15);"
        "padding:1px 4px;border-radius:3px;}"
        "pre{background:rgba(128,128,128,0.12);padding:12px;border-radius:6px;"
        "overflow-x:auto;} blockquote{border-left:3px solid rgba(128,128,128,0.4);"
        "margin-left:0;padding-left:14px;color:#777;}"
        "table{border-collapse:collapse;} td,th{border:1px solid rgba(128,128,128,0.4);"
        "padding:4px 10px;} img{max-width:100%;}"
        "</style></head><body>" + body + "</body></html>"
    )


class TextDocView(DocumentView):
    view_id = "text"

    def __init__(self, engine: TextEngine, settings=None, parent=None) -> None:
        super().__init__(engine, parent)
        self.text_engine: TextEngine = engine
        self._settings = settings
        self._editor = QPlainTextEdit()
        self._editor.setObjectName("documentText")
        self._editor.setPlainText(engine.full_text())
        self._editor.textChanged.connect(self._on_text_changed)

        self._find_bar = QWidget()
        find_lay = QHBoxLayout(self._find_bar)
        find_lay.setContentsMargins(8, 4, 8, 4)
        self._find_edit = QLineEdit()
        self._find_edit.setPlaceholderText("Find")
        self._replace_edit = QLineEdit()
        self._replace_edit.setPlaceholderText("Replace with")
        find_btn = QPushButton("Find")
        replace_btn = QPushButton("Replace")
        replace_all_btn = QPushButton("Replace all")
        close_btn = QPushButton("×")
        close_btn.setFixedWidth(28)
        find_btn.clicked.connect(self._find_next)
        replace_btn.clicked.connect(self._replace_one)
        replace_all_btn.clicked.connect(self._replace_all)
        close_btn.clicked.connect(lambda: self._find_bar.hide())
        for wdg in (self._find_edit, self._replace_edit, find_btn,
                    replace_btn, replace_all_btn, close_btn):
            find_lay.addWidget(wdg)
        self._find_bar.hide()

        self._preview: QTextBrowser | None = None
        self._highlighter: QSyntaxHighlighter | None = None
        self._is_markdown = engine.path.suffix.lower() in (".md", ".markdown")
        self._splitter = QSplitter(Qt.Vertical)

        if self._is_markdown:
            self._highlighter = _MarkdownHighlighter(
                self._editor.document(), Palette())
            self._preview = QTextBrowser()
            self._preview.setOpenExternalLinks(False)
            self._splitter.addWidget(self._editor)
            self._splitter.addWidget(self._preview)
            self._splitter.setSizes([400, 300])
            self._update_preview()
        else:
            self._splitter.addWidget(self._editor)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._find_bar)
        lay.addWidget(self._splitter)

    # -- editing ------------------------------------------------------------
    def _on_text_changed(self) -> None:
        self.text_engine.replace_full_text(self._editor.toPlainText())
        self.content_changed.emit()
        self.state_changed.emit()
        if self._preview is not None:
            self._update_preview()

    def _update_preview(self) -> None:
        if self._preview is not None:
            self._preview.setHtml(markdown_to_html(self._editor.toPlainText()))

    def set_split_mode(self, mode: str) -> None:
        """editor|preview|split"""
        if self._preview is None:
            return
        if mode == "editor":
            self._preview.hide()
        elif mode == "preview":
            self._editor.hide()
        else:
            self._editor.show()
            self._preview.show()

    # -- find/replace -----------------------------------------------------------
    def _find_next(self) -> None:
        query = self._find_edit.text()
        if not query:
            return
        if not self._editor.find(query):
            # wrap around
            cursor = self._editor.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            self._editor.setTextCursor(cursor)
            self._editor.find(query)
        self._find_bar.show()

    def _replace_one(self) -> None:
        cursor = self._editor.textCursor()
        if cursor.hasSelection() and \
                cursor.selectedText() == self._find_edit.text():
            cursor.insertText(self._replace_edit.text())
        self._find_next()

    def _replace_all(self) -> None:
        query = self._find_edit.text()
        if not query:
            return
        text = self._editor.toPlainText()
        count = text.count(query)
        if count:
            new_text = text.replace(query, self._replace_edit.text())
            self._editor.setPlainText(new_text)
            self.request_toast.emit(f"Replaced {count} occurrence(s)", "success")

    # -- overrides ---------------------------------------------------------
    def show_find(self) -> None:
        self._find_bar.show()
        self._find_edit.setFocus()

    def find_in_view(self, query: str, case_sensitive: bool = False,
                     whole_word: bool = False, regex: bool = False,
                     backwards: bool = False) -> int:
        self.show_find()
        self._find_edit.setText(query)
        self._find_next()
        return 1

    def selected_text(self) -> str:
        return self._editor.textCursor().selectedText()

    def save_state(self) -> dict:
        return {"page": self.current_page,
                "scroll": self._editor.verticalScrollBar().value()}

    def restore_state(self, state: dict) -> None:
        self._current_page = int(state.get("page", 0))
        from PySide6.QtCore import QTimer
        QTimer.singleShot(50, lambda: self._editor.verticalScrollBar().setValue(
            int(state.get("scroll", 0))))

    def save(self) -> Path:
        self.text_engine.replace_full_text(self._editor.toPlainText())
        return self.text_engine.save()

    def save_as(self, target: Path) -> Path:
        self.text_engine.replace_full_text(self._editor.toPlainText())
        return self.text_engine.save(Path(target))
