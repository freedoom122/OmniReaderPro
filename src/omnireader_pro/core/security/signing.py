"""Cryptographic document signing and signature verification.

Uses the ``cryptography`` package to load PKCS#12/.pfx identities and
pyHanko (when available) to produce real PAdES-compatible PDF signatures.
pyHanko is an optional dependency: when absent, signing is offered through
a clear, honest message rather than a silent visual-only workaround.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("omnireader.signing")

try:
    from cryptography.hazmat.primitives.serialization import pkcs12
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    HAS_CRYPTO = True
except ImportError:  # pragma: no cover
    HAS_CRYPTO = False

try:
    from pyhanko.sign import signers
    HAS_PYHANKO = True
except ImportError:  # pragma: no cover
    HAS_PYHANKO = False


@dataclass
class SigningIdentity:
    label: str = ""
    subject: str = ""
    issuer: str = ""
    not_before: str = ""
    not_after: str = ""
    expired: bool = False
    _cert: object = field(default=None, repr=False)
    _key: object = field(default=None, repr=False)


def load_pkcs12(path: Path, password: str) -> SigningIdentity:
    """Load a .p12/.pfx signing identity."""
    if not HAS_CRYPTO:
        raise RuntimeError("The 'cryptography' package is required for signing")
    data = Path(path).read_bytes()
    try:
        key, cert, extra = pkcs12.load_key_and_certificates(
            data, password.encode("utf-8") if password else None)
    except ValueError as e:
        raise ValueError("Wrong certificate password or invalid file") from e
    if key is None or cert is None:
        raise ValueError("The certificate file does not contain a private key "
                         "and certificate pair")
    ident = SigningIdentity(
        label=cert.subject.rfc4514_string(),
        subject=cert.subject.rfc4514_string(),
        issuer=cert.issuer.rfc4514_string(),
        not_before=cert.not_valid_before_utc.isoformat(),
        not_after=cert.not_valid_after_utc.isoformat(),
        expired=cert.not_valid_after_utc < datetime.now(timezone.utc),
        _cert=cert,
        _key=key,
    )
    return ident


def identity_summary(ident: SigningIdentity) -> dict:
    return {
        "subject": ident.subject,
        "issuer": ident.issuer,
        "valid_from": ident.not_before,
        "valid_to": ident.not_after,
        "expired": ident.expired,
    }


def sign_pdf(source: Path, target: Path, identity: SigningIdentity,
             reason: str = "", location: str = "", *,
             visible_rect: tuple | None = None, page: int = 0) -> Path:
    """Apply a real cryptographic (PAdES-style) signature using pyHanko.

    Raises RuntimeError with an honest explanation when pyHanko is not
    installed — we never fake a signature with an image.
    """
    if not HAS_PYHANKO:
        raise RuntimeError(
            "Cryptographic PDF signing requires the 'pyhanko' package "
            "(pip install pyhanko). OmniReader does not fake signatures by "
            "stamping images.")
    signer = signers.SimpleSigner.load(
        key_data=identity._key.private_bytes(
            encoding=__import__("cryptography.hazmat.primitives.serialization",
                                fromlist=["Encoding"]).Encoding.PEM,
            format=__import__("cryptography.hazmat.primitives.serialization",
                              fromlist=["PrivateFormat"]).PrivateFormat.PKCS8,
            encryption_algorithm=__import__(
                "cryptography.hazmat.primitives.serialization",
                fromlist=["NoEncryption"]).NoEncryption()),
        cert_data=identity._cert.public_bytes(
            __import__("cryptography.hazmat.primitives.serialization",
                       fromlist=["Encoding"]).Encoding.PEM),
        key_passphrase=None,
    )
    if signer is None:
        raise RuntimeError("Could not build a signer from this identity")
    pdf_signer = signers.PdfSigner(
        signers.PdfSignatureMetadata(field_name="OmniReader-Signature",
                                     reason=reason or None,
                                     location=location or None),
        signer=signer,
    )
    with open(source, "rb") as inf, open(target, "wb") as outf:
        pdf_signer.sign(inf, outf)
    return Path(target)


def verify_pdf_signatures(pdf_path: Path) -> list[dict]:
    """Verify signatures when pyHanko is available; otherwise report
    structural presence via pypdf. Always honest about what was checked."""
    results = []
    if HAS_PYHANKO:
        try:
            from pyhanko_certvalidator import ValidationContext
            from pyhanko.pdf_utils.reader import PdfFileReader
            with open(pdf_path, "rb") as fh:
                reader = PdfFileReader(fh)
                for info in reader.embedded_signatures:
                    try:
                        status = info.compute_integrity_info()
                        results.append({
                            "field": info.field_name if hasattr(info, "field_name") else "?",
                            "intact": status.valid,
                            "verified": False,  # full chain validation is offline-limited
                            "detail": "Document integrity verified; certificate "
                                      "chain not validated (no trust store configured)",
                        })
                    except Exception as e:
                        results.append({
                            "field": "?", "intact": False, "verified": False,
                            "detail": f"Integrity check failed: {e}"})
        except Exception as e:
            logger.debug("pyhanko verify failed: %s", e)
    # Structural fallback: list signature fields via the PDF engine.
    try:
        from omnireader_pro.core.documents.pdf_engine import PdfEngine
        engine = PdfEngine(pdf_path)
        for info in engine.signature_info():
            results.append({
                "field": info["name"],
                "intact": None,
                "verified": False,
                "detail": "Signature field present; install pyhanko for "
                          "integrity verification" if info["signed"] else
                          "Unsigned signature field",
            })
        engine.close()
    except Exception:
        pass
    return results
