import uuid

from fastapi import APIRouter, Request

from app.api.deps import CurrentUser, EmbedderDep, SessionDep
from app.api.schemas.chat import Citation
from app.api.schemas.conversation import (
    AskRequest,
    AskResponse,
    ConversationSummary,
    MessageResponse,
)
from app.core.errors import DomainError, to_http_exception
from app.services.chat_service import ChatService

router = APIRouter(tags=["chat"])


def _service(request: Request, session: SessionDep, embedder: EmbedderDep) -> ChatService:
    return ChatService(session, embedder, request.app.state.checkpointer)


@router.post("/ask", response_model=AskResponse)
async def ask(
    payload: AskRequest,
    user: CurrentUser,
    request: Request,
    session: SessionDep,
    embedder: EmbedderDep,
) -> AskResponse:
    try:
        answer = await _service(request, session, embedder).ask(
            user, payload.question, payload.conversation_id
        )
    except DomainError as exc:
        # BUG 3: an LLM failure becomes a 502, not a 200 whose body is the exception text.
        raise to_http_exception(exc) from exc

    return AskResponse(
        conversation_id=answer.conversation_id,
        answer=answer.answer,
        citations=[
            Citation(
                chunk_id=c.chunk_id,
                source=c.source,
                article_number=c.article_number,
                score=c.score,
                rank=c.rank,
                excerpt=c.content[:400],
            )
            for c in answer.citations
        ],
    )


@router.get("/conversations", response_model=list[ConversationSummary])
async def list_conversations(
    user: CurrentUser, request: Request, session: SessionDep, embedder: EmbedderDep
) -> list[ConversationSummary]:
    conversations = await _service(request, session, embedder).list_conversations(user)
    return [ConversationSummary.model_validate(c) for c in conversations]


@router.get("/conversations/{conversation_id}", response_model=list[MessageResponse])
async def history(
    conversation_id: uuid.UUID,
    user: CurrentUser,
    request: Request,
    session: SessionDep,
    embedder: EmbedderDep,
) -> list[MessageResponse]:
    try:
        messages = await _service(request, session, embedder).history(user, conversation_id)
    except DomainError as exc:
        # 404 whether it does not exist or belongs to someone else.
        raise to_http_exception(exc) from exc

    return [MessageResponse.model_validate(m) for m in messages]
