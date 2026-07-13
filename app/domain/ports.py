"""Ports: the interfaces the domain depends on.

The old HybridRetriever imported SentenceTransformer, Chroma, BM25Okapi and faiss
directly, so testing the ranking logic meant downloading a 470MB model and standing
up a vector store. Depending on these Protocols instead means the retriever can be
exercised against in-memory fakes — which is also what lets the eval harness sweep
fusion weights offline, with no database and no network.
"""
from collections.abc import Sequence
from typing import Protocol

import numpy as np

from app.domain.models import ChunkRecord


class Embedder(Protocol):
    @property
    def model_name(self) -> str: ...

    @property
    def dimensions(self) -> int: ...

    async def embed_query(self, text: str) -> np.ndarray: ...

    async def embed_documents(self, texts: Sequence[str]) -> np.ndarray: ...


class ChunkRepository(Protocol):
    """Storage for chunks and both retrieval arms.

    Both candidate methods return {chunk_id: score}, higher is better, already
    truncated to `limit`. Returning a mapping rather than a list is deliberate: the
    two arms must be unioned by id, and the union is the only place the two score
    scales meet.
    """

    async def dense_candidates(
        self, embedding: np.ndarray, limit: int
    ) -> dict[int, float]: ...

    async def lexical_candidates(self, query: str, limit: int) -> dict[int, float]: ...

    async def fetch(self, chunk_ids: Sequence[int]) -> dict[int, ChunkRecord]: ...

    async def count(self) -> int: ...


class Reranker(Protocol):
    async def rerank(
        self, query: str, candidates: Sequence[ChunkRecord], top_k: int
    ) -> list[tuple[int, float]]:
        """Return (chunk_id, score) best-first."""
        ...
