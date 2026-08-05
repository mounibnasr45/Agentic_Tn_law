"""Runs a question through the agent, persists the answer and its citations, and
streams the trace as it happens."""
import asyncio
import contextlib
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

from langchain_core.messages import HumanMessage
from openai import APIConnectionError as OpenAIAPIConnectionError
from openai import AuthenticationError as OpenAIAuthenticationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.graph import MAX_ITERATIONS, build_agent, build_reflection_llm
from app.agent.reflection import reflect_and_reground
from app.agent.tools import build_retrieval_tool, retrieved_chunks
from app.agent.trace import AgentTrace, TraceStep, current_trace
from app.core.config import Settings, get_settings
from app.core.errors import (
    ConversationNotFound,
    CorpusNotReady,
    UpstreamLLMAuthenticationError,
    UpstreamLLMConnectionError,
    UpstreamLLMError,
)
from app.core.logging import get_logger
from app.domain.models import RetrievedChunk
from app.domain.ports import Embedder
from app.infra.db.models import Citation, Conversation, Message, User
from app.infra.db.repositories.chunk_repo import PostgresChunkRepository

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Answer:
    conversation_id: uuid.UUID
    answer: str
    citations: list[RetrievedChunk]
    # What the agent did to produce the answer. Not persisted: it describes ONE run, and a
    # replayed conversation would show a trace that no longer matches the current corpus or
    # prompts. It is live-only, which is honest about what it is.
    trace: AgentTrace


@dataclass(frozen=True, slots=True)
class StreamError:
    """A run-time failure surfaced IN the stream rather than as an HTTP status.

    By the time stream_answer() is producing events, the response's 200 status and headers
    are already on the wire (see ChatService.prepare_stream's docstring) — there is no
    status code left to change. This carries the same information ask() would raise as an
    UpstreamLLM* exception, just as data instead of a raised exception, so the client sees
    an explicit failure event rather than a stream that silently stops.
    """

    message: str


class ChatService:
    def __init__(self, session: AsyncSession, embedder: Embedder, checkpointer) -> None:
        self._session = session
        self._embedder = embedder
        self._checkpointer = checkpointer

    async def _conversation_for(
        self, user: User, conversation_id: uuid.UUID | None
    ) -> Conversation:
        """Fetch the user's conversation, or start one.

        THE OWNERSHIP CHECK. LangGraph loads whatever thread_id it is handed — it has no
        concept of a user. If the caller could name any thread, they could read anyone's
        history, which is bug 2 wearing a different hat. The `user_id == user.id` predicate
        below is the only thing preventing that, so it is a WHERE clause, not an
        afterthought: a missing conversation and someone else's conversation must be
        indistinguishable to the caller (404 either way), or the API becomes an oracle for
        which conversation ids exist.
        """
        if conversation_id is None:
            conversation = Conversation(user_id=user.id, thread_id=str(uuid.uuid4()))
            self._session.add(conversation)
            await self._session.flush()
            return conversation

        conversation = await self._session.scalar(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user.id,
            )
        )
        if conversation is None:
            raise ConversationNotFound()
        return conversation

    async def ask(
        self,
        user: User,
        question: str,
        conversation_id: uuid.UUID | None = None,
        language: str = "fr",
    ) -> Answer:
        settings = get_settings()

        if await PostgresChunkRepository(self._session).count() == 0:
            raise CorpusNotReady()

        conversation = await self._conversation_for(user, conversation_id)

        trace = AgentTrace(max_iterations=MAX_ITERATIONS)
        started = time.perf_counter()

        answer, citations, regrounded = await self._run_agent(
            conversation, question, trace, language
        )
        latency_ms = int((time.perf_counter() - started) * 1000)

        await self._persist(conversation, question, answer, citations, latency_ms, settings)

        log.info(
            "question_answered",
            conversation_id=str(conversation.id),
            latency_ms=latency_ms,
            citation_count=len(citations),
            # Logged per answer so the checkpoint's real-world trigger rate is measurable
            # rather than assumed. If this is true on almost every question the reflector is
            # too eager; if it is never true the prompt is not finding gaps that exist.
            regrounded=regrounded,
        )

        return Answer(
            conversation_id=conversation.id,
            answer=answer,
            citations=citations,
            trace=trace,
        )

    async def prepare_stream(
        self, user: User, conversation_id: uuid.UUID | None
    ) -> Conversation:
        """Preflight checks that must still produce a real HTTP status.

        The streaming route calls this BEFORE building its StreamingResponse. Once that
        response exists, Starlette sends the 200 status the instant it starts iterating the
        generator — before the generator has done anything — so an exception raised from
        inside stream_answer() can no longer become a 404 or 503, only a truncated
        connection. Corpus-readiness and conversation ownership are exactly the two checks
        ask() can currently fail on before touching the agent, so they run here instead,
        as an ordinary awaited call the route can still translate with to_http_exception.
        """
        if await PostgresChunkRepository(self._session).count() == 0:
            raise CorpusNotReady()
        return await self._conversation_for(user, conversation_id)

    async def stream_answer(
        self, conversation: Conversation, question: str, language: str = "fr"
    ) -> AsyncIterator[TraceStep | Answer | StreamError]:
        """Same work as ask(), but yields each trace step the instant it happens.

        THE PRODUCER/CONSUMER SHAPE. _run_agent() still runs to completion in one call — it
        is LangGraph's ainvoke(), there is no hook to pause it mid-way. What makes this
        live is that its trace gets a `live` queue (app/agent/trace.py) and _run_agent()
        runs as its own asyncio.Task alongside this generator instead of being awaited
        directly here. Whenever that task suspends on an LLM or DB call, the event loop is
        free to also resume this generator's `queue.get()` and hand a step to the caller —
        instead of everything arriving in one lump when the run finishes.

        A run-time failure becomes a StreamError, not a raised exception: by the time this
        generator is being iterated, the response's 200 status is already on the wire (see
        prepare_stream's docstring), so raising here would only truncate the connection
        instead of telling the client what happened.
        """
        settings = get_settings()
        queue: asyncio.Queue[TraceStep] = asyncio.Queue()
        trace = AgentTrace(max_iterations=MAX_ITERATIONS, live=queue)
        started = time.perf_counter()

        task = asyncio.ensure_future(self._run_agent(conversation, question, trace, language))

        while not task.done():
            get_next = asyncio.ensure_future(queue.get())
            done, _pending = await asyncio.wait(
                {task, get_next}, return_when=asyncio.FIRST_COMPLETED
            )
            if get_next in done:
                yield get_next.result()
            else:
                get_next.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await get_next

        # The run may have queued its last step(s) and finished in the same event-loop
        # tick, before this loop's next `queue.get()` had a chance to pick them up.
        while not queue.empty():
            yield queue.get_nowait()

        try:
            answer, citations, regrounded = task.result()
        except (
            UpstreamLLMConnectionError,
            UpstreamLLMAuthenticationError,
            UpstreamLLMError,
        ) as exc:
            yield StreamError(message=exc.detail)
            return

        latency_ms = int((time.perf_counter() - started) * 1000)
        await self._persist(conversation, question, answer, citations, latency_ms, settings)

        log.info(
            "question_answered",
            conversation_id=str(conversation.id),
            latency_ms=latency_ms,
            citation_count=len(citations),
            regrounded=regrounded,
        )

        yield Answer(
            conversation_id=conversation.id,
            answer=answer,
            citations=citations,
            trace=trace,
        )

    async def _run_agent(
        self, conversation: Conversation, question: str, trace: AgentTrace, language: str = "fr"
    ) -> tuple[str, list[RetrievedChunk], bool]:
        """Invoke the agent and the reflection checkpoint; returns (answer, citations, regrounded).

        Shared by ask() and stream_answer() so the two front doors run byte-identical
        logic — the same reason IngestionService is the one place ingestion happens for
        both the CLI and the admin upload endpoint.
        """
        # Reset the per-request collectors. ContextVars are isolated per asyncio task, so
        # two concurrent requests — and, on the streaming path, this task running alongside
        # its own generator — cannot bleed citations or trace steps into each other.
        token = retrieved_chunks.set([])
        trace_token = current_trace.set(trace)

        try:
            agent = build_agent(self._session, self._embedder, self._checkpointer, language)

            result = await agent.ainvoke(
                {"messages": [HumanMessage(content=question)]},
                config={
                    "configurable": {"thread_id": conversation.thread_id},
                    # A hard stop on the agentic loop. Without it a confused model can
                    # search the corpus forever, and every iteration is an LLM call.
                    "recursion_limit": MAX_ITERATIONS * 2,
                },
            )
            answer = result["messages"][-1].content

            # THE REFLECTION CHECKPOINT, and its placement is the whole trick.
            #
            # It runs INSIDE the ContextVar window and BEFORE citations are read. The
            # retrieval tool appends whatever it finds to `retrieved_chunks`, so a definition
            # article pulled in during reflection lands in `citations` below and becomes a
            # Citation row with a real chunk_id foreign key — exactly like the agent's own
            # retrievals. Read citations first and the answer would cite an article with no
            # citation row behind it, quietly undoing bug 4's guarantee.
            #
            # reflect_and_reground never raises (see its docstring): on any failure it
            # returns the draft untouched, so it cannot reach the 502 translation below. An
            # enhancement must not be able to turn a correct answer into a server error.
            answer, regrounded = await reflect_and_reground(
                draft=answer,
                citations=retrieved_chunks.get([]),
                llm=build_reflection_llm(),
                retrieval_tool=build_retrieval_tool(self._session, self._embedder),
            )

            citations = retrieved_chunks.get([])

            # Counted from the trace rather than from the graph's message list: one
            # recorded retrieval step IS one tool call, and reading it here avoids
            # depending on LangGraph's internal message shape, which changes between
            # versions.
            trace.iterations_used = sum(1 for s in trace.steps if s.kind == "retrieval")
            trace.regrounded = regrounded

            return answer, citations, regrounded

        except Exception as exc:
            if isinstance(exc, OpenAIAPIConnectionError):
                log.warning("agent_connection_failed", conversation_id=str(conversation.id))
                raise UpstreamLLMConnectionError() from exc

            if isinstance(exc, OpenAIAuthenticationError):
                log.warning("agent_authentication_failed", conversation_id=str(conversation.id))
                raise UpstreamLLMAuthenticationError() from exc

            # BUG 3. The old run() caught Exception and returned str(e) AS THE ASSISTANT'S
            # ANSWER, so an upstream timeout was rendered to the user as legal advice with a
            # 200 OK. A failure must never be indistinguishable from an answer. We log, wrap
            # it as an upstream failure, and let the caller map it to a real failure signal —
            # a 502 on the batch path, a StreamError event on the streaming path.
            log.exception("agent_invocation_failed", conversation_id=str(conversation.id))
            raise UpstreamLLMError() from exc

        finally:
            retrieved_chunks.reset(token)
            current_trace.reset(trace_token)

    async def _persist(
        self,
        conversation: Conversation,
        question: str,
        answer: str,
        citations: list[RetrievedChunk],
        latency_ms: int,
        settings: Settings,
    ) -> None:
        self._session.add(
            Message(conversation_id=conversation.id, role="user", content=question)
        )
        assistant = Message(
            conversation_id=conversation.id,
            role="assistant",
            content=answer,
            model=settings.agent_llm_model,
            latency_ms=latency_ms,
        )
        self._session.add(assistant)
        await self._session.flush()

        # BUG 4's fix, made durable. A citation row requires a chunk_id foreign key, so the
        # API physically cannot return a citation for a chunk that was not retrieved. That
        # is a stronger guarantee than instructing the model to cite its sources.
        for chunk in citations:
            self._session.add(
                Citation(
                    message_id=assistant.id,
                    chunk_id=chunk.chunk_id,
                    source=chunk.source,
                    article_number=chunk.article_number,
                    excerpt=chunk.content[:500],
                    score=chunk.score,
                    rank=chunk.rank,
                )
            )

        if conversation.title is None:
            conversation.title = question[:120]

    async def list_conversations(self, user: User) -> list[Conversation]:
        return list(
            await self._session.scalars(
                select(Conversation)
                .where(Conversation.user_id == user.id)
                .order_by(Conversation.updated_at.desc())
            )
        )

    async def history(self, user: User, conversation_id: uuid.UUID) -> list[Message]:
        conversation = await self._conversation_for(user, conversation_id)

        return list(
            await self._session.scalars(
                select(Message)
                .where(Message.conversation_id == conversation.id)
                .order_by(Message.created_at)
            )
        )
