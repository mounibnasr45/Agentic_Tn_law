"""Ask a question, persist the answer and its citations."""
import time
import uuid
from dataclasses import dataclass

from langchain_core.messages import HumanMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.graph import MAX_ITERATIONS, build_agent
from app.agent.tools import retrieved_chunks
from app.core.config import get_settings
from app.core.errors import ConversationNotFound, CorpusNotReady, UpstreamLLMError
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
    ) -> Answer:
        settings = get_settings()

        if await PostgresChunkRepository(self._session).count() == 0:
            raise CorpusNotReady()

        conversation = await self._conversation_for(user, conversation_id)

        # Reset the per-request collector. ContextVars are isolated per asyncio task, so
        # two concurrent requests cannot bleed citations into each other.
        token = retrieved_chunks.set([])
        started = time.perf_counter()

        try:
            agent = build_agent(self._session, self._embedder, self._checkpointer)

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
            citations = retrieved_chunks.get([])

        except Exception as exc:
            # BUG 3. The old run() caught Exception and returned str(e) AS THE ASSISTANT'S
            # ANSWER, so an upstream timeout was rendered to the user as legal advice with a
            # 200 OK. A failure must never be indistinguishable from an answer. We log, wrap
            # it as an upstream failure, and let the API map it to 502 — the caller can then
            # tell "the model broke" from "the law says X".
            log.exception("agent_invocation_failed", conversation_id=str(conversation.id))
            raise UpstreamLLMError() from exc

        finally:
            retrieved_chunks.reset(token)

        latency_ms = int((time.perf_counter() - started) * 1000)

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

        log.info(
            "question_answered",
            conversation_id=str(conversation.id),
            latency_ms=latency_ms,
            citation_count=len(citations),
        )

        return Answer(
            conversation_id=conversation.id,
            answer=answer,
            citations=citations,
        )

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
