"""Document engine tests: open, extract, metadata, save round-trips."""
from __future__ import annotations

from pathlib import Path

import pytest

from veyrion_workspace.core.documents.registry import open_document


def test_open_pdf(sample_pdf):
    result = open_document(sample_pdf)
    assert result.ok, result.error
    e = result.engine
    assert e.page_count == 6
    assert "Page 1" in e.page_text(0)
    md = e.metadata()
    assert md.title == "Sample PDF"
    assert md.author == "Veyrion Tests"
    assert md.word_count > 10
    e.close()


def test_pdf_search(sample_pdf):
    result = open_document(sample_pdf)
    e = result.engine
    hits = e.search("alpha beta")
    assert len(hits) == 6
    assert hits[0]["page"] == 0
    assert hits[0]["match"].lower() == "alpha beta"
    e.close()


def test_pdf_search_case_whole_word(sample_pdf):
    result = open_document(sample_pdf)
    e = result.engine
    hits = e.search("ALPHA", case_sensitive=True)
    assert len(hits) == 0
    hits = e.search("ALPHA", case_sensitive=False)
    assert len(hits) == 6
    e.close()


def test_pdf_render(sample_pdf):
    result = open_document(sample_pdf)
    e = result.engine
    pix = e.render_page(0, zoom=1.0)
    assert pix.width > 0 and pix.height > 0
    thumb = e.render_thumbnail(0, 64)
    assert thumb is not None
    e.close()


def test_pdf_save_roundtrip(sample_pdf, tmp_path):
    result = open_document(sample_pdf)
    e = result.engine
    out = e.save(tmp_path / "copy.pdf")
    assert out.exists()
    reopened = open_document(out)
    assert reopened.ok
    assert reopened.engine.page_count == 6
    reopened.engine.close()
    e.close()


def test_pdf_page_operations(sample_pdf):
    result = open_document(sample_pdf)
    e = result.engine
    e.rotate_page(0, 90)
    info = e.page_info(0)
    assert info.rotation == 90
    e.delete_pages([5])
    assert e.page_count == 5
    e.insert_blank_page(0)
    assert e.page_count == 6
    e.duplicate_pages([0])
    assert e.page_count == 7
    e.close()


def test_pdf_extract_split(sample_pdf, tmp_path):
    result = open_document(sample_pdf)
    e = result.engine
    out = tmp_path / "extract.pdf"
    e.extract_pages_to([0, 1], out)
    r2 = open_document(out)
    assert r2.engine.page_count == 2
    r2.engine.close()
    parts = e.split_at([(0, 1), (2, 3)], tmp_path / "parts", "doc")
    assert len(parts) == 2
    e.close()


def test_pdf_forms(sample_pdf, tmp_path):
    import fitz
    # Build a PDF with a text field.
    doc = fitz.open()
    page = doc.new_page()
    widget = fitz.Widget()
    widget.rect = fitz.Rect(72, 72, 300, 100)
    widget.field_name = "name"
    widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    widget.field_value = ""
    page.add_widget(widget)
    path = tmp_path / "form.pdf"
    doc.save(str(path))
    doc.close()
    result = open_document(path)
    e = result.engine
    fields = e.form_fields()
    assert any(f["name"] == "name" for f in fields)
    assert e.set_field_value(0, "name", "Alice")
    assert e.clear_form() >= 1
    e.close()


def test_pdf_annotations_roundtrip(sample_pdf, tmp_path):
    result = open_document(sample_pdf)
    e = result.engine
    import fitz
    xref = e.add_highlight(0, [fitz.Rect(70, 95, 300, 110).quad], "#FF0000", 0.5)
    assert xref > 0
    note_xref = e.add_note(0, (72, 200), "test note")
    assert note_xref > 0
    saved = e.save(tmp_path / "ann.pdf")
    e.close()
    reopened = open_document(saved)
    r2 = reopened.engine
    anns = r2.annotations()
    assert any(a["type"].lower() == "highlight" for a in anns)
    assert any("test note" in (a.get("text") or "") for a in anns)
    r2.close()


def test_open_epub(sample_epub):
    result = open_document(sample_epub)
    assert result.ok, result.error
    e = result.engine
    assert e.page_count == 2
    md = e.metadata()
    assert md.title == "Test E-book"
    assert "fox" in e.page_text(0).lower()
    toc = e.toc()
    assert len(toc) >= 1
    assert toc[0].title
    e.close()


def test_epub_save_roundtrip(sample_epub, tmp_path):
    result = open_document(sample_epub)
    e = result.engine
    out = e.save(tmp_path / "copy.epub")
    assert out.exists() and out.stat().st_size > 1000
    e.close()


def test_epub_fallback_parser(tmp_path):
    """An EPUB that trips ebooklib must still open via the fallback parser."""
    import zipfile
    path = tmp_path / "weird.epub"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("META-INF/container.xml", """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
 <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>""")
        zf.writestr("OEBPS/content.opf", """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="id">
 <metadata><dc:title xmlns:dc="http://purl.org/dc/elements/1.1/">Fallback Book</dc:title></metadata>
 <manifest>
  <item id="c1" href="chap1.xhtml" media-type="application/xhtml+xml"/>
  <item id="c2" href="chap2.xhtml" media-type="application/xhtml+xml"/>
 </manifest>
 <spine><itemref idref="c1"/><itemref idref="c2"/></spine>
</package>""")
        zf.writestr("OEBPS/chap1.xhtml",
                    "<html><body><h1>One</h1><p>Fallback parser content alpha.</p></body></html>")
        zf.writestr("OEBPS/chap2.xhtml",
                    "<html><body><h1>Two</h1><p>More content beta.</p></body></html>")
    result = open_document(path)
    assert result.ok, result.error
    e = result.engine
    assert e.page_count == 2
    assert "alpha" in e.page_text(0)
    assert "Fallback Book" in e.metadata().title
    e.close()


def test_open_text(sample_txt):
    result = open_document(sample_txt)
    assert result.ok
    e = result.engine
    assert "Line one" in e.page_text(0)
    assert e.metadata().word_count > 100
    e.close()


def test_text_save_roundtrip(sample_txt, tmp_path):
    result = open_document(sample_txt)
    e = result.engine
    e.replace_full_text("new content entirely")
    out = e.save(tmp_path / "out.txt")
    assert out.read_text(encoding="utf-8") == "new content entirely"
    e.close()


def test_markdown_toc(sample_md):
    result = open_document(sample_md)
    e = result.engine
    toc = e.toc()
    assert any(t.title == "Title" and t.level == 1 for t in toc)
    assert any(t.title == "Section" and t.level == 2 for t in toc)
    e.close()


def test_open_docx(sample_docx):
    result = open_document(sample_docx)
    assert result.ok, result.error
    e = result.engine
    assert e.blocks()
    md = e.metadata()
    assert md.title == "Test Heading"
    assert md.word_count > 5
    e.close()


def test_docx_edit_and_save(sample_docx, tmp_path):
    result = open_document(sample_docx)
    e = result.engine
    # find first paragraph block and edit it
    for i, b in enumerate(e.blocks()):
        if b["kind"] == "paragraph" and b.get("text"):
            e.set_block_text(i, "EDITED TEXT")
            break
    out = e.save(tmp_path / "edited.docx")
    e.close()
    r2 = open_document(out)
    e2 = r2.engine
    texts = [b.get("text", "") for b in e2.blocks()
             if b["kind"] == "paragraph"]
    assert "EDITED TEXT" in texts
    e2.close()


def test_open_comic(sample_cbz):
    result = open_document(sample_cbz)
    assert result.ok, result.error
    e = result.engine
    assert e.page_count == 3
    img = e.render_page(0, zoom=1.0)
    assert img is not None
    e.close()


def test_open_image(sample_image):
    result = open_document(sample_image)
    assert result.ok
    e = result.engine
    assert e.page_count == 1
    img = e.render_page(0)
    assert img.size == (320, 240)
    md = e.metadata()
    assert md.extra["size"] == "320 x 240"
    e.close()


def test_unknown_extension_is_identified(tmp_path):
    path = tmp_path / "mystery.zzz"
    path.write_text("hello world\nplain text\n")
    result = open_document(path)
    # Text sniffing should still open it as text.
    assert result.ok
    assert result.engine.page_text(0).strip() == "hello world\nplain text"
    result.engine.close()


def test_missing_file():
    result = open_document(Path("Z:/does/not/exist.pdf"))
    assert not result.ok
    assert "does not exist" in result.error.lower()


def test_empty_file(tmp_path):
    path = tmp_path / "empty.pdf"
    path.write_bytes(b"")
    result = open_document(path)
    assert not result.ok
    assert "empty" in result.error.lower()


def test_corrupt_pdf(tmp_path):
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"%PDF-1.4 garbage that is not a real pdf " * 10)
    result = open_document(path)
    assert not result.ok
    assert result.error  # never raises


def test_corrupt_epub(tmp_path):
    path = tmp_path / "broken.epub"
    path.write_bytes(b"PK\x03\x04 not a real zip")
    result = open_document(path)
    assert not result.ok
    assert result.error


def test_word_count_statistics(sample_pdf, sample_txt):
    for p in (sample_pdf, sample_txt):
        result = open_document(p)
        assert result.engine.metadata().word_count >= 0
        result.engine.close()