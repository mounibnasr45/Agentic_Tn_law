from pathlib import Path

import fitz  # PyMuPDF
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)


def extract_text_from_pdf(pdf_path: str | Path) -> str:
    try:
        with fitz.open(pdf_path) as doc:
            return "\n".join(page.get_text("text") for page in doc)
    except Exception:
        log.exception("pdf_extraction_failed", path=str(pdf_path))
        return ""


def load_specific_documents() -> list[Document]:
    """Load the corpus files named in settings, skipping any that are absent."""
    settings = get_settings()
    docs: list[Document] = []

    for filename in settings.default_document_filenames:
        path = settings.documents_dir / filename
        if not path.exists():
            log.warning("corpus_document_missing", filename=filename, path=str(path))
            continue

        if path.suffix.lower() != ".pdf":
            continue

        text = extract_text_from_pdf(path)
        if text:
            docs.append(Document(page_content=text, metadata={"source": filename}))

    log.info("corpus_loaded", document_count=len(docs))
    return docs


def split_documents_into_chunks(
    documents: list[Document],
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[Document]:
    """Split documents into chunks.

    chunk_size/chunk_overlap default to None rather than to config values. A
    `chunk_size=config.CHUNK_SIZE` default is evaluated once at import, so it
    freezes the value for the life of the process and cannot be overridden per
    call or per test — which is exactly why nothing here was configurable.
    """
    settings = get_settings()
    chunk_size = settings.chunk_size if chunk_size is None else chunk_size
    chunk_overlap = settings.chunk_overlap if chunk_overlap is None else chunk_overlap

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        is_separator_regex=False,
    )

    split_docs: list[Document] = []
    for doc_idx, doc in enumerate(documents):
        chunks = splitter.split_text(doc.page_content)
        for chunk_idx, chunk_text in enumerate(chunks):
            split_docs.append(
                Document(
                    page_content=chunk_text,
                    metadata={
                        **doc.metadata,
                        "doc_id": f"doc_{doc_idx}",
                        "chunk_num": chunk_idx + 1,
                        "total_chunks_in_doc": len(chunks),
                    },
                )
            )

    log.info(
        "documents_chunked",
        document_count=len(documents),
        chunk_count=len(split_docs),
        chunk_size=chunk_size,
    )
    return split_docs
