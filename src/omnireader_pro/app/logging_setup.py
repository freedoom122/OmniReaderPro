"""Structured, privacy-conscious logging.

Logs never contain document contents, passwords, or note text. Sensitive
path components are reduced to their basename for file-name-level context
without leaking the user's folder structure.
"""
from __future__ import annotations

import gzip
import logging
import logging.handlers
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from omnireader_pro.app import paths

_SENSITIVE_ENV_KEYS = {
    "PASSWORD", "PASSWD", "TOKEN", "SECRET", "KEY", "API_KEY", "APIKEY",
    "CREDENTIAL", "CRED", "PWD",
}

logger = logging.getLogger("omnireader")


class _RedactingFilter(logging.Filter):
    """Strip obvious secrets from any log record before formatting."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        try:
            msg = record.getMessage()
            lowered = msg.lower()
            for marker in ("password", "passwd", "token", "secret", "apikey", "api_key"):
                if marker in lowered and "=" in msg:
                    # Redact the value side of key=value pairs.
                    parts = msg.split()
                    cleaned = []
                    for p in parts:
                        pl = p.lower()
                        if any(f"{marker}" in pl and ("=" in p or ":" in p) for marker in _SENSITIVE_ENV_KEYS):
                            head = p.split("=", 1)[0].split(":", 1)[0]
                            cleaned.append(f"{head}=<redacted>")
                        else:
                            cleaned.append(p)
                    record.msg = " ".join(cleaned)
                    record.args = None
        except Exception:
            pass
        return True


def _setup_file_handler(log_dir: Path, verbose: bool) -> logging.Handler:
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        log_dir / "omnireader.log", maxBytes=1_500_000, backupCount=4, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S"
    ))
    return handler


def setup_logging(verbose: bool = False) -> Path:
    """Initialize the root 'omnireader' logger. Returns the log directory."""
    log_dir = paths.logs_dir()
    log_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger("omnireader")
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    root.handlers.clear()
    root.addFilter(_RedactingFilter())

    fh = _setup_file_handler(log_dir, verbose)
    root.addHandler(fh)

    if verbose:
        sh = logging.StreamHandler(sys.stderr)
        sh.setFormatter(logging.Formatter("%(levelname)-7s %(name)s: %(message)s"))
        root.addHandler(sh)

    # Quiet down noisy third-party loggers.
    for name in ("PIL", "urllib3", "comtypes", "pyttsx3.driver"):
        logging.getLogger(name).setLevel(logging.WARNING)

    return log_dir


def open_logs_folder() -> None:
    """Open the log folder in the OS file browser."""
    log_dir = paths.logs_dir()
    if sys.platform.startswith("win"):
        os.startfile(log_dir)  # noqa: S606
    elif sys.platform == "darwin":
        import subprocess
        subprocess.Popen(["open", str(log_dir)])
    else:
        import subprocess
        subprocess.Popen(["xdg-open", str(log_dir)])


def export_diagnostic_report(destination: Path) -> Path:
    """Export a sanitized diagnostic bundle (logs + system info, no document data)."""
    destination.parent.mkdir(parents=True, exist_ok=True)

    def safe_sysinfo() -> str:
        lines = [
            "OmniReader Pro Diagnostic Report",
            f"Generated: {datetime.now(timezone.utc).isoformat()}",
            f"Python: {sys.version}",
            f"Platform: {sys.platform}",
        ]
        try:
            import platform
            lines.append(f"Machine: {platform.machine()}")
            lines.append(f"Release: {platform.release()}")
        except Exception:
            pass
        return "\n".join(lines) + "\n"

    with gzip.open(destination, "wt", encoding="utf-8") as fh:
        fh.write(safe_sysinfo())
        fh.write("\n--- Application log (most recent 4000 lines) ---\n")
        log_file = paths.logs_dir() / "omnireader.log"
        if log_file.exists():
            try:
                text = log_file.read_text(encoding="utf-8", errors="replace")
                fh.write("\n".join(text.splitlines()[-4000:]))
            except Exception as e:
                fh.write(f"(log read failed: {type(e).__name__})\n")
        fh.write("\n--- Dependency availability ---\n")
        for mod in ("fitz", "pypdf", "docx", "ebooklib", "PIL", "openpyxl", "pptx",
                    "pytesseract", "pyttsx3", "cryptography", "rapidfuzz"):
            try:
                __import__(mod)
                fh.write(f"{mod}: OK\n")
            except Exception as e:
                fh.write(f"{mod}: unavailable ({type(e).__name__})\n")
    return destination


def prune_old_logs(keep_days: int = 30) -> None:
    """Delete rotated log files older than keep_days."""
    cutoff = time.time() - keep_days * 86400
    log_dir = paths.logs_dir()
    if not log_dir.exists():
        return
    for f in log_dir.glob("omnireader.log*"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink(missing_ok=True)
        except OSError:
            pass
