"""Serves the source PDFs the agent cites, inline in the browser or as a
download, so a citation can be checked against its source."""
from pathlib import Path

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, SessionDep
from app.api.schemas.documents import CorpusDocumentOut
from app.core.config import get_settings
from app.core.errors import DocumentNotFound, to_http_exception
from app.infra.db.models import Chunk, Document

router = APIRouter(prefix="/documents", tags=["documents"])


def _resolved_path(document: Document) -> Path:
    """Where this document's bytes live, refusing anything outside the corpus directory.

    storage_key is written by IngestionService and is therefore trusted-ish — but it is a
    database column, and a database column is exactly the kind of thing that becomes
    attacker-controlled two refactors from now (an admin upload that sanitises its
    filename slightly differently, say). Resolving it and re-checking containment costs a
    syscall and removes the possibility entirely: this route can only ever serve files
    from documents_dir, whatever the row says.
    """
    settings = get_settings()
    root = settings.documents_dir.resolve()

    # Falls back to the title because storage_key is nullable — it stays NULL for rows
    # created before it existed, and the corpus files are named after their title anyway.
    candidate = Path(document.storage_key) if document.storage_key else root / document.title
    resolved = candidate.resolve()

    if resolved != root and root not in resolved.parents:
        raise DocumentNotFound()
    if not resolved.is_file():
        raise DocumentNotFound()

    return resolved


async def list_indexed_documents(session: AsyncSession) -> list[CorpusDocumentOut]:
    """The corpus, as something to read rather than something to operate.

    Only indexed documents: a row that is still processing has no citable content yet, and
    one that failed has nothing behind it at all. Offering either would be offering a
    broken link.

    A plain function, not a route, so both the authenticated in-app viewer and the
    unauthenticated landing page (app/api/routes/public.py) run the exact same query —
    the corpus overview a visitor sees before signing up must not be able to drift from
    what they get after.
    """
    rows = await session.execute(
        select(Document, func.count(Chunk.id))
        .outerjoin(Chunk, Chunk.document_id == Document.id)
        .where(Document.status == "indexed")
        .group_by(Document.id)
        .order_by(Document.title)
    )

    documents = []
    for document, chunk_count in rows.all():
        try:
            size = _resolved_path(document).stat().st_size
        except Exception:  # noqa: BLE001 - a missing file must not break the whole listing
            # Indexed in the database but absent from disk: possible after a redeploy that
            # changed the corpus. Listing it as 0 bytes is better than a 500 on the page,
            # and the file route will return a clean 404 if it is opened.
            size = 0

        documents.append(
            CorpusDocumentOut(
                id=document.id,
                title=document.title,
                size_bytes=size,
                chunk_count=chunk_count,
                indexed_at=document.indexed_at,
            )
        )

    return documents


@router.get("", response_model=list[CorpusDocumentOut])
async def list_documents(user: CurrentUser, session: SessionDep) -> list[CorpusDocumentOut]:
    return await list_indexed_documents(session)


@router.get("/{document_id}/file")
async def get_document_file(
    document_id: str,
    user: CurrentUser,
    session: SessionDep,
    download: bool = Query(False, description="attachment instead of inline preview"),
) -> FileResponse:
    document = await session.get(Document, document_id)
    if document is None:
        raise to_http_exception(DocumentNotFound())

    try:
        path = _resolved_path(document)
    except DocumentNotFound as exc:
        raise to_http_exception(exc) from exc

    disposition = "attachment" if download else "inline"

    return FileResponse(
        path,
        media_type="application/pdf",
        # filename= alone would force `attachment`; setting the header directly is what
        # keeps the inline case inline. FileResponse quotes the filename for us here.
        headers={
            "Content-Disposition": f'{disposition}; filename="{document.title}"',
            # The corpus changes only on a reindex, and the browser re-requests on every
            # navigation otherwise — which on a free tier means re-sending 500KB.
            "Cache-Control": "private, max-age=3600",
        },
    )
