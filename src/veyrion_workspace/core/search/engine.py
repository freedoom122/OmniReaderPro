"""Global search engine over the SQLite FTS5 index plus live in-document search.

The FTS index covers document text (per page/section) and metadata. Indexing
runs in background tasks; in-document search runs synchronously per page but
is always called from worker threads by the UI.
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from veyrion_workspace.storage.database import Database

logger = logging.getLogger("veyrion.search")

try:
    from rapidfuzz import fuzz
    HAS_FUZZ = True
except ImportError:  # pragma: no cover
    HAS_FUZZ = False


@dataclass
class SearchHit:
    doc_path: str
    doc_title: str
    page: int
    context: str
    match: str
    score: float = 0.0

    def as_dict(self) -> dict:
        return {
            "doc_path": self.doc_path, "doc_title": self.doc_title,
            "page": self.page, "context": self.context,
            "match": self.match, "score": self.score,
        }


class SearchEngine:
    def __init__(self, db: Database) -> None:
        self._db = db

    # -- indexing ------------------------------------------------------------
    def index_page(self, doc_path: str, page: int, text: str) -> None:
        self._db.execute(
            "INSERT INTO text_index (doc_path, page, body) VALUES (?,?,?)",
            (doc_path, str(page), text[:20000]))

    def index_metadata(self, doc_path: str, title: str, author: str,
                       subject: str, keywords: str) -> None:
        self._db.execute(
            "INSERT INTO meta_index (doc_path, title, author, subject, keywords) "
            "VALUES (?,?,?,?,?)",
            (doc_path, title, author, subject, keywords))

    def clear_document(self, doc_path: str) -> None:
        self._db.execute("DELETE FROM text_index WHERE doc_path=?", (doc_path,))
        self._db.execute("DELETE FROM meta_index WHERE doc_path=?", (doc_path,))

    def document_is_indexed(self, doc_path: str) -> bool:
        row = self._db.query_one(
            "SELECT 1 FROM text_index WHERE doc_path=? LIMIT 1", (doc_path,))
        return row is not None

    def index_document(self, engine, progress=None, cancel=None) -> int:
        """Index all pages of an open engine. Returns pages indexed."""
        doc_path = str(engine.path)
        self.clear_document(doc_path)
        count = 0
        for page_idx, text in engine.iter_text():
            if cancel and cancel.is_set():
                break
            if text and text.strip():
                self.index_page(doc_path, page_idx, text)
            count += 1
            if progress and count % 10 == 0:
                progress(count, engine.page_count)
        md = engine.metadata()
        self.index_metadata(doc_path, md.title, md.author, md.subject, md.keywords)
        return count

    # -- queries ----------------------------------------------------------------
    def _fts_query(self, query: str, fuzzy: bool) -> str:
        """Build an FTS5 MATCH expression from user input."""
        if fuzzy and HAS_FUZZ:
            # FTS has no edit-distance; emulate by expanding to prefix terms.
            words = re.findall(r"\w+", query)[:6]
            return " OR ".join(f'"{w}"*' for w in words) or '""'
        query = query.strip()
        if not query:
            return '""'
        if query.startswith('"'):  # user-provided phrase
            return query
        if any(ch in query for ch in ('*', '(', ')', 'OR', 'AND', 'NOT')):
            return query  # advanced syntax passthrough
        words = re.findall(r"\w+", query)
        return " AND ".join(f'"{w}"' for w in words) or '""'

    def search(self, query: str, *, fuzzy: bool = False, limit: int = 200,
               annotation_only: bool = False) -> list[SearchHit]:
        if annotation_only:
            return self._search_annotations(query, limit)
        fts_query = self._fts_query(query, fuzzy)
        hits: list[SearchHit] = []
        try:
            rows = self._db.query(
                """SELECT doc_path, page,
                          bm25(text_index) AS rank,
                          snippet(text_index, 2, '[[', ']]', '…', 14) AS snip
                   FROM text_index
                   WHERE text_index MATCH ?
                   ORDER BY rank LIMIT ?""",
                (fts_query, limit))
        except Exception:
            logger.debug("fts query failed: %s", fts_query)
            rows = []
        # Deduplicate per page and fetch titles.
        title_cache: dict[str, str] = {}
        seen: set = set()
        for row in rows:
            path = row["doc_path"]
            page_key = (path, row["page"])
            if page_key in seen:
                continue
            seen.add(page_key)
            if path not in title_cache:
                trow = self._db.query_one(
                    "SELECT title FROM documents WHERE path=?", (path,))
                title_cache[path] = (trow["title"] if trow and trow["title"]
                                     else Path(path).name)
            snippet = row["snip"] or ""
            match = ""
            m = re.search(r"\[\[(.+?)\]\]", snippet)
            if m:
                match = m.group(1)
            hits.append(SearchHit(
                doc_path=path, doc_title=title_cache[path],
                page=int(row["page"]) if str(row["page"]).isdigit() else 0,
                context=snippet.replace("[[", "").replace("]]", ""),
                match=match, score=-row["rank"] if row["rank"] is not None else 0))
        return hits

    def _search_annotations(self, query: str, limit: int) -> list[SearchHit]:
        rows = self._db.query(
            """SELECT doc_path, page, text, note FROM annotations
               WHERE text LIKE ? OR note LIKE ? LIMIT ?""",
            (f"%{query}%", f"%{query}%", limit))
        hits = []
        for row in rows:
            hits.append(SearchHit(
                doc_path=row["doc_path"], doc_title=Path(row["doc_path"]).name,
                page=row["page"], context=(row["text"] or row["note"]),
                match=query))
        return hits

    def search_metadata(self, query: str, limit: int = 50) -> list[SearchHit]:
        rows = self._db.query(
            """SELECT doc_path, title, author, bm25(meta_index) AS rank
               FROM meta_index WHERE meta_index MATCH ? ORDER BY rank LIMIT ?""",
            (self._fts_query(query, False), limit))
        return [SearchHit(
            doc_path=r["doc_path"], doc_title=r["title"] or Path(r["doc_path"]).name,
            page=0, context=f"{r['title']} — {r['author']}", match=query)
            for r in rows]

    # -- stats ---------------------------------------------------------------
    def indexed_page_count(self) -> int:
        row = self._db.query_one("SELECT COUNT(*) AS c FROM text_index")
        return row["c"] if row else 0
