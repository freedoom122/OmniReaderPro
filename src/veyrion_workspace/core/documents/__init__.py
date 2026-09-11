"""Document engines and the format registry."""
from veyrion_workspace.core.documents.base import (
    Capability,
    CorruptDocumentError,
    DocumentEngine,
    DocumentError,
    DocumentMetadata,
    EncryptedDocumentError,
    PageInfo,
    TocEntry,
)
from veyrion_workspace.core.documents.registry import open_document

__all__ = [
    "Capability", "CorruptDocumentError", "DocumentEngine", "DocumentError",
    "DocumentMetadata", "EncryptedDocumentError", "PageInfo", "TocEntry",
    "open_document",
]
