"""Filesystem safety helpers shared by every subsystem.

Every path that originates from user input, document contents, archives, or
plugins passes through :func:`validate_path` before touching the disk.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path, PureWindowsPath

# Extensions the application can genuinely open.
SUPPORTED_EXTENSIONS: dict[str, str] = {
    ".pdf": "PDF Document",
    ".epub": "EPUB E-book",
    ".mobi": "Mobipocket E-book",
    ".azw": "Kindle E-book",
    ".azw3": "Kindle E-book",
    ".djvu": "DjVu Document",
    ".cbz": "Comic Book Zip",
    ".cbr": "Comic Book Rar",
    ".xps": "XPS Document",
    ".oxps": "XPS Document",
    ".chm": "Compiled HTML Help",
    ".docx": "Word Document",
    ".doc": "Word Document (legacy)",
    ".odt": "OpenDocument Text",
    ".rtf": "Rich Text",
    ".txt": "Plain Text",
    ".md": "Markdown",
    ".markdown": "Markdown",
    ".html": "HTML",
    ".htm": "HTML",
    ".xml": "XML",
    ".csv": "CSV Data",
    ".tsv": "TSV Data",
    ".json": "JSON Data",
    ".svg": "SVG Image",
    ".png": "PNG Image",
    ".jpg": "JPEG Image",
    ".jpeg": "JPEG Image",
    ".webp": "WebP Image",
    ".bmp": "Bitmap Image",
    ".tif": "TIFF Image",
    ".tiff": "TIFF Image",
    ".gif": "GIF Image",
    ".pptx": "PowerPoint Presentation",
    ".xlsx": "Excel Workbook",
    ".log": "Log File",
}

EXECUTABLE_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".com", ".scr", ".pif", ".msi", ".vbs", ".ps1",
    ".js", ".jse", ".wsf", ".wsh", ".hta", ".cpl", ".jar", ".sh", ".dll", ".lnk",
}

_WIN_RESERVED = re.compile(
    r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?$", re.IGNORECASE
)
_INVALID_NAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

MAX_ARCHIVE_RATIO = 200          # zip-bomb guard
MAX_ARCHIVE_TOTAL_MB = 2048      # decompressed size cap
MAX_ARCHIVE_DEPTH = 4            # nested archive cap


class PathSafetyError(ValueError):
    """Raised when a path fails validation."""


def validate_path(
    path: str | Path,
    *,
    must_exist: bool = False,
    allow_missing_parent: bool = True,
) -> Path:
    """Normalize and validate a filesystem path.

    Raises :class:`PathSafetyError` for empty paths, null bytes, Windows
    device names, or paths that try to escape their intended root.
    """
    if path is None:
        raise PathSafetyError("Empty path")
    raw = str(path)
    if "\x00" in raw:
        raise PathSafetyError("Path contains null bytes")
    raw = raw.strip()
    if not raw:
        raise PathSafetyError("Empty path")

    p = Path(os.path.expanduser(raw))

    if _looks_like_windows_device(p.name):
        raise PathSafetyError(f"Reserved device name not allowed: {p.name}")

    if must_exist and not p.exists():
        raise PathSafetyError(f"Path does not exist: {p.name}")
    if not allow_missing_parent:
        if not p.parent.exists():
            raise PathSafetyError(f"Parent folder does not exist: {p.parent.name}")
    return p


def _looks_like_windows_device(name: str) -> bool:
    if not sys.platform.startswith("win") and not PureWindowsPath(name).name == name:
        pass
    return bool(_WIN_RESERVED.match(name))


def is_executable_extension(ext: str) -> bool:
    return ext.lower() in EXECUTABLE_EXTENSIONS


def safe_filename(name: str, fallback: str = "file") -> str:
    """Sanitize an untrusted filename for use on disk."""
    name = _INVALID_NAME_CHARS.sub("_", str(name)).strip(" .")
    if not name:
        name = fallback
    if _WIN_RESERVED.match(name):
        name = "_" + name
    return name[:180]


def ensure_within(child: str | Path, parent: str | Path) -> Path:
    """Return ``child`` resolved, raising if it escapes ``parent``."""
    parent_p = Path(parent).resolve()
    child_p = Path(child)
    if not child_p.is_absolute():
        child_p = parent_p / child_p
    resolved = child_p.resolve()
    try:
        resolved.relative_to(parent_p)
    except ValueError as exc:
        raise PathSafetyError(
            f"Path escapes allowed directory: {resolved.name}"
        ) from exc
    return resolved


def unique_path(directory: Path, stem: str, suffix: str) -> Path:
    """Find a non-colliding path in ``directory`` like ``stem (2).ext``."""
    directory.mkdir(parents=True, exist_ok=True)
    candidate = directory / f"{stem}{suffix}"
    n = 2
    while candidate.exists():
        candidate = directory / f"{stem} ({n}){suffix}"
        n += 1
    return candidate


def format_size(num: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num < 1024 or unit == "TB":
            return f"{num:.0f} {unit}" if unit == "B" else f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} TB"


def detect_kind(path: Path) -> str:
    """Broad category used by the library and smart collections."""
    ext = path.suffix.lower()
    if ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif", ".svg"):
        return "image"
    if ext in (".cbz", ".cbr"):
        return "comic"
    if ext in (".epub", ".mobi", ".azw", ".azw3"):
        return "ebook"
    if ext == ".pdf":
        return "pdf"
    if ext in (".docx", ".doc", ".odt", ".rtf", ".pptx", ".xlsx"):
        return "office"
    if ext in (".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".xml", ".log"):
        return "text"
    if ext in (".html", ".htm"):
        return "web"
    return "other"
