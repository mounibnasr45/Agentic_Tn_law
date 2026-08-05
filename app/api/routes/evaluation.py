"""Serves the retrieval evaluation results to the UI, read from the same
eval/baseline.json CI gates against."""
import json
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter

from app.api.schemas.evaluation import (
    AblationArm,
    EncoderComparison,
    EvaluationResponse,
    GoldenSetInfo,
)
from app.core.config import get_settings
from app.core.errors import DomainError, to_http_exception

router = APIRouter(prefix="/evaluation", tags=["evaluation"])

# parents: [0]=routes [1]=api [2]=app [3]=project root. The eval/ directory is a sibling
# of app/, so it is [3] — not [2], which lands inside the package.
EVAL_DIR = Path(__file__).resolve().parents[3] / "eval"
BASELINE = EVAL_DIR / "baseline.json"
GOLDEN_SET = EVAL_DIR / "golden_set.json"


class EvaluationUnavailable(DomainError):
    status_code = 503
    detail = "Les résultats d'évaluation ne sont pas disponibles."


def _arm_label(name: str) -> str:
    """The retrieval strategy a weight actually denotes.

    The weight IS the arm: 0.0 is dense-only, 1.0 is lexical-only, between is hybrid. The
    ablation exists because that single axis produces all three strategies people normally
    hand-code as separate classes.
    """
    if "rrf" in name.lower():
        return "rrf"
    if "w=0.0" in name:
        return "dense"
    if "w=1.0" in name:
        return "lexical"
    return "hybrid"


@lru_cache
def _load() -> EvaluationResponse:
    """Read once. The files are build artefacts that cannot change while the app runs."""
    if not BASELINE.exists() or not GOLDEN_SET.exists():
        raise EvaluationUnavailable()

    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    golden = json.loads(GOLDEN_SET.read_text(encoding="utf-8"))

    arms = [
        AblationArm(
            name=name,
            arm=_arm_label(name),
            hit_at_1=m["hit@1"],
            hit_at_3=m["hit@3"],
            hit_at_5=m["hit@5"],
            hit_at_10=m["hit@10"],
            mrr=m["MRR"],
            ndcg_at_10=m["nDCG@10"],
        )
        for name, m in baseline["scores"].items()
    ]
    best = max(arms, key=lambda a: a.hit_at_5)

    questions = golden["questions"]
    sources = sorted({q["expected_source"] for q in questions})

    return EvaluationResponse(
        model=baseline["model"],
        corpus_chunks=baseline["corpus_chunks"],
        arms=arms,
        best_arm=best.name,
        deployed_weight_bm25=get_settings().hybrid_weight_bm25,
        golden_set=GoldenSetInfo(
            questions=len(questions),
            sources=sources,
            # Stated because it bounds every number on the page: with 56 questions one
            # flipped question moves hit@5 by 1/56 ≈ 1.8 points, so a 0.05 gap is about
            # three questions and may be noise.
            one_question_worth=1 / len(questions) if questions else 0.0,
        ),
        # BUG 13, kept on the page because it is the harness's strongest justification:
        # the encoder accepted 128 tokens while chunks were sized at 700 CHARACTERS, so
        # 38% of chunks were silently truncated before ever being embedded. No exception,
        # just a transformers warning. Only the eval numbers revealed it.
        encoder_fix=EncoderComparison(
            before_model="paraphrase-multilingual-MiniLM-L12-v2",
            before_max_tokens=128,
            before_hit_at_1=0.250,
            before_hit_at_5=0.500,
            before_mrr=0.364,
            after_model="intfloat/multilingual-e5-small",
            after_max_tokens=512,
            after_hit_at_1=0.679,
            after_hit_at_5=0.839,
            after_mrr=0.747,
            truncated_chunks=277,
            total_chunks=712,
            dropped_token_pct=11.3,
        ),
    )


@router.get("", response_model=EvaluationResponse)
async def evaluation() -> EvaluationResponse:
    try:
        return _load()
    except DomainError as exc:
        raise to_http_exception(exc) from exc
