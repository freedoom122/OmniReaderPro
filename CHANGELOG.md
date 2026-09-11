# Changelog

All notable changes to Veyrion Workspace are recorded here.
Format based on [Keep a Changelog](https://keepachangelog.com/).

## [1.1.0] — 2026-09-11

Product rebrand to **Veyrion Workspace**, published by **Veyrion Studios**.
No functional changes: every existing feature behaves exactly as before.

### Changed

- **Name and identity** — window title, About dialog, onboarding, executable
  (`VeyrionWorkspace.exe`), install directory, and installer are rebranded. The
  application organization is now `Veyrion Studios`.
- **App data** — user data lives in `%APPDATA%\VeyrionWorkspace`.
- **Icon** — new mark (a Veyrion "V" on a folded document page) replacing the
  previous monogram, regenerated at all seven icon sizes.
- **Python package** — the import path is now `veyrion_workspace`.
- **Source layout** — `run_veyrion.py` / `run_veyrion.pyw`,
  `packaging/veyrion.spec`, `installer/veyrion_setup.iss`, and
  `resources/icons/veyrion.*`.

### Added

- **Automatic upgrade migration** — a workspace created under the previous name
  is copied into the new location on first launch (settings, database, notes,
  vault, sessions, backups, plugins), with `omnireader.*` files renamed to
  `veyrion.*`. Derived caches are skipped, the original folder is preserved, and
  a failed copy rolls back rather than leaving a half-written workspace.
- `scripts/make_sample_documents.py` — regenerates the bundled welcome PDF from
  the current brand and version, so it can never drift from the release.
- `tests/test_migration.py` — 11 tests covering the migration path.

### Fixed

- The Inno Setup script had an invalid `AppId` GUID and pointed at the wrong
  app-data folder; both corrected. (NSIS remains the shipped installer.)
- The NSIS installer now removes a previous-name install directory and its
  shortcuts during an upgrade, guarded by an executable check so a tampered
  registry value cannot delete an unrelated directory.
- The welcome PDF's footer used a non-Latin-1 separator that extracted as a
  replacement character; the generator now emits ASCII punctuation only.

## [1.0.0] — 2026-09-09

Initial release. Built from scratch as a local-first desktop document
workspace.

### Added

- **Application shell**
  - Document tabs with close/drag affordances, split view (horizontal and
    vertical), dockable panels with persisted layout, status bar with page
    navigation, zoom, and background-task status.
  - Command palette (`Ctrl+K`) covering actions, recent files, bookmarks,
    and settings.
  - First-run onboarding (theme, folders, OCR, reading defaults) — skippable
    in full.
  - Window state persistence (size/position/maximized/fullscreen), system
    light/dark detection, high-DPI support.
- **Reading**
  - PDF: single/continuous/two-page/two-cover modes, fit width/page/height,
    zoom 50–800%, page rotation, virtualized lazy rendering with LRU pixmap
    cache, prefetching, thumbnails, search with on-page highlight,
    presentation mode with transition options.
  - EPUB/EPUB3 reflow reader: font family/size, line height, paragraph
    spacing, margins, width, alignment, light/dark/sepia/OLED/custom themes,
    TOC, internal links, footnotes.
  - MOBI/AZW/AZW3 extraction, CBZ (and CBR when `unrar` is available),
    image viewer with zoom/pan/rotate/fit, DOCX/ODT/RTF/PPTX/XLSX previews,
    Markdown editor with live preview, HTML, CSV/JSON/XML, plain text.
  - Reading position persistence: reopening a document returns to the same
    page/scroll.
- **Editing**
  - PDF page operations: rotate, delete, duplicate, reorder, extract,
    insert blank, insert from another PDF, merge, split, crop, resize.
  - True redaction with content removal + **Verify Redaction** reporting.
  - Watermarks, headers/footers, Bates numbering, metadata and page-label
    editing.
  - AcroForm reading/filling/clearing/resetting/validation.
  - DOCX editing (paragraphs, styles, tables) with non-destructive
    round-trip of unexposed package parts.
  - EPUB editor: metadata, cover, chapters, TOC, HTML/CSS editing.
- **Annotations**
  - Highlight, underline, strikeout, squiggly, sticky/text notes, freehand
    ink, shapes (rect/ellipse/line/arrow), text boxes, stamps — stored as
    standard PDF annotations.
  - Annotation manager panel with filter/sort/search/edit/delete and export
    to Markdown/HTML/CSV/JSON/PDF.
- **Search**
  - SQLite FTS5 full-text index of document text, metadata, annotations,
    bookmarks, and notes; background indexing; case/whole-word/regex/fuzzy/
    phrase modes; result navigation straight to the source.
- **Library**
  - Folder import, watch folders, recent files, favorites, collections,
    tags, ratings, reading progress; grid/list/compact/cover/table views;
    sorting and filtering; batch operations.
- **Tools**
  - OCR (Tesseract): current page / selection / whole document, language
    selection, background progress, cancel, searchable-PDF output — disabled
    with explanation when the engine is absent.
  - Text-to-speech: play/pause/stop/prev/next, speed 0.5–3×, voice and
    volume, background processing.
  - Dictionary (bundled wordnet-style source), selection translation
    (offline engines when available; online only on explicit user action),
    extractive summarization, keyword extraction, language detection.
  - Document comparison (PDF/DOCX/text) with per-page line diffs.
  - Conversion: PDF ⇄ text/Markdown/HTML/images, text → PDF, images → PDF,
    CSV → PDF tables, DOCX → Markdown, annotation exports.
  - Printing with page ranges, copies, orientation, duplex, multiple pages
    per sheet, annotations toggle.
- **Security**
  - Secure vault: AES-256-GCM, PBKDF2 600k, per-item nonces, manual and
    inactivity auto-lock, key zeroization.
  - Privacy tools: metadata inspection and stripping (PDF/EXIF/XMP),
    redaction verification, secure delete.
  - Path validation, archive traversal and zip-bomb guards, controlled temp
    directories, atomic saves, version history (default 5), session journal
    with crash recovery, autosave (120 s default, configurable).
  - Plugin system with permission manifests, user approval, and facade
    gating; sample word-count plugin included.
- **Robustness**
  - Background task manager with progress/speed/ETA/cancel/retry for OCR,
    indexing, thumbnails, conversion, comparison, and exports.
  - Settings: versioned JSON with validation, corruption recovery (backup +
    defaults), per-category reset.
  - Logging to app-data `logs/`, sanitized diagnostic report export.
  - 104 automated tests: unit, integration, security, workflows, UI smoke.

### Packaging

- PyInstaller one-folder windowed build (no console) with generated icon
  (`scripts/build_windows.ps1`, `packaging/veyrion.spec`).
- Inno Setup installer: shortcuts, per-user file associations for 20+
  formats, uninstall with optional data preservation
  (`installer/veyrion_setup.iss`).

### Documentation

- `README.md`, `USER_GUIDE.md`, `SECURITY.md`, `DECISIONS.md`,
  `THIRD_PARTY_LICENSES.md`, `CHANGELOG.md`, `demo.py`.

## [Unreleased]

- Nothing yet.