"""Application data locations, resolved per operating system.

Everything the app writes lives under one managed root per platform so
documents never get scattered and users can find and clear their data.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from omnireader_pro import APP_NAME


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_data_root() -> Path:
    """Root directory for all writable app data."""
    env = os.environ.get("OMNIREADER_DATA_DIR")
    if env:
        return Path(env).resolve()
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
        return base / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    xdg = os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
    return Path(xdg) / APP_NAME


def settings_dir() -> Path:
    return app_data_root() / "settings"


def database_dir() -> Path:
    return app_data_root() / "database"


def cache_dir() -> Path:
    return app_data_root() / "cache"


def logs_dir() -> Path:
    return app_data_root() / "logs"


def backups_dir() -> Path:
    return app_data_root() / "backups"


def plugins_dir() -> Path:
    return app_data_root() / "plugins"


def temp_dir() -> Path:
    return app_data_root() / "tmp"


def sessions_dir() -> Path:
    return app_data_root() / "sessions"


def notes_dir() -> Path:
    return app_data_root() / "notes"


def vault_dir() -> Path:
    return app_data_root() / "vault"


def all_dirs() -> list[Path]:
    return [
        settings_dir(), database_dir(), cache_dir(), logs_dir(), backups_dir(),
        plugins_dir(), temp_dir(), sessions_dir(), notes_dir(), vault_dir(),
    ]


def ensure_all() -> None:
    for d in all_dirs():
        d.mkdir(parents=True, exist_ok=True)
