"""Corpus ingestion: PDF bytes in, chunked and embedded rows in Postgres out."""
import hashlib
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import EmptyUpload, NotAPdf, UploadTooLarge
from app.core.logging import get_logger
from app.domain.chunking import split_by_article
from app.domain.ports import Embedder
from app.infra.db.models import Chunk, Document
from app.infra.db.session import get_sessionmaker
from app.infra.pdf import extract_text

log = get_logger(__name__)

# How many chunks to embed before committing progress. The trade-off is granularity vs.
# write amplification: 32 gives an admin watching a 474-chunk penal code about 15 visible
# steps, at the cost of 15 small UPDATEs. Embedding one at a time would report beautifully
# and waste the encoder's batching entirely.
EMBED_BATCH_SIZE = 32

# Refuse absurd uploads. A legal code is a few MB; 50MB is generous. Without a ceiling,
# one request can exhaust a free tier's memory. Keep in sync with UploadTooLarge.detail.
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


class IngestionService:
    def __init__(self, session: AsyncSession, embedder: Embedder) -> None:
        self._session = session
        self._embedder = embedder

    # --- the request-time half -----------------------------------------------------

    async def register(self, filename: str, data: bytes) -> Document:
        """Validate, persist the file, and create or reset its document row.

        Idempotent on content: re-uploading identical bytes reuses the existing row rather
        than duplicating the corpus (documents.sha256 is UNIQUE). Re-uploading the same
        bytes for a document that is already indexed with the CURRENT encoder is a no-op —
        the caller checks `needs_processing` and skips the background task.
        """
        if not filename.lower().endswith(".pdf"):
            raise NotAPdf()
        if not data:
            raise EmptyUpload()
        if len(data) > MAX_UPLOAD_BYTES:
            raise UploadTooLarge()

        settings = get_settings()
        digest = hashlib.sha256(data).hexdigest()

        # Write before the DB row exists, not after: a row pointing at a file that failed
        # to write is a document that can never be processed and never explains why.
        settings.documents_dir.mkdir(parents=True, exist_ok=True)
        path = settings.documents_dir / filename
        path.write_bytes(data)

        document = await self._session.scalar(
            select(Document).where(Document.sha256 == digest)
        )

        if document is None:
            document = Document(
                title=filename,
                sha256=digest,
                status="pending",
                storage_key=str(path),
            )
            self._session.add(document)
        else:
            # Deliberately does NOT touch status here. An earlier version reset it to
            # "pending" for every re-upload, which broke needs_processing() below: that
            # method read the status this line had just overwritten, concluded the document
            # was unindexed, and re-embedded an unchanged corpus on every single upload.
            # process() owns the status transitions; register() only records the file.
            document.storage_key = str(path)

        await self._session.flush()
        return document

    async def needs_processing(self, document: Document) -> bool:
        """False when this document already has chunks from the CURRENT encoder.

        Asks about the INDEX, not about document.status. Two reasons that matters:

          - status is mutable state that register() and process() both write, so reading it
            here couples this answer to call ordering. Counting chunks does not.
          - a document can be status="indexed" with zero chunks — a crash between the last
            batch and the final commit leaves exactly that. Trusting the status would
            declare a corpus indexed that is physically empty.

        The encoder comparison is the part that is easy to omit and expensive to get wrong.
        When the encoder changes — as it did for bug 13 — stored chunks are stale even
        though the bytes are identical, and mixing embeddings from two encoders in one index
        produces confident nonsense.

        It compares against THIS SERVICE'S EMBEDDER, not settings.embedding_model_name. The
        embedder is what will actually write the vectors, and it is injected — so a settings
        string is a claim about configuration while `self._embedder.model_name` is a fact
        about what is about to happen. They agree in production and diverge anywhere an
        embedder is injected (tests, a re-index script pinned to an older encoder), and in
        every one of those cases the injected object is the correct authority.
        """
        indexed_model = await self._session.scalar(
            select(Chunk.embedding_model).where(Chunk.document_id == document.id).limit(1)
        )

        if indexed_model is None:
            return True  # no chunks: never successfully indexed, whatever status claims

        return indexed_model != self._embedder.model_name

    # --- the background half -------------------------------------------------------

    @staticmethod
    async def process(document_id, embedder: Embedder) -> None:
        """Extract, chunk, embed and index. Owns its session; never raises.

        Runs as a BackgroundTask, where nothing is left to catch an exception: an escaped
        error would be logged by Starlette as an unhandled task failure and the document
        would sit at "processing" forever, with the admin's progress bar frozen and no
        explanation. Every failure therefore lands on the row as status="failed" plus a
        human-readable reason.
        """
        settings = get_settings()

        async with get_sessionmaker()() as session:
            document = await session.get(Document, document_id)
            if document is None:  # deleted between request and background task
                log.warning("ingestion_document_vanished", document_id=str(document_id))
                return

            try:
                document.status = "processing"
                document.chunks_done = 0
                document.error = None
                await session.commit()

                text = extract_text(settings.documents_dir / document.title)
                if not text.strip():
                    raise ValueError(
                        "Aucun texte extrait du PDF (document scanné ou protégé ?)."
                    )

                chunks = split_by_article(
                    text,
                    source=document.title,
                    max_chars=settings.chunk_size,
                    overlap=settings.chunk_overlap,
                )
                if not chunks:
                    raise ValueError("Le document n'a produit aucun fragment indexable.")

                document.chunks_total = len(chunks)
                await session.commit()

                log.info(
                    "document_chunked",
                    filename=document.title,
                    chunks=len(chunks),
                    citable_as_article=sum(1 for c in chunks if c.article_number),
                )

                # Replace rather than append: re-ingesting a document must not leave the
                # previous run's chunks behind as duplicates in the index.
                await session.execute(delete(Chunk).where(Chunk.document_id == document.id))
                document.corpus_version += 1

                for start in range(0, len(chunks), EMBED_BATCH_SIZE):
                    batch = chunks[start : start + EMBED_BATCH_SIZE]
                    embeddings = await embedder.embed_documents([c.content for c in batch])

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
                        for i, c in enumerate(batch)
                    )

                    # Commit per batch so the progress the admin is polling is real: it
                    # reflects rows that are actually in the index, not rows we intend to
                    # write. A crash at 60% leaves a document that genuinely holds 60% of
                    # its chunks, and status="failed" tells the admin to re-run it.
                    document.chunks_done = min(start + len(batch), len(chunks))
                    await session.commit()

                document.status = "indexed"
                document.indexed_at = datetime.now(UTC)
                await session.commit()

                log.info("document_indexed", filename=document.title, chunks=len(chunks))

            except Exception as exc:
                # Roll back the in-flight batch before writing the failure, or the UPDATE
                # itself fails on a poisoned transaction and the row keeps saying
                # "processing" — the exact frozen-bar state this handler exists to prevent.
                await session.rollback()
                log.exception("ingestion_failed", document_id=str(document_id))

                document = await session.get(Document, document_id)
                if document is not None:
                    document.status = "failed"
                    # str(exc), not the traceback: this string is rendered in the admin UI.
                    # A ValueError we raised above is already a sentence; anything else gets
                    # its class name so the message is never an empty string.
                    document.error = str(exc) or exc.__class__.__name__
                    await session.commit()

    # --- read model for the admin screen -------------------------------------------

    async def list_documents(self) -> list[Document]:
        return list(
            await self._session.scalars(
                select(Document).order_by(Document.created_at.desc())
            )
        )

    async def corpus_chunk_count(self) -> int:
        return int(await self._session.scalar(select(func.count()).select_from(Chunk)) or 0)
