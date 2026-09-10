"""Storage tests: database integrity, migrations, repositories, FTS search."""
from __future__ import annotations

import pytest

from omnireader_pro.core.search.engine import SearchEngine
from omnireader_pro.storage.repositories import (
    AnnotationRecord, AnnotationRepository, DocumentRecord, LibraryRepository,
    NoteRecord, NoteRepository, ProgressRepository, SmartCollectionRepository,
)


def test_database_integrity_and_migrations(db):
    assert db.integrity_check()
    row = db.query_one("SELECT MAX(version) AS v FROM schema_migrations")
    assert row["v"] == 3
    # Re-running migrate is a no-op.
    assert db.migrate() == 0


def test_database_wal_mode(db):
    row = db.query_one("PRAGMA journal_mode")
    assert str(row[0]).lower() == "wal"


def test_kv_store(db):
    db.kv_set("hello", "world")
    assert db.kv_get("hello") == "world"
    db.kv_set("hello", "again")
    assert db.kv_get("hello") == "again"


def test_library_repository_crud(db):
    repo = LibraryRepository(db)
    rec = DocumentRecord(path="C:/docs/a.pdf", title="A", kind="pdf",
                         page_count=10, size_bytes=1000)
    doc_id = repo.upsert(rec)
    assert doc_id > 0
    # upsert again — same path, no duplicate
    repo.upsert(rec)
    assert len(repo.all()) == 1
    got = repo.get_by_path("C:/docs/a.pdf")
    assert got.page_count == 10
    repo.set_rating("C:/docs/a.pdf", 4)
    repo.set_favorite("C:/docs/a.pdf", True)
    got = repo.get_by_path("C:/docs/a.pdf")
    assert got.rating == 4 and got.favorite
    repo.mark_opened("C:/docs/a.pdf")
    assert repo.get_by_path("C:/docs/a.pdf").last_opened > 0


def test_library_tags(db):
    repo = LibraryRepository(db)
    repo.upsert(DocumentRecord(path="C:/docs/t.pdf", title="T"))
    repo.add_tag("C:/docs/t.pdf", "important", "#FF0000")
    repo.add_tag("C:/docs/t.pdf", "work")
    tags = repo.tags_for("C:/docs/t.pdf")
    assert set(tags) == {"important", "work"}
    assert repo.all_tags()
    repo.remove_tag("C:/docs/t.pdf", "work")
    assert repo.tags_for("C:/docs/t.pdf") == ["important"]


def test_collections(db):
    repo = LibraryRepository(db)
    repo.upsert(DocumentRecord(path="C:/docs/c.pdf", title="C"))
    cid = repo.create_collection("Read Later")
    repo.add_to_collection("C:/docs/c.pdf", cid)
    docs = repo.docs_in_collection(cid)
    assert len(docs) == 1 and docs[0].title == "C"
    assert repo.collection_names_for("C:/docs/c.pdf") == ["Read Later"]
    repo.remove_from_collection("C:/docs/c.pdf", cid)
    assert repo.docs_in_collection(cid) == []


def test_annotation_repository(db):
    repo = AnnotationRepository(db)
    rec = AnnotationRecord(uuid="abc", doc_path="C:/docs/a.pdf", page=2,
                           atype="highlight", text="quote")
    repo.upsert(rec)
    found = repo.for_document("C:/docs/a.pdf")
    assert len(found) == 1 and found[0].text == "quote"
    # upsert updates
    rec.text = "changed"
    repo.upsert(rec)
    assert repo.for_document("C:/docs/a.pdf")[0].text == "changed"
    assert repo.count_for_document("C:/docs/a.pdf") == 1
    repo.delete("abc")
    assert repo.for_document("C:/docs/a.pdf") == []


def test_notes_repository(db):
    repo = NoteRepository(db)
    nid = repo.create(NoteRecord(title="First", body="hello"))
    rec = repo.all()[0]
    assert rec.id == nid
    rec.body = "world"
    repo.update(rec)
    assert repo.all()[0].body == "world"
    repo.delete(nid)
    assert repo.all() == []


def test_progress_repository(db):
    repo = ProgressRepository(db)
    repo.save("C:/docs/a.pdf", page=3, scroll=0.5, zoom=1.4, mode="pdf")
    state = repo.load("C:/docs/a.pdf")
    assert state["page"] == 3 and state["zoom"] == 1.4
    repo.forget("C:/docs/a.pdf")
    assert repo.load("C:/docs/a.pdf") is None


def test_smart_collections(db):
    repo = SmartCollectionRepository(db)
    docs = [
        DocumentRecord(path="a.pdf", kind="pdf", progress=0.0,
                       favorite=True, last_opened=0),
        DocumentRecord(path="b.epub", kind="ebook", progress=0.5),
    ]
    assert repo.evaluate('[["kind","eq","pdf"]]', docs[0], {})
    assert not repo.evaluate('[["kind","eq","pdf"]]', docs[1], {})
    assert repo.evaluate('[["progress","lt",1]]', docs[1], {})
    assert repo.evaluate('[["favorite","eq",1]]', docs[0], {})
    assert repo.evaluate('[["last_opened","within_days",1]]',
                         docs[0], {"last_opened": __import__("time").time()})
    # built-ins exist after migration
    names = [s["name"] for s in repo.all()]
    assert "All PDFs" in names and "Favorites" in names


def test_search_index_and_query(db):
    engine = SearchEngine(db)
    engine.index_page("C:/docs/a.pdf", 0,
                      "The quick brown fox jumps over the lazy dog")
    engine.index_page("C:/docs/a.pdf", 1, "Foxes live in the forest")
    engine.index_metadata("C:/docs/a.pdf", "Fox Book", "Jane Doe", "", "")
    assert engine.document_is_indexed("C:/docs/a.pdf")
    hits = engine.search("fox")
    assert len(hits) >= 1
    assert hits[0].doc_path == "C:/docs/a.pdf"
    phrase = engine.search("quick brown")
    assert len(phrase) == 1
    meta = engine.search_metadata("Jane")
    assert len(meta) == 1
    assert engine.indexed_page_count() == 2


def test_search_clear_and_reindex(db):
    engine = SearchEngine(db)
    engine.index_page("C:/docs/x.pdf", 0, "content goes here")
    engine.clear_document("C:/docs/x.pdf")
    assert not engine.document_is_indexed("C:/docs/x.pdf")


def test_search_annotation_only(db):
    from omnireader_pro.storage.repositories import AnnotationRepository
    repo = AnnotationRepository(db)
    repo.upsert(AnnotationRecord(uuid="u1", doc_path="C:/docs/a.pdf",
                                 page=1, atype="highlight", note="pivotal insight"))
    engine = SearchEngine(db)
    hits = engine.search("pivotal", annotation_only=True)
    assert len(hits) == 1
    assert hits[0].page == 1