"""FastAPI application factory: routes, middleware, startup/shutdown, and
optionally the built Angular bundle."""
import asyncio
import sys
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import FileResponse, JSONResponse

from app.agent.graph import create_checkpointer
from app.api.routes import admin, auth, chat, documents, evaluation, health, public, search
from app.core.config import get_settings
from app.core.errors import DomainError, to_http_exception
from app.core.logging import configure_logging, get_logger, request_id_var
from app.core.runtime import configure_event_loop
from app.infra.db.session import dispose_engine
from app.infra.embeddings import create_embedder

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Load expensive, stateless resources ONCE.

    The embedding model takes seconds to load. Building it per request — or lazily on
    first request — would make the first caller after every deploy wait for it, and
    would race if two requests arrived together. Loading it here means the container is
    not "ready" until it genuinely can serve.
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

    # The embedder logs its own resolved identity once built (which is the one that
    # matters — see needs_processing's drift guard); this only records the choice.
    log.info("loading_embedder", provider=settings.embedding_provider)
    app.state.embedder = create_embedder(settings)

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

        # Ingestion runs IN-PROCESS, reusing app.state.embedder — NOT a subprocess. With
        # a local encoder a `python -m app.cli ingest` child loaded a second copy of the
        # runtime and weights on top of this process's, which was enough to OOM a 512MB
        # instance outright. Sharing the one embedder also guarantees the corpus is
        # embedded by exactly the encoder that will later query it.
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
    app.include_router(documents.router, prefix="/api")
    app.include_router(public.router, prefix="/api")
    app.include_router(admin.router, prefix="/api")
    # Unauthenticated, like /health: published measurements about a public corpus.
    app.include_router(evaluation.router, prefix="/api")

    # LAST, and only when configured. The catch-all route below would shadow every API
    # path if it were registered first — FastAPI matches in registration order.
    if settings.static_dir is not None and settings.static_dir.is_dir():
        _serve_spa(app, settings.static_dir)

    return app


def _serve_spa(app: FastAPI, root: Path) -> None:
    """Serve the built Angular bundle from this same process.

    Only the single-container deployment uses this; see Settings.static_dir for why the
    nginx-fronted topologies leave it unset. Deliberately mirrors the two rules
    web/nginx.conf.template already encodes, because a second way to serve the same files
    is a second place for them to drift:

      * a path that does not exist on disk returns index.html, not 404, so a hard refresh
        on /chat/<uuid> is resolved by the Angular router rather than by the server;
      * index.html is never cached (it names the current hashed bundles, so a stale copy
        pins the browser to a deployment that no longer exists) while the fingerprinted
        bundles beside it are immutable and cached for a year.
    """
    root = root.resolve()
    index = root / "index.html"

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str) -> FileResponse:
        # An unmatched /api/* path is a genuine 404, not a page. Without this it would
        # fall through and hand the SPA's HTML to an API client expecting JSON.
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")

        candidate = (root / full_path).resolve()
        # `root in parents` is the path-traversal guard: it rejects ../ escapes that
        # resolve outside the bundle, which would otherwise serve any readable file.
        if candidate.is_file() and root in candidate.parents:
            return FileResponse(
                candidate, headers={"Cache-Control": "public, max-age=31536000, immutable"}
            )

        return FileResponse(index, headers={"Cache-Control": "no-store, must-revalidate"})


app = create_app()
