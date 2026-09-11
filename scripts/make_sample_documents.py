#!/usr/bin/env python3
"""Generate the bundled sample documents.

Kept as a script (rather than a committed binary nobody can reproduce) so
the welcome document always matches the current brand and version.

Run:  python scripts/make_sample_documents.py
"""
from __future__ import annotations

from pathlib import Path

import fitz

from veyrion_workspace import APP_NAME, APP_TAGLINE, ORG_NAME, __version__

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "resources" / "sample_documents"
OUT_DIR.mkdir(parents=True, exist_ok=True)

INK = (0.078, 0.063, 0.055)      # #14100E
ACCENT = (0.780, 0.322, 0.165)   # #C7522A
MUTED = (0.42, 0.38, 0.33)
RULE = (0.73, 0.68, 0.60)

BODY = [
    "A universal document workspace. Open PDF, EPUB, DOCX, Markdown, comic",
    "archives, images and more, then read, annotate, edit, search, convert,",
    "compare, present and protect them without leaving the application.",
    "",
    "Try this:",
    "    -  Ctrl+K   the command palette, for anything you cannot find",
    "    -  Ctrl+O   open a document",
    "    -  Ctrl+F   search inside the current document",
    "    -  Select text to highlight, annotate, translate or look it up",
    "    -  Drag a file onto the window to open it in a new tab",
    "",
    "Everything stays on this machine. No account, no telemetry, and no",
    "network request unless you explicitly ask for one.",
]


def build_welcome(path: Path) -> Path:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)  # A4 portrait

    left = 72
    y = 150

    page.insert_text((left, y), APP_NAME, fontname="hebo", fontsize=30,
                     color=INK)
    y += 30
    page.insert_text((left, y), APP_TAGLINE, fontname="hebo", fontsize=11,
                     color=ACCENT)

    y += 26
    page.draw_line(fitz.Point(left, y), fitz.Point(523, y), color=RULE,
                   width=1)
    y += 38

    for line in BODY:
        page.insert_text((left, y), line, fontname="helv", fontsize=11.5,
                         color=MUTED)
        y += 19

    # ASCII only: the PDF base-14 fonts encode WinAnsi, and non-Latin-1
    # punctuation extracts as replacement characters.
    page.insert_text((left, 780), f"Version {__version__}   |   {ORG_NAME}",
                     fontname="helv", fontsize=9.5, color=RULE)

    doc.set_metadata({
        "title": f"Welcome to {APP_NAME}",
        "author": ORG_NAME,
        "subject": APP_TAGLINE,
        "creator": APP_NAME,
        "producer": APP_NAME,
    })
    doc.save(str(path), garbage=4, deflate=True)
    doc.close()
    return path


def main() -> None:
    out = build_welcome(OUT_DIR / "welcome.pdf")
    print("wrote", out, f"({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
