"""In-memory fakes for the domain ports.

These exist because the domain depends on Protocols rather than on SentenceTransformer
and Postgres. That is the whole payoff of the ports layer: the ranking logic is tested
here in milliseconds, with no model download, no database and no network — and the
eval harness reuses these same fakes to sweep fusion weights offline in CI.
"""
from collections.abc import Sequence

import numpy as np

from app.domain.models import ChunkRecord
from app.infra.db.models import EMBEDDING_DIMENSIONS


class FakeEmbedder:
    """Deterministic bag-of-words embedder over a fixed vocabulary.

    Not a random vector generator: cosine similarity between these embeddings is
    *meaningful*, so a test can assert that a query about theft ranks the theft article
    above the treason article, and the assertion means something.
    """

    VOCABULARY = ("vol", "peine", "prison", "constitution", "president", "liberte")

    def __init__(
        self, model_name: str = "fake-embedder", dimensions: int = EMBEDDING_DIMENSIONS
    ) -> None:
        self._model_name = model_name
        # Padded to the production dimension so these vectors are storable in the real
        # vector(384) column. The chunks.embedding column enforces its width, which is
        # a feature: it makes an accidental encoder swap fail loudly at write time
        # rather than silently poisoning the index with incompatible geometry.
        self._dimensions = dimensions

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def _encode(self, text: str) -> np.ndarray:
        lowered = text.lower()

        vector = np.zeros(self._dimensions, dtype=float)
        for i, term in enumerate(self.VOCABULARY):
            vector[i] = float(lowered.count(term))

        norm = np.linalg.norm(vector)
        return vector / norm if norm else vector  # unit-normalised, as in production

    async def embed_query(self, text: str) -> np.ndarray:
        return self._encode(text)

    async def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, self.dimensions))
        return np.vstack([self._encode(t) for t in texts])


class FakeChunkRepository:
    """Durable-by-construction chunk store.

    The key property, and the reason bug 1 cannot recur: this fake holds the corpus and
    answers BOTH arms from it. There is no in-memory index built at startup that a cold
    process could fail to restore. Postgres behaves the same way — that is the point of
    moving retrieval into it.
    """

    def __init__(self, records: Sequence[ChunkRecord], embedder: FakeEmbedder) -> None:
        self._records = {record.id: record for record in records}
        self._embedder = embedder
        self._embeddings = {
            record.id: embedder._encode(record.content) for record in records
        }

    async def dense_candidates(self, embedding: np.ndarray, limit: int) -> dict[int, float]:
        scored = {
            chunk_id: float(np.dot(embedding, vector))  # both unit-norm -> cosine similarity
            for chunk_id, vector in self._embeddings.items()
        }
        return dict(sorted(scored.items(), key=lambda kv: kv[1], reverse=True)[:limit])

    async def lexical_candidates(self, query: str, limit: int) -> dict[int, float]:
        terms = set(query.lower().split())
        scored: dict[int, float] = {}
        for chunk_id, record in self._records.items():
            content = record.content.lower()
            overlap = sum(content.count(term) for term in terms)
            if overlap:
                scored[chunk_id] = float(overlap)
        return dict(sorted(scored.items(), key=lambda kv: kv[1], reverse=True)[:limit])

    async def fetch(self, chunk_ids: Sequence[int]) -> dict[int, ChunkRecord]:
        return {cid: self._records[cid] for cid in chunk_ids if cid in self._records}

    async def count(self) -> int:
        return len(self._records)
