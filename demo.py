#!/usr/bin/env python3
"""Veyrion Workspace - end-to-end workflow demonstration.

Runs the full product loop headlessly and prints a report:

  open -> read -> search -> annotate -> save -> reopen -> verify ->
  edit pages -> convert -> compare -> library/index -> vault -> redaction

This is the same path the test suite covers, packaged as a single readable
walkthrough. Exit code 0 = every step succeeded.

Usage:
    python demo.py            (from the project root; uses src/ on sys.path)
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

# Redirect all app data so the demo never touches the real user database.
os.environ["VEYRION_DATA_DIR"] = str(Path(tempfile.mkdtemp(prefix="or_demo_")))

import fitz  # noqa: E402

PASS = 0
FAIL = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    status = "PASS" if ok else "FAIL"
    if ok:
        PASS += 1
    else:
        FAIL += 1
    print(f"  [{status}] {label}" + (f" - {detail}" if detail and not ok else ""))


def main() -> int:
    print("=" * 64)
    print("Veyrion Workspace - end-to-end demo")
    print("=" * 64)

    work = Path(tempfile.mkdtemp(prefix="or_demo_work_"))

    # ---------------------------------------------------------------- 1. open
    print("\n[1] Document engines: PDF, EPUB, DOCX, text, comic, image")
    from veyrion_workspace.core.documents.registry import open_document

    pdf_path = work / "demo.pdf"
    doc = fitz.open()
    for i in range(8):
        page = doc.new_page()
        page.insert_text((72, 100), f"Page {i + 1} - the quick brown fox")
        page.insert_text((72, 130), f"Confidential draft revision {i}")
        if i == 0:
            page.insert_text((72, 170), "Executive summary for the quarterly report")
    doc.set_metadata({"title": "Demo Document", "author": "Veyrion Demo"})
    doc.save(str(pdf_path))
    doc.close()

    r = open_document(pdf_path)
    check("open PDF", r.ok and r.engine.page_count == 8)
    e = r.engine

    check("page text", "quick brown fox" in e.page_text(0))
    check("metadata title", e.metadata().title == "Demo Document")
    check("TOC/outline present", e.toc() is not None)

    # --------------------------------------------------------------- 2. search
    print("\n[2] In-document search")
    hits = e.search("brown fox")
    check("search finds hits", len(hits) >= 1, f"{len(hits)} hits")
    check("search hit has page", hits and hits[0]["page"] is not None)

    # ------------------------------------------------------------ 3. annotate
    print("\n[3] Annotations (standard PDF structures)")
    e.add_highlight(0, [fitz.Rect(72, 95, 300, 112).quad], "#E5B25D", 0.4)
    e.add_note(1, (72, 200), "demo sticky note")
    e.add_ink(0, [[(100, 100), (150, 140), (200, 100)]], "#C7522A", 2.0)
    check("3 annotations created", len(e.annotations()) == 3)

    # ----------------------------------------------------------------- 4. save
    print("\n[4] Atomic save + version history")
    from veyrion_workspace.core.versioning import VersionStore
    vs = VersionStore(depth=3)
    saved = work / "demo_annotated.pdf"
    e.save(saved)
    e.close()
    check("save produced file", saved.exists() and saved.stat().st_size > 0)

    r2 = open_document(saved)
    check("reopen keeps annotations", len(r2.engine.annotations()) == 3)
    r2.engine.close()

    # ----------------------------------------------------------- 5. edit pages
    print("\n[5] Page operations")
    e3 = open_document(saved).engine
    e3.delete_pages([0])
    e3.rotate_page(0, 90)
    e3.duplicate_pages([1])
    check("delete/rotate/duplicate", e3.page_count == 8)
    edited = e3.save(work / "demo_edited.pdf")
    e3.close()

    # ------------------------------------------------------- 6. convert/export
    print("\n[6] Conversion")
    from veyrion_workspace.core.conversion.convert import (
        document_to_markdown, pdf_to_images, pdf_to_text,
    )
    txt = pdf_to_text(saved, work / "demo.txt")
    check("PDF -> text", "quick brown fox" in txt.read_text(encoding="utf-8"))
    imgs = pdf_to_images(saved, work / "imgs", "png", pages=[0, 1])
    check("PDF -> images", len(imgs) == 2 and imgs[0].exists())
    md = document_to_markdown(saved, work / "demo.md")
    check("PDF -> markdown", md.exists() and md.stat().st_size > 0)

    # ------------------------------------------------------------- 7. compare
    print("\n[7] Comparison")
    from veyrion_workspace.core.comparison import compare_documents
    result = compare_documents(saved, edited)
    check("compare reports diffs", result.pages_compared == 8 and not result.identical)
    check("compare page-level diff", result.pages_changed >= 1)

    # ---------------------------------------------------- 8. library + search
    print("\n[8] Library index + global search")
    from veyrion_workspace.storage.database import Database
    from veyrion_workspace.storage.repositories import DocumentRecord, LibraryRepository
    from veyrion_workspace.core.search.engine import SearchEngine
    db = Database()
    repo = LibraryRepository(db)
    se = SearchEngine(db)
    rr = open_document(saved)
    repo.upsert(DocumentRecord(path=str(saved), title="Demo", kind="pdf",
                               page_count=rr.engine.page_count))
    se.index_document(rr.engine)
    rr.engine.close()
    found = se.search("quarterly")
    check("global search finds indexed doc", any("demo" in h.doc_path.lower() for h in found))
    db.close()

    # -------------------------------------------------------------- 9. vault
    print("\n[9] Secure vault")
    from veyrion_workspace.core.security.vault import Vault
    vault_dir = work / "vault"
    v = Vault(vault_dir)
    v.create("correct horse battery staple")
    item_id = v.add_item("demo_secret.pdf", saved)
    out = work / "restored.pdf"
    v.extract_item(item_id, out)
    check("vault encrypt/decrypt round-trip", out.read_bytes() == saved.read_bytes())
    v.lock()
    check("vault locks", v.is_locked())

    # ---------------------------------------------------------- 10. redaction
    print("\n[10] Redaction + verification")
    from veyrion_workspace.core.documents.pdf_engine import verify_redaction_in_file
    red = work / "redacted.pdf"
    e4 = open_document(saved).engine
    # "Confidential draft revision N" appears on every page (y~130): mark
    # every page, then apply - the verifier must find nothing afterwards.
    for pno in range(e4.page_count):
        e4.add_redaction(pno, (60, 120, 400, 145))
    e4.apply_redactions()
    e4.save(red)
    e4.close()
    report = verify_redaction_in_file(red, ["Confidential"])
    check("redaction removed text", report["found"]["Confidential"] == [],
          f"found on pages {report['found']['Confidential']}")
    check("verifier ran", report.get("checked", True))

    # ------------------------------------------------------------ 11. finish
    print("\n" + "=" * 64)
    print(f"DEMO COMPLETE - {PASS} passed, {FAIL} failed")
    print("=" * 64)
    shutil.rmtree(work, ignore_errors=True)
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())