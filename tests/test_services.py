"""Service-layer tests: settings, tasks, recovery, versioning, annotations,
conversion, printing, text intelligence, plugins."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from veyrion_workspace.core.annotations.service import AnnotationService
from veyrion_workspace.core.comparison import compare_documents
from veyrion_workspace.core.dictionary import Dictionary
from veyrion_workspace.core.plugins.host import PERMISSIONS, PluginHost, PluginManifest
from veyrion_workspace.core.printing.printing import parse_page_range
from veyrion_workspace.core.summarization import keywords, summarize
from veyrion_workspace.core.translation import detect_language
from veyrion_workspace.core.versioning import VersionStore
from veyrion_workspace.services.recovery import SessionJournal
from veyrion_workspace.services.tasks import TaskManager
from veyrion_workspace.storage.repositories import AnnotationRepository


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
def test_settings_defaults_and_persistence(data_dir):
    from veyrion_workspace.services.settings import Settings
    s = Settings()
    assert s.get("appearance", "theme") == "light"
    s.set("appearance", "theme", "dark")
    s2 = Settings()
    assert s2.get("appearance", "theme") == "dark"


def test_settings_corruption_recovers_with_backup(data_dir):
    from veyrion_workspace.services.settings import Settings
    s = Settings()
    s.set("general", "first_run_complete", True)
    s.file_path = s._file
    s._file.write_text("{ not valid json !!!", encoding="utf-8")
    s2 = Settings()
    assert s2.restored_defaults
    assert s2.get("general", "first_run_complete") is False
    backups = list(data_dir.glob("settings/*.corrupt-*.json"))
    assert backups, "corrupt backup should be preserved"


def test_settings_invalid_types_dropped(data_dir):
    from veyrion_workspace.services.settings import Settings
    s = Settings()
    s._file.write_text(
        json.dumps({"appearance": {"theme": 42}, "appearance2": []}),
        encoding="utf-8")
    s2 = Settings()
    # Wrong type is dropped, defaults kept.
    assert s2.get("appearance", "theme") == "light"


def test_settings_reset(data_dir):
    from veyrion_workspace.services.settings import Settings
    s = Settings()
    s.set("appearance", "theme", "oled")
    s.reset_section("appearance")
    assert s.get("appearance", "theme") == "light"


# ---------------------------------------------------------------------------
# Task manager
# ---------------------------------------------------------------------------
def test_task_runs_and_reports():
    tm = TaskManager(max_workers=2)
    events = []

    def work(progress=None, cancel=None):
        progress(0.5, "halfway")
        return 42

    task = tm.submit("Test", "test", work)
    deadline = time.time() + 10
    while task.state.value not in ("done", "failed") and time.time() < deadline:
        time.sleep(0.02)
    assert task.state.value == "done"
    assert task.result == 42
    assert task.progress == 1.0
    tm.shutdown()


def test_task_cancel():
    tm = TaskManager(max_workers=1)

    def slow(progress=None, cancel=None):
        i = 0
        while not cancel.is_set() and i < 1000:
            time.sleep(0.01)
            i += 1
        return "stopped"

    task = tm.submit("Slow", "test", slow)
    time.sleep(0.1)
    assert task.cancel()
    deadline = time.time() + 10
    while task.state.value not in ("cancelled", "done") and time.time() < deadline:
        time.sleep(0.02)
    assert task.state.value == "cancelled"
    tm.shutdown()


def test_task_failure_reports_error():
    tm = TaskManager(max_workers=1)

    def boom(progress=None, cancel=None):
        raise ValueError("kaboom")

    task = tm.submit("Fail", "test", boom)
    deadline = time.time() + 10
    while task.state.value not in ("failed",) and time.time() < deadline:
        time.sleep(0.02)
    assert task.state.value == "failed"
    assert "kaboom" in task.error
    tm.shutdown()


# ---------------------------------------------------------------------------
# Recovery journal
# ---------------------------------------------------------------------------
def test_journal_clean_vs_dirty(tmp_path):
    j = SessionJournal(tmp_path)
    assert j.acquire_lock()
    j.record([{"path": "a.pdf", "state": {"page": 3}}], active_tab=0)
    assert j.has_unsaved_session()
    assert j.recoverable_tabs()[0]["path"] == "a.pdf"
    j.mark_clean_exit()
    assert not j.has_unsaved_session()
    j.release_lock()


def test_journal_corrupt_is_safe(tmp_path):
    j = SessionJournal(tmp_path)
    j._journal.write_text("{corrupt", encoding="utf-8")
    assert not j.has_unsaved_session()
    assert j.recoverable_tabs() == []


# ---------------------------------------------------------------------------
# Versioning
# ---------------------------------------------------------------------------
def test_version_store_prunes_and_rolls_back(tmp_path):
    vs = VersionStore(depth=3)
    f = tmp_path / "doc.txt"
    for i in range(1, 6):
        vs.snapshot_before_save(f)
        f.write_text(f"version {i}")
    versions = vs.versions(f)
    assert len(versions) == 3  # depth enforced
    assert vs.rollback(f, versions[0]["path"])
    assert f.read_text() == "version 4"
    # rollback is itself snapshotted
    assert len(vs.versions(f)) == 3


def test_version_snapshot_never_touches_original(tmp_path):
    vs = VersionStore(depth=2)
    f = tmp_path / "keep.txt"
    f.write_text("original")
    vs.snapshot_before_save(f)
    assert f.read_text() == "original"


# ---------------------------------------------------------------------------
# Annotation service
# ---------------------------------------------------------------------------
def test_annotation_service_crud_and_export(db, settings, tmp_path):
    svc = AnnotationService(AnnotationRepository(db), settings)
    rec = svc.create("C:/docs/x.pdf", 2, "highlight",
                     rect=[10, 10, 100, 30], text="quote", note="thought")
    assert rec.uuid
    assert svc.count_for_document("C:/docs/x.pdf") == 1
    svc.update(rec, note="updated thought")
    assert svc.for_document("C:/docs/x.pdf")[0].note == "updated thought"
    for fmt in ("markdown", "html", "csv", "json", "pdf"):
        out = svc.export("C:/docs/x.pdf", fmt, tmp_path / f"out.{fmt}",
                         title="Test")
        assert out.exists() and out.stat().st_size > 0
    svc.delete(rec.uuid, "C:/docs/x.pdf")
    assert svc.count_for_document("C:/docs/x.pdf") == 0


def test_annotation_import_from_pdf(sample_pdf, settings, db):
    from veyrion_workspace.core.documents.registry import open_document
    result = open_document(sample_pdf)
    e = result.engine
    import fitz
    e.add_highlight(0, [fitz.Rect(70, 95, 300, 110).quad], "#E5B25D")
    svc = AnnotationService(AnnotationRepository(db), settings)
    imported = svc.import_from_pdf(e)
    assert imported == 1
    assert svc.count_for_document(str(sample_pdf)) == 1
    e.close()


# ---------------------------------------------------------------------------
# Conversion
# ---------------------------------------------------------------------------
def test_pdf_to_text_and_images(sample_pdf, tmp_path):
    from veyrion_workspace.core.conversion.convert import pdf_to_images, pdf_to_text
    text_out = pdf_to_text(sample_pdf, tmp_path / "out.txt")
    assert "Page 1" in text_out.read_text(encoding="utf-8")
    imgs = pdf_to_images(sample_pdf, tmp_path / "imgs", "png", dpi=72,
                         pages=[0, 1])
    assert len(imgs) == 2
    assert imgs[0].exists()


def test_text_to_pdf_roundtrip(sample_txt, tmp_path):
    from veyrion_workspace.core.conversion.convert import text_to_pdf
    out = text_to_pdf(sample_txt, tmp_path / "typed.pdf", title="Converted")
    assert out.stat().st_size > 500
    import fitz
    doc = fitz.open(str(out))
    assert doc.page_count >= 1
    assert "Line one" in doc[0].get_text()
    doc.close()


def test_images_to_pdf(sample_image, sample_dir, tmp_path):
    from veyrion_workspace.core.conversion.convert import images_to_pdf
    out = images_to_pdf([sample_image, sample_image], tmp_path / "img.pdf")
    import fitz
    doc = fitz.open(str(out))
    assert doc.page_count == 2
    doc.close()


def test_csv_to_pdf_table(sample_csv, tmp_path):
    from veyrion_workspace.core.conversion.convert import csv_to_pdf_table
    out = csv_to_pdf_table(sample_csv, tmp_path / "table.pdf", title="Data")
    assert out.stat().st_size > 500


def test_docx_to_markdown(sample_docx, tmp_path):
    from veyrion_workspace.core.conversion.convert import document_to_markdown
    out = document_to_markdown(sample_docx, tmp_path / "out.md")
    text = out.read_text(encoding="utf-8")
    assert "# " in text  # headings preserved
    assert "regular words" in text


# ---------------------------------------------------------------------------
# Printing
# ---------------------------------------------------------------------------
def test_parse_page_range():
    assert parse_page_range("", 10) == list(range(10))
    assert parse_page_range("1-3", 10) == [0, 1, 2]
    assert parse_page_range("1-3,5", 10) == [0, 1, 2, 4]
    assert parse_page_range("8-", 10) == [7, 8, 9]
    assert parse_page_range("0,99", 10) == []
    assert parse_page_range("5-2", 10) == []


# ---------------------------------------------------------------------------
# Text intelligence
# ---------------------------------------------------------------------------
def test_summarize_returns_key_sentences():
    text = ("The fox is a small animal. " * 4 +
            "Foxes eat fruit and mice. " * 4 +
            "Foxes live in forests. " * 4)
    summary = summarize(text, 2)
    assert 1 <= len(summary) <= 2
    assert all(s in text for s in summary)


def test_keywords_extraction():
    kws = keywords("alpha beta gamma alpha beta alpha delta", 3)
    assert kws[0][0] == "alpha"


def test_dictionary_lookup():
    d = Dictionary()
    entry = d.lookup("Ephemeral.")
    assert entry and entry["def"]
    assert d.lookup("notawordzzz") is None
    assert len(d.suggestions("ephe")) >= 1


def test_language_detection():
    assert detect_language("The quick brown fox jumps") == "en"
    assert detect_language("Der schnelle braune Fuchs springt") == "de"
    assert detect_language("Le renard brun saute") == "fr"


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------
def test_compare_documents(sample_pdf, tmp_path):
    import fitz
    modified = tmp_path / "modified.pdf"
    doc = fitz.open(str(sample_pdf))
    page = doc[0]
    page.insert_text((72, 250), "A brand new sentence inserted")
    doc.save(str(modified))
    doc.close()
    result = compare_documents(sample_pdf, modified)
    assert result.pages_compared == 6
    assert result.pages_changed >= 1
    assert result.words_added >= 5
    changed = [d for d in result.page_diffs if d.status == "changed"]
    assert changed and any("brand new" in line for line in changed[0].added_lines)


def test_compare_identical(sample_pdf):
    result = compare_documents(sample_pdf, sample_pdf)
    assert result.identical
    assert result.pages_changed == 0


def test_compare_error_path(tmp_path, sample_pdf):
    result = compare_documents(tmp_path / "missing.pdf", sample_pdf)
    assert result.error


# ---------------------------------------------------------------------------
# Plugins
# ---------------------------------------------------------------------------
def _write_plugin(plugins_dir: Path, plugin_id: str, perms, body="",
                  trusted=False):
    d = plugins_dir / plugin_id
    d.mkdir(parents=True, exist_ok=True)
    manifest = {
        "id": plugin_id, "name": plugin_id.title(), "version": "1.0.0",
        "entry": "main.py", "permissions": perms, "description": "test",
        "author": "tester", "trusted": trusted,
    }
    (d / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    (d / "main.py").write_text(body or
        "def activate(facade):\n    facade.log('activated')\n", encoding="utf-8")


def test_plugin_manifest_validation(data_dir, tmp_path):
    plugins_dir = tmp_path / "plugins"
    _write_plugin(plugins_dir, "good_plugin", ["document.read"])
    m = PluginManifest.load(plugins_dir / "good_plugin")
    assert m.id == "good_plugin"
    # invalid id
    (plugins_dir / "Bad!ID").mkdir()
    (plugins_dir / "Bad!ID" / "plugin.json").write_text(
        json.dumps({"id": "Bad!ID", "entry": "main.py", "permissions": []}),
        encoding="utf-8")
    with pytest.raises(Exception):
        PluginManifest.load(plugins_dir / "Bad!ID")
    # undeclared permission
    _write_plugin(plugins_dir, "greedy", ["network"])
    with pytest.raises(Exception):
        PluginManifest.load(plugins_dir / "greedy")
    # entry escaping the folder
    d = plugins_dir / "escape"
    d.mkdir()
    (d / "plugin.json").write_text(json.dumps(
        {"id": "escape", "entry": "../../etc/passwd", "permissions": []}),
        encoding="utf-8")
    with pytest.raises(Exception):
        PluginManifest.load(d)


def test_plugin_permission_enforcement(data_dir, tmp_path):
    from veyrion_workspace.services.settings import Settings
    plugins_dir = data_dir / "plugins"
    _write_plugin(plugins_dir, "reader", ["document.read"],
                  "def activate(facade):\n    facade.open_document('x')\n")
    host = PluginHost(Settings(), app_api={"open_document": lambda p: "ok"})
    # Not approved -> refused
    with pytest.raises(Exception):
        host.load_plugin("reader")
    # Approved + permission granted -> works
    host.approve("reader")
    mod = host.load_plugin("reader")
    assert mod is not None


def test_plugin_permission_denied_when_not_declared(data_dir, tmp_path):
    from veyrion_workspace.services.settings import Settings
    plugins_dir = data_dir / "plugins"
    _write_plugin(plugins_dir, "nosy", ["document.read"],
                  "def activate(facade):\n    facade._require('network')\n")
    host = PluginHost(Settings(), app_api={})
    host.approve("nosy")
    with pytest.raises(PermissionError):
        host.load_plugin("nosy")


def test_plugin_load_all_approved_skips_invalid(data_dir, tmp_path):
    from veyrion_workspace.services.settings import Settings
    plugins_dir = data_dir / "plugins"
    _write_plugin(plugins_dir, "ok_one", ["document.read"])
    host = PluginHost(Settings(), app_api={})
    host.approve("ok_one")
    results = host.load_all_approved()
    assert any(r["ok"] for r in results)