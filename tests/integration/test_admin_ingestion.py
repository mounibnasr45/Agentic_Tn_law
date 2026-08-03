"""Admin corpus upload, against a real Postgres.

Nothing is mocked except the LLM (which these routes never call anyway). The PDF is real —
generated with PyMuPDF at fixture time rather than committed as a binary — so extraction,
article-aware chunking, embedding and the citation-grade chunk rows are all exercised for
real. The embedder is the FakeEmbedder so no 450MB download happens in CI; it satisfies the
same Embedder protocol the production encoder does.

THE PRIVILEGE BOUNDARY IS THE POINT OF HALF THESE TESTS. Uploading a document re-chunks and
re-embeds the corpus, which changes every future answer the system gives. On a public URL
that must not be reachable by "any account that managed to register".
"""
import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.agent.graph import create_checkpointer
from app.main import create_app
from tests.fakes import FakeEmbedder

# Optional-dependency stubbing lives in conftest.py, which pytest imports before this
# module — see the explanation there of why setdefault-on-sys.modules was wrong.

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="no DATABASE_URL; integration tests need Postgres"
)

TRUNCATE = (
    "TRUNCATE users, refresh_tokens, conversations, messages, citations, "
    "documents, chunks RESTART IDENTITY CASCADE"
)


def make_pdf(body: str) -> bytes:
    """A real, minimal PDF containing article-shaped legal text.

    Generated rather than committed: a binary fixture in the repo is opaque to review, and
    generating it means the text under test is visible right here in the assertions.
    """
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), body, fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


ARTICLES = (
    "Article 500\n"
    "Le vol simple est puni d'un an d'emprisonnement.\n\n"
    "Article 501\n"
    "Le vol avec effraction est puni de cinq ans.\n"
)


@pytest_asyncio.fixture
async def app_and_engine(tmp_path, monkeypatch):
    # Uploads are written to settings.documents_dir. Point it at tmp_path so the test
    # cannot overwrite the real corpus PDFs sitting in documents/.
    monkeypatch.setenv("DOCUMENTS_DIR", str(tmp_path))
    from app.core.config import get_settings

    get_settings.cache_clear()

    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with engine.begin() as conn:
        await conn.execute(text(TRUNCATE))

    app = create_app()
    app.state.embedder = FakeEmbedder()
    checkpointer, pool = await create_checkpointer(os.environ["DATABASE_URL"])
    app.state.checkpointer = checkpointer

    yield app, engine

    await pool.close()
    async with engine.begin() as conn:
        await conn.execute(text(TRUNCATE))
    await engine.dispose()
    get_settings.cache_clear()


async def _client(app) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _register(client, email: str) -> dict:
    response = await client.post(
        "/api/auth/register", json={"email": email, "password": "correct-horse-battery"}
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _make_admin(engine, email: str) -> None:
    """Promote via SQL — the same effect as `python -m app.cli grant-admin`.

    Deliberately not exposed over HTTP anywhere in the app, which is why the test has to
    reach into the database to do it.
    """
    async with engine.begin() as conn:
        await conn.execute(text("UPDATE users SET is_admin = true WHERE email = :e"), {"e": email})


async def _admin_headers(client, engine, email: str = "root@tunis.tn") -> dict:
    """Register, promote to admin, return auth headers.

    Takes an ALREADY-OPEN client rather than creating one: httpx auto-opens a client on
    first use, and a client that has been used cannot then be entered with `async with`
    ("Cannot open a client instance more than once").
    """
    headers = await _register(client, email)
    await _make_admin(engine, email)
    return headers


def _upload(name: str = "code.pdf", body: str = ARTICLES):
    return {"file": (name, make_pdf(body), "application/pdf")}


class TestPrivilegeBoundary:
    """Corpus upload replaces the ground truth for every future answer."""

    async def test_an_anonymous_caller_cannot_upload(self, app_and_engine):
        app, _ = app_and_engine
        async with await _client(app) as client:
            response = await client.post("/api/admin/documents", files=_upload())
        assert response.status_code == 401

    async def test_an_ordinary_logged_in_user_cannot_upload(self, app_and_engine):
        """Registering must not be enough. This is the test that matters on a public URL."""
        app, _ = app_and_engine
        async with await _client(app) as client:
            headers = await _register(client, "nobody@tunis.tn")
            response = await client.post(
                "/api/admin/documents", files=_upload(), headers=headers
            )

        assert response.status_code == 403
        assert response.json()["detail"] == "Accès réservé aux administrateurs."

    async def test_an_ordinary_user_cannot_read_corpus_status(self, app_and_engine):
        app, _ = app_and_engine
        async with await _client(app) as client:
            headers = await _register(client, "nobody@tunis.tn")
            response = await client.get("/api/admin/corpus", headers=headers)
        assert response.status_code == 403

    async def test_an_admin_can_upload(self, app_and_engine):
        app, engine = app_and_engine
        async with await _client(app) as client:
            headers = await _admin_headers(client, engine)
            response = await client.post(
                "/api/admin/documents", files=_upload(), headers=headers
            )

        assert response.status_code == 202, response.text


class TestIngestion:
    async def test_an_uploaded_pdf_becomes_searchable_chunks(self, app_and_engine):
        """The whole pipeline: upload -> extract -> chunk by article -> embed -> rows.

        BackgroundTasks run before ASGITransport returns the response, so by the time this
        assertion executes the ingest has completed — no polling needed in-process.
        """
        app, engine = app_and_engine
        async with await _client(app) as client:
            headers = await _admin_headers(client, engine)
            response = await client.post(
                "/api/admin/documents", files=_upload(), headers=headers
            )
            assert response.status_code == 202
            assert response.json()["processing"] is True

            corpus = (await client.get("/api/admin/corpus", headers=headers)).json()

        assert corpus["total_chunks"] > 0, "nothing was indexed"
        document = corpus["documents"][0]
        assert document["status"] == "indexed", document.get("error")
        assert document["chunks_done"] == document["chunks_total"] > 0
        assert document["progress"] == 1.0

        async with engine.connect() as conn:
            articles = [
                r[0]
                for r in (
                    await conn.execute(
                        text("SELECT article_number FROM chunks ORDER BY chunk_index")
                    )
                ).all()
            ]

        # Article-aware chunking, not fixed-size: the article numbers must survive, because
        # that column is what makes a citation checkable at all.
        assert "Article 500" in articles
        assert "Article 501" in articles

    async def test_reuploading_identical_bytes_does_not_duplicate_the_corpus(
        self, app_and_engine
    ):
        """documents.sha256 is UNIQUE; the second upload must reuse the row and skip work.

        The PDF is generated ONCE and both uploads send those same bytes. That is not a
        convenience: PyMuPDF stamps a creation timestamp into every document it writes, so
        calling make_pdf() twice with identical text yields different bytes and a different
        sha256 — which is a correct "new document", and would make this test silently assert
        nothing about deduplication.
        """
        app, engine = app_and_engine
        pdf = make_pdf(ARTICLES)
        payload = {"file": ("code.pdf", pdf, "application/pdf")}

        async with await _client(app) as client:
            headers = await _admin_headers(client, engine)
            first = await client.post("/api/admin/documents", files=payload, headers=headers)
            after_first = (await client.get("/api/admin/corpus", headers=headers)).json()

            second = await client.post("/api/admin/documents", files=payload, headers=headers)
            after_second = (await client.get("/api/admin/corpus", headers=headers)).json()

        assert first.json()["processing"] is True
        # Already indexed with the CURRENT encoder — no background work scheduled.
        assert second.json()["processing"] is False
        assert len(after_second["documents"]) == 1, "the corpus was duplicated"
        assert after_second["total_chunks"] == after_first["total_chunks"]

    async def test_a_second_document_adds_to_the_corpus(self, app_and_engine):
        app, engine = app_and_engine
        async with await _client(app) as client:
            headers = await _admin_headers(client, engine)
            await client.post("/api/admin/documents", files=_upload("a.pdf"), headers=headers)
            await client.post(
                "/api/admin/documents",
                files=_upload("b.pdf", "Article 900\nDisposition finale.\n"),
                headers=headers,
            )
            corpus = (await client.get("/api/admin/corpus", headers=headers)).json()

        assert len(corpus["documents"]) == 2
        assert all(d["status"] == "indexed" for d in corpus["documents"])


class TestFailureStates:
    """A failed ingest must be a visible, terminal state — never a bar frozen at
    'processing' with no explanation."""

    async def test_a_non_pdf_upload_is_rejected(self, app_and_engine):
        app, engine = app_and_engine
        async with await _client(app) as client:
            headers = await _admin_headers(client, engine)
            response = await client.post(
                "/api/admin/documents",
                files={"file": ("notes.txt", b"not a pdf", "text/plain")},
                headers=headers,
            )
        assert response.status_code == 415

    async def test_an_empty_upload_is_rejected(self, app_and_engine):
        app, engine = app_and_engine
        async with await _client(app) as client:
            headers = await _admin_headers(client, engine)
            response = await client.post(
                "/api/admin/documents",
                files={"file": ("empty.pdf", b"", "application/pdf")},
                headers=headers,
            )
        assert response.status_code == 400

    async def test_a_pdf_with_no_extractable_text_fails_with_a_reason(self, app_and_engine):
        """A scanned PDF has pages but no text layer. It must land on status=failed with a
        message an admin can act on, not sit at 'processing' forever."""
        app, engine = app_and_engine

        import fitz

        doc = fitz.open()
        doc.new_page()  # a page with no text at all
        blank = doc.tobytes()
        doc.close()

        async with await _client(app) as client:
            headers = await _admin_headers(client, engine)
            response = await client.post(
                "/api/admin/documents",
                files={"file": ("scan.pdf", blank, "application/pdf")},
                headers=headers,
            )
            assert response.status_code == 202  # accepted, then fails in the background

            corpus = (await client.get("/api/admin/corpus", headers=headers)).json()

        document = corpus["documents"][0]
        assert document["status"] == "failed"
        assert document["error"], "a failed document must say why"
        assert corpus["is_ingesting"] is False, "failed is a terminal state"


class TestCorpusStatus:
    async def test_status_reports_the_encoder_so_a_stale_index_is_visible(
        self, app_and_engine
    ):
        """Bug 13 went unnoticed because nothing displayed which encoder built the index."""
        app, engine = app_and_engine
        async with await _client(app) as client:
            headers = await _admin_headers(client, engine)
            corpus = (await client.get("/api/admin/corpus", headers=headers)).json()

        from app.core.config import get_settings

        assert corpus["embedding_model"] == get_settings().embedding_model_name

    async def test_progress_is_zero_not_nan_before_any_chunking(self, app_and_engine):
        """chunks_total is 0 in 'pending', and every document passes through 'pending' —
        so the naive client-side division is a guaranteed ZeroDivisionError."""
        app, engine = app_and_engine
        async with await _client(app) as client:
            headers = await _admin_headers(client, engine)
            await client.post("/api/admin/documents", files=_upload(), headers=headers)
            detail = (await client.get("/api/admin/corpus", headers=headers)).json()

        assert all(isinstance(d["progress"], float) for d in detail["documents"])
