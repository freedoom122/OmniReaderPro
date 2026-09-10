"""Office document views.

DOCX: block-based editor (paragraphs with headings, tables) with save-back
into the original package. ODT/RTF/PPTX/XLSX: high-fidelity read views with
honest labeling of what is editable.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
    QSplitter, QTableWidget, QTableWidgetItem, QTabWidget, QTextBrowser,
    QVBoxLayout, QWidget, QListWidget, QStackedWidget, QFontComboBox,
    QComboBox,
)

from omnireader_pro.core.documents.office_engine import (
    DocxEngine, OdtEngine, PptxEngine, RtfEngine, XlsxEngine,
)
from omnireader_pro.ui.document_view import DocumentView
from omnireader_pro.ui.views.text_view import markdown_to_html


class DocxView(DocumentView):
    view_id = "docx"

    def __init__(self, engine: DocxEngine, parent=None) -> None:
        super().__init__(engine, parent)
        self.docx: DocxEngine = engine

        tabs = QTabWidget()
        # -- Document tab: block list editor --------------------------------
        doc_page = QWidget()
        doc_lay = QHBoxLayout(doc_page)
        doc_lay.setContentsMargins(0, 0, 0, 0)

        self._block_list = QListWidget()
        self._block_list.currentRowChanged.connect(self._on_block_selected)
        doc_lay.addWidget(self._block_list, 1)

        edit_side = QWidget()
        edit_lay = QVBoxLayout(edit_side)
        self._style_label = QLabel()
        self._style_label.setObjectName("dimLabel")
        self._editor = QPlainTextEdit()
        self._editor.setObjectName("documentText")
        self._apply_btn = QPushButton("Apply to paragraph")
        self._apply_btn.setObjectName("accentButton")
        self._apply_btn.clicked.connect(self._apply_edit)
        edit_lay.addWidget(self._style_label)
        edit_lay.addWidget(self._editor, 1)
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(self._apply_btn)
        edit_lay.addLayout(btn_row)
        doc_lay.addWidget(edit_side, 2)

        # -- Tables tab -----------------------------------------------------
        self._table_page = QWidget()
        table_lay = QHBoxLayout(self._table_page)
        self._table = QTableWidget()
        table_lay.addWidget(self._table)

        tabs.addTab(doc_page, "Document")
        tabs.addTab(self._table_page, "Tables")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(tabs)
        self._load_blocks()

    def _load_blocks(self) -> None:
        self._block_list.clear()
        self._blocks = self.docx.blocks()
        for i, b in enumerate(self._blocks):
            if b["kind"] == "paragraph":
                level = b.get("level") or 0
                prefix = f"H{level}: " if level else ""
                text = b.get("text", "")[:80]
                self._block_list.addItem(f"{prefix}{text}")
            else:
                rows = len(b.get("rows", []))
                self._block_list.addItem(f"[Table — {rows} rows]")

    def _on_block_selected(self, row: int) -> None:
        if not (0 <= row < len(self._blocks)):
            return
        b = self._blocks[row]
        if b["kind"] == "paragraph":
            self._editor.setPlainText(b.get("text", ""))
            self._style_label.setText(f"Style: {b.get('style', 'Normal')}")
            self._editor.setEnabled(True)
            self._apply_btn.setEnabled(True)
        else:
            self._editor.setPlainText("")
            self._style_label.setText("Table (read-only in this tab)")
            self._editor.setEnabled(False)
            self._apply_btn.setEnabled(False)
            rows = b.get("rows", [])
            if rows:
                self._table.setColumnCount(max(len(r) for r in rows))
                self._table.setRowCount(len(rows))
                for r, row in enumerate(rows):
                    for c, cell in enumerate(row):
                        self._table.setItem(
                            r, c, QTableWidgetItem(str(cell)))

    def _apply_edit(self) -> None:
        row = self._block_list.currentRow()
        if not (0 <= row < len(self._blocks)):
            return
        if self._blocks[row]["kind"] != "paragraph":
            return
        self.docx.set_block_text(row, self._editor.toPlainText())
        self._load_blocks()
        self._block_list.setCurrentRow(row)
        self.content_changed.emit()
        self.request_toast.emit("Paragraph updated", "success")

    def page_text(self, page: int = -1) -> str:
        idx = self._current_page if page < 0 else page
        return self.docx.page_text(idx)

    def selected_text(self) -> str:
        return self._editor.textCursor().selectedText()

    def save(self) -> Path:
        return self.docx.save()

    def save_as(self, target: Path) -> Path:
        return self.docx.save(Path(target))


class _ReadonlyTextView(DocumentView):
    """Shared read-only view for ODT/RTF/PPTX/XLSX text content."""

    view_id = "office_readonly"

    def __init__(self, engine, label: str, parent=None) -> None:
        super().__init__(engine, parent)
        self._browser = QTextBrowser()
        self._browser.setObjectName("documentText")
        notice = QLabel(f"  {label} — view mode. Use Export to convert or extract.")
        notice.setObjectName("dimLabel")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(notice)
        lay.addWidget(self._browser, 1)
        self._load()

    def _load(self) -> None:
        parts = []
        total = self.page_count
        for i in range(min(total, 40)):
            text = self.engine.page_text(i).strip()
            if text:
                header = self._page_header(i)
                parts.append(f"### {header}\n\n{text}")
        self._browser.setHtml(markdown_to_html("\n\n".join(parts)))

    def _page_header(self, index: int) -> str:
        name = getattr(self.engine, "_sheets", None)
        if name and 0 <= index < len(name):
            return name[index]
        return f"Section {index + 1}"

    def page_text(self, page: int = -1) -> str:
        idx = self._current_page if page < 0 else page
        return self.engine.page_text(idx)


class OdtView(_ReadonlyTextView):
    view_id = "odt"

    def __init__(self, engine: OdtEngine, parent=None) -> None:
        super().__init__(engine, "OpenDocument Text", parent)


class RtfView(_ReadonlyTextView):
    view_id = "rtf"

    def __init__(self, engine: RtfEngine, parent=None) -> None:
        super().__init__(engine, "Rich Text", parent)


class PptxView(_ReadonlyTextView):
    view_id = "pptx"

    def __init__(self, engine: PptxEngine, parent=None) -> None:
        super().__init__(engine, "PowerPoint presentation", parent)


class XlsxView(_ReadonlyTextView):
    view_id = "xlsx"

    def __init__(self, engine: XlsxEngine, parent=None) -> None:
        super().__init__(engine, "Excel workbook", parent)
