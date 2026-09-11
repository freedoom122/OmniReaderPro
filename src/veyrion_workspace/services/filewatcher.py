"""File watcher: keeps the library in sync with watched folders.

Uses a polling scanner (no OS-specific dependencies, works on locked-down
systems) that runs on a background thread with a configurable interval.
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from veyrion_workspace.utils.pathutils import SUPPORTED_EXTENSIONS

logger = logging.getLogger("veyrion.watcher")


class FolderWatcher:
    def __init__(self, folders: list[str], interval: float = 20.0,
                 on_new=None, on_changed=None) -> None:
        self._folders = [Path(f) for f in folders]
        self._interval = interval
        self._on_new = on_new
        self._on_changed = on_changed
        self._snapshot: dict[str, tuple[float, int]] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="or-watcher",
                                        daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    def set_folders(self, folders: list[str]) -> None:
        self._folders = [Path(f) for f in folders]
        self._snapshot.clear()

    def scan_once(self) -> tuple[list[Path], list[Path]]:
        """One manual scan; returns (new_files, changed_files)."""
        current: dict[str, tuple[float, int]] = {}
        for folder in self._folders:
            if not folder.exists() or not folder.is_dir():
                continue
            try:
                for entry in folder.rglob("*"):
                    if not entry.is_file():
                        continue
                    if entry.suffix.lower() not in SUPPORTED_EXTENSIONS:
                        continue
                    try:
                        stat = entry.stat()
                        current[str(entry)] = (stat.st_mtime, stat.st_size)
                    except OSError:
                        continue
            except OSError:
                continue
        new_files = [Path(p) for p in current if p not in self._snapshot]
        changed = [Path(p) for p in current
                   if p in self._snapshot and current[p] != self._snapshot[p]]
        self._snapshot = current
        return new_files, changed

    def _loop(self) -> None:
        # Prime the snapshot without firing callbacks at startup.
        self.scan_once()
        while not self._stop.wait(self._interval):
            try:
                new_files, changed = self.scan_once()
            except Exception:
                logger.exception("watcher scan failed")
                continue
            for f in new_files:
                if self._on_new:
                    try:
                        self._on_new(f)
                    except Exception:
                        logger.exception("on_new callback failed")
            for f in changed:
                if self._on_changed:
                    try:
                        self._on_changed(f)
                    except Exception:
                        logger.exception("on_changed callback failed")
