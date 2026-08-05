"""Response model for the evaluation endpoint — the shape of eval/baseline.json
as the UI needs it."""
from pydantic import BaseModel


class AblationArm(BaseModel):
    """One retrieval configuration and its six ranking metrics."""

    name: str
    arm: str  # dense | hybrid | lexical | rrf
    hit_at_1: float
    hit_at_3: float
    hit_at_5: float
    hit_at_10: float
    mrr: float
    ndcg_at_10: float


class GoldenSetInfo(BaseModel):
    questions: int
    sources: list[str]
    # 1/questions. Published because it is the honest error bar on every number here: with
    # 56 questions a single flipped question moves a metric by 1.8 points, so small gaps
    # between arms are not meaningful.
    one_question_worth: float


class EncoderComparison(BaseModel):
    """Bug 13: the encoder that silently truncated the corpus, before and after."""

    before_model: str
    before_max_tokens: int
    before_hit_at_1: float
    before_hit_at_5: float
    before_mrr: float

    after_model: str
    after_max_tokens: int
    after_hit_at_1: float
    after_hit_at_5: float
    after_mrr: float

    truncated_chunks: int
    total_chunks: int
    dropped_token_pct: float


class EvaluationResponse(BaseModel):
    model: str
    corpus_chunks: int
    arms: list[AblationArm]
    best_arm: str
    # What the app actually ships. Displayed next to the winning arm so the page shows the
    # measurement AND the decision taken from it — 0.0 means dense-only, which is what won.
    deployed_weight_bm25: float
    golden_set: GoldenSetInfo
    encoder_fix: EncoderComparison

    # Pydantic reserves the `model_` prefix; `model` is a legitimate field name here and
    # the warning it triggers is noise.
    model_config = {"protected_namespaces": ()}
