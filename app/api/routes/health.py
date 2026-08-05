"""Liveness and readiness check: database reachable, embedding model loaded,
corpus indexed."""

from fastapi import APIRouter
from sqlalchemy import func as sa_func
from sqlalchemy import select, text

from app.api.deps import EmbedderDep, SessionDep
from app.api.schemas.common import HealthResponse
from app.core.logging import get_logger
from app.infra.db.models import Chunk

router = APIRouter(tags=["health"])
log = get_logger(__name__)


@router.get("/health", response_model=HealthResponse)
async def health(session: SessionDep, embedder: EmbedderDep) -> HealthResponse:
    """Liveness AND readiness.

    Reports corpus_chunks because "the process is up" is not the same as "the service can
    answer". A container with an empty corpus is running and useless; a health check that
    only proves the event loop is alive would happily route traffic to it.
    """
    database = True
    chunks = 0
    try:
        await session.execute(text("SELECT 1"))
        result = await session.execute(select(sa_func.count()).select_from(Chunk))
        chunks = int(result.scalar_one())
    except Exception:
        log.exception("health_database_check_failed")
        database = False

    return HealthResponse(
        status="ok" if (database and chunks > 0) else "degraded",
        database=database,
        model_loaded=embedder is not None,
        embedding_model=embedder.model_name if embedder else "",
        corpus_chunks=chunks,
    )
