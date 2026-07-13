"""The LangGraph agent.

BUG 2 DIES HERE, and it is worth being precise about how.

The old design held a ConversationBufferWindowMemory as an ATTRIBUTE of the agent object,
and the frontend cached that object process-wide with @st.cache_resource. Conversation
history was therefore a property of the PROCESS. Every visitor shared one buffer.

The fix is not a bigger cache key. It is that the agent is now STATELESS and memory lives
in Postgres, addressed by a thread_id that belongs to a row with a user_id on it. There is
no object to share, because there is no state on the object. Two users cannot see each
other's history for the same reason two users cannot see each other's database rows.

Note the ownership boundary: LangGraph will cheerfully load ANY thread_id it is handed. It
does not know about users. The check that a thread belongs to the caller lives in
chat_service, against the conversations table — never assume the framework is doing it.
"""
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.prebuilt import create_react_agent
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.prompts import SYSTEM_PROMPT
from app.agent.tools import build_retrieval_tool
from app.core.config import get_settings
from app.core.logging import get_logger
from app.domain.ports import Embedder

log = get_logger(__name__)

# Hard cap on the agentic loop. The old executor allowed 10, which on a bad day means ten
# LLM round trips and ten corpus searches for one question — the single biggest latency and
# cost sink in an agent. Four is enough for search -> read -> maybe re-search -> answer.
MAX_ITERATIONS = 4


def langgraph_dsn(database_url: str) -> str:
    """LangGraph's checkpointer takes a raw psycopg DSN, not a SQLAlchemy URL."""
    return database_url.replace("postgresql+psycopg://", "postgresql://")


async def create_checkpointer(database_url: str) -> tuple[AsyncPostgresSaver, AsyncConnectionPool]:
    """Postgres-backed conversation memory.

    The pool arguments are not optional decoration:
      - autocommit=True: setup() issues CREATE TABLE / migration statements that cannot run
        inside the implicit transaction psycopg would otherwise open. Without it, setup()
        fails with a confusing error about a transaction already being in progress.
      - row_factory=dict_row: the saver indexes rows by column NAME. With the default tuple
        rows it raises TypeError deep inside its own deserialisation.

    Both are the kind of thing you lose an afternoon to.
    """
    pool = AsyncConnectionPool(
        conninfo=langgraph_dsn(database_url),
        max_size=10,
        open=False,
        kwargs={"autocommit": True, "row_factory": dict_row},
    )
    await pool.open()

    checkpointer = AsyncPostgresSaver(pool)
    # Idempotent; creates LangGraph's own tables. Alembic must NOT manage them — see the
    # include_object filter in alembic/env.py, without which autogenerate writes a
    # migration that drops every checkpoint.
    await checkpointer.setup()

    log.info("checkpointer_ready")
    return checkpointer, pool


def build_agent(session: AsyncSession, embedder: Embedder, checkpointer: AsyncPostgresSaver):
    """A stateless agent. All conversation state lives in the checkpointer, keyed by thread."""
    settings = get_settings()

    llm = ChatOpenAI(
        model=settings.agent_llm_model,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        # An agent loop with no request deadline can pin a worker indefinitely on a slow
        # upstream. The old code had AGENT_REQUEST_TIMEOUT in config and applied it only to
        # a dead code path.
        timeout=settings.agent_request_timeout,
        max_retries=settings.llm_max_retries,
        default_headers={
            "HTTP-Referer": settings.app_referer,
            "X-Title": settings.app_title,
        },
    )

    return create_react_agent(
        model=llm,
        tools=[build_retrieval_tool(session, embedder)],
        prompt=SYSTEM_PROMPT,
        checkpointer=checkpointer,
    )
