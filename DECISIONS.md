# OmniReader Pro — Decision Log

This file records significant engineering decisions and their rationale, so
future maintainers (and users who care) can see *why* the software is built
the way it is. Entries are ordered by area, newest first within each area.

## Technology stack

### PySide6 / Qt 6 chosen over alternatives
**Decision:** PySide6 (Qt for Python) is the GUI foundation.
**Why:** Native-feeling desktop widgets, dockable panels, QGraphicsView for
high-performance page rendering, mature high-DPI support, and the only major
Python GUI toolkit with first-class commercial-quality document-viewer
patterns. Tkinter cannot deliver the required visual quality; wxPython has a
smaller community; Electron-style stacks would sacrifice the local-first,
low-memory desktop feel.

### PyMuPDF (fitz) as the PDF core
**Decision:** All PDF rendering, editing, annotation, redaction, form, and
page operations use PyMuPDF. `pypdf` is used only for signature-field
inspection and as a fallback probe.
**Why:** PyMuPDF is the fastest, most complete, permissively licensed PDF
library available for Python. It supports standard PDF annotation structures
natively (we write real PDF annots, not sidecar overlays), true redaction
with content removal, and incremental saves.

### EPUB handled by ebooklib + our own reflow renderer
**Decision:** EPUB is parsed with `ebooklib`, but the reader UI is our own
QTextDocument-based reflow view rather than a browser embed.
**Why:** A QTextDocument renderer gives full control over typography, themes,
annotations, TTS sentence tracking, and RTL — without shipping a second
rendering engine. Qt WebEngine remains available for HTML/SVG rendering
where it is genuinely useful.

## Security

### Vault encryption: AES-256-GCM with PBKDF2-HMAC-SHA256 (600k iterations)
**Decision:** The document vault encrypts each item with AES-256-GCM
(authenticated encryption) and derives keys with PBKDF2-HMAC-SHA256,
600,000 iterations, random 16-byte salt, per-item random nonce.
**Why:** AES-GCM is modern authenticated encryption from the well-audited
`cryptography` package. Argon2id would be preferable for the KDF, but at the
time of writing there was no dependable, pinned Windows wheel for Python
3.13; PBKDF2 at 600k iterations (OWASP 2023 recommendation) is the
standard-library-verifiable fallback. See `SECURITY.md` for honest limits.

### Vault stays unlocked after creation
**Decision:** Creating a vault leaves it unlocked.
**Why:** The user just typed the password; requiring a second unlock
immediately afterward is hostile UX. Locking is available on demand and
auto-locks after the configured inactivity timeout.

### Redaction removes content and verifies it
**Decision:** Redaction uses PyMuPDF's `apply_redactions` (which removes the
underlying text/images and optional metadata), and the app provides a
"Verify Redaction" flow that re-opens the saved file, searches the phrases,
and inspects page content before reporting.
**Why:** Redaction-by-black-rectangle is not security. The verification
reports what it actually finds; where the PDF format cannot guarantee
perfect sanitization (e.g., content inside incremental-update chains or
malformed streams), the report says so.

### Documents are untrusted input
**Decision:** Path validation, null-byte/device-name rejection, archive
traversal guards, decompression-ratio limits, capped extraction sizes,
controlled temp directories, and no code execution from documents.
**Why:** PDF/EPUB/HTML/archives routinely carry hostile content. See
`SECURITY.md` for the full threat model.

### Network policy: offline-first
**Decision:** No telemetry, no analytics, no update pings by default, no
background requests. A global Offline Mode gate blocks all network features.
Any network use must be explicit and feature-visible (Wikipedia lookup, web
translation fallback, update check — all off by default).
**Why:** Privacy is a feature. The application is fully functional offline.

## Data & persistence

### SQLite with WAL for the library/index
**Decision:** SQLite (WAL mode) holds library records, annotations, notes,
and the FTS5 full-text index, with versioned migrations and integrity checks.
**Why:** Zero-administration, single-file, transactional, and FTS5 gives
real full-text search without a server.

### Atomic saves + version history
**Decision:** Every save writes to a temp file, flushes, then atomically
replaces the target. Before a save, the current file is snapshotted into a
per-document version history (default depth 5, configurable).
**Why:** The original file must survive any failure. Windows file locking
also means we close/reopen the document handle around self-replacement
(observed as `PermissionError` otherwise).

### Autosave default 120 s, working-copy-first
**Decision:** Autosave writes to the app's controlled temp area and only
promotes to the original on explicit Save, unless the user opts into
in-place autosave.
**Why:** Editing sessions must be recoverable without ever half-overwriting
the user's original document.

## UI / UX

### Document-first design, no "AI dashboard" look
**Decision:** The visual system uses a restrained ink/paper palette, a single
accent (burnt sienna), custom flat SVG icon family, compact toolbar
controls, subtle depth, and the document as the visual hero. Docks are
optional and persist layout.
**Why:** The specification explicitly rejects generic template styling.
Every visual element (typography scale, spacing, hover/selection states) is
defined in `ui/theme.py` and `ui/widgets.py`.

### Command palette as the power-user hub
**Decision:** `Ctrl+K` searches actions, recent files, settings, and
bookmarks; virtually every feature is reachable from it.
**Why:** Keyboard-first power users and discoverability both win — a
searchable action list is faster than hunting menus and makes the feature
set legible.

### QGraphicsScene for PDF pages
**Decision:** The PDF view renders pages into a QGraphicsScene with
virtualized, lazily rendered, prefetched page items and an LRU pixmap cache.
**Why:** 1000-page PDFs must scroll smoothly without loading everything into
memory. QGraphicsView provides viewport culling; the render pool keeps
expensive rasterization off the GUI thread.

## OCR

### Tesseract integration is optional at runtime
**Decision:** OCR requires the Tesseract engine binary (installed
separately); the app detects it, shows its status, and disables OCR actions
with an explanation when absent.
**Why:** Bundling Tesseract binaries multiplies installer size and license
surface for a feature not everyone needs. Honest capability detection beats
a broken "OCR" button.

## Plugins

### Permission-declaring plugins, loaded only after approval
**Decision:** Plugins declare permissions in `plugin.json`; the host
validates the manifest (id pattern, entry containment, known permissions),
imports nothing until the user approves, and hands the plugin a thin facade
whose every method re-checks grants. Permission denials propagate as
`PermissionError`, not crashes.
**Why:** Plugins are untrusted code. The permission model keeps them from
receiving blanket privileges, and failing loudly on denial is a security
event, not a bug.

## Comparison

### Text-line diff per page, plus structural metadata
**Decision:** Document comparison extracts per-page text, aligns lines, and
reports added/removed/changed lines per page with similarity; PDFs also get
a page count/size comparison.
**Why:** Pixel-perfect semantic comparison across formats is not honestly
achievable; a line-level diff with clear "what changed on which page" is
real, verifiable, and useful.

## Packaging

### PyInstaller one-folder, windowed build
**Decision:** `packaging/omnireader.spec` produces a console-less
`OmniReaderPro.exe` with the app icon; Inno Setup (`installer/`) adds
shortcuts, per-user file associations, and clean uninstall.
**Why:** No console window is a hard requirement. One-folder (not one-file)
reduces startup time and antivirus false positives while still being
portable.

### Icons generated from code
**Decision:** `scripts/make_icon.py` renders the SVG master to PNG/ICO
assets; ICO embeds 16–256 px sizes (Pillow requires the primary image to be
the largest, which we honored after observing single-frame output).
**Why:** Reproducible assets without designer handoffs; the mark is
geometric by design.

## Known limitations (honest list)

- **Redaction** cannot guarantee perfect removal of text hidden inside
  malformed/incremental PDF structures; verification reports what it finds.
- **Secure delete** overwrites bytes but NTFS journaling means recovery may
  still be possible with forensic tools.
- **Digital signatures** are inspected and reported (certificate, validity,
  modification state) but new cryptographic signing is not offered; a visual
  signature image is clearly labeled as non-cryptographic.
- **MOBI/AZW** extraction is read-oriented; complex formatting may not
  round-trip into other formats.
- **DJVU/XPS/CHM/DOC** open via external converters when installed; there is
  no native renderer for these formats in this build.
- **Comparison** is line-based, not semantic.
## D-XX — GitHub distribution via NSIS installer (2026-09-10)

**Decision:** Publish the app at `github.com/freedoom122/OmniReaderPro` and
distribute the one-time installer as a release asset rather than in-repo.

**Rationale:**

- GitHub blocks files > 100 MB in git but allows up to 2 GB per release asset;
  the 157 MB installer belongs in Releases.
- Inno Setup was unavailable; NSIS 3.11 (zlib-licensed, portable ZIP from
  SourceForge) was used instead — per-user install (`RequestExecutionLevel
  user`), no UAC, LZMA solid compression (569 MB → 157 MB), Start Menu +
  desktop shortcuts, proper uninstaller, uninstall registry entry.
- The existing home-directory git checkout pointed at an unrelated public
  repo (`DoomSMP`); a fresh dedicated repository was created for the project.
- Build pipeline: PyInstaller (windowed, no console) → `packaging/dist/`
  staging copy → `tools/nsis-3.11/Bin/makensis.exe packaging/installer.nsi`
  → `OmniReaderPro-Setup-1.0.0.exe` (+ SHA-256 sidecar). Installer binaries
  and the NSIS toolchain are gitignored; only sources are versioned.
