"""Crash recovery and session journal.

The app writes a small journal file after every meaningful state change
(opened tabs, scroll position, zoom, dirty flags). On startup after an
unclean exit, the journal is detected and the session can be restored.
Journals are written atomically so a crash mid-write can never corrupt them.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

from omnireader_pro.utils.safeio import atomic_write_text

logger = logging.getLogger("omnireader.recovery")

JOURNAL_FILE = "session.json"
LOCK_FILE = "app.lock"


class SessionJournal:
    def __init__(self, sessions_dir: Path) -> None:
        self._dir = Path(sessions_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._journal = self._dir / JOURNAL_FILE
        self._lock = self._dir / LOCK_FILE
        self._clean_exit = False

    # -- process lock -------------------------------------------------------
    def acquire_lock(self) -> bool:
        """Single-instance guard. Returns False if another instance holds it."""
        try:
            if self._lock.exists():
                # Stale lock from a crashed session?
                try:
                    pid = int(self._lock.read_text().strip() or "0")
                except (ValueError, OSError):
                    pid = 0
                if pid and _pid_alive(pid):
                    return False
            self._lock.write_text(str(os.getpid()), encoding="utf-8")
            return True
        except OSError:
            return False

    def release_lock(self) -> None:
        try:
            self._lock.unlink(missing_ok=True)
        except OSError:
            pass

    # -- clean-exit detection -------------------------------------------------
    def mark_clean_exit(self) -> None:
        self._clean_exit = True
        try:
            if self._journal.exists():
                # Keep the journal but flag it clean so recovery isn't forced.
                state = self._read_journal()
                state["clean"] = True
                self._write_journal(state)
        except Exception:
            pass
        self.release_lock()

    def has_unsaved_session(self) -> bool:
        state = self._read_journal()
        if not state:
            return False
        if state.get("clean"):
            return False
        return bool(state.get("tabs"))

    def recoverable_tabs(self) -> list[dict]:
        state = self._read_journal()
        return state.get("tabs", []) if state else []

    # -- journal writing --------------------------------------------------------
    def record(self, tabs: list[dict], active_tab: int = -1) -> None:
        state = {"clean": False, "time": time.time(), "active_tab": active_tab,
                 "tabs": tabs}
        self._write_journal(state)

    def clear(self) -> None:
        try:
            self._journal.unlink(missing_ok=True)
        except OSError:
            pass

    # -- internals ------------------------------------------------------------
    def _read_journal(self) -> dict:
        try:
            if not self._journal.exists():
                return {}
            return json.loads(self._journal.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _write_journal(self, state: dict) -> None:
        try:
            atomic_write_text(self._journal, json.dumps(state, indent=1))
        except OSError:
            logger.warning("could not write session journal")


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        if os.name == "nt":
            import ctypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            handle = kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if handle:
                kernel32.CloseHandle(handle)
                return True
            return False
        os.kill(pid, 0)
        return True
    except (OSError, AttributeError):
        return False
