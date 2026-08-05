"""Hybrid retrieval: runs the dense and lexical arms, fuses their candidates, and
returns the ranked chunks."""
from enum import StrEnum

from app.core.logging import get_logger
from app.domain.fusion import align_candidates, reciprocal_rank_fusion
from app.domain.models import RetrievedChunk
from app.domain.ports import ChunkRepository, Embedder
from app.domain.scoring import (
    combine_scores,
    normalize_bm25,
    normalize_semantic,
    top_k_indices,
)

log = get_logger(__name__)

# How many candidates to pull from each arm before fusing. Larger = less truncation
# bias in align_candidates (a chunk missing from one arm is scored 0.0 for that arm),
# at the cost of a wider SQL scan. This is an ablation axis, not a constant of nature.
DEFAULT_CANDIDATE_LIMIT = 50


class FusionStrategy(StrEnum):
    WEIGHTED = "weighted"  # min-max normalise both arms, blend by weight
    RRF = "rrf"  # fuse by rank; the two score scales never meet


class HybridRetriever:
    def __init__(
        self,
        embedder: Embedder,
        repository: ChunkRepository,
        candidate_limit: int = DEFAULT_CANDIDATE_LIMIT,
    ) -> None:
        self._embedder = embedder
        self._repository = repository
        self._candidate_limit = candidate_limit

    async def search(
        self,
        query: str,
        top_k: int,
        weight_bm25: float = 0.4,
        fusion: FusionStrategy = FusionStrategy.WEIGHTED,
    ) -> list[RetrievedChunk]:
        if not query.strip() or top_k <= 0:
            return []

        embedding = await self._embedder.embed_query(query)

        # SEQUENTIAL, DELIBERATELY. This used asyncio.gather() to run the two arms
        # concurrently, which looks like free parallelism and is in fact a latent crash:
        # a SQLAlchemy AsyncSession is NOT safe for concurrent use. Two coroutines racing
        # to provision the same connection raise
        #
        #     InvalidRequestError: This session is provisioning a new connection;
        #     concurrent operations are not permitted
        #
        # and it only fires on a session that has not yet opened a connection — so it
        # passes every warm test and fails intermittently on the first query of a fresh
        # request. Exactly the kind of bug that reaches production and then cannot be
        # reproduced.
        #
        # Making this genuinely concurrent would mean one session per arm, which drags
        # transaction semantics into the domain layer for a saving of a few milliseconds
        # against a local Postgres. If it ever matters, the right move is one round trip:
        # both arms as CTEs in a single statement.
        dense = await self._repository.dense_candidates(embedding, self._candidate_limit)
        lexical = await self._repository.lexical_candidates(query, self._candidate_limit)

        if not dense and not lexical:
            log.info("no_candidates", query_length=len(query))
            return []

        if fusion is FusionStrategy.RRF:
            fused = reciprocal_rank_fusion(lexical, dense)
            chunk_ids = sorted(fused, key=lambda cid: fused[cid], reverse=True)[:top_k]
            scores = [fused[cid] for cid in chunk_ids]
            retrieval_type = "rrf"
        else:
            candidate_ids, lexical_scores, dense_scores = align_candidates(lexical, dense)

            combined = combine_scores(
                normalize_bm25(lexical_scores),
                normalize_semantic(dense_scores),
                weight_bm25,
            )

            selected = top_k_indices(combined, top_k)
            chunk_ids = [candidate_ids[i] for i in selected]
            scores = [float(combined[i]) for i in selected]
            retrieval_type = _describe(weight_bm25)

        records = await self._repository.fetch(chunk_ids)

        results = [
            RetrievedChunk(
                chunk_id=chunk_id,
                content=records[chunk_id].content,
                source=records[chunk_id].source,
                article_number=records[chunk_id].article_number,
                score=score,
                rank=rank,
                retrieval_type=retrieval_type,
            )
            for rank, (chunk_id, score) in enumerate(zip(chunk_ids, scores, strict=True), start=1)
            if chunk_id in records  # a chunk deleted between candidate and fetch
        ]

        log.info(
            "search_complete",
            result_count=len(results),
            retrieval_type=retrieval_type,
            dense_candidates=len(dense),
            lexical_candidates=len(lexical),
        )
        return results


def _describe(weight_bm25: float) -> str:
    """The weight IS the arm: 1.0 is lexical-only, 0.0 is dense-only, between is hybrid.

    Naming it honestly matters — the regression test for bug 1 asserts on this value,
    and the whole point is that a deployed process must not quietly report "hybrid"
    while doing something else.
    """
    if weight_bm25 >= 1.0:
        return "lexical"
    if weight_bm25 <= 0.0:
        return "dense"
    return "hybrid"
