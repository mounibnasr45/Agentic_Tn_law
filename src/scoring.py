"""Pure scoring maths for hybrid retrieval.

Deliberately free of faiss / sentence-transformers / chroma imports so the
ranking logic can be tested (and swept for the retrieval eval) without loading
an embedding model.
"""
import numpy as np


def normalize_bm25(scores: np.ndarray) -> np.ndarray:
    """Min-max BM25 scores into [0, 1].

    A query whose terms appear in no document yields an all-zero score vector;
    min == max there, so scale to zeros rather than dividing by zero.
    """
    scores = np.asarray(scores, dtype=float)
    if scores.size == 0:
        return scores

    lo, hi = float(np.min(scores)), float(np.max(scores))
    if hi == lo:
        return np.zeros_like(scores) if hi == 0 else np.ones_like(scores)
    return (scores - lo) / (hi - lo)


def normalize_semantic(scores: np.ndarray) -> np.ndarray:
    """Clip cosine similarities into [0, 1] so they share BM25's scale."""
    return np.clip(np.asarray(scores, dtype=float), 0.0, 1.0)


def combine_scores(
    bm25_scores: np.ndarray,
    semantic_scores: np.ndarray,
    weight_bm25: float,
) -> np.ndarray:
    """Blend the two normalized signals. Semantic weight is 1 - weight_bm25."""
    if not 0.0 <= weight_bm25 <= 1.0:
        raise ValueError(f"weight_bm25 must be in [0, 1], got {weight_bm25}")

    bm25_scores = np.asarray(bm25_scores, dtype=float)
    semantic_scores = np.asarray(semantic_scores, dtype=float)
    if bm25_scores.shape != semantic_scores.shape:
        raise ValueError(
            f"score vectors must align: {bm25_scores.shape} vs {semantic_scores.shape}"
        )

    return weight_bm25 * bm25_scores + (1.0 - weight_bm25) * semantic_scores


def top_k_indices(scores: np.ndarray, k: int) -> list[int]:
    """Indices of the k highest scores, best first. Never returns more than exist."""
    scores = np.asarray(scores, dtype=float)
    k = min(max(k, 0), scores.size)
    if k == 0:
        return []
    return [int(i) for i in np.argsort(scores)[-k:][::-1]]
