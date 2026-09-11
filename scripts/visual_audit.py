#!/usr/bin/env python3
"""Visual audit: boot the real MainWindow, open a PDF, cycle themes,
toggle every dock, verify layout invariants, and capture screenshots.

Screenshots land in artifacts/visual_audit/*.png - inspect them for
polish issues (spacing, contrast, dock behavior).
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["VEYRION_DATA_DIR"] = str(
    Path(tempfile.mkdtemp(prefix="or_audit_")))

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtCore import QTimer
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

PASS = 0
FAIL = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  [PASS] {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label}" + (f" - {detail}" if detail else ""))


import time as _time


def settle(app, ms: int = 120) -> None:
    """Process events for a bit so render jobs and timers land."""
    deadline = _time.time() + ms / 1000.0
    while _time.time() < deadline:
        app.processEvents()
        _time.sleep(0.02)


def main() -> int:
    print("=" * 64)
    print("Veyrion Workspace - visual audit")
    print("=" * 64)

    from veyrion_workspace.services.settings import Settings
    from veyrion_workspace.services.tasks import TaskManager
    from veyrion_workspace.storage.database import Database
    from veyrion_workspace.services.recovery import SessionJournal
    from veyrion_workspace.ui.theme import THEMES, build_qss, get_palette
    from veyrion_workspace.ui.main_window import MainWindow

    app = QApplication(sys.argv)
    settings = Settings()
    settings.set("general", "first_run_complete", True)
    settings.set("general", "restore_session", False)
    settings.set("appearance", "theme", "light")
    db = Database()
    tasks = TaskManager(2)
    journal = SessionJournal(Path(os.environ["VEYRION_DATA_DIR"]) / "sessions")
    journal.acquire_lock()

    w = MainWindow(settings, db, tasks, journal)
    w.resize(1280, 800)
    w.show()
    settle(app)

    out_dir = ROOT / "artifacts" / "visual_audit"
    out_dir.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------------- 1. open
    print("\n[1] Open the welcome PDF")
    pdf = ROOT / "resources" / "sample_documents" / "welcome.pdf"
    w.open_path(str(pdf))
    settle(app, 300)
    check("tab opened", w.tabs.count() == 1, f"count={w.tabs.count()}")
    tab_title = w.tabs.tabText(0) if w.tabs.count() else ""
    check("tab titled with file name", "welcome" in tab_title.lower(), tab_title)
    view = w.tabs.currentWidget()
    check("view is a PdfView", type(view).__name__ == "PdfView")
    check("page count", view.page_count == 1, f"pages={view.page_count}")
    settle(app, 400)  # let the page render
    check("page rendered (cache has pixmaps)", len(view._cache._entries) >= 1,
          f"cache={len(view._cache._entries)}")
    sb = w.statusBar()
    labels = " | ".join(l.text() for l in sb.findChildren(object) if hasattr(l, "text"))
    check("status bar shows page info", "1" in labels, labels[:80])

    # --------------------------------------------------------------- 2. theme
    print("\n[2] Theme cycling (screenshots per theme)")
    for theme_name in ("light", "dark", "oled", "sepia", "high-contrast"):
        palette = get_palette(theme_name, settings.get("appearance", "accent"))
        app.setStyleSheet(build_qss(palette))
        settings.set("appearance", "theme", theme_name)
        settle(app, 200)
        shot = out_dir / f"theme-{theme_name}.png"
        w.grab().save(str(shot))
        img = QImage(str(shot))
        check(f"theme '{theme_name}' screenshot saved",
              img.width() > 200 and img.height() > 200, f"{shot.name} {img.width()}x{img.height()}")
        # Sample the window background corner: should not be pure black/white
        # except for oled/high-contrast where extremes are expected.
        corner = img.pixelColor(40, 40)
        lum = (corner.red() + corner.green() + corner.blue()) / 3
        if theme_name == "oled":
            check("oled background is near-black", lum < 40, f"lum={lum:.0f}")
        elif theme_name == "light":
            check("light background is light", lum > 150, f"lum={lum:.0f}")
        elif theme_name == "sepia":
            r, g, b = corner.red(), corner.green(), corner.blue()
            check("sepia is warm (red > blue)",
                  r > b and abs(r - g) < 60, f"rgb=({r},{g},{b})")

    # restore light theme for the dock pass
    app.setStyleSheet(build_qss(get_palette("light", "")))
    settings.set("appearance", "theme", "light")
    settle(app, 150)

    # ---------------------------------------------------------------- 3. docks
    print("\n[3] Dock panels toggle & layout")
    docks = [
        ("library", w.dock_library), ("thumbs", w.dock_thumbs),
        ("toc", w.dock_toc), ("bookmarks", w.dock_bookmarks),
        ("annotations", w.dock_annotations), ("notes", w.dock_notes),
        ("search", w.dock_search), ("tasks", w.dock_tasks),
        ("props", w.dock_props),
    ]
    for name, dock in docks:
        visible_before = dock.isVisible()
        dock.show()
        settle(app, 100)
        visible_after = dock.isVisible()
        check(f"dock '{name}' shows", visible_after,
              f"before={visible_before}")
        w._toggle_panel(name) if hasattr(w, "_toggle_panel") else None
    shot = out_dir / "docks-all.png"
    w.grab().save(str(shot))
    check("screenshot with all docks", shot.exists())

    # Toggle each off via the View menu machinery, then back on
    from PySide6.QtWidgets import QDockWidget
    for name, dock in docks:
        if dock.isVisible():
            dock.hide()
            settle(app, 60)
    w.dock_library.show()
    w.dock_thumbs.show()
    w.dock_annotations.show()
    settle(app, 150)
    shot2 = out_dir / "docks-selected.png"
    w.grab().save(str(shot2))
    check("screenshot with selected docks", shot2.exists())

    # ------------------------------------------------------------ 4. behavior
    print("\n[4] Reader behavior")
    if type(view).__name__ == "PdfView":
        view.fit_width()
        settle(app, 150)
        check("fit-width sets zoom", view._zoom > 0.5, f"zoom={view._zoom:.2f}")
        view.rotate(90)
        settle(app, 150)
        check("rotate keeps page", view._current_page == 0,
              f"page={view._current_page}")
        state = view.save_state()
        check("state persists rotation", state["rotation"] == 90)

    # -------------------------------------------------------------- 5. finish
    print("\n" + "=" * 64)
    print(f"AUDIT COMPLETE - {PASS} passed, {FAIL} failed")
    print(f"Screenshots: {out_dir}")
    print("=" * 64)

    journal.mark_clean_exit()
    journal.release_lock()
    tasks.shutdown(wait=False)
    try:
        db.close()
    except Exception:
        pass
    w.close()
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())