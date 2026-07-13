from fastapi import APIRouter

from app.api.deps import CurrentUser, EmbedderDep, SessionDep
from app.api.schemas.chat import Citation, SearchResponse
from app.core.config import get_settings
from app.core.errors import CorpusNotReady, to_http_exception
from app.domain.retrieval import FusionStrategy, HybridRetriever
from app.infra.db.repositories.chunk_repo import PostgresChunkRepository

router = APIRouter(prefix="/search", tags=["search"])


@router.post("", response_model=SearchResponse)
async def search(
    query: str,
    user: CurrentUser,
    session: SessionDep,
    embedder: EmbedderDep,
    top_k: int = 5,
    weight_bm25: float | None = None,
    fusion: FusionStrategy = FusionStrategy.WEIGHTED,
) -> SearchResponse:
    """Retrieval with no LLM.

    Worth exposing on its own: it is cheap, deterministic, and shows exactly what the
    retriever returns without an LLM paraphrasing over its mistakes. It is also the
    endpoint that makes the eval numbers reproducible by anyone reading the README.
    """
    settings = get_settings()
    repository = PostgresChunkRepository(session)

    if await repository.count() == 0:
        raise to_http_exception(CorpusNotReady())

    retriever = HybridRetriever(embedder, repository, settings.candidate_limit)
    chunks = await retriever.search(
        query,
        top_k=top_k,
        weight_bm25=settings.hybrid_weight_bm25 if weight_bm25 is None else weight_bm25,
        fusion=fusion,
    )

    return SearchResponse(
        query=query,
        retrieval_type=chunks[0].retrieval_type if chunks else "none",
        results=[
            Citation(
                chunk_id=c.chunk_id,
                source=c.source,
                article_number=c.article_number,
                score=c.score,
                rank=c.rank,
                excerpt=c.content[:400],
            )
            for c in chunks
        ],
    )
