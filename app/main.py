"""FastAPI application factory.

    uvicorn app.main:app --workers 1

WORKERS = 1, DELIBERATELY. Each uvicorn worker is a separate process and loads its own
copy of the ~450MB embedding model. `--workers 4` on a 512MB free tier is an instant OOM,
and on a 2GB box it quadruples memory for no throughput gain, because the work is I/O
against Postgres and an LLM, not CPU. Scale with replicas behind a reverse proxy instead.
Knowing WHY workers is 1 is worth more than setting it to 4.
"""
import asyncio
import sys
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

from app.agent.graph import create_checkpointer
from app.api.routes import admin, auth, chat, evaluation, health, search
from app.core.config import get_settings
from app.core.errors import DomainError, to_http_exception
from app.core.logging import configure_logging, get_logger, request_id_var
from app.core.runtime import configure_event_loop
from app.infra.db.session import dispose_engine
from app.infra.embeddings.sentence_transformer import SentenceTransformerEmbedder

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Load expensive, stateless resources ONCE.

    The embedding model is 450MB and takes seconds to load. Building it per request — or
    lazily on first request — would make the first caller after every deploy wait for it,
    and would race if two requests arrived together. Loading it here means the container
    is not "ready" until it genuinely can serve.
    """
    settings = get_settings()

    # A default JWT secret is an authentication bypass sitting in a public repo: anyone
    # who reads it can forge a token for any user. Refuse to start rather than serve
    # traffic that only LOOKS authenticated.
    if settings.jwt_secret_is_the_insecure_default:
        if settings.environment == "production":
            raise RuntimeError(
                "JWT_SECRET is still the committed development default. Set it, or every "
                "reader of this repository can forge a token for any user."
            )
        log.warning(
            "insecure_jwt_secret",
            detail="using the committed development default; set JWT_SECRET before deploying",
        )

    log.info("loading_embedder", model=settings.embedding_model_name)
    app.state.embedder = SentenceTransformerEmbedder(settings.embedding_model_name)

    if settings.auto_migrate_on_startup:
        # alembic upgrade runs as a SUBPROCESS: alembic/env.py calls asyncio.run() at
        # module import time, which raises "cannot be called from a running event loop"
        # from inside a lifespan that is itself running inside uvicorn's loop. It's cheap
        # to shell out for — no torch, no model — unlike ingestion below.
        log.info("auto_migrate_starting")
        migrate = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "alembic", "upgrade", "head"
        )
        if await migrate.wait() != 0:
            raise RuntimeError("alembic upgrade head failed during startup — see logs above")

        # Ingestion runs IN-PROCESS, reusing app.state.embedder — NOT a subprocess. A
        # `python -m app.cli ingest` child would load its own copy of torch and the
        # ~450MB model on top of this process's already-imported copy, which is exactly
        # what OOM'd a 512MB Free instance before a single chunk was embedded.
        log.info("auto_ingest_starting")
        from app.cli import ingest as ingest_corpus

        if await ingest_corpus(app.state.embedder) != 0:
            raise RuntimeError("corpus ingestion failed during startup — see logs above")

        log.info("auto_migrate_complete")

    # Conversation memory. setup() is idempotent and creates LangGraph's own tables; doing
    # it here means the container is not "ready" until memory genuinely works, rather than
    # discovering it on the first user's first message.
    app.state.checkpointer, app.state.checkpointer_pool = await create_checkpointer(
        settings.database_url
    )

    log.info("startup_complete")

    yield

    await app.state.checkpointer_pool.close()
    await dispose_engine()
    log.info("shutdown_complete")


def create_app() -> FastAPI:
    configure_event_loop()
    settings = get_settings()
    configure_logging(level=settings.log_level, json_logs=settings.log_json)

    app = FastAPI(
        title="Agent Juridique Tunisien",
        description="RAG sur la Constitution et le Code Pénal tunisiens.",
        version="2.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def bind_request_id(request: Request, call_next):
        """Stamp every log line emitted while handling this request with one id.

        This is what makes the structlog work from P1 pay off: without a correlation id,
        concurrent requests interleave their log lines and no failure can be reconstructed.
        """
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        token = request_id_var.set(request_id)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)

        response.headers["X-Request-ID"] = request_id
        return response

    @app.exception_handler(DomainError)
    async def domain_error_handler(_request: Request, exc: DomainError) -> JSONResponse:
        """Any DomainError that escapes a handler becomes its proper HTTP status.

        BUG 3 lived exactly here. The old agent caught Exception and returned str(e) as
        the assistant's ANSWER, so an upstream timeout was served as legal advice with a
        200 OK. A failure must be a failure.
        """
        http = to_http_exception(exc)
        return JSONResponse(
            status_code=http.status_code,
            content={"detail": http.detail},
            headers=http.headers,
        )

    app.include_router(health.router, prefix="/api")
    app.include_router(auth.router, prefix="/api")
    app.include_router(search.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")
    app.include_router(admin.router, prefix="/api")
    # Unauthenticated, like /health: published measurements about a public corpus.
    app.include_router(evaluation.router, prefix="/api")

    return app


app = create_app()
