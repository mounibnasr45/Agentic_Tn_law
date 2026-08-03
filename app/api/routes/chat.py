import json
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.agent.trace import TraceStep
from app.api.deps import CurrentUser, EmbedderDep, SessionDep
from app.api.schemas.chat import Citation
from app.api.schemas.conversation import (
    AskRequest,
    AskResponse,
    ConversationSummary,
    MessageResponse,
    TraceResponse,
    TraceResult,
    TraceStepResponse,
)
from app.core.errors import DomainError, to_http_exception
from app.services.chat_service import Answer, ChatService, StreamError

router = APIRouter(tags=["chat"])


def _service(request: Request, session: SessionDep, embedder: EmbedderDep) -> ChatService:
    return ChatService(session, embedder, request.app.state.checkpointer)


def _trace_step_response(step: TraceStep) -> TraceStepResponse:
    return TraceStepResponse(
        kind=step.kind,
        label=step.label,
        query=step.query,
        results=[
            TraceResult(article_number=a, score=score, rank=rank)
            for a, score, rank in step.results
        ],
        detail=step.detail,
    )


def _ask_response(answer: Answer) -> AskResponse:
    return AskResponse(
        conversation_id=answer.conversation_id,
        answer=answer.answer,
        trace=TraceResponse(
            steps=[_trace_step_response(s) for s in answer.trace.steps],
            iterations_used=answer.trace.iterations_used,
            max_iterations=answer.trace.max_iterations,
            regrounded=answer.trace.regrounded,
        ),
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

    return _ask_response(answer)


def _ndjson_line(event: str, data: dict) -> bytes:
    return (json.dumps({"event": event, "data": data}, ensure_ascii=False) + "\n").encode(
        "utf-8"
    )


@router.post("/ask/stream")
async def ask_stream(
    payload: AskRequest,
    user: CurrentUser,
    request: Request,
    session: SessionDep,
    embedder: EmbedderDep,
) -> StreamingResponse:
    """NDJSON, one `{"event": "step" | "final" | "error", "data": ...}` object per line.

    fetch() + a streamed request body, not EventSource — EventSource cannot carry an
    Authorization header, which is why this project avoided streaming for a long time (see
    app/agent/trace.py). A normal fetch() sends the header like any other request; what it
    does NOT fix is a proxy buffering the response, which is why `X-Accel-Buffering` is set
    below and why the corpus/ownership checks run in prepare_stream() before this function
    even returns — after that point the 200 status is already committed and cannot become a
    404 or 503 anymore, only an in-band "error" event (see stream_answer's docstring).
    """
    service = _service(request, session, embedder)

    try:
        conversation = await service.prepare_stream(user, payload.conversation_id)
    except DomainError as exc:
        raise to_http_exception(exc) from exc

    async def generate() -> AsyncIterator[bytes]:
        async for event in service.stream_answer(conversation, payload.question):
            if isinstance(event, TraceStep):
                yield _ndjson_line("step", _trace_step_response(event).model_dump())
            elif isinstance(event, StreamError):
                yield _ndjson_line("error", {"message": event.message})
            else:
                yield _ndjson_line("final", _ask_response(event).model_dump(mode="json"))

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson",
        headers={"X-Accel-Buffering": "no"},
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
