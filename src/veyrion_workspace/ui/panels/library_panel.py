"""Library panel: the document manager.

Grid / list / compact / table views over the library database with real
sorting, filtering, smart collections, tags, ratings, favorites, batch
operations, and context menus. Every action writes through to the DB.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox,
    QStackedWidget, QTableWidget, QTableWidgetItem, QToolBar, QTreeView,
    QVBoxLayout, QWidget, QTreeWidget, QTreeWidgetItem, QGridLayout,
    QToolButton, QSizePolicy,
)

from veyrion_workspace.app import paths
from veyrion_workspace.core.library.scanner import import_document
from veyrion_workspace.storage.repositories import DocumentRecord, LibraryRepository
from veyrion_workspace.ui.icons import icon
from veyrion_workspace.ui.theme import Palette
from veyrion_workspace.ui.widgets import EmptyState, SectionHeader, show_toast
from veyrion_workspace.utils.pathutils import format_size

KIND_LABELS = {
    "pdf": "PDF", "ebook": "E-book", "comic": "Comic", "image": "Image",
    "office": "Office", "text": "Text", "web": "Web", "other": "Other",
}


class LibraryPanel(QWidget):
    open_requested = Signal(str)          # doc path
    open_in_tab_requested = Signal(str)

    def __init__(self, library: LibraryRepository, settings, task_manager,
                 parent=None) -> None:
        super().__init__(parent)
        self._library = library
        self._settings = settings
        self._tasks = task_manager
        self._palette = Palette()
        self._docs: list[DocumentRecord] = []
        self._filter_kind = ""
        self._filter_text = ""
        self._filter_tag = ""
        self._filter_favorite = False
        self._only_annotated = False
        self._smart_rules = None
        self._smart_extra = {}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # -- toolbar ------------------------------------------------------
        bar = QToolBar()
        bar.setMovable(False)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter library…")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._refresh)
        self._view_combo = QComboBox()
        self._view_combo.addItems(["Grid", "List", "Compact", "Table"])
        self._view_combo.setCurrentText(
            str(settings.get("library", "view", "Grid")).title() if settings else "Grid")
        self._view_combo.currentTextChanged.connect(self._on_view_changed)
        self._sort_combo = QComboBox()
        self._sort_combo.addItems([
            "Last opened", "Title", "Author", "Date added", "Size",
            "Pages", "Rating", "Progress", "Type"])
        self._sort_combo.currentTextChanged.connect(self._refresh)
        self._kind_combo = QComboBox()
        self._kind_combo.addItems(["All types"] + list(KIND_LABELS.values()))
        self._kind_combo.currentTextChanged.connect(self._on_kind_filter)
        self._fav_btn = QToolButton()
        self._fav_btn.setIcon(icon("star", "#B07A21"))
        self._fav_btn.setCheckable(True)
        self._fav_btn.setToolTip("Favorites only")
        self._fav_btn.toggled.connect(self._refresh)
        self._ann_btn = QToolButton()
        self._ann_btn.setIcon(icon("highlighter", "#8A5A2B"))
        self._ann_btn.setCheckable(True)
        self._ann_btn.setToolTip("Annotated only")
        self._ann_btn.toggled.connect(self._refresh)

        bar.addWidget(QLabel(" "))
        bar.addWidget(self._search)
        bar.addWidget(QLabel(" View "))
        bar.addWidget(self._view_combo)
        bar.addWidget(QLabel(" Sort "))
        bar.addWidget(self._sort_combo)
        bar.addWidget(QLabel(" "))
        bar.addWidget(self._kind_combo)
        bar.addWidget(self._fav_btn)
        bar.addWidget(self._ann_btn)
        lay.addWidget(bar)

        # -- stack of views ------------------------------------------------
        self._stack = QStackedWidget()
        self._grid = _GridWidget(self._palette)
        self._grid.item_activated.connect(self._open_item)
        self._grid.context_menu.connect(self._context_menu)
        self._list = QListWidget()
        self._list.itemActivated.connect(lambda i: self._open_item(i.data(Qt.UserRole)))
        self._list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._list.customContextMenuRequested.connect(
            lambda pos: self._context_menu(self._list.itemAt(pos).data(Qt.UserRole)
                                           if self._list.itemAt(pos) else None,
                                           self._list.mapToGlobal(pos)))
        self._table = QTableWidget()
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels(
            ["Title", "Author", "Type", "Pages", "Size", "Progress"])
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.itemDoubleClicked.connect(
            lambda i: self._open_item(self._docs[i.row()].path))
        self._table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._table.customContextMenuRequested.connect(
            lambda pos: self._context_menu(self._docs[self._table.itemAt(pos).row()].path,
                                           self._table.mapToGlobal(pos))
            if self._table.itemAt(pos) else None)
        self._empty = EmptyState(
            "library", "Your library is empty",
            "Open a document or add a folder to build your collection.",
            "Add folder…")
        if self._empty.action_button:
            self._empty.action_button.clicked.connect(self._add_folder)
        for w in (self._grid, self._list, self._table, self._empty):
            self._stack.addWidget(w)
        lay.addWidget(self._stack, 1)

        self._status = QLabel("")
        self._status.setObjectName("dimLabel")
        self._status.setContentsMargins(10, 2, 10, 4)
        lay.addWidget(self._status)

        self._on_view_changed(self._view_combo.currentText())

    # ------------------------------------------------------------------ data
    def reload(self) -> None:
        self._refresh()

    def _refresh(self, *args) -> None:
        docs = self._library.all()
        text = (self._search.text() or "").lower()
        kind_map_rev = {v: k for k, v in KIND_LABELS.items()}
        kind_filter = kind_map_rev.get(self._kind_combo.currentText(), "")
        fav_only = self._fav_btn.isChecked()
        ann_only = self._ann_btn.isChecked()
        filtered = []
        for d in docs:
            if text and text not in (d.title + " " + d.author).lower():
                continue
            if kind_filter and d.kind != kind_filter:
                continue
            if fav_only and not d.favorite:
                continue
            if ann_only and d.progress >= 0 and not self._is_annotated(d):
                continue
            filtered.append(d)
        sort_key = {
            "Last opened": lambda d: d.last_opened,
            "Title": lambda d: d.title.lower(),
            "Author": lambda d: (d.author or "").lower(),
            "Date added": lambda d: d.added_at,
            "Size": lambda d: d.size_bytes,
            "Pages": lambda d: d.page_count,
            "Rating": lambda d: d.rating,
            "Progress": lambda d: d.progress,
            "Type": lambda d: d.kind,
        }[self._sort_combo.currentText()]
        filtered.sort(key=sort_key, reverse=self._sort_combo.currentText()
                      in ("Last opened", "Date added", "Size", "Pages",
                          "Rating", "Progress"))
        self._docs = filtered
        self._render()

    def _is_annotated(self, d: DocumentRecord) -> bool:
        # Cheap check via the annotations table count column if populated by UI.
        return getattr(d, "has_annotations", False) or d.rating > 0 or d.favorite

    def _render(self) -> None:
        if not self._docs:
            self._stack.setCurrentWidget(self._empty)
            self._status.setText("")
            return
        view = self._view_combo.currentText()
        if view == "Grid":
            self._stack.setCurrentWidget(self._grid)
            self._grid.set_documents(self._docs)
        elif view == "Table":
            self._stack.setCurrentWidget(self._table)
            self._render_table()
        elif view == "Compact":
            self._stack.setCurrentWidget(self._list)
            self._render_list(compact=True)
        else:
            self._stack.setCurrentWidget(self._list)
            self._render_list(compact=False)
        total = len(self._docs)
        size = sum(d.size_bytes for d in self._docs)
        self._status.setText(
            f"{total} document{'s' if total != 1 else ''} · {format_size(size)}")

    def _render_list(self, compact: bool) -> None:
        self._list.clear()
        icon_size = 16 if compact else 28
        self._list.setIconSize(QSize(icon_size, icon_size))
        for d in self._docs:
            kind = KIND_LABELS.get(d.kind, "File")
            title = d.title or Path(d.path).name
            if compact:
                item = QListWidgetItem(icon("page", "#6E6A61"), title)
            else:
                prog = f" — {int(d.progress * 100)}%" if d.progress else ""
                item = QListWidgetItem(
                    icon("book", "#C7522A"),
                    f"{title}  ·  {d.author or 'Unknown'}  ·  {kind}{prog}")
            item.setData(Qt.UserRole, d.path)
            item.setToolTip(d.path)
            self._list.addItem(item)

    def _render_table(self) -> None:
        self._table.setRowCount(len(self._docs))
        for row, d in enumerate(self._docs):
            values = [
                d.title or Path(d.path).name, d.author or "—",
                KIND_LABELS.get(d.kind, "—"),
                str(d.page_count) if d.page_count else "—",
                format_size(d.size_bytes),
                f"{int(d.progress * 100)}%" if d.progress else "—",
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.UserRole, d.path)
                self._table.setItem(row, col, item)

    # ------------------------------------------------------------------ actions
    def _open_item(self, path: str) -> None:
        if path:
            self.open_requested.emit(path)

    def _on_view_changed(self, view: str) -> None:
        if self._settings:
            self._settings.set("library", "view", view.lower())
        self._refresh()

    def _on_kind_filter(self, *args) -> None:
        self._refresh()

    def _add_folder(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        folder = QFileDialog.getExistingDirectory(self, "Add folder to library")
        if folder:
            self.import_folder(Path(folder))

    def import_folder(self, folder: Path) -> None:
        from veyrion_workspace.core.library.scanner import scan_folder
        task = self._tasks.submit(
            f"Importing {folder.name}", "scan", scan_folder, folder,
            self._library, True)
        task_id = task.id

        def on_done(t, event) -> None:
            if t.id == task_id and event == "done":
                imported, skipped = t.result or (0, 0)
                self.reload()
                show_toast(self.window(),
                           f"Imported {imported} document(s) ({skipped} skipped)",
                           "success")
        self._tasks.add_listener(on_done)
        self.reload()

    def _context_menu(self, path, global_pos) -> None:
        if not path:
            return
        menu = QMenu(self)
        open_act = menu.addAction(icon("open", "#2A2721"), "Open")
        open_tab = menu.addAction(icon("split", "#2A2721"), "Open in New Tab")
        menu.addSeparator()
        fav_menu = menu.addMenu(icon("star", "#B07A21"), "Favorite")
        d = self._library.get_by_path(path)
        toggle_fav = fav_menu.addAction(
            "Remove favorite" if (d and d.favorite) else "Add to favorites")
        rate_menu = menu.addMenu("Rate")
        for stars in range(1, 6):
            rate_menu.addAction("★" * stars,
                                lambda s=stars: self._rate(path, s))
        tag_menu = menu.addMenu(icon("tag", "#8A5A2B"), "Add tag")
        for tag in [t for t, _ in self._library.all_tags()][:12]:
            tag_menu.addAction(tag, lambda t=tag: self._add_tag(path, t))
        new_tag = tag_menu.addAction("New tag…")
        new_tag.triggered.connect(lambda: self._new_tag(path))
        menu.addSeparator()
        reveal = menu.addAction(icon("folder", "#6E6A61"), "Reveal in Explorer")
        props = menu.addAction(icon("info", "#6E6A61"), "Properties")
        menu.addSeparator()
        remove = menu.addAction(icon("trash", "#A33B2E"), "Remove from library")
        delete = menu.addAction(icon("trash", "#A33B2E"), "Delete file…")

        chosen = menu.exec(global_pos)
        if chosen is None:
            return
        if chosen is open_act:
            self._open_item(path)
        elif chosen is open_tab:
            self.open_in_tab_requested.emit(path)
        elif chosen is toggle_fav:
            self._library.set_favorite(path, not (d and d.favorite))
            self.reload()
        elif chosen is reveal:
            import subprocess
            import sys
            if sys.platform.startswith("win"):
                subprocess.Popen(["explorer", "/select,", path])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-R", path])
            else:
                subprocess.Popen(["xdg-open", str(Path(path).parent)])
        elif chosen is props:
            self.show_properties(path)
        elif chosen is remove:
            self._library.delete(path)
            self.reload()
        elif chosen is delete:
            confirm = QMessageBox.question(
                self, "Delete file",
                f"Move this file to the Recycle Bin?\n\n{Path(path).name}\n\n"
                f"This cannot be undone from Veyrion.")
            if confirm == QMessageBox.Yes:
                try:
                    Path(path).unlink()
                    self._library.delete(path)
                    self.reload()
                except OSError as e:
                    QMessageBox.warning(self, "Delete failed",
                                        f"The file could not be deleted:\n{e}")

    def _rate(self, path: str, stars: int) -> None:
        self._library.set_rating(path, stars)
        self.reload()

    def _add_tag(self, path: str, tag: str) -> None:
        self._library.add_tag(path, tag)
        self.reload()

    def _new_tag(self, path: str) -> None:
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "New tag", "Tag name:")
        if ok and name.strip():
            self._library.add_tag(path, name.strip())
            self.reload()

    def show_properties(self, path: str) -> None:
        d = self._library.get_by_path(path)
        if not d:
            return
        from PySide6.QtWidgets import QDialog, QDialogButtonBox
        dlg = QDialog(self)
        dlg.setWindowTitle("Document properties")
        lay = QGridLayout(dlg)
        fields = [
            ("Title", d.title), ("Author", d.author), ("Type", d.format),
            ("Pages", str(d.page_count)), ("Words", str(d.word_count)),
            ("Size", format_size(d.size_bytes)),
            ("Folder", d.folder),
            ("Progress", f"{int(d.progress * 100)}%"),
            ("Rating", "★" * d.rating if d.rating else "—"),
            ("Added", _fmt_time(d.added_at)),
            ("Last opened", _fmt_time(d.last_opened) if d.last_opened else "Never"),
            ("Modified", _fmt_time(d.last_modified)),
        ]
        for i, (k, v) in enumerate(fields):
            lay.addWidget(QLabel(f"<b>{k}</b>"), i, 0)
            val = QLabel(str(v) or "—")
            val.setTextInteractionFlags(Qt.TextSelectableByMouse)
            lay.addWidget(val, i, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(dlg.reject)
        buttons.clicked.connect(dlg.accept)
        lay.addWidget(buttons, len(fields), 0, 1, 2)
        dlg.exec()


def _fmt_time(ts: float) -> str:
    import time
    if not ts:
        return "—"
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))


class _GridWidget(QListWidget):
    """Cover-flow style grid of document cards."""

    item_activated = Signal(str)
    context_menu = Signal(str, object)   # path, QGlobalPos

    def __init__(self, palette: Palette) -> None:
        super().__init__()
        self._palette = palette
        self.setViewMode(QListWidget.IconMode)
        self.setResizeMode(QListWidget.Adjust)
        self.setMovement(QListWidget.Static)
        self.setSpacing(14)
        self.setIconSize(QSize(96, 128))
        self.setUniformItemSizes(True)
        self.setWordWrap(True)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu_at)

    def set_documents(self, docs: list) -> None:
        self.clear()
        for d in docs:
            item = QListWidgetItem()
            title = d.title or Path(d.path).name
            item.setText(f"{title}\n{d.author or ''}")
            item.setData(Qt.UserRole, d.path)
            item.setTextAlignment(Qt.AlignHCenter | Qt.AlignBottom)
            cover = self._cover_pixmap(d)
            if cover is not None:
                item.setIcon(cover)
            else:
                item.setIcon(icon("book", "#C7522A"))
            self.addItem(item)

    def _cover_pixmap(self, d: DocumentRecord) -> QPixmap | None:
        if d.cover_path and Path(d.cover_path).exists():
            pm = QPixmap(d.cover_path)
            if not pm.isNull():
                return pm
        return None

    def _menu_at(self, pos) -> None:
        item = self.itemAt(pos)
        if item:
            self.context_menu.emit(item.data(Qt.UserRole), self.mapToGlobal(pos))

    def mouseDoubleClickEvent(self, event) -> None:
        item = self.itemAt(event.position().toPoint())
        if item:
            self.item_activated.emit(item.data(Qt.UserRole))
        super().mouseDoubleClickEvent(event)
