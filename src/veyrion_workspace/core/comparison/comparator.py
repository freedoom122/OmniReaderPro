"""Document comparison.

Provides textual comparison with page-level mapping (diff of per-page text)
and a word-level diff summary. Visual comparison is delivered in the UI by
rendering pages side by side; this module computes the structured diff.
Honest limitation: PDF/DOCX comparison is text-level, not semantic.
"""
from __future__ import annotations

import difflib
import logging
from dataclasses import dataclass, field
from pathlib import Path

from veyrion_workspace.core.documents.registry import open_document

logger = logging.getLogger("veyrion.compare")


@dataclass
class PageDiff:
    page: int
    status: str              # same|changed|added|removed
    similarity: float = 1.0
    removed_lines: list[str] = field(default_factory=list)
    added_lines: list[str] = field(default_factory=list)


@dataclass
class ComparisonResult:
    doc_a: str = ""
    doc_b: str = ""
    identical: bool = False
    pages_compared: int = 0
    pages_changed: int = 0
    words_added: int = 0
    words_removed: int = 0
    page_diffs: list[PageDiff] = field(default_factory=list)
    error: str = ""


def _page_texts(path: Path) -> list[str]:
    result = open_document(path)
    if not result.ok:
        raise RuntimeError(result.error)
    engine = result.engine
    texts = [engine.page_text(i) for i in range(engine.page_count)]
    engine.close()
    return texts


def compare_documents(path_a: Path, path_b: Path,
                      progress=None, cancel=None) -> ComparisonResult:
    """Compare two documents page-by-page with word-level statistics."""
    result = ComparisonResult(doc_a=str(path_a), doc_b=str(path_b))
    try:
        texts_a = _page_texts(Path(path_a))
        texts_b = _page_texts(Path(path_b))
    except Exception as e:
        result.error = str(e)
        return result

    total = max(len(texts_a), len(texts_b))
    matcher = difflib.SequenceMatcher(a=None, b=None, autojunk=False)
    for idx in range(total):
        if cancel is not None and cancel.is_set():
            break
        a = texts_a[idx] if idx < len(texts_a) else None
        b = texts_b[idx] if idx < len(texts_b) else None
        if a is None:
            result.page_diffs.append(PageDiff(page=idx, status="added"))
            continue
        if b is None:
            result.page_diffs.append(PageDiff(page=idx, status="removed"))
            continue
        if a.strip() == b.strip():
            result.page_diffs.append(PageDiff(page=idx, status="same"))
            continue
        matcher.set_seq1(a.splitlines())
        matcher.set_seq2(b.splitlines())
        removed, added = [], []
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag in ("delete", "replace"):
                removed.extend(l.strip() for l in matcher.a[i1:i2] if l.strip())
            if tag in ("insert", "replace"):
                added.extend(l.strip() for l in matcher.b[j1:j2] if l.strip())
        sim = matcher.quick_ratio()
        result.page_diffs.append(PageDiff(
            page=idx, status="changed", similarity=sim,
            removed_lines=removed[:60], added_lines=added[:60]))
        result.words_added += sum(len(l.split()) for l in added)
        result.words_removed += sum(len(l.split()) for l in removed)
        if progress:
            progress((idx + 1) / total, f"page {idx + 1} of {total}")

    result.pages_compared = total
    result.pages_changed = sum(1 for d in result.page_diffs if d.status != "same")
    result.identical = result.pages_changed == 0 and len(texts_a) == len(texts_b)
    return result


def compare_texts(text_a: str, text_b: str) -> list[str]:
    """Unified diff of two raw texts (for the compare viewer)."""
    return list(difflib.unified_diff(
        text_a.splitlines(), text_b.splitlines(),
        fromfile="document A", tofile="document B", lineterm=""))
