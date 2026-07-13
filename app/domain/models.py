"""Domain types. Plain dataclasses — no ORM, no framework, no I/O."""
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Chunk:
    """A piece of a legal document, before it is persisted."""

    content: str
    source: str
    chunk_index: int
    article_number: str | None = None
    part_index: int | None = None  # set only when one article had to be split


@dataclass(frozen=True, slots=True)
class ChunkRecord:
    """A chunk as it exists in storage."""

    id: int
    content: str
    source: str
    chunk_index: int
    article_number: str | None = None


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    """A chunk returned by a search, with the score and rank that put it there.

    This is the type the retrieval tool returns to the agent. The old tool flattened
    results into a truncated string, which is why scores, chunk ids and article
    numbers could never reach the caller and `sources` ended up as a hardcoded
    placeholder (bug 4).
    """

    chunk_id: int
    content: str
    source: str
    article_number: str | None
    score: float
    rank: int
    retrieval_type: str  # "hybrid" | "dense" | "lexical" | "rrf"
