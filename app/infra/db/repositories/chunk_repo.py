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
        """The lexical arm: OR the query's lexemes, rank by cover density.

        THE BUG THE EVAL HARNESS FOUND. This used websearch_to_tsquery, which ANDs
        unquoted terms: the question "Quelle est la peine pour un vol commis avec arme ?"
        compiles to

            'quel' & 'pein' & 'vol' & 'comm' & 'arme'

        and demands every one of those stems in a single chunk. Across 716 chunks of
        Tunisian law that matched EXACTLY ZERO. The lexical arm returned nothing for
        every natural-language question, so "hybrid" retrieval was silently identical to
        dense-only — the very bug we had just finished fixing, reintroduced one layer
        down. The ablation table made it obvious: every fusion weight from 0.0 to 0.8
        scored identically, and lexical-only scored ~0.

        AND-semantics is right for a search box where the user types keywords. It is
        wrong for a system whose users ask questions in sentences. OR-ing the lexemes and
        ranking by ts_rank_cd is the BM25-shaped behaviour we actually wanted: a chunk
        matching more query terms, more closely together, ranks higher.

        Building the query as `to_tsvector(q) -> lexemes -> 'a | b | c'` (rather than
        splitting the string in Python) means Postgres does the stemming, unaccenting and
        stop-word removal with the SAME configuration used to build the index. Hand-rolled
        tokenisation would drift from the index and silently lose matches.
        """
        if not query.strip():
            return {}

        lexemes = func.array_to_string(
            func.tsvector_to_array(func.to_tsvector(FRENCH_CONFIG, query)), " | "
        )
        tsquery = func.to_tsquery(FRENCH_CONFIG, lexemes)

        # ts_rank_cd, not ts_rank: the cover-density variant rewards query terms that
        # appear NEAR each other. "peine" next to "vol" is a far stronger signal than the
        # two words at opposite ends of a long article.
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
