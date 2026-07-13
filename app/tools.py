"""Agent tools.

The retrieval tool now queries Postgres through the domain retriever, so it inherits
the durability fix: a tool call from a cold worker runs genuine hybrid retrieval rather
than silently degrading.

asyncio.run() below is a deliberate, temporary bridge. LangChain's Tool.func is sync,
and the AgentExecutor calling it is sync, but everything underneath is async. P5
replaces the whole executor with LangGraph and this bridge disappears — it is not the
shape to copy.
"""
import asyncio

from langchain.tools import Tool
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.logging import get_logger
from app.domain.models import RetrievedChunk
from app.domain.retrieval import HybridRetriever
from app.infra.db.repositories.chunk_repo import PostgresChunkRepository
from app.infra.db.session import get_sessionmaker
from app.infra.embeddings.sentence_transformer import SentenceTransformerEmbedder

log = get_logger(__name__)


class RechercheDocumentInput(BaseModel):
    query: str = Field(
        description=(
            "La requête de recherche pour trouver des articles juridiques pertinents."
        )
    )


async def retrieve(query: str, embedder) -> list[RetrievedChunk]:
    """Structured retrieval. Returns chunks, not a string.

    Bug 4's root cause was flattening these into a truncated string inside the tool,
    which destroyed the chunk ids, scores and article numbers — so citations could
    never reach the caller and `sources` ended up a hardcoded placeholder. The
    structured type is preserved here; P5 persists it as citation rows.
    """
    settings = get_settings()

    async with get_sessionmaker()() as session:
        retriever = HybridRetriever(
            embedder, PostgresChunkRepository(session), settings.candidate_limit
        )
        return await retriever.search(
            query,
            top_k=settings.top_k_retriever,
            weight_bm25=settings.hybrid_weight_bm25,
        )


def format_for_prompt(chunks: list[RetrievedChunk]) -> str:
    """Render chunks into the prompt. The structured objects survive alongside this."""
    if not chunks:
        return "Aucun document pertinent trouvé pour votre requête."

    return "Extraits de documents pertinents trouvés:\n" + "\n\n---\n\n".join(
        f"[{c.article_number or 'préambule'}] Source: {c.source}\n{c.content}"
        for c in chunks
    )


def setup_outil_recherche_documentaire(embedder: SentenceTransformerEmbedder) -> Tool:
    def rechercher_documents(query: str) -> str:
        try:
            chunks = asyncio.run(retrieve(query, embedder))
        except Exception:
            log.exception("retrieval_tool_failed", query_length=len(query))
            raise

        log.info(
            "retrieval_tool_called",
            result_count=len(chunks),
            articles=[c.article_number for c in chunks[:5]],
        )
        return format_for_prompt(chunks)

    return Tool(
        name="outil_recherche_documentaire",
        func=rechercher_documents,
        description=(
            "Recherche dans les documents juridiques tunisiens (Constitution, Code "
            "Pénal) les articles pertinents. À utiliser pour toute question juridique."
        ),
        args_schema=RechercheDocumentInput,
    )


def get_all_tools(embedder: SentenceTransformerEmbedder) -> list[Tool]:
    # The DuckDuckGo web tool is gone. A legal assistant that cites arbitrary web pages
    # undermines the one thing it is for — being grounded in the Constitution and the
    # Penal Code — and its output cannot be scored against the golden set, so it would
    # make the eval harness meaningless. It also called a blocking HTTP client with no
    # timeout. If it comes back, it comes back behind a flag and it never emits a citation.
    return [setup_outil_recherche_documentaire(embedder)]
