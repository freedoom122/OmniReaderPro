"""Security tests: path validation, archive extraction, vault, redaction
verification, metadata stripping."""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from veyrion_workspace.core.documents.pdf_engine import verify_redaction_in_file
from veyrion_workspace.core.security.privacy import inspect_metadata, strip_metadata
from veyrion_workspace.core.security.vault import (
    InvalidPasswordError, Vault, VaultError, VaultLockedError,
)
from veyrion_workspace.utils.pathutils import (
    PathSafetyError, ensure_within, safe_filename, validate_path,
)
from veyrion_workspace.utils.safeio import (
    atomic_write_text, extract_zip_safe, secure_delete,
)


# ---------------------------------------------------------------------------
# Path safety
# ---------------------------------------------------------------------------
def test_validate_path_rejects_null_bytes():
    with pytest.raises(PathSafetyError):
        validate_path("file\x00name.pdf")


def test_validate_path_rejects_empty():
    with pytest.raises(PathSafetyError):
        validate_path("   ")


def test_validate_path_windows_device_names():
    with pytest.raises(PathSafetyError):
        validate_path("CON")
    with pytest.raises(PathSafetyError):
        validate_path("NUL.txt")


def test_safe_filename_sanitizes():
    assert ":" not in safe_filename("a:b/c")
    assert "/" not in safe_filename("a/b")
    assert safe_filename("") == "file"
    assert "?" not in safe_filename("what?")
    assert len(safe_filename("x" * 500)) <= 180


def test_ensure_within_blocks_escape(tmp_path):
    target = ensure_within("ok/file.txt", tmp_path)
    assert target == (tmp_path / "ok" / "file.txt")
    with pytest.raises(PathSafetyError):
        ensure_within("../escape.txt", tmp_path)


# ---------------------------------------------------------------------------
# Archive extraction guards
# ---------------------------------------------------------------------------
def _zip_with(path, entries):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries:
            zf.writestr(name, data)


def test_extract_zip_safe_happy_path(tmp_path):
    arc = tmp_path / "good.zip"
    _zip_with(arc, [("a.txt", b"hello"), ("sub/b.txt", b"world")])
    out = tmp_path / "out"
    extracted = extract_zip_safe(arc, out)
    assert (out / "a.txt").read_bytes() == b"hello"
    assert (out / "sub" / "b.txt").read_bytes() == b"world"
    assert len(extracted) == 2


def test_extract_zip_blocks_traversal(tmp_path):
    arc = tmp_path / "evil.zip"
    _zip_with(arc, [("../evil.txt", b"pwned")])
    with pytest.raises(PathSafetyError):
        extract_zip_safe(arc, tmp_path / "out")
    assert not (tmp_path.parent / "evil.txt").exists()


def test_extract_zip_blocks_absolute(tmp_path):
    arc = tmp_path / "abs.zip"
    _zip_with(arc, [("/tmp/evil.txt", b"x")])
    with pytest.raises(PathSafetyError):
        extract_zip_safe(arc, tmp_path / "out")


def test_extract_zip_blocks_backslash_traversal(tmp_path):
    arc = tmp_path / "win.zip"
    _zip_with(arc, [("..\\evil.txt", b"x")])
    with pytest.raises(PathSafetyError):
        extract_zip_safe(arc, tmp_path / "out")


def test_extract_zip_blocks_bomb(tmp_path):
    arc = tmp_path / "bomb.zip"
    # High compression ratio: 1MB of zeros stored as ~1KB.
    _zip_with(arc, [("bomb.bin", b"\x00" * (1024 * 1024))])
    with pytest.raises(PathSafetyError):
        extract_zip_safe(arc, tmp_path / "out", max_ratio=10)


def test_atomic_write_preserves_original_on_failure(tmp_path):
    target = tmp_path / "doc.txt"
    target.write_text("ORIGINAL")
    # A path whose parent is a regular file cannot be created: the atomic
    # write must fail cleanly without touching anything else.
    blocker = tmp_path / "blocker.txt"
    blocker.write_text("x")
    with pytest.raises(OSError):
        atomic_write_text(blocker / "x.txt", "data")
    assert target.read_text() == "ORIGINAL"


def test_secure_delete(tmp_path):
    f = tmp_path / "secret.txt"
    f.write_bytes(b"sensitive data")
    assert secure_delete(f)
    assert not f.exists()


# ---------------------------------------------------------------------------
# Vault
# ---------------------------------------------------------------------------
@pytest.fixture()
def vault(tmp_path):
    v = Vault(tmp_path / "vault")
    v.create("correct horse battery staple")
    return v


def test_vault_lock_blocks_access(vault):
    vault.lock()
    assert vault.is_locked()
    with pytest.raises(VaultLockedError):
        vault.list_items()


def test_vault_wrong_password(vault):
    vault.lock()
    with pytest.raises(InvalidPasswordError):
        vault.unlock("wrong")


def test_vault_roundtrip(vault, tmp_path):
    src = tmp_path / "secret.pdf"
    src.write_bytes(b"%PDF-1.7 fake content " * 100)
    item_id = vault.add_item("Secret", src)
    out = tmp_path / "restored.pdf"
    vault.extract_item(item_id, out)
    assert out.read_bytes() == src.read_bytes()


def test_vault_change_password(vault, tmp_path):
    src = tmp_path / "doc.txt"
    src.write_bytes(b"hello vault")
    item_id = vault.add_item("doc", src)
    vault.change_password("correct horse battery staple", "new pass")
    with pytest.raises(InvalidPasswordError):
        vault.unlock("correct horse battery staple")
    vault.unlock("new pass")
    out = tmp_path / "out.txt"
    vault.extract_item(item_id, out)
    assert out.read_bytes() == b"hello vault"


def test_vault_detects_tampering(vault, tmp_path):
    src = tmp_path / "d.txt"
    src.write_bytes(b"data")
    item_id = vault.add_item("d", src)
    item_path = vault.items_dir / f"{item_id}.oritem"
    blob = bytearray(item_path.read_bytes())
    blob[-1] ^= 0xFF
    item_path.write_bytes(bytes(blob))
    with pytest.raises(VaultError):
        vault.extract_item(item_id, tmp_path / "x.txt")


def test_vault_password_not_stored(vault):
    raw = (vault.dir / "vault.dat").read_bytes()
    assert b"correct horse" not in raw


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------
def test_redaction_removes_content(tmp_path):
    import fitz
    path = tmp_path / "secret.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Confidential report summary here")
    page.insert_text((72, 130), "Keep this visible text")
    doc.save(str(path))
    doc.close()

    from veyrion_workspace.core.documents.registry import open_document
    result = open_document(path)
    e = result.engine
    import fitz as fz
    # Redact over the confidential line.
    e.add_redaction(0, (60, 80, 320, 115))
    e.apply_redactions()
    saved = e.save(tmp_path / "redacted.pdf")
    e.close()

    report = verify_redaction_in_file(saved, ["Confidential", "report"])
    assert report["found"]["Confidential"] == []
    assert report["found"]["report"] == []
    reopened = open_document(saved)
    text = reopened.engine.page_text(0)
    assert "Confidential" not in text
    assert "Keep this visible text" in text
    reopened.engine.close()


def test_verify_redaction_detects_leaks(tmp_path):
    path = tmp_path / "leaky.pdf"
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "TopSecretPhrase remains")
    doc.save(str(path))
    doc.close()
    report = verify_redaction_in_file(path, ["TopSecretPhrase"])
    assert report["found"]["TopSecretPhrase"] == [0]


# ---------------------------------------------------------------------------
# Metadata privacy
# ---------------------------------------------------------------------------
def test_inspect_and_strip_pdf_metadata(sample_pdf, tmp_path):
    md = inspect_metadata(sample_pdf)
    assert "title" in md
    clean = strip_metadata(sample_pdf, tmp_path / "clean.pdf")
    md2 = inspect_metadata(clean)
    assert not any(k.lower() in ("title", "author") for k in md2)


def test_inspect_image_exif(tmp_path):
    from PIL import Image
    img = Image.new("RGB", (64, 64))
    exif = Image.Exif()
    exif[271] = "TestCamera"  # Make
    img.save(tmp_path / "with_exif.jpg", exif=exif)
    md = inspect_metadata(tmp_path / "with_exif.jpg")
    assert any("Make" in k for k in md)