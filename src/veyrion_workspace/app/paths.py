"""Application data locations, resolved per operating system.

Everything the app writes lives under one managed root per platform so
documents never get scattered and users can find and clear their data.

A one-time migration lifts data written by the application's former name
into the current root, so upgrading across the rebrand keeps the library,
settings, vault, and session journal intact.
"""
from __future__ import annotations

import logging
import os
import shutil
import sys
from pathlib import Path

from veyrion_workspace import (
    CURRENT_FILE_PREFIX,
    DATA_DIR_NAME,
    LEGACY_DATA_DIR_NAMES,
    LEGACY_FILE_PREFIX,
)

logger = logging.getLogger("veyrion.paths")

# Subdirectories worth migrating. Caches and temp files are deliberately
# excluded: they are derived data, and copying a large thumbnail cache would
# stall the first launch for no benefit.
_MIGRATE_SUBDIRS = (
    "settings", "database", "notes", "vault", "sessions", "backups", "plugins",
)

_migration_attempted = False


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _root_for(name: str) -> Path:
    """Application-data root for an arbitrary application folder name."""
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
        return base / name
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / name
    xdg = os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
    return Path(xdg) / name


def app_data_root() -> Path:
    """Root directory for all writable app data."""
    env = os.environ.get("VEYRION_DATA_DIR")
    if env:
        return Path(env).resolve()
    return _root_for(DATA_DIR_NAME)


def legacy_data_root() -> Path | None:
    """The pre-rebrand data root, if one exists on this machine."""
    for name in LEGACY_DATA_DIR_NAMES:
        candidate = _root_for(name)
        if candidate.is_dir():
            return candidate
    return None


def _rename_legacy_files(root: Path) -> int:
    """Rename ``omnireader.*`` files inside a migrated tree to ``veyrion.*``."""
    renamed = 0
    for path in list(root.rglob(f"{LEGACY_FILE_PREFIX}*")):
        if not path.is_file():
            continue
        new_name = CURRENT_FILE_PREFIX + path.name[len(LEGACY_FILE_PREFIX):]
        target = path.with_name(new_name)
        try:
            path.rename(target)
            renamed += 1
        except OSError:
            logger.warning("could not rename %s -> %s", path, target)
    return renamed


def migrate_legacy_data() -> Path | None:
    """Copy a previous-name workspace into the current data root, once.

    Returns the newly populated root when a migration happened, else ``None``.
    The original directory is intentionally left in place: the app never
    deletes user data it did not create in this session, and a failed copy is
    rolled back so a half-written workspace can never be presented as valid.
    """
    global _migration_attempted
    if _migration_attempted:
        return None
    _migration_attempted = True

    # An explicit data dir means a caller (tests, portable install) is in
    # control of layout; never second-guess it.
    if os.environ.get("VEYRION_DATA_DIR"):
        return None

    target = app_data_root()
    if target.exists():
        return None

    legacy = legacy_data_root()
    if legacy is None:
        return None

    logger.info("migrating existing data from %s", legacy)
    try:
        target.mkdir(parents=True, exist_ok=True)
        for sub in _MIGRATE_SUBDIRS:
            source = legacy / sub
            if source.is_dir():
                shutil.copytree(source, target / sub, dirs_exist_ok=True)
        _rename_legacy_files(target)
    except Exception:
        logger.exception("data migration failed; starting with a clean workspace")
        shutil.rmtree(target, ignore_errors=True)
        return None

    logger.info("data migration complete")
    return target


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
    migrate_legacy_data()
    for d in all_dirs():
        d.mkdir(parents=True, exist_ok=True)
