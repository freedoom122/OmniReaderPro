"""Document version history and crash-safe saves.

Every save creates a timestamped backup of the previous file state (bounded
by a configurable depth, default 5) before atomically replacing the target.
Saving never destroys the original: writes go to a temp file first, are
validated, then atomically replace the destination.
"""
from __future__ import annotations

import hashlib
import logging
import shutil
import time
from pathlib import Path

from veyrion_workspace.app import paths
from veyrion_workspace.utils.safeio import atomic_copy, atomic_write_bytes

logger = logging.getLogger("veyrion.versioning")


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()[:16]
    except OSError:
        return ""


class VersionStore:
    """Manages versioned backups for every edited document."""

    def __init__(self, depth: int = 5) -> None:
        self.depth = max(1, depth)
        self._root = paths.backups_dir() / "versions"
        self._root.mkdir(parents=True, exist_ok=True)

    def _doc_dir(self, path: Path) -> Path:
        import hashlib
        key = hashlib.sha256(str(path).lower().encode("utf-8")).hexdigest()[:16]
        return self._root / key

    def snapshot_before_save(self, target: Path) -> Path | None:
        """Copy the current file into version history before it is replaced."""
        target = Path(target)
        if not target.exists():
            return None
        doc_dir = self._doc_dir(target)
        doc_dir.mkdir(parents=True, exist_ok=True)
        # Millisecond precision: several saves within one second must not
        # collide into equal filenames (sorting would then be by hash).
        stamp = time.strftime("%Y%m%d-%H%M%S") + f"-{int(time.time() * 1000) % 1000:03d}"
        backup = doc_dir / f"{stamp}-{file_hash(target)}{target.suffix}"
        try:
            if not backup.exists():
                atomic_copy(target, backup)
            self._prune(doc_dir)
            return backup
        except OSError:
            logger.warning("version snapshot failed for %s", target.name)
            return None

    def snapshot_copy(self, source: Path, note: str = "") -> Path | None:
        """External callers snapshot a source file (e.g. before risky edits)."""
        return self.snapshot_before_save(source)

    def _prune(self, doc_dir: Path) -> None:
        versions = sorted(doc_dir.glob("*"))
        while len(versions) > self.depth:
            oldest = versions.pop(0)
            try:
                oldest.unlink()
            except OSError:
                pass

    def versions(self, target: Path) -> list[dict]:
        doc_dir = self._doc_dir(Path(target))
        out = []
        for f in sorted(doc_dir.glob("*"), reverse=True):
            try:
                out.append({
                    "path": f,
                    "time": f.stat().st_mtime,
                    "size": f.stat().st_size,
                })
            except OSError:
                continue
        return out

    def rollback(self, target: Path, version_path: Path) -> bool:
        """Atomically restore a previous version over the live file."""
        target, version_path = Path(target), Path(version_path)
        if not version_path.exists():
            return False
        # Snapshot the current state before rolling back, so rollback is
        # itself reversible.
        if target.exists():
            self.snapshot_before_save(target)
        try:
            atomic_copy(version_path, target)
            return True
        except OSError:
            logger.exception("rollback failed for %s", target.name)
            return False

    def clear(self, target: Path | None = None) -> int:
        if target is not None:
            doc_dir = self._doc_dir(Path(target))
            count = len(list(doc_dir.glob("*"))) if doc_dir.exists() else 0
            if doc_dir.exists():
                shutil.rmtree(doc_dir, ignore_errors=True)
            return count
        count = 0
        for d in self._root.glob("*"):
            shutil.rmtree(d, ignore_errors=True)
            count += 1
        return count
