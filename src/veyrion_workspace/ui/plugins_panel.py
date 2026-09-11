"""Plugins manager dialog.

Shows every discovered plugin with its declared permissions, lets the user
approve (or revoke) each one, and reports load errors honestly. Invalid
plugins are listed as invalid, never crash the app.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout,
    QWidget,
)

from veyrion_workspace.core.plugins.host import PERMISSIONS, PluginHost


class PluginsDialog(QDialog):
    def __init__(self, parent, host: PluginHost) -> None:
        super().__init__(parent)
        self.setWindowTitle("Plugins")
        self.setMinimumSize(560, 460)
        self.host = host
        lay = QVBoxLayout(self)

        self._list = QListWidget()
        self._list.currentItemChanged.connect(self._show_details)
        lay.addWidget(self._list, 1)

        self._details = QLabel("")
        self._details.setWordWrap(True)
        self._details.setObjectName("dimLabel")
        self._details.setMinimumHeight(120)
        self._details.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        lay.addWidget(self._details)

        row = QHBoxLayout()
        self._approve_btn = QPushButton("Approve & load")
        self._approve_btn.setObjectName("accentButton")
        self._approve_btn.clicked.connect(self._approve)
        self._revoke_btn = QPushButton("Revoke")
        self._revoke_btn.clicked.connect(self._revoke)
        self._install_btn = QPushButton("Install plugin folder…")
        self._install_btn.clicked.connect(self._install)
        row.addWidget(self._install_btn)
        row.addStretch(1)
        row.addWidget(self._revoke_btn)
        row.addWidget(self._approve_btn)
        lay.addLayout(row)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.clicked.connect(self.accept)
        lay.addWidget(buttons)
        self.reload()

    def reload(self) -> None:
        self._list.clear()
        self._plugins = self.host.discover()
        for p in self._plugins:
            status = "✓ approved" if p["approved"] else "— not approved"
            if p.get("error"):
                status = "✗ invalid"
            item = QListWidgetItem(f"{p['name']}  v{p['version']}  ·  {status}")
            item.setData(Qt.UserRole, p)
            self._list.addItem(item)
        if self._plugins:
            self._list.setCurrentRow(0)

    def _show_details(self, current, previous) -> None:
        if current is None:
            return
        p = current.data(Qt.UserRole)
        perm_lines = "\n".join(
            f"  • {PERMISSIONS.get(perm, perm)}" for perm in p["permissions"])
        if p.get("error"):
            self._details.setText(
                f"<b>{p['name']}</b> — INVALID<br>{p['error']}")
            self._approve_btn.setEnabled(False)
            return
        self._approve_btn.setEnabled(True)
        self._details.setText(
            f"<b>{p['name']}</b> v{p['version']} by {p['author'] or 'unknown'}"
            f"<br>{p['description']}<br><br>"
            f"<b>Declared permissions:</b><br>{perm_lines or 'none'}<br><br>"
            f"Plugins are untrusted code. Approve only plugins you trust — "
            f"permissions are enforced by the host facade.")

    def _approve(self) -> None:
        item = self._list.currentItem()
        if item is None:
            return
        p = item.data(Qt.UserRole)
        if p.get("error"):
            return
        if not p["permissions"]:
            confirm = QMessageBox.question(
                self, "Load plugin",
                f"Load '{p['name']}'? It declares no permissions.")
            if confirm != QMessageBox.Yes:
                return
        self.host.approve(p["id"])
        try:
            self.host.load_plugin(p["id"])
            QMessageBox.information(
                self, "Plugin loaded",
                f"'{p['name']}' loaded successfully.")
        except Exception as e:
            self.host.revoke(p["id"])
            QMessageBox.warning(
                self, "Plugin failed to load",
                f"'{p['name']}' was disabled:\n\n{e}")
        self.reload()

    def _revoke(self) -> None:
        item = self._list.currentItem()
        if item is None:
            return
        p = item.data(Qt.UserRole)
        self.host.revoke(p["id"])
        self.reload()

    def _install(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Choose a plugin folder (contains plugin.json)")
        if not folder:
            return
        import shutil
        src = Path(folder)
        target = self.host.installed_plugin_path() / src.name
        if target.exists():
            QMessageBox.information(
                self, "Already installed",
                f"A plugin named '{src.name}' is already installed. "
                f"Replace it? Remove the old folder first.")
            return
        shutil.copytree(src, target)
        self.reload()