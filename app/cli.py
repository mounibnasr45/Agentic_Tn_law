"""Ingestion CLI.

    python -m app.cli ingest          # index the corpus into Postgres
    python -m app.cli search "query"  # sanity-check retrieval from a cold process

The `search` command exists precisely because of bug 1: it runs in a FRESH process that
never built an index. If it returns hybrid results, retrieval is genuinely durable. The
old code would have returned dense-only here and said nothing.
"""
import argparse
import asyncio
import hashlib
import sys
from datetime import UTC, datetime

from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.core.runtime import configure_event_loop
from app.document_processor import extract_text_from_pdf
from app.domain.chunking import split_by_article
from app.domain.retrieval import HybridRetriever
from app.infra.db.models import Chunk, Document
from app.infra.db.repositories.chunk_repo import PostgresChunkRepository
from app.infra.db.session import dispose_engine, get_sessionmaker
from app.infra.embeddings.sentence_transformer import SentenceTransformerEmbedder

log = get_logger(__name__)


async def ingest() -> int:
    settings = get_settings()

    missing = settings.missing_documents()
    if missing:
        log.error(
            "corpus_documents_missing",
            missing=missing,
            directory=str(settings.documents_dir),
        )
        return 1

    embedder = SentenceTransformerEmbedder(settings.embedding_model_name)

    async with get_sessionmaker()() as session:
        for filename in settings.default_document_filenames:
            path = settings.documents_dir / filename

            text = extract_text_from_pdf(path)
            if not text.strip():
                log.error("no_text_extracted", filename=filename)
                return 1

            digest = hashlib.sha256(path.read_bytes()).hexdigest()

            chunks = split_by_article(
                text,
                source=filename,
                max_chars=settings.chunk_size,
                overlap=settings.chunk_overlap,
            )
            with_articles = sum(1 for c in chunks if c.article_number)
            log.info(
                "document_chunked",
                filename=filename,
                chunks=len(chunks),
                citable_as_article=with_articles,
            )

            # Re-ingesting the same file replaces its chunks rather than duplicating the
            # corpus. The chunks cascade on document delete.
            existing = await session.scalar(select(Document).where(Document.sha256 == digest))
            if existing:
                await session.execute(delete(Chunk).where(Chunk.document_id == existing.id))
                document = existing
                document.corpus_version += 1
            else:
                document = Document(title=filename, sha256=digest, status="processing")
                session.add(document)
                await session.flush()

            embeddings = await embedder.embed_documents([c.content for c in chunks])

            session.add_all(
                Chunk(
                    document_id=document.id,
                    chunk_index=c.chunk_index,
                    article_number=c.article_number,
                    part_index=c.part_index,
                    content=c.content,
                    embedding_model=embedder.model_name,
                    embedding=embeddings[i].tolist(),
                )
                for i, c in enumerate(chunks)
            )

            document.status = "indexed"
            document.indexed_at = datetime.now(UTC)
            await session.commit()

            log.info("document_indexed", filename=filename, chunks=len(chunks))

    return 0


async def search(query: str) -> int:
    """Query from a cold process — nothing was indexed in THIS process."""
    settings = get_settings()
    embedder = SentenceTransformerEmbedder(settings.embedding_model_name)

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

    args = parser.parse_args()
    configure_event_loop()
    settings = get_settings()
    configure_logging(level=settings.log_level, json_logs=settings.log_json)

    try:
        if args.command == "ingest":
            return asyncio.run(_with_cleanup(ingest()))
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
