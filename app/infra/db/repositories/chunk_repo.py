"""Postgres-backed ChunkRepository: both retrieval arms, as SQL."""
from collections.abc import Sequence

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import ChunkRecord
from app.infra.db.models import Chunk, Document

# The Postgres text-search configuration created in migration 0001. Plain 'french'
# does not strip accents, so a query for "francais" would miss "français" — which in a
# French legal corpus is not an edge case, it is most of the corpus.
FRENCH_CONFIG = "french_unaccent"


class PostgresChunkRepository:
    """Implements the ChunkRepository port.

    Both arms read from durable, transactional storage. Nothing is built at startup and
    nothing is cached in the process, so a cold worker answers exactly like a warm one.
    That property IS the fix for bug 1.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def dense_candidates(self, embedding: np.ndarray, limit: int) -> dict[int, float]:
        # THE TRAP: pgvector's <=> is cosine DISTANCE — 0.0 means identical, 2.0 means
        # opposite. Lower is better. Our scoring pipeline expects a SIMILARITY where
        # higher is better (normalize_semantic clips to [0,1]). Hand the distance
        # straight through and the dense arm ranks BACKWARDS — while still returning
        # plausible-looking French legal text, so nothing looks obviously wrong. The
        # conversion below is not a nicety.
        distance = Chunk.embedding.cosine_distance(embedding.tolist())

        rows = await self._session.execute(
            select(Chunk.id, (1 - distance).label("similarity"))
            .order_by(distance)  # ascending distance == descending similarity
            .limit(limit)
        )
        return {chunk_id: float(similarity) for chunk_id, similarity in rows}

    async def lexical_candidates(self, query: str, limit: int) -> dict[int, float]:
        # websearch_to_tsquery, not plainto_tsquery: it tolerates the punctuation and
        # quoting real users type, instead of raising a syntax error on an apostrophe —
        # and French legal queries are full of apostrophes.
        tsquery = func.websearch_to_tsquery(FRENCH_CONFIG, query)

        # ts_rank_cd, not ts_rank: the cover-density variant rewards query terms that
        # appear NEAR each other. "peine" and "vol" adjacent is a much stronger signal
        # than the two words at opposite ends of a long article.
        rank = func.ts_rank_cd(Chunk.tsv, tsquery)

        rows = await self._session.execute(
            select(Chunk.id, rank.label("rank"))
            .where(Chunk.tsv.op("@@")(tsquery))
            .order_by(rank.desc())
            .limit(limit)
        )
        return {chunk_id: float(score) for chunk_id, score in rows}

    async def fetch(self, chunk_ids: Sequence[int]) -> dict[int, ChunkRecord]:
        if not chunk_ids:
            return {}

        rows = await self._session.execute(
            select(
                Chunk.id,
                Chunk.content,
                Chunk.chunk_index,
                Chunk.article_number,
                Document.title,
            )
            .join(Document, Chunk.document_id == Document.id)
            .where(Chunk.id.in_(chunk_ids))
        )

        return {
            row.id: ChunkRecord(
                id=row.id,
                content=row.content,
                source=row.title,
                chunk_index=row.chunk_index,
                article_number=row.article_number,
            )
            for row in rows
        }

    async def count(self) -> int:
        result = await self._session.execute(select(func.count()).select_from(Chunk))
        return int(result.scalar_one())
