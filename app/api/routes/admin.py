"""Admin corpus management.

Every route here is behind CurrentAdmin, which chains onto get_current_user — so an admin
route cannot skip the token/active-account checks the normal user dependency performs.

WHY UPLOAD RETURNS 202 AND NOT 200. Ingesting a legal code is extract + chunk + embed over
hundreds of chunks on a CPU: tens of seconds at best. Holding the request open for that
would hit the proxy's idle timeout on a free host and hand the admin a 504 for an ingest
that is in fact running fine. 202 Accepted with a document row the client can poll is the
honest shape — the work is queued, here is its id, ask again.
"""
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, File, UploadFile, status

from app.api.deps import CurrentAdmin, EmbedderDep, SessionDep
from app.api.schemas.admin import CorpusStatusOut, DocumentOut, UploadAccepted
from app.core.config import get_settings
from app.core.errors import DocumentNotFound, to_http_exception
from app.core.logging import get_logger
from app.services.ingestion_service import IngestionService

log = get_logger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

# Terminal states. A document in any other state still has work in flight, which is what
# tells the client to keep polling.
_SETTLED = {"indexed", "failed"}


@router.post(
    "/documents",
    response_model=UploadAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_document(
    admin: CurrentAdmin,
    session: SessionDep,
    embedder: EmbedderDep,
    background: BackgroundTasks,
    # Annotated form rather than `file: UploadFile = File(...)`: a call in an argument
    # default is evaluated once at import (ruff B008), and the Annotated spelling is the
    # current FastAPI idiom anyway.
    file: Annotated[UploadFile, File()],
) -> UploadAccepted:
    """Accept a PDF, register it, and queue the indexing.

    The commit before add_task is deliberate and load-bearing. BackgroundTasks run after
    the response is sent, and the background job opens its OWN session — so if this
    request's transaction has not committed yet, that job looks up a document id that does
    not exist and exits as "vanished". Commit first, queue second.
    """
    service = IngestionService(session, embedder)

    data = await file.read()
    document = await service.register(file.filename or "document.pdf", data)

    processing = await service.needs_processing(document)
    document_id = document.id

    await session.commit()

    if processing:
        # The embedder is the singleton from app.state — loaded once in the lifespan. It is
        # passed in rather than rebuilt because constructing it costs a 450MB weight load.
        background.add_task(IngestionService.process, document_id, embedder)
        log.info(
            "ingestion_queued",
            document_id=str(document_id),
            filename=document.title,
            admin_id=str(admin.id),
        )
    else:
        log.info("ingestion_skipped_already_indexed", document_id=str(document_id))

    await session.refresh(document)
    return UploadAccepted(
        document=DocumentOut.model_validate(document), processing=processing
    )


@router.get("/corpus", response_model=CorpusStatusOut)
async def corpus_status(
    admin: CurrentAdmin,
    session: SessionDep,
    embedder: EmbedderDep,
) -> CorpusStatusOut:
    """The admin screen's polling endpoint: every document, plus corpus totals.

    Deliberately cheap — a SELECT over documents and one COUNT — because the client hits it
    on a timer while an ingest runs. Nothing here loads a model or touches the LLM.
    """
    service = IngestionService(session, embedder)
    documents = await service.list_documents()

    return CorpusStatusOut(
        documents=[DocumentOut.model_validate(d) for d in documents],
        total_chunks=await service.corpus_chunk_count(),
        # Reported so a stale index is VISIBLE rather than inferred. If this string stops
        # matching what the chunks were embedded with, retrieval is quietly degraded — the
        # exact shape of bug 13, which went unnoticed precisely because nothing displayed it.
        embedding_model=get_settings().embedding_model_name,
        is_ingesting=any(d.status not in _SETTLED for d in documents),
    )


@router.get("/documents/{document_id}", response_model=DocumentOut)
async def document_detail(
    document_id: str,
    admin: CurrentAdmin,
    session: SessionDep,
    embedder: EmbedderDep,
) -> DocumentOut:
    """One document's live progress.

    Exists alongside /corpus so a client watching a single upload can poll a small response
    instead of the whole corpus listing.
    """
    from app.infra.db.models import Document

    document = await session.get(Document, document_id)
    if document is None:
        raise to_http_exception(DocumentNotFound())

    return DocumentOut.model_validate(document)
