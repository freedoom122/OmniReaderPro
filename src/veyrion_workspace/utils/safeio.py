"""Safe file operations: atomic writes, guarded archive extraction, secure delete."""
from __future__ import annotations

import logging
import os
import secrets
import shutil
import stat
import tempfile
import threading
import time
import zipfile
from pathlib import Path

from veyrion_workspace.utils.pathutils import (
    MAX_ARCHIVE_DEPTH,
    MAX_ARCHIVE_RATIO,
    MAX_ARCHIVE_TOTAL_MB,
    PathSafetyError,
    ensure_within,
    safe_filename,
)

logger = logging.getLogger("veyrion.safeio")

_registered_temps: list[Path] = []
_temps_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Atomic writes
# ---------------------------------------------------------------------------
def atomic_write_bytes(target: Path, data: bytes, *, fsync: bool = True) -> None:
    """Write ``data`` to ``target`` atomically; the original survives failure."""
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent)
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            if fsync:
                fh.flush()
                os.fsync(fh.fileno())
        os.replace(tmp, target)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def atomic_write_text(target: Path, text: str, encoding: str = "utf-8") -> None:
    atomic_write_bytes(target, text.encode(encoding))


def atomic_copy(src: Path, dst: Path) -> None:
    """Copy ``src`` to ``dst`` via a temp file so ``dst`` is never half-written."""
    src, dst = Path(src), Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{dst.name}.", suffix=".tmp", dir=str(dst.parent))
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        shutil.copyfile(src, tmp)
        os.replace(tmp, dst)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


# ---------------------------------------------------------------------------
# Controlled temporary files
# ---------------------------------------------------------------------------
def make_temp_file(suffix: str = "", prefix: str = "or_", in_app_temp: bool = True) -> Path:
    """Create a temp file inside the app's controlled temp dir (or system temp)."""
    from veyrion_workspace.app import paths

    directory = paths.temp_dir() if in_app_temp else None
    if in_app_temp:
        directory.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(suffix=suffix, prefix=prefix, dir=directory)
    os.close(fd)
    p = Path(name)
    with _temps_lock:
        _registered_temps.append(p)
    return p


def make_temp_dir(prefix: str = "or_") -> Path:
    from veyrion_workspace.app import paths
    paths.temp_dir().mkdir(parents=True, exist_ok=True)
    d = Path(tempfile.mkdtemp(prefix=prefix, dir=str(paths.temp_dir())))
    with _temps_lock:
        _registered_temps.append(d)
    return d


def cleanup_temps(max_age_hours: float | None = None) -> int:
    """Remove registered temp files (or stale ones older than max_age_hours)."""
    from veyrion_workspace.app import paths
    removed = 0
    now = time.time()
    tdir = paths.temp_dir()
    if tdir.exists():
        for entry in tdir.iterdir():
            try:
                if max_age_hours is None or now - entry.stat().st_mtime > max_age_hours * 3600:
                    if entry.is_dir():
                        shutil.rmtree(entry, ignore_errors=True)
                    else:
                        entry.unlink(missing_ok=True)
                    removed += 1
            except OSError:
                pass
    with _temps_lock:
        _registered_temps.clear()
    return removed


# ---------------------------------------------------------------------------
# Archive extraction with traversal + zip-bomb guards
# ---------------------------------------------------------------------------
class _SafeZipInfo:
    pass


def extract_zip_safe(
    archive: Path,
    destination: Path,
    *,
    max_total_mb: int = MAX_ARCHIVE_TOTAL_MB,
    max_ratio: int = MAX_ARCHIVE_RATIO,
    max_files: int = 20000,
) -> list[Path]:
    """Extract a ZIP/CBZ with path-traversal and decompression-bomb guards.

    Returns the list of extracted top-level entries. Raises
    :class:`PathSafetyError` on hostile archives.
    """
    archive = Path(archive)
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)

    extracted: list[Path] = []
    total_written = 0
    limit = max_total_mb * 1024 * 1024

    with zipfile.ZipFile(archive) as zf:
        infos = zf.infolist()
        if len(infos) > max_files:
            raise PathSafetyError(f"Archive contains too many entries ({len(infos)})")

        # First pass: validate every member before writing anything.
        for info in infos:
            if info.is_dir():
                continue
            name = info.filename
            if name.startswith("/") or ".." in Path(name).parts or "\\" in name:
                raise PathSafetyError(f"Unsafe path in archive: {name}")
            if Path(name).drive:
                raise PathSafetyError(f"Absolute path in archive: {name}")
            if info.file_size > 0 and info.compress_size > 0:
                ratio = info.file_size / info.compress_size
                if ratio > max_ratio:
                    raise PathSafetyError(
                        f"Compression ratio {ratio:.0f}x exceeds safety limit for {name}"
                    )
            total_written += info.file_size
            if total_written > limit:
                raise PathSafetyError(
                    f"Archive would decompress beyond {max_total_mb} MB limit"
                )

        # Second pass: write.
        for info in infos:
            if info.is_dir():
                continue
            target = ensure_within(safe_filename(info.filename, "entry"), destination)
            # safe_filename flattens directories; preserve structure instead:
            rel = Path(info.filename)
            target = destination
            for part in rel.parts:
                if part in ("", ".", ".."):
                    continue
                target = target / safe_filename(part)
            target = target.resolve()
            try:
                target.relative_to(destination)
            except ValueError as exc:
                raise PathSafetyError(f"Traversal attempt: {info.filename}") from exc
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as srcfh, open(target, "wb") as dstfh:
                shutil.copyfileobj(srcfh, dstfh, length=1 << 20)
            extracted.append(target)

    return extracted


def list_zip_names(archive: Path) -> list[str]:
    """List member names without extracting."""
    with zipfile.ZipFile(archive) as zf:
        return [i.filename for i in zf.infolist() if not i.is_dir()]


# ---------------------------------------------------------------------------
# Secure-ish delete
# ---------------------------------------------------------------------------
def secure_delete(path: Path, passes: int = 3) -> bool:
    """Overwrite a file with random bytes before unlinking.

    NOTE: on journaled filesystems (NTFS) this reduces but cannot guarantee
    recovery-proof deletion; documented honestly in SECURITY.md.
    """
    path = Path(path)
    if not path.exists():
        return True
    try:
        size = path.stat().st_size
        with open(path, "r+b") as fh:
            for _ in range(max(1, passes)):
                fh.seek(0)
                remaining = size
                while remaining > 0:
                    chunk = secrets.token_bytes(min(1 << 20, remaining))
                    fh.write(chunk)
                    remaining -= len(chunk)
                fh.flush()
                os.fsync(fh.fileno())
        path.unlink()
        return True
    except OSError as e:
        logger.warning("secure_delete failed for %s: %s", path.name, e)
        try:
            path.unlink()
            return True
        except OSError:
            return False


def remove_tree(path: Path) -> None:
    """rm -rf that clears read-only bits (Windows DLLs)."""
    path = Path(path)

    def onerror(func, tgt, exc):
        try:
            os.chmod(tgt, stat.S_IWRITE)
            func(tgt)
        except OSError:
            pass

    if path.exists():
        shutil.rmtree(path, onerror=onerror)
