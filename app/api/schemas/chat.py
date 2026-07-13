from pydantic import BaseModel, Field


class Citation(BaseModel):
    """A real citation, carrying the chunk it came from.

    BUG 4 was that `sources` was a hardcoded placeholder string: the retrieval tool
    flattened its results into truncated text, so scores, chunk ids and article numbers
    could never reach the caller. This type is the structural fix — the API cannot return
    a citation it did not actually retrieve.
    """

    chunk_id: int
    source: str
    article_number: str | None
    score: float
    rank: int
    excerpt: str


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)


class AskResponse(BaseModel):
    answer: str
    citations: list[Citation]


class SearchResponse(BaseModel):
    """Retrieval only — no LLM. Cheap, deterministic, and the honest way to show what the
    retriever actually returns without an LLM paraphrasing over its mistakes."""

    query: str
    retrieval_type: str
    results: list[Citation]
