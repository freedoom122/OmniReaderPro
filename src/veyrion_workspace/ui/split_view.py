"""Split view: two documents side by side with optional synchronized scrolling.

Accessed from the View menu or the command palette ("Split View"). Any
combination of documents works, including the same document twice.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QSplitter, QToolButton,
    QVBoxLayout, QWidget,
)

from veyrion_workspace.ui.document_view import DocumentView
from veyrion_workspace.ui.icons import icon


class SplitView(QWidget):
    """Hosts two DocumentViews with sync-scroll and swap support."""

    close_requested = Signal()

    def __init__(self, left_view: DocumentView | None,
                 right_view: DocumentView | None,
                 horizontal: bool = True, parent=None) -> None:
        super().__init__(parent)
        self._horizontal = horizontal
        self._sync = False
        self._left_view: DocumentView | None = None
        self._right_view: DocumentView | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Control bar
        bar = QHBoxLayout()
        bar.setContentsMargins(6, 3, 6, 3)
        self._left_combo = QComboBox()
        self._right_combo = QComboBox()
        self._left_combo.setMinimumWidth(200)
        self._right_combo.setMinimumWidth(200)
        self._sync_btn = QToolButton()
        self._sync_btn.setText("Sync scroll")
        self._sync_btn.setCheckable(True)
        self._sync_btn.toggled.connect(self._on_sync_toggled)
        swap_btn = QToolButton()
        swap_btn.setIcon(icon("compare", "#2A2721"))
        swap_btn.setToolTip("Swap panes")
        swap_btn.clicked.connect(self._swap)
        close_btn = QToolButton()
        close_btn.setIcon(icon("close", "#2A2721"))
        close_btn.setToolTip("Close split view")
        close_btn.clicked.connect(self.close_requested.emit)
        bar.addWidget(QLabel("Left:"))
        bar.addWidget(self._left_combo, 1)
        bar.addWidget(QLabel("Right:"))
        bar.addWidget(self._right_combo, 1)
        bar.addWidget(self._sync_btn)
        bar.addWidget(swap_btn)
        bar.addWidget(close_btn)
        lay.addLayout(bar)

        # Panes
        self._splitter = QSplitter()
        self._splitter.setChildrenCollapsible(True)
        if horizontal:
            self._splitter.setOrientation(Qt.Horizontal)
        else:
            self._splitter.setOrientation(Qt.Vertical)
        self._left_holder = QFrame()
        self._right_holder = QFrame()
        self._splitter.addWidget(self._left_holder)
        self._splitter.addWidget(self._right_holder)
        self._splitter.setSizes([500, 500])
        lay.addWidget(self._splitter, 1)

        self._panes = [self._left_holder, self._right_holder]
        self.set_left(left_view)
        self.set_right(right_view)

    # ------------------------------------------------------------------ panes
    def set_left(self, view: DocumentView | None) -> None:
        self._set_pane(0, view)
        self._left_view = view

    def set_right(self, view: DocumentView | None) -> None:
        self._set_pane(1, view)
        self._right_view = view

    def _set_pane(self, idx: int, view: DocumentView | None) -> None:
        holder = self._panes[idx]
        # Clear existing content
        old_lay = holder.layout()
        if old_lay is not None:
            while old_lay.count():
                item = old_lay.takeAt(0)
                w = item.widget()
                if w is not None:
                    w.setParent(None)
            holder.setLayout(None)
        lay = QVBoxLayout(holder)
        lay.setContentsMargins(0, 0, 0, 0)
        if view is not None:
            lay.addWidget(view)
            view.show()
            if view.is_modified:
                from veyrion_workspace.ui.widgets import show_toast
                show_toast(self.window(), f"{view.display_name} has unsaved "
                                          f"changes — Save first", "warning")
        else:
            label = QLabel("Empty pane — open a document into this side")
            label.setAlignment(Qt.AlignCenter)
            label.setObjectName("dimLabel")
            lay.addWidget(label)

    def views(self) -> list[DocumentView | None]:
        return [self._left_view, self._right_view]

    def populate_combos(self, views: list[DocumentView]) -> None:
        """Fill the dropdowns with all open documents."""
        for combo in (self._left_combo, self._right_combo):
            combo.blockSignals(True)
            combo.clear()
            for v in views:
                combo.addItem(v.display_name, v)
            combo.blockSignals(False)
        if self._left_view is not None:
            self._left_combo.setCurrentIndex(
                max(0, self._left_combo.findData(self._left_view)))
        if self._right_view is not None:
            self._right_combo.setCurrentIndex(
                max(0, self._right_combo.findData(self._right_view)))

    def _swap(self) -> None:
        left, right = self._left_view, self._right_view
        self.set_left(right)
        self.set_right(left)

    def _on_sync_toggled(self, on: bool) -> None:
        self._sync = on

    def set_sync(self, on: bool) -> None:
        self._sync_btn.setChecked(on)

    @property
    def synced(self) -> bool:
        return self._sync

    def sync_pages(self) -> None:
        """Align both panes to the same page (for comparison reading)."""
        if self._left_view is not None and self._right_view is not None:
            page = max(self._left_view.current_page,
                       self._right_view.current_page)
            self._left_view.go_to_page(page)
            self._right_view.go_to_page(page)