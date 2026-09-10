"""SQLite database manager: connection lifecycle, WAL, migrations, integrity.

The database is the backbone of the library, annotation store, notes,
reading state, and full-text search. All access is serialized through a
single connection guarded by a re-entrant lock, which is safe for the
application's threaded workloads and avoids SQLITE_BUSY entirely.
"""
from __future__ import annotations

import logging
import shutil
import sqlite3
import threading
import time
from pathlib import Path

from omnireader_pro.app import paths

logger = logging.getLogger("omnireader.db")

MIGRATIONS: list[tuple[int, str]] = [
    (1, """
    CREATE TABLE IF NOT EXISTS documents (
        id INTEGER PRIMARY KEY,
        path TEXT UNIQUE NOT NULL,
        title TEXT DEFAULT '',
        author TEXT DEFAULT '',
        subject TEXT DEFAULT '',
        keywords TEXT DEFAULT '',
        kind TEXT DEFAULT 'other',
        format TEXT DEFAULT '',
        size_bytes INTEGER DEFAULT 0,
        page_count INTEGER DEFAULT 0,
        word_count INTEGER DEFAULT 0,
        rating INTEGER DEFAULT 0,
        favorite INTEGER DEFAULT 0,
        progress REAL DEFAULT 0.0,
        folder TEXT DEFAULT '',
        cover_path TEXT DEFAULT '',
        metadata_json TEXT DEFAULT '{}',
        added_at REAL DEFAULT 0,
        last_opened REAL DEFAULT 0,
        last_modified REAL DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_docs_last_opened ON documents(last_opened);
    CREATE INDEX IF NOT EXISTS idx_docs_kind ON documents(kind);
    CREATE INDEX IF NOT EXISTS idx_docs_author ON documents(author);

    CREATE TABLE IF NOT EXISTS collections (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        parent_id INTEGER,
        smart_rules TEXT DEFAULT ''
    );

    CREATE TABLE IF NOT EXISTS document_collections (
        doc_id INTEGER NOT NULL,
        collection_id INTEGER NOT NULL,
        UNIQUE(doc_id, collection_id)
    );

    CREATE TABLE IF NOT EXISTS tags (
        id INTEGER PRIMARY KEY,
        name TEXT UNIQUE NOT NULL,
        color TEXT DEFAULT '#8A8F98'
    );

    CREATE TABLE IF NOT EXISTS document_tags (
        doc_id INTEGER NOT NULL,
        tag_id INTEGER NOT NULL,
        UNIQUE(doc_id, tag_id)
    );

    CREATE TABLE IF NOT EXISTS annotations (
        id INTEGER PRIMARY KEY,
        uuid TEXT UNIQUE NOT NULL,
        doc_path TEXT NOT NULL,
        page INTEGER NOT NULL DEFAULT 0,
        atype TEXT NOT NULL,
        rect_json TEXT DEFAULT '[]',
        color TEXT DEFAULT '#E5B25D',
        opacity REAL DEFAULT 1.0,
        width REAL DEFAULT 2.0,
        text TEXT DEFAULT '',
        note TEXT DEFAULT '',
        author TEXT DEFAULT '',
        tags TEXT DEFAULT '',
        created_at REAL DEFAULT 0,
        modified_at REAL DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_ann_doc ON annotations(doc_path);

    CREATE TABLE IF NOT EXISTS bookmarks (
        id INTEGER PRIMARY KEY,
        doc_path TEXT NOT NULL,
        page INTEGER NOT NULL DEFAULT 0,
        scroll REAL DEFAULT 0.0,
        title TEXT DEFAULT '',
        created_at REAL DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_bm_doc ON bookmarks(doc_path);

    CREATE TABLE IF NOT EXISTS notes (
        id INTEGER PRIMARY KEY,
        doc_path TEXT DEFAULT '',
        title TEXT DEFAULT '',
        body TEXT DEFAULT '',
        tags TEXT DEFAULT '',
        anchors_json TEXT DEFAULT '[]',
        created_at REAL DEFAULT 0,
        modified_at REAL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS reading_progress (
        doc_path TEXT PRIMARY KEY,
        page INTEGER DEFAULT 0,
        scroll REAL DEFAULT 0.0,
        zoom REAL DEFAULT 1.0,
        mode TEXT DEFAULT '',
        updated_at REAL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS reading_sessions (
        id INTEGER PRIMARY KEY,
        doc_path TEXT NOT NULL,
        started_at REAL DEFAULT 0,
        ended_at REAL DEFAULT 0,
        pages_read INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS ocr_cache (
        doc_path TEXT NOT NULL,
        page INTEGER NOT NULL,
        lang TEXT NOT NULL,
        text TEXT DEFAULT '',
        created_at REAL DEFAULT 0,
        PRIMARY KEY (doc_path, page, lang)
    );

    CREATE TABLE IF NOT EXISTS kv (
        key TEXT PRIMARY KEY,
        value TEXT DEFAULT ''
    );
    """),
    (2, """
    CREATE TABLE IF NOT EXISTS smart_collections (
        id INTEGER PRIMARY KEY,
        name TEXT UNIQUE NOT NULL,
        rules_json TEXT NOT NULL DEFAULT '[]',
        built_in INTEGER DEFAULT 0
    );
    INSERT OR IGNORE INTO smart_collections (name, rules_json, built_in) VALUES
        ('All PDFs', '[["kind","eq","pdf"]]', 1),
        ('Recently opened', '[["last_opened","within_days",7]]', 1),
        ('Favorites', '[["favorite","eq",1]]', 1),
        ('Unread', '[["progress","lt",1]]', 1),
        ('Annotated', '[["annotated","eq",1]]', 1);
    CREATE INDEX IF NOT EXISTS idx_notes_doc ON notes(doc_path);
    """),
    (3, """
    CREATE VIRTUAL TABLE IF NOT EXISTS text_index USING fts5(
        doc_path, page, body, tokenize='unicode61 remove_diacritics 2'
    );
    CREATE VIRTUAL TABLE IF NOT EXISTS meta_index USING fts5(
        doc_path, title, author, subject, keywords, tokenize='unicode61 remove_diacritics 2'
    );
    """),
]


class Database:
    """Serialized SQLite connection with versioned migrations."""

    def __init__(self, db_dir: Path | None = None) -> None:
        self._dir = Path(db_dir) if db_dir else paths.database_dir()
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / "omnireader.db"
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None
        self.open()

    @property
    def path(self) -> Path:
        return self._path

    def open(self) -> None:
        with self._lock:
            if self._conn is not None:
                return
            self._conn = sqlite3.connect(
                str(self._path), check_same_thread=False, timeout=10.0
            )
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.execute("PRAGMA busy_timeout=8000")
            self.migrate()

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.execute("PRAGMA optimize")
                    self._conn.commit()
                except sqlite3.Error:
                    pass
                self._conn.close()
                self._conn = None

    # -- migrations -------------------------------------------------------
    def migrate(self) -> int:
        """Apply pending migrations; back up the file before upgrading."""
        with self._lock:
            assert self._conn is not None
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "version INTEGER PRIMARY KEY, applied_at REAL)"
            )
            row = self._conn.execute(
                "SELECT MAX(version) AS v FROM schema_migrations"
            ).fetchone()
            current = row["v"] or 0
            applied = 0
            for version, sql in MIGRATIONS:
                if version <= current:
                    continue
                if self._path.exists() and self._path.stat().st_size > 0:
                    try:
                        backup = self._dir / f"omnireader.pre-migration-{version}.db"
                        if not backup.exists():
                            shutil.copy2(self._path, backup)
                    except OSError:
                        logger.warning("Could not back up database before migration")
                try:
                    self._conn.executescript(sql)
                    self._conn.execute(
                        "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                        (version, time.time()),
                    )
                    self._conn.commit()
                    applied += 1
                    logger.info("Applied database migration %d", version)
                except sqlite3.Error:
                    logger.exception("Migration %d failed", version)
                    raise
            return applied

    def integrity_check(self) -> bool:
        with self._lock:
            try:
                row = self._conn.execute("PRAGMA integrity_check").fetchone()
                return bool(row) and str(row[0]).lower() == "ok"
            except sqlite3.Error:
                return False

    # -- execution ---------------------------------------------------------
    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    def executemany(self, sql: str, seq) -> None:
        with self._lock:
            self._conn.executemany(sql, seq)
            self._conn.commit()

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def query_one(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    def transaction(self):
        """Context manager for multi-statement transactions."""
        return _Transaction(self)

    def kv_get(self, key: str, default: str = "") -> str:
        row = self.query_one("SELECT value FROM kv WHERE key=?", (key,))
        return row["value"] if row else default

    def kv_set(self, key: str, value: str) -> None:
        self.execute(
            "INSERT INTO kv (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


class _Transaction:
    def __init__(self, db: Database) -> None:
        self._db = db

    def __enter__(self) -> Database:
        self._db._lock.acquire()
        self._db._conn.execute("BEGIN")
        return self._db

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if exc_type is None:
                self._db._conn.commit()
            else:
                self._db._conn.rollback()
        finally:
            self._db._lock.release()
