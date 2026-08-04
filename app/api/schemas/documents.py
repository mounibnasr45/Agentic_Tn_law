import uuid
from datetime import datetime

from pydantic import BaseModel


class CorpusDocumentOut(BaseModel):
    """A source document as the reader-facing viewer needs it.

    Deliberately NOT admin.DocumentOut, which carries ingestion machinery — chunks_done,
    error, corpus_version. Those answer "is the pipeline healthy", which is an operator's
    question; this answers "what can I read", which is a reader's. Sharing one schema
    would leak the first set of concerns onto a page that has no use for them, and would
    couple a public surface to a model that changes whenever ingestion does.
    """

    id: uuid.UUID
    title: str
    # Bytes on disk, so the UI can warn before a slow load rather than after it.
    size_bytes: int
    # Chunks derived from THIS document — the honest measure of how much of it the agent
    # can actually cite, and 0 for a document that failed to index.
    chunk_count: int
    indexed_at: datetime | None
