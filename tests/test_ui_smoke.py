"""Headless (offscreen) UI smoke tests.

These prove the GUI layer constructs and responds without a display server,
which catches import errors, signal typos, and layout bugs early.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def _settle(app, seconds=0.2):
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.02)


def test_theme_and_icons(qapp):
    from omnireader_pro.ui.theme import THEMES, build_qss, get_palette
    from omnireader_pro.ui.icons import available_icons, icon, make_window_icon
    for name in THEMES:
        qss = build_qss(get_palette(name))
        assert len(qss) > 5000
    for name in available_icons():
        assert not icon(name, "#2A2721").isNull()
    assert not make_window_icon().isNull()


def test_pdf_view_constructs(qapp, data_dir, sample_pdf):
    from omnireader_pro.core.documents.registry import open_document
    from omnireader_pro.ui.views.pdf_view import PdfView
    result = open_document(sample_pdf)
    v = PdfView(result.engine)
    v.resize(900, 700)
    v.show()
    _settle(qapp)
    assert v.page_count == 6
    v.go_to_page(3)
    assert v.current_page == 3
    v.set_zoom(2.0)
    v.fit_width()
    v.rotate(90)
    hits = v.find_in_view("alpha beta")
    assert hits == 6
    v.clear_find()
    v.go_to_page(3)
    state = v.save_state()
    assert state["page"] == 3
    v.close_view()


def test_main_window_smoke(qapp, data_dir, sample_pdf):
    from omnireader_pro.services.recovery import SessionJournal
    from omnireader_pro.services.settings import Settings
    from omnireader_pro.services.tasks import TaskManager
    from omnireader_pro.storage.database import Database
    from omnireader_pro.ui.main_window import MainWindow
    settings = Settings()
    db = Database()
    tasks = TaskManager(2)
    journal = SessionJournal(data_dir / "sessions")
    w = MainWindow(settings, db, tasks, journal)
    w.resize(1200, 800)
    w.show()
    _settle(qapp)
    assert w.windowTitle().startswith("OmniReader Pro")
    w.open_path(str(sample_pdf))
    _settle(qapp)
    assert w.tabs.count() == 1
    view = w.current_view()
    assert view is not None
    w._next_page()
    _settle(qapp)
    assert view.current_page == 1
    # Command palette commands list is populated
    cmds = w._palette_commands()
    assert any("Open File" in c.title for c in cmds)
    assert any("Merge PDFs" in c.title for c in cmds)
    # Theme switch does not crash
    w.action_toggle_theme()
    _settle(qapp)
    w.action_toggle_theme()
    # Vim navigation
    settings.set("keyboard", "vim_mode", True)
    w.tabs.closeTab(0) if hasattr(w.tabs, "closeTab") else None
    tasks.shutdown(wait=False)
    db.close()


def test_all_dialogs_construct(qapp, data_dir, sample_pdf):
    from omnireader_pro.core.documents.registry import open_document
    from omnireader_pro.services.settings import Settings
    from omnireader_pro.services.tasks import TaskManager
    from omnireader_pro.storage.database import Database
    from omnireader_pro.ui.dialogs import (
        AboutDialog, CompareDialog, DictionaryDialog, ExportDialog,
        FindDialog, FormsDialog, MetadataDialog, OptimizeDialog,
        PrintDialog, PrivacyDialog, SignDialog, TranslateDialog, VaultDialog,
        VerifyRedactionDialog,
    )
    from omnireader_pro.ui.onboarding import OnboardingDialog
    from omnireader_pro.ui.presentation import PresentationWindow
    from omnireader_pro.ui.settings_dialog import SettingsDialog
    from omnireader_pro.ui.views.pdf_view import PdfView
    settings = Settings()
    tasks = TaskManager(2)
    db = Database()
    result = open_document(sample_pdf)
    v = PdfView(result.engine)
    dialogs = [
        PrintDialog(None, v), ExportDialog(None, v, tasks),
        FindDialog(None, v), TranslateDialog(None, "hola mundo", settings),
        DictionaryDialog(None, "ephemeral"), CompareDialog(None, tasks),
        VaultDialog(None, settings), PrivacyDialog(None, db, settings),
        VerifyRedactionDialog(None, v.pdf), FormsDialog(None, v),
        MetadataDialog(None, v), OptimizeDialog(None, v, tasks),
        SignDialog(None, v), AboutDialog(None), SettingsDialog(None),
        OnboardingDialog(None, settings),
    ]
    for d in dialogs:
        d.show()
        _settle(qapp, 0.05)
    pres = PresentationWindow(None, v)
    pres.resize(800, 600)
    pres.show()
    _settle(qapp)
    pres.close()
    v.close_view()
    tasks.shutdown(wait=False)
    db.close()


def test_split_view_constructs(qapp, data_dir, sample_pdf):
    from omnireader_pro.core.documents.registry import open_document
    from omnireader_pro.ui.split_view import SplitView
    from omnireader_pro.ui.views.pdf_view import PdfView
    r1 = open_document(sample_pdf)
    v1 = PdfView(r1.engine)
    v2 = PdfView(r1.engine)
    split = SplitView(v1, v2)
    split.show()
    _settle(qapp)
    split.sync_pages()
    assert split.views()[0] is v1
    v1.close_view()
    v2.close_view()


def test_view_factory_all_formats(qapp, data_dir, sample_pdf, sample_epub,
                                  sample_docx, sample_txt, sample_md,
                                  sample_cbz, sample_image, sample_csv):
    from omnireader_pro.core.documents.registry import open_document
    from omnireader_pro.services.settings import Settings
    from omnireader_pro.ui.views.factory import create_view
    s = Settings()
    expected = {
        sample_pdf: "PdfView", sample_epub: "EpubView",
        sample_docx: "DocxView", sample_txt: "TextDocView",
        sample_md: "TextDocView", sample_cbz: "ComicView",
        sample_image: "ImageView", sample_csv: "TextDocView",
    }
    for path, cls_name in expected.items():
        result = open_document(path)
        assert result.ok, (path, result.error)
        view = create_view(result, s)
        assert view is not None, path
        assert type(view).__name__ == cls_name, path
        view.show()
        _settle(qapp, 0.05)
        view.close_view()