"""Information panels: search results, annotations, notes, thumbnails,
table of contents, bookmarks, background tasks, and document properties."""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMenu, QProgressBar, QPushButton,
    QScrollArea, QTableWidget, QTableWidgetItem, QTextBrowser, QToolBar,
    QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
    QHeaderView, QSizePolicy,
)

from omnireader_pro.core.search.engine import SearchEngine
from omnireader_pro.core.annotations.service import AnnotationService
from omnireader_pro.storage.repositories import NoteRecord, NoteRepository
from omnireader_pro.ui.icons import icon
from omnireader_pro.ui.theme import Palette
from omnireader_pro.ui.widgets import EmptyState, SectionHeader, show_toast
from omnireader_pro.utils.pathutils import format_size


class SearchPanel(QWidget):
    """Global search across indexed documents and annotations."""

    hit_selected = Signal(str, int)   # doc path, page

    def __init__(self, search_engine: SearchEngine, parent=None) -> None:
        super().__init__(parent)
        self._search = search_engine
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        self._query = QLineEdit()
        self._query.setPlaceholderText("Search all documents…")
        self._query.setClearButtonEnabled(True)
        self._query.returnPressed.connect(self.run_search)
        lay.addWidget(self._query)

        opts = QHBoxLayout()
        self._scope = QComboBox()
        self._scope.addItems(["Documents", "Annotations only", "Metadata"])
        opts.addWidget(self._scope, 1)
        self._go = QPushButton("Search")
        self._go.setObjectName("accentButton")
        self._go.clicked.connect(self.run_search)
        opts.addWidget(self._go)
        lay.addLayout(opts)

        self._status = QLabel("")
        self._status.setObjectName("dimLabel")
        lay.addWidget(self._status)

        self._results = QListWidget()
        self._results.itemClicked.connect(self._on_hit)
        self._results.setWordWrap(True)
        lay.addWidget(self._results, 1)

    def run_search(self) -> None:
        query = self._query.text().strip()
        self._results.clear()
        if not query:
            return
        scope = self._scope.currentText()
        if scope == "Annotations only":
            hits = self._search.search(query, annotation_only=True)
        elif scope == "Metadata":
            hits = self._search.search_metadata(query)
        else:
            hits = self._search.search(query)
        for h in hits[:300]:
            label = (f"<b>{h.doc_title}</b>  ·  page {h.page + 1}<br>"
                     f"<span style='color:#8a8578'>{h.context}</span>")
            item = QListWidgetItem()
            item.setData(Qt.UserRole, {"path": h.doc_path, "page": h.page})
            from PySide6.QtWidgets import QLabel as _Q
            widget = QLabel(label)
            widget.setContentsMargins(6, 4, 6, 4)
            item.setSizeHint(widget.sizeHint() + QSize(0, 8))
            self._results.addItem(item)
            self._results.setItemWidget(item, widget)
        self._status.setText(f"{len(hits)} result(s)" if hits else "No matches")

    def _on_hit(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.UserRole)
        if data:
            self.hit_selected.emit(data["path"], data["page"])


class AnnotationsPanel(QWidget):
    """Annotation workspace: filter, search, jump, edit, delete, export."""

    annotation_selected = Signal(str, int)   # doc_path, page
    annotations_changed = Signal()

    def __init__(self, ann_service: AnnotationService, parent=None) -> None:
        super().__init__(parent)
        self._anns = ann_service
        self._doc_filter = ""
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)

        self._filter = QLineEdit()
        self._filter.setPlaceholderText("Filter annotations…")
        self._filter.setClearButtonEnabled(True)
        self._filter.textChanged.connect(self.reload)
        lay.addWidget(self._filter)

        self._scope_combo = QComboBox()
        self._scope_combo.addItems(["Current document", "All documents"])
        self._scope_combo.currentIndexChanged.connect(self.reload)
        lay.addWidget(self._scope_combo)

        self._list = QListWidget()
        self._list.itemClicked.connect(self._on_selected)
        self._list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._menu)
        lay.addWidget(self._list, 1)

        export_row = QHBoxLayout()
        for fmt in ("Markdown", "HTML", "CSV", "JSON", "PDF"):
            btn = QToolButton()
            btn.setText(fmt)
            btn.clicked.connect(lambda _=False, f=fmt: self._export(f.lower()))
            export_row.addWidget(btn)
        export_row.addStretch(1)
        lay.addLayout(export_row)

    def set_document_filter(self, doc_path: str) -> None:
        self._doc_filter = doc_path

    def reload(self) -> None:
        self._list.clear()
        text = (self._filter.text() or "").lower()
        all_docs = self._scope_combo.currentText() == "All documents"
        records = self._anns.all_annotations() if all_docs \
            else self._anns.for_document(self._doc_filter)
        for rec in records:
            body = rec.text or rec.note or f"[{rec.atype}]"
            if text and text not in (body + rec.note).lower():
                continue
            kind_icon = {
                "highlight": "highlighter", "underline": "underline",
                "strikeout": "strikeout", "squiggly": "underline",
                "note": "note", "freetext": "text", "ink": "ink",
                "rectangle": "shapes", "ellipse": "shapes",
                "arrow": "shapes", "line": "shapes", "stamp": "stamp",
            }.get(rec.atype, "note")
            from PySide6.QtGui import QColor
            item = QListWidgetItem(icon(kind_icon, rec.color),
                                   f"p.{rec.page + 1}  ·  {body[:100]}")
            item.setData(Qt.UserRole, {"path": rec.doc_path, "page": rec.page,
                                       "uuid": rec.uuid})
            item.setToolTip(f"{rec.atype} by {rec.author or 'Me'} on "
                            f"{time.strftime('%Y-%m-%d', time.localtime(rec.created_at))}")
            self._list.addItem(item)

    def _on_selected(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.UserRole)
        if data:
            self.annotation_selected.emit(data["path"], data["page"])

    def _menu(self, pos) -> None:
        item = self._list.itemAt(pos)
        if not item:
            return
        data = item.data(Qt.UserRole)
        menu = QMenu(self)
        jump = menu.addAction("Go to annotation")
        edit = menu.addAction("Edit note…")
        delete = menu.addAction(icon("trash", "#A33B2E"), "Delete")
        chosen = menu.exec(self._list.mapToGlobal(pos))
        if chosen is jump:
            self.annotation_selected.emit(data["path"], data["page"])
        elif chosen is edit:
            self._edit_note(data["uuid"])
        elif chosen is delete:
            self._anns.delete(data["uuid"], data["path"])
            self.reload()
            self.annotations_changed.emit()

    def _edit_note(self, uuid: str) -> None:
        from PySide6.QtWidgets import QInputDialog
        rec = next((r for r in self._anns.all_annotations() if r.uuid == uuid), None)
        if not rec:
            return
        text, ok = QInputDialog.getMultiLineText(
            self, "Edit annotation note", "Note text:", rec.note)
        if ok:
            self._anns.update(rec, note=text)
            self.reload()
            self.annotations_changed.emit()

    def _export(self, fmt: str) -> None:
        from PySide6.QtWidgets import QFileDialog
        doc_path = self._doc_filter or ""
        if not doc_path:
            self._scope_combo.setCurrentIndex(0)
            return
        default = Path(doc_path).with_suffix(f".annotations.{fmt}")
        target, _ = QFileDialog.getSaveFileName(
            self, "Export annotations", str(default))
        if not target:
            return
        out = self._anns.export(doc_path, fmt, Path(target),
                                title=Path(doc_path).name)
        show_toast(self.window(), f"Annotations exported to {out.name}", "success")


class NotesPanel(QWidget):
    """Document-linked notes / notebook entries."""

    note_selected = Signal(str, int)  # doc_path, page (anchor)

    def __init__(self, note_repo: NoteRepository, parent=None) -> None:
        super().__init__(parent)
        self._repo = note_repo
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        row = QHBoxLayout()
        self._new_btn = QPushButton("New note")
        self._new_btn.clicked.connect(self._new_note)
        self._delete_btn = QPushButton("Delete")
        self._delete_btn.clicked.connect(self._delete_note)
        row.addWidget(self._new_btn)
        row.addWidget(self._delete_btn)
        row.addStretch(1)
        lay.addLayout(row)

        self._list = QListWidget()
        self._list.currentItemChanged.connect(self._on_selected)
        lay.addWidget(self._list, 1)

        self._editor_title = QLineEdit()
        self._editor_title.setPlaceholderText("Title")
        self._editor_title.textEdited.connect(self._save_current)
        self._editor = QTextBrowser()
        lay.addWidget(self._editor_title)
        lay.addWidget(self._editor, 2)
        self._current: NoteRecord | None = None
        self.reload()

    def reload(self) -> None:
        self._list.clear()
        for rec in self._repo.all():
            title = rec.title or "(untitled note)"
            when = time.strftime("%Y-%m-%d", time.localtime(rec.modified_at))
            item = QListWidgetItem(icon("note", "#8A5A2B"), f"{title}\n{when}")
            item.setData(Qt.UserRole, rec.id)
            self._list.addItem(item)

    def _new_note(self) -> None:
        rec = NoteRecord(title="New note", body="")
        self._repo.create(rec)
        self.reload()

    def _delete_note(self) -> None:
        if self._current:
            self._repo.delete(self._current.id)
            self._current = None
            self.reload()

    def _on_selected(self, current, previous) -> None:
        if current is None:
            return
        note_id = current.data(Qt.UserRole)
        for rec in self._repo.all():
            if rec.id == note_id:
                self._current = rec
                self._editor_title.setText(rec.title)
                self._editor.setHtml(markdown_to_html(rec.body or ""))
                break

    def _save_current(self) -> None:
        if self._current:
            self._current.title = self._editor_title.text()
            self._repo.update(self._current)
            self.reload()

    def set_body_editable(self) -> None:
        pass


def markdown_to_html(text: str) -> str:
    from omnireader_pro.ui.views.text_view import markdown_to_html as _m
    return _m(text)


class ThumbnailsPanel(QWidget):
    """Page thumbnail strip with click navigation."""

    page_selected = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._view = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        self._area = QScrollArea()
        self._area.setWidgetResizable(True)
        self._container = QWidget()
        self._grid = QGridLayout(self._container)
        self._grid.setSpacing(6)
        self._area.setWidget(self._container)
        lay.addWidget(self._area)
        self._buttons: list[QToolButton] = []

    def set_view(self, view) -> None:
        self._view = view
        self.rebuild()

    def rebuild(self) -> None:
        for b in self._buttons:
            b.deleteLater()
        self._buttons = []
        if self._view is None:
            return
        count = self._view.page_count
        cols = 2
        for i in range(count):
            btn = QToolButton()
            btn.setText(str(i + 1))
            btn.setCheckable(True)
            btn.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            btn.setIconSize(QSize(88, 110))
            btn.clicked.connect(lambda _=False, idx=i: self.page_selected.emit(idx))
            self._buttons.append(btn)
            self._grid.addWidget(btn, i // cols, i % cols)
        self._render_thumbs()

    def _render_thumbs(self) -> None:
        """Render thumbnails in the background via the view's engine."""
        if self._view is None:
            return
        import io
        for i, btn in enumerate(self._buttons):
            try:
                if i < self._view.page_count:
                    img = self._view.engine.render_thumbnail(i, 110)
                    if img is not None:
                        if hasattr(img, "save") and not hasattr(img, "scaled"):
                            buf = io.BytesIO()
                            img.save(buf, format="PNG")
                            from PySide6.QtGui import QImage
                            qimg = QImage.fromData(buf.getvalue(), "PNG")
                            btn.setIcon(icon_or_pixmap(qimg))
                        else:
                            btn.setIcon(icon_or_pixmap(img))
            except Exception:
                pass
        self.highlight(self._view.current_page)

    def highlight(self, page: int) -> None:
        for i, btn in enumerate(self._buttons):
            btn.setChecked(i == page)


def icon_or_pixmap(qimg) -> object:
    from PySide6.QtGui import QPixmap, QImage, QIcon
    if isinstance(qimg, QImage):
        return QIcon(QPixmap.fromImage(qimg))
    if isinstance(qimg, QPixmap):
        return QIcon(qimg)
    return qimg


class TocPanel(QWidget):
    """Table of contents / outline with clickable navigation."""

    entry_selected = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.itemClicked.connect(self._on_click)
        lay.addWidget(self._tree)
        self._empty = EmptyState("toc", "No outline",
                                 "This document has no table of contents.")
        lay.addWidget(self._empty)
        self._empty.hide()

    def set_toc(self, entries) -> None:
        self._tree.clear()
        if not entries:
            self._tree.hide()
            self._empty.show()
            return
        self._tree.show()
        self._empty.hide()
        stack = [(entry, None) for entry in reversed(entries)]
        parents: dict[int, QTreeWidgetItem] = {}
        # Build by level with a simple stack pass.
        level_items: dict[int, QTreeWidgetItem] = {}
        roots: list[QTreeWidgetItem] = []
        for entry in entries:
            item = QTreeWidgetItem([entry.title or "(untitled)"])
            item.setData(0, Qt.UserRole, entry.page)
            if entry.level <= 1 or not level_items:
                roots.append(item)
                level_items.clear()
                level_items[entry.level] = item
            else:
                parent = None
                for lvl in range(entry.level - 1, 0, -1):
                    if lvl in level_items:
                        parent = level_items[lvl]
                        break
                if parent is None:
                    roots.append(item)
                else:
                    parent.addChild(item)
                level_items[entry.level] = item
        self._tree.insertTopLevelItems(0, roots)
        self._tree.expandAll()

    def _on_click(self, item, col) -> None:
        page = item.data(0, Qt.UserRole)
        if page is not None:
            self.entry_selected.emit(int(page))


class BookmarksPanel(QWidget):
    bookmark_selected = Signal(int, float)

    def __init__(self, db, parent=None) -> None:
        super().__init__(parent)
        self._db = db
        self._doc_path = ""
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        self._add_btn = QPushButton("Bookmark current page")
        self._add_btn.clicked.connect(self._add)
        lay.addWidget(self._add_btn)
        self._list = QListWidget()
        self._list.itemClicked.connect(self._on_click)
        lay.addWidget(self._list, 1)

    def set_document(self, doc_path: str) -> None:
        self._doc_path = doc_path
        self.reload()

    def reload(self) -> None:
        self._list.clear()
        if not self._doc_path:
            return
        rows = self._db.query(
            "SELECT * FROM bookmarks WHERE doc_path=? ORDER BY page", (self._doc_path,))
        for row in rows:
            item = QListWidgetItem(icon("bookmark", "#C7522A"),
                                   f"p.{row['page'] + 1} — {row['title'] or 'Bookmark'}")
            item.setData(Qt.UserRole, {"page": row["page"], "scroll": row["scroll"]})
            self._list.addItem(item)

    def _add(self) -> None:
        from PySide6.QtWidgets import QInputDialog
        if not self._doc_path:
            return
        page = 0
        view = self.window().current_view() if hasattr(self.window(), "current_view") else None
        if view is not None:
            page = view.current_page
        title, ok = QInputDialog.getText(self, "Bookmark", "Label (optional):")
        self._db.execute(
            "INSERT INTO bookmarks (doc_path, page, title, created_at) VALUES (?,?,?,?)",
            (self._doc_path, page, title if ok else "", time.time()))
        self.reload()

    def _on_click(self, item) -> None:
        data = item.data(Qt.UserRole)
        self.bookmark_selected.emit(data["page"], data["scroll"])


class TasksPanel(QWidget):
    """Background task center: live progress, cancel, retry, errors."""

    def __init__(self, task_manager, parent=None) -> None:
        super().__init__(parent)
        self._tm = task_manager
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        self._rows: dict[str, dict] = {}
        self._grid = QVBoxLayout()
        self._grid.setSpacing(6)
        lay.addLayout(self._grid)
        lay.addStretch(1)
        self._clear_btn = QPushButton("Clear finished")
        self._clear_btn.clicked.connect(self._clear)
        lay.addWidget(self._clear_btn)
        self._tm.add_listener(self._on_event)
        self.reload()

    def reload(self) -> None:
        for task in self._tm.all_tasks():
            self._update_row(task)

    def _on_event(self, task, event) -> None:
        try:
            # Task events arrive from worker threads; schedule on the UI thread.
            from PySide6.QtCore import QMetaObject, Q_ARG, QueuedConnection
            QMetaObject.invokeMethod(self, "_ui_reload",
                                     QueuedConnection)
        except Exception:
            pass

    def _ui_reload(self) -> None:
        self.reload()

    def _update_row(self, task) -> None:
        from PySide6.QtCore import QMetaObject, QueuedConnection
        QMetaObject.invokeMethod(self, "_ui_update", QueuedConnection)

    def _clear(self) -> None:
        self._tm.clear_finished()
        self.reload()


class PropertiesPanel(QWidget):
    """Read-only document properties, computed from the live engine."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        self._form = QFormLayout()
        self._form.setLabelAlignment(Qt.AlignRight)
        lay.addLayout(self._form)
        lay.addStretch(1)
        self._empty = EmptyState("properties", "No document",
                                 "Open a document to see its properties.")
        lay.addWidget(self._empty)
        self.set_document(None)

    def set_document(self, view) -> None:
        # Clear form
        while self._form.rowCount():
            self._form.removeRow(0)
        if view is None:
            self._empty.show()
            return
        self._empty.hide()
        try:
            md = view.engine.metadata()
            fields = [
                ("Title", md.title or "—"),
                ("Author", md.author or "—"),
                ("Subject", md.subject or "—"),
                ("Pages", str(md.page_count)),
                ("Words", f"{md.word_count:,}" if md.word_count else "—"),
                ("Encrypted", "Yes" if md.encrypted else "No"),
                ("Scanned", "Likely" if md.scanned else "No"),
                ("Signed", "Yes" if md.signed else "No"),
                ("Producer", md.producer or "—"),
            ]
            for key, value in fields:
                label = QLabel(str(value))
                label.setWordWrap(True)
                label.setTextInteractionFlags(Qt.TextSelectableByMouse)
                self._form.addRow(f"<b>{key}</b>", label)
        except Exception:
            self._empty.show()
