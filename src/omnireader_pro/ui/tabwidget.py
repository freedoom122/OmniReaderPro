"""Multi-tab workspace: draggable tabs with pinning, restore-closed,
close-others, close-to-right, duplicate, and per-tab state preservation."""
from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QMenu, QTabBar, QTabWidget, QVBoxLayout, QWidget,
)

from omnireader_pro.ui.icons import icon


@dataclass
class TabState:
    path: str = ""
    view: QWidget | None = None
    pinned: bool = False
    state: dict = field(default_factory=dict)


class DocumentTabWidget(QTabWidget):
    """Tab container with document-aware context menu behavior."""

    tab_close_requested = Signal(int)
    tab_detach_requested = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setTabsClosable(True)
        self.setMovable(True)
        self.setDocumentMode(True)
        self.setTabBarAutoHide(False)
        bar = self.tabBar()
        bar.setContextMenuPolicy(Qt.CustomContextMenu)
        bar.customContextMenuRequested.connect(self._context_menu)
        bar.tabBarDoubleClicked = getattr(bar, 'tabBarDoubleClicked', None)
        if hasattr(bar, 'tabBarDoubleClicked'):
            bar.tabBarDoubleClicked.connect(
                lambda idx: self.tab_detach_requested.emit(idx))
        self.tabCloseRequested.connect(self._on_close_requested)
        self._closed_stack: list[tuple[str, dict]] = []

    # -- helpers -----------------------------------------------------------
    def find_tab_by_path(self, path: str) -> int:
        path_lower = str(path).lower()
        for i in range(self.count()):
            view = self.widget(i)
            if view is not None and str(getattr(view, "path", "")).lower() == path_lower:
                return i
        return -1

    def pin_state(self, index: int) -> bool:
        view = self.widget(index)
        return bool(getattr(view, "_pinned", False))

    def set_pinned(self, index: int, pinned: bool) -> None:
        view = self.widget(index)
        if view is None:
            return
        view._pinned = pinned
        self.setTabText(index, ("📌 " if pinned else "") + self.tabText(index).replace("📌 ", ""))

    def _on_close_requested(self, index: int) -> None:
        view = self.widget(index)
        if view is not None and getattr(view, "_pinned", False):
            return  # pinned tabs are protected
        self._remember_closed(index)
        self.tab_close_requested.emit(index)

    def _remember_closed(self, index: int) -> None:
        view = self.widget(index)
        if view is not None:
            try:
                state = view.save_state()
            except Exception:
                state = {}
            self._closed_stack.append(
                (str(getattr(view, "path", "")), state))
            if len(self._closed_stack) > 20:
                self._closed_stack.pop(0)

    def pop_last_closed(self) -> tuple[str, dict] | None:
        if self._closed_stack:
            return self._closed_stack.pop()
        return None

    def _context_menu(self, pos) -> None:
        bar = self.tabBar()
        index = bar.tabAt(pos)
        if index < 0:
            return
        menu = QMenu(self)
        pin = menu.addAction("Pin tab" if not self.pin_state(index) else "Unpin tab")
        dup = menu.addAction("Duplicate tab")
        detach = menu.addAction("Detach to window")
        menu.addSeparator()
        close = menu.addAction("Close")
        close_others = menu.addAction("Close others")
        close_right = menu.addAction("Close tabs to the right")
        chosen = menu.exec(bar.mapToGlobal(pos))
        if chosen is None:
            return
        if chosen is pin:
            self.set_pinned(index, not self.pin_state(index))
        elif chosen is dup:
            self.tab_detach_requested.emit(-1)  # main window handles duplicate
            view = self.widget(index)
            if view is not None:
                self.window().reopen_path(str(getattr(view, "path", "")))
        elif chosen is detach:
            self.tab_detach_requested.emit(index)
        elif chosen is close:
            self._on_close_requested(index)
        elif chosen is close_others:
            for i in range(self.count() - 1, -1, -1):
                if i != index and not self.pin_state(i):
                    self._remember_closed(i)
                    self.tab_close_requested.emit(i)
        elif chosen is close_right:
            for i in range(self.count() - 1, index, -1):
                if not self.pin_state(i):
                    self._remember_closed(i)
                    self.tab_close_requested.emit(i)
