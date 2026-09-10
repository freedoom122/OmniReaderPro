"""Optional update checking.

Off by default. When enabled, the check is manual (Settings > Updates or
the command palette) and only reports whether a newer version exists —
it never downloads or installs anything by itself. No silent executables,
no background requests.
"""
from __future__ import annotations

import json
import logging
import urllib.request
from pathlib import Path

from omnireader_pro import __version__

logger = logging.getLogger("omnireader.updates")

UPDATE_MANIFEST_URL = "https://api.github.com/repos/omnireader-pro/omnireader-pro/releases/latest"


def check_for_update(timeout: int = 10) -> dict:
    """Query the release manifest. Returns a status dict (never raises)."""
    try:
        req = urllib.request.Request(
            UPDATE_MANIFEST_URL,
            headers={"Accept": "application/vnd.github+json",
                     "User-Agent": f"OmniReaderPro/{__version__}"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        latest = str(data.get("tag_name", "")).lstrip("v")
        return {
            "available": _version_tuple(latest) > _version_tuple(__version__),
            "latest": latest,
            "current": __version__,
            "url": data.get("html_url", ""),
            "notes": (data.get("body") or "")[:400],
        }
    except Exception as e:
        logger.debug("update check failed: %s", e)
        return {"available": False, "latest": "", "current": __version__,
                "url": "", "notes": "", "error": str(e)}


def _version_tuple(v: str) -> tuple:
    parts = []
    for chunk in str(v).replace("-", ".").split("."):
        if chunk.isdigit():
            parts.append(int(chunk))
        else:
            parts.append(0)
    return tuple(parts[:3])


def run_update_check_dialog(parent) -> None:
    """Manual, user-visible update check with honest result display."""
    from PySide6.QtWidgets import QMessageBox
    result = check_for_update()
    if result.get("error"):
        QMessageBox.information(
            parent, "Update check",
            "Could not reach the update server. OmniReader works fully "
            "offline; this is optional.")
        return
    if result["available"]:
        box = QMessageBox(parent)
        box.setWindowTitle("Update available")
        box.setText(f"Version {result['latest']} is available "
                    f"(you have {result['current']}).")
        box.setInformativeText(
            "OmniReader never downloads or installs updates on its own. "
            "Open the release page to review the changelog and download "
            "manually.")
        box.addButton("Open release page", QMessageBox.AcceptRole)
        box.addButton("Later", QMessageBox.RejectRole)
        box.exec()
        if box.buttonRole(box.clickedButton()) == QMessageBox.AcceptRole:
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl(result["url"]))
    else:
        QMessageBox.information(
            parent, "Update check",
            f"You are on the latest version ({result['current']}).")