"""Ingestion and administration CLI.

    python -m app.cli ingest                 # index the corpus into Postgres
    python -m app.cli search "query"         # sanity-check retrieval from a cold process
    python -m app.cli grant-admin <email>    # allow an account to manage the corpus

The `search` command exists precisely because of bug 1: it runs in a FRESH process that
never built an index. If it returns hybrid results, retrieval is genuinely durable. The
old code would have returned dense-only here and said nothing.

`ingest` no longer implements ingestion — it drives IngestionService, the same code the
admin upload endpoint runs. Two implementations of chunk-and-embed would drift, and the
eval harness only ever measures whatever the CLI produced.
"""
import argparse
import asyncio
import sys

from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.core.runtime import configure_event_loop
from app.domain.ports import Embedder
from app.domain.retrieval import HybridRetriever
from app.infra.db.models import User
from app.infra.db.repositories.chunk_repo import PostgresChunkRepository
from app.infra.db.session import dispose_engine, get_sessionmaker
from app.infra.embeddings import create_embedder
from app.services.ingestion_service import IngestionService

log = get_logger(__name__)


async def ingest(embedder: Embedder | None = None) -> int:
    """Index the corpus files listed in settings.default_document_filenames.

    Thin: register() and process() are IngestionService's, so the CLI and the admin upload
    endpoint produce byte-identical chunks. The one behaviour worth preserving from the old
    implementation is the skip — `preDeployCommand` on Render runs this on every push, and
    without it each redeploy re-embeds an unchanged corpus for identical output.

    `embedder` lets a caller that already loaded one pass it in instead of this function
    loading its own. app/main.py's Free-tier startup path does exactly that: it used to
    shell out to `python -m app.cli ingest` as a subprocess, which loaded a SECOND copy of
    the embedding runtime into a fresh process while the parent's own copy was already
    resident — on a 512MB instance that alone was enough to OOM before a single chunk was
    embedded.
    """
    settings = get_settings()

    missing = settings.missing_documents()
    if missing:
        log.error(
            "corpus_documents_missing",
            missing=missing,
            directory=str(settings.documents_dir),
        )
        return 1

    if embedder is None:
        embedder = create_embedder(settings)

    async with get_sessionmaker()() as session:
        service = IngestionService(session, embedder)

        for filename in settings.default_document_filenames:
            path = settings.documents_dir / filename
            document = await service.register(filename, path.read_bytes())

            if not await service.needs_processing(document):
                log.info("document_already_indexed", filename=filename)
                await session.commit()  # persist storage_key from register()
                continue

            document_id = document.id
            # Commit before processing: process() opens its own session and would not see
            # an uncommitted row.
            await session.commit()

            await IngestionService.process(document_id, embedder)

            # process() records failures on the row rather than raising, so the CLI has to
            # read the outcome back to decide its exit code. Returning 0 on a failed ingest
            # would let a broken corpus pass a deploy pipeline.
            await session.refresh(document)
            if document.status == "failed":
                log.error("ingest_failed", filename=filename, error=document.error)
                return 1

    return 0


async def grant_admin(email: str) -> int:
    """Make an existing account an administrator.

    A CLI command, on purpose. The alternatives are worse: "the first account to register
    becomes admin" is a race with whoever finds a public URL first, and a self-service
    admin toggle in the API is not a privilege boundary at all. Granting admin requires
    shell access to the deployment, which is the property we actually want.
    """
    async with get_sessionmaker()() as session:
        user = await session.scalar(select(User).where(User.email == email))

        if user is None:
            log.error("user_not_found", email=email)
            return 1

        if user.is_admin:
            log.info("already_admin", email=email)
            return 0

        user.is_admin = True
        await session.commit()

    log.info("admin_granted", email=email)
    return 0


async def search(query: str) -> int:
    """Query from a cold process — nothing was indexed in THIS process."""
    settings = get_settings()
    embedder = create_embedder(settings)

    async with get_sessionmaker()() as session:
        repository = PostgresChunkRepository(session)

        total = await repository.count()
        if total == 0:
            log.error("corpus_empty", remedy="python -m app.cli ingest")
            return 1

        retriever = HybridRetriever(embedder, repository, settings.candidate_limit)
        results = await retriever.search(
            query, top_k=5, weight_bm25=settings.hybrid_weight_bm25
        )

    print(f"\ncorpus: {total} chunks | query: {query!r}\n")
    for r in results:
        article = r.article_number or "(non-article)"
        print(f"  [{r.rank}] {r.score:.4f}  {r.retrieval_type:8}  {r.source} — {article}")
        print(f"      {r.content[:100].strip()}...\n")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("ingest", help="chunk, embed and index the corpus into Postgres")
    search_parser = sub.add_parser("search", help="query retrieval from a cold process")
    search_parser.add_argument("query")
    admin_parser = sub.add_parser("grant-admin", help="allow an account to manage the corpus")
    admin_parser.add_argument("email")

    args = parser.parse_args()
    configure_event_loop()
    settings = get_settings()
    configure_logging(level=settings.log_level, json_logs=settings.log_json)

    try:
        if args.command == "ingest":
            return asyncio.run(_with_cleanup(ingest()))
        if args.command == "grant-admin":
            return asyncio.run(_with_cleanup(grant_admin(args.email)))
        return asyncio.run(_with_cleanup(search(args.query)))
    except KeyboardInterrupt:
        return 130


async def _with_cleanup(coro) -> int:
    try:
        return await coro
    finally:
        await dispose_engine()


if __name__ == "__main__":
    sys.exit(main())
