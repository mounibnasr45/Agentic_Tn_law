"""Request/response models for conversations and their message history."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.api.schemas.chat import Citation


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    # None starts a new thread. Naming an existing one continues it — and the service
    # checks it belongs to the caller, because LangGraph will not.
    conversation_id: uuid.UUID | None = None
    # Which language the ANSWER is written in; the corpus stays French either way, so
    # cited articles are still quoted in French. Defaults to French because that is the
    # language of the texts, and a client that never sends the field keeps working.
    language: Literal["fr", "en"] = "fr"


class TraceResult(BaseModel):
    """One retrieved hit, as shown in the trace panel."""

    article_number: str | None
    score: float
    rank: int


class TraceStepResponse(BaseModel):
    kind: str  # retrieval | reflection | answer
    label: str
    # The query the AGENT composed. Rendering it next to the user's question is the single
    # clearest signal that something reasoned between the two.
    query: str | None = None
    results: list[TraceResult] = []
    detail: str | None = None


class TraceResponse(BaseModel):
    """What the agent did to produce this answer.

    Live-only and not persisted: it describes one run against one corpus version, so
    replaying it beside an old message would show a trace that no longer corresponds to
    anything. `history` therefore returns messages without traces, which is honest.
    """

    steps: list[TraceStepResponse]
    # Shown as "2 / 4" — evidence the agentic loop has a deliberate ceiling rather than
    # running until the model gets bored.
    iterations_used: int
    max_iterations: int
    # True when the reflection checkpoint found an undefined legal term and re-retrieved.
    regrounded: bool


class AskResponse(BaseModel):
    conversation_id: uuid.UUID
    answer: str
    citations: list[Citation]
    trace: TraceResponse


class ConversationSummary(BaseModel):
    id: uuid.UUID
    title: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    role: str
    content: str
    latency_ms: int | None
    created_at: datetime

    model_config = {"from_attributes": True}
