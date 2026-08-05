"""PDF text extraction, via PyMuPDF."""
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
