"""Document engines and the format registry."""
from omnireader_pro.core.documents.base import (
    Capability,
    CorruptDocumentError,
    DocumentEngine,
    DocumentError,
    DocumentMetadata,
    EncryptedDocumentError,
    PageInfo,
    TocEntry,
)
from omnireader_pro.core.documents.registry import open_document

__all__ = [
    "Capability", "CorruptDocumentError", "DocumentEngine", "DocumentError",
    "DocumentMetadata", "EncryptedDocumentError", "PageInfo", "TocEntry",
    "open_document",
]
