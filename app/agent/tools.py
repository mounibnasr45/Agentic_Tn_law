"""The retrieval tool, and how citations escape it.

BUG 4's ROOT CAUSE. A LangChain/LangGraph tool must return a STRING — that is what goes
into the model's context. The old tool therefore flattened its results into truncated text
and threw the structure away, so chunk ids, scores and article numbers could never reach
the caller, and `sources` ended up as a hardcoded placeholder that the UI string-compared
against.

The fix is not to change what the tool returns to the MODEL (it still needs prose), but to
give the retrieved chunks a second exit: a ContextVar the chat service reads after the run.
ContextVars propagate into asyncio tasks and are isolated per task, so two concurrent
requests cannot see each other's citations — which matters, because the same bug class as
bug 2 would otherwise reappear here.
"""
from contextvars import ContextVar

from langchain_core.tools import tool
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.domain.models import RetrievedChunk
from app.domain.ports import Embedder
from app.domain.retrieval import HybridRetriever
from app.infra.db.repositories.chunk_repo import PostgresChunkRepository

log = get_logger(__name__)

# What the tool retrieved during THIS request. Set by the chat service before the run,
# read after it. Never a module global: that is exactly the mistake bug 2 was.
retrieved_chunks: ContextVar[list[RetrievedChunk]] = ContextVar("retrieved_chunks")


def build_retrieval_tool(session: AsyncSession, embedder: Embedder):
    settings = get_settings()

    @tool("rechercher_textes_juridiques")
    async def rechercher(query: str) -> str:
        """Recherche les articles pertinents dans la Constitution tunisienne et le Code Pénal.

        Args:
            query: la question ou les termes juridiques à rechercher, en français.
        """
        retriever = HybridRetriever(
            embedder, PostgresChunkRepository(session), settings.candidate_limit
        )
        chunks = await retriever.search(
            query,
            top_k=settings.top_k_retriever,
            weight_bm25=settings.hybrid_weight_bm25,
        )

        # The structured exit. The model gets prose below; the service gets the objects.
        collected = retrieved_chunks.get([])
        seen = {c.chunk_id for c in collected}
        collected.extend(c for c in chunks if c.chunk_id not in seen)
        retrieved_chunks.set(collected)

        log.info(
            "retrieval_tool_called",
            result_count=len(chunks),
            articles=[c.article_number for c in chunks[:5]],
        )

        if not chunks:
            return (
                "Aucune disposition pertinente trouvée dans la Constitution "
                "ni dans le Code Pénal."
            )

        # Full chunk text, not truncated to 1000 chars as before. The article IS the unit
        # of law; handing the model half of one invites it to complete the other half from
        # memory, which is exactly how a plausible fake article number gets invented.
        return "\n\n---\n\n".join(
            f"[{c.article_number or 'préambule'} — {c.source}]\n{c.content}" for c in chunks
        )

    return rechercher
