"""Combining the lexical and dense retrieval arms.

The in-memory retriever scored the WHOLE corpus with both arms, so the two score
vectors were already aligned and could be blended element-wise. Moving retrieval into
SQL changes that: each arm returns only its own top-N, so the candidate sets differ
and must be unioned before they can be blended.

Two strategies live here, and which one is better is a measured result rather than an
opinion — both are arms in the ablation harness.
"""
import numpy as np


def align_candidates(
    lexical: dict[int, float],
    dense: dict[int, float],
) -> tuple[list[int], np.ndarray, np.ndarray]:
    """Union two candidate sets into aligned score vectors.

    Returns (chunk_ids, lexical_scores, dense_scores) where all three are index-aligned,
    so the result can be handed straight to scoring.combine_scores().

    KNOWN BIAS, worth stating out loud: a chunk that is absent from one arm's top-N is
    scored 0.0 for that arm. That is NOT the same as "its score was low but positive" —
    we simply never asked. Score-level fusion over truncated candidate lists always has
    this bias, and it grows as the candidate limit shrinks. reciprocal_rank_fusion()
    below sidesteps it by never comparing raw scores at all.
    """
    chunk_ids = sorted(set(lexical) | set(dense))

    lexical_scores = np.array([lexical.get(cid, 0.0) for cid in chunk_ids], dtype=float)
    dense_scores = np.array([dense.get(cid, 0.0) for cid in chunk_ids], dtype=float)

    return chunk_ids, lexical_scores, dense_scores


def reciprocal_rank_fusion(
    *rankings: dict[int, float],
    k: int = 60,
) -> dict[int, float]:
    """Fuse rankings by position rather than by score: sum of 1 / (k + rank).

    Ranks are 1-based and derived per-arm by sorting on that arm's own score, so the
    two arms' score SCALES never meet — which is the whole point. BM25 scores are
    unbounded and corpus-dependent while cosine similarity is bounded [0,1]; min-max
    normalising them onto a common range (what combine_scores does) is a defensible
    approximation, not a principled one.

    k=60 is the value from the original Cormack et al. paper and is the near-universal
    default. It damps the influence of the top ranks: without it, rank 1 would dominate
    rank 2 by 2x, which makes the fusion brittle to a single arm's mistake.
    """
    fused: dict[int, float] = {}

    for ranking in rankings:
        ordered = sorted(ranking.items(), key=lambda kv: kv[1], reverse=True)
        for rank, (chunk_id, _score) in enumerate(ordered, start=1):
            fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (k + rank)

    return fused
