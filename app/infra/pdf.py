"""PDF text extraction.

Replaces app/document_processor.py, whose split_documents_into_chunks() was superseded by
app/domain/chunking.py (article-aware) and had zero callers left. Deleting it also drops
langchain-text-splitters and langchain-core.documents from the ingest path — the corpus is
now split on article boundaries, not on character counts, because the article is the atomic
unit of law and a chunk straddling two of them cannot be cited as either.
"""
from pathlib import Path

import fitz  # PyMuPDF

from app.core.logging import get_logger

log = get_logger(__name__)


def extract_text(pdf_path: str | Path) -> str:
    try:
        with fitz.open(pdf_path) as document:
            return "\n".join(page.get_text("text") for page in document)
    except Exception:
        log.exception("pdf_extraction_failed", path=str(pdf_path))
        return ""
