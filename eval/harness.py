"""Run the golden set against a retrieval configuration."""
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from app.domain.ports import ChunkRepository, Embedder
from app.domain.retrieval import HybridRetriever
from eval.metrics import Label, Metrics, evaluate

GOLDEN_SET = Path(__file__).parent / "golden_set.json"


@dataclass(frozen=True, slots=True)
class Question:
    id: int
    question: str
    expected: Label


def load_golden_set(path: Path = GOLDEN_SET) -> list[Question]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [
        Question(
            id=q["id"],
            question=q["question"],
            expected=(q["expected_source"], q["expected_article"]),
        )
        for q in payload["questions"]
    ]


@dataclass(frozen=True, slots=True)
class Config:
    """One arm of the ablation."""

    name: str
    weight_bm25: float = 0.4
    fusion: str = "weighted"
    top_k: int = 10
    candidate_limit: int = 50


async def run(
    config: Config,
    embedder: Embedder,
    repository: ChunkRepository,
    questions: Sequence[Question],
) -> tuple[Metrics, list[dict]]:
    """Score one configuration. Returns aggregate metrics plus the per-question detail.

    The per-question detail is what makes the harness useful rather than decorative: an
    aggregate number tells you the system got worse, the detail tells you WHICH questions
    broke, which is the only thing you can act on.
    """
    from app.domain.retrieval import FusionStrategy

    retriever = HybridRetriever(embedder, repository, config.candidate_limit)
    strategy = FusionStrategy(config.fusion)

    scored: list[tuple[list[Label], Label]] = []
    detail: list[dict] = []

    for question in questions:
        chunks = await retriever.search(
            question.question,
            top_k=config.top_k,
            weight_bm25=config.weight_bm25,
            fusion=strategy,
        )

        # Article-level relevance, de-duplicated: a long article split into three chunks
        # must not occupy three of the top-10 slots in the ranking we score. We keep the
        # best-ranked chunk per article and score the article ranking.
        labels: list[Label] = []
        for chunk in chunks:
            label = (chunk.source, chunk.article_number)
            if label not in labels:
                labels.append(label)

        scored.append((labels, question.expected))
        detail.append(
            {
                "id": question.id,
                "question": question.question,
                "expected": f"{question.expected[1]} ({question.expected[0]})",
                "found_at_rank": next(
                    (i for i, label in enumerate(labels, 1) if label == question.expected),
                    None,
                ),
                "top_3": [f"{label[1]}" for label in labels[:3]],
            }
        )

    return evaluate(scored), detail
