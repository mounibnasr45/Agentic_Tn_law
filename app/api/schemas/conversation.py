import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.api.schemas.chat import Citation


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    # None starts a new thread. Naming an existing one continues it — and the service
    # checks it belongs to the caller, because LangGraph will not.
    conversation_id: uuid.UUID | None = None


class AskResponse(BaseModel):
    conversation_id: uuid.UUID
    answer: str
    citations: list[Citation]


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
