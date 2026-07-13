"""Retrieval metrics. Pure arithmetic — no LLM, no network, no cost, deterministic.

Retrieval is a ranking problem, and ranking has real metrics. Grading it with an LLM
judge would be nondeterministic (the same run scores differently), cost money on every
execution, and be unable to gate a CI job — you cannot fail a build on a number that
wobbles. Everything here is a division.

RELEVANCE IS DEFINED AT ARTICLE LEVEL. A long article is split across several chunks
(see domain/chunking.py), and retrieving any one of its parts means the retriever found
the right law. Scoring at chunk level would punish the retriever for our own chunking
decisions rather than for its ranking.
"""
import math
from collections.abc import Sequence
from dataclasses import dataclass

# (source, article_number) — e.g. ("penal_code.pdf", "Article 258")
Label = tuple[str, str | None]


def _first_relevant_rank(retrieved: Sequence[Label], expected: Label) -> int | None:
    """1-based rank of the first correct article, or None if it never appears."""
    for rank, label in enumerate(retrieved, start=1):
        if label == expected:
            return rank
    return None


def hit_at_k(retrieved: Sequence[Label], expected: Label, k: int) -> bool:
    """Did the right article appear anywhere in the top k?"""
    rank = _first_relevant_rank(retrieved[:k], expected)
    return rank is not None


def reciprocal_rank(retrieved: Sequence[Label], expected: Label) -> float:
    """1/rank of the first correct article; 0.0 if absent.

    Rewards putting the answer HIGH, not merely somewhere in the list. Rank 1 scores
    1.0, rank 2 scores 0.5, rank 10 scores 0.1. A system that always finds the article
    at rank 9 has a perfect hit-rate@10 and a terrible MRR — and it is a bad system,
    because the LLM's context window is the real budget and rank 9 may not fit in it.
    """
    rank = _first_relevant_rank(retrieved, expected)
    return 1.0 / rank if rank else 0.0


def ndcg_at_k(retrieved: Sequence[Label], expected: Label, k: int) -> float:
    """Normalised discounted cumulative gain, binary relevance, single relevant item.

    With exactly one relevant item the ideal DCG is 1.0 (it sits at rank 1), so this
    reduces to 1 / log2(rank + 1). It discounts more gently than MRR — rank 2 scores
    0.63 rather than 0.5 — which is the more forgiving view of "close to the top".
    Reported alongside MRR because the two disagree about how much rank 2 hurts, and
    that disagreement is informative.
    """
    rank = _first_relevant_rank(retrieved[:k], expected)
    return 1.0 / math.log2(rank + 1) if rank else 0.0


@dataclass(frozen=True, slots=True)
class Metrics:
    n: int
    hit_rate_at_1: float
    hit_rate_at_3: float
    hit_rate_at_5: float
    hit_rate_at_10: float
    mrr: float
    ndcg_at_10: float

    def as_row(self) -> dict[str, float]:
        return {
            "hit@1": self.hit_rate_at_1,
            "hit@3": self.hit_rate_at_3,
            "hit@5": self.hit_rate_at_5,
            "hit@10": self.hit_rate_at_10,
            "MRR": self.mrr,
            "nDCG@10": self.ndcg_at_10,
        }


def evaluate(results: Sequence[tuple[Sequence[Label], Label]]) -> Metrics:
    """Aggregate per-query rankings into one score.

    `results` is [(retrieved_labels_best_first, expected_label), ...].
    """
    if not results:
        return Metrics(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    n = len(results)

    def mean(values) -> float:
        return sum(values) / n

    return Metrics(
        n=n,
        hit_rate_at_1=mean(hit_at_k(r, e, 1) for r, e in results),
        hit_rate_at_3=mean(hit_at_k(r, e, 3) for r, e in results),
        hit_rate_at_5=mean(hit_at_k(r, e, 5) for r, e in results),
        hit_rate_at_10=mean(hit_at_k(r, e, 10) for r, e in results),
        mrr=mean(reciprocal_rank(r, e) for r, e in results),
        ndcg_at_10=mean(ndcg_at_k(r, e, 10) for r, e in results),
    )
