"""Endpoints a visitor can call before signing up — the landing page's data source."""
from fastapi import APIRouter

from app.api.deps import SessionDep
from app.api.routes.documents import list_indexed_documents
from app.api.schemas.documents import CorpusDocumentOut

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/corpus", response_model=list[CorpusDocumentOut])
async def public_corpus_overview(session: SessionDep) -> list[CorpusDocumentOut]:
    """What the corpus actually contains, for a visitor deciding whether to sign up.

    Deliberately unauthenticated, like /health and /evaluation: this is a listing of
    published, public legal texts and how many passages of each are indexed — not the
    documents themselves, which still requires an account (GET /documents/{id}/file).
    Showing real, live counts here rather than a marketing claim is the whole point of a
    technical landing page.
    """
    return await list_indexed_documents(session)
