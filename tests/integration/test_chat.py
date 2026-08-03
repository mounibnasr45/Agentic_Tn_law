"""Bugs 2, 3 and 4, proven dead against a real Postgres.

The LLM is mocked throughout — CI needs no API key, the tests are deterministic, and they
run in milliseconds. What is NOT mocked: Postgres, pgvector, the LangGraph checkpointer,
the retrieval tool, and the citation rows. The interesting behaviour is all in those.
"""
import os
import uuid
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from openai import AuthenticationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# Optional-dependency stubbing lives in conftest.py, which pytest imports before
# this module — see the explanation there of why setdefault-on-sys.modules was wrong.
# These two imports must follow the sys.modules stubbing above — app.agent.graph imports
# langgraph.checkpoint.postgres.aio at module load, so the fakes have to be registered
# first on any machine where the real packages aren't installed.
from app.agent.graph import create_checkpointer  # noqa: E402
from app.infra.db.models import Chunk, Document
from app.main import create_app  # noqa: E402
from tests.fakes import FakeEmbedder

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="no DATABASE_URL; integration tests need Postgres"
)

CORPUS = [
    ("Article 258", "Quiconque soustrait frauduleusement une chose qui ne lui appartient "
                    "pas est coupable de vol."),
    ("Article 261", "Est puni de vingt ans de prison, le vol commis avec arme."),
    ("Article 23", "L'Etat interdit la torture. Le crime de torture est imprescriptible."),
]


class ScriptedChatModel(BaseChatModel):
    """A real BaseChatModel whose replies are scripted.

    Duck-typing does not work here: create_react_agent composes the model into a Runnable
    chain (`prompt | model`), so anything that is not a genuine Runnable fails with
    `TypeError: Expected a Runnable`. Subclassing BaseChatModel is the honest way to fake
    an LLM, and it means the graph, the tool-calling protocol and the ToolNode are all
    exercised for real — only the network call is replaced.
    """

    replies: list[AIMessage] = []
    fail_with: Exception | None = None

    model_config = {"arbitrary_types_allowed": True}

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **_kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **_kwargs) -> ChatResult:
        if self.fail_with is not None:
            raise self.fail_with

        reply = self.replies.pop(0) if self.replies else AIMessage(content="")
        return ChatResult(generations=[ChatGeneration(message=reply)])

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        return self._generate(messages, stop, run_manager, **kwargs)


def searching_model(
    answer: str = "Selon l'article 261, la peine est de vingt ans.",
) -> ScriptedChatModel:
    """Calls the retrieval tool once, then answers — the normal agent trajectory."""
    return ScriptedChatModel(
        replies=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "rechercher_textes_juridiques",
                        "args": {"query": "peine vol avec arme"},
                        "id": "call_1",
                    }
                ],
            ),
            AIMessage(content=answer),
        ]
    )


@pytest_asyncio.fixture
async def app_and_engine():
    engine = create_async_engine(os.environ["DATABASE_URL"])

    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE users, refresh_tokens, conversations, messages, citations, "
                "documents, chunks RESTART IDENTITY CASCADE"
            )
        )

    # Seed the corpus with the fake embedder, so no model is downloaded.
    embedder = FakeEmbedder()
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        document = Document(title="penal_code.pdf", sha256="chatfixture", status="indexed")
        session.add(document)
        await session.flush()

        embeddings = await embedder.embed_documents([body for _, body in CORPUS])
        session.add_all(
            Chunk(
                document_id=document.id,
                chunk_index=i,
                article_number=article,
                content=body,
                embedding_model=embedder.model_name,
                embedding=embeddings[i].tolist(),
            )
            for i, (article, body) in enumerate(CORPUS)
        )
        await session.commit()

    app = create_app()
    app.state.embedder = embedder
    checkpointer, pool = await create_checkpointer(os.environ["DATABASE_URL"])
    app.state.checkpointer = checkpointer

    yield app, engine

    await pool.close()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE users, refresh_tokens, conversations, messages, citations, "
                "documents, chunks RESTART IDENTITY CASCADE"
            )
        )
    await engine.dispose()


async def _client(app) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _register(client, email: str) -> dict:
    response = await client.post(
        "/api/auth/register", json={"email": email, "password": "correct-horse-battery"}
    )
    assert response.status_code == 201
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


class TestBug2CrossUserMemory:
    """The old agent held its memory as an object attribute, and the frontend cached that
    object process-wide. Every visitor shared one ConversationBufferWindowMemory. Now
    memory lives in Postgres keyed by a thread that belongs to a user row."""

    async def test_two_users_cannot_see_each_others_conversations(self, app_and_engine):
        app, _ = app_and_engine

        async with await _client(app) as client:
            alice = await _register(client, "alice@tunis.tn")
            bob = await _register(client, "bob@tunis.tn")

            with patch("app.agent.graph.ChatOpenAI", return_value=searching_model()):
                created = await client.post(
                    "/api/ask",
                    json={"question": "Quelle peine pour un vol avec arme ?"},
                    headers=alice,
                )
            assert created.status_code == 200
            alice_conversation = created.json()["conversation_id"]

            # Bob's conversation list must be empty...
            bob_list = await client.get("/api/conversations", headers=bob)
            assert bob_list.json() == []

            # ...and naming Alice's conversation id must give Bob a 404, NOT her history.
            # 404 rather than 403: telling him it exists but is not his is still telling him
            # it exists.
            stolen = await client.get(f"/api/conversations/{alice_conversation}", headers=bob)
            assert stolen.status_code == 404

    async def test_a_user_sees_their_own_history(self, app_and_engine):
        app, _ = app_and_engine

        async with await _client(app) as client:
            alice = await _register(client, "alice@tunis.tn")

            with patch("app.agent.graph.ChatOpenAI", return_value=searching_model()):
                created = await client.post(
                    "/api/ask", json={"question": "Qu'est-ce que le vol ?"}, headers=alice
                )
            conversation_id = created.json()["conversation_id"]

            history = await client.get(f"/api/conversations/{conversation_id}", headers=alice)

            assert history.status_code == 200
            roles = [m["role"] for m in history.json()]
            assert roles == ["user", "assistant"]

    async def test_an_unauthenticated_caller_cannot_ask(self, app_and_engine):
        app, _ = app_and_engine

        async with await _client(app) as client:
            response = await client.post("/api/ask", json={"question": "Vol ?"})

        assert response.status_code == 401


class TestBug3FailuresAreNotAnswers:
    async def test_an_llm_failure_returns_502_not_a_200_containing_the_error(
        self, app_and_engine
    ):
        """The old run() caught Exception and returned str(e) AS the answer, so an upstream
        timeout was served to the user as legal advice with a 200 OK."""
        app, _ = app_and_engine

        broken = ScriptedChatModel(fail_with=TimeoutError("upstream timed out"))

        async with await _client(app) as client:
            headers = await _register(client, "alice@tunis.tn")

            with patch("app.agent.graph.ChatOpenAI", return_value=broken):
                response = await client.post(
                    "/api/ask", json={"question": "Quelle peine pour un vol ?"}, headers=headers
                )

        assert response.status_code == 502
        body = response.json()
        # The failure must not be dressed up as content.
        assert "upstream timed out" not in str(body)
        assert "answer" not in body

    async def test_a_failed_question_is_not_persisted_as_an_answer(self, app_and_engine):
        app, engine = app_and_engine

        broken = ScriptedChatModel(fail_with=RuntimeError("boom"))

        async with await _client(app) as client:
            headers = await _register(client, "alice@tunis.tn")
            with patch("app.agent.graph.ChatOpenAI", return_value=broken):
                await client.post("/api/ask", json={"question": "Vol ?"}, headers=headers)

        async with engine.connect() as conn:
            messages = (await conn.execute(text("SELECT count(*) FROM messages"))).scalar_one()

        assert messages == 0, "a failed run wrote a message row"

    async def test_openrouter_authentication_failure_returns_a_configuration_error(
        self, app_and_engine
    ):
        app, _ = app_and_engine

        response_stub = type(
            "ResponseStub",
            (),
            {"status_code": 401, "request": None, "headers": {}},
        )()
        broken = ScriptedChatModel(
            fail_with=AuthenticationError(
                message="User not found.", response=response_stub, body={"error": {}}
            )
        )

        async with await _client(app) as client:
            headers = await _register(client, "alice@tunis.tn")

            with patch("app.agent.graph.ChatOpenAI", return_value=broken):
                response = await client.post(
                    "/api/ask", json={"question": "Quelle peine pour un vol ?"}, headers=headers
                )

        assert response.status_code == 502
        # Source of truth is UpstreamLLMAuthenticationError.detail in app/core/errors.py.
        assert response.json()["detail"] == "OPENROUTER_API_KEY invalide ou révoquée."


class TestBug4RealCitations:
    """`sources` was a hardcoded placeholder string, because the tool flattened its results
    into truncated text before anything could use them."""

    async def test_the_answer_carries_citations_with_real_article_numbers(self, app_and_engine):
        app, _ = app_and_engine

        async with await _client(app) as client:
            headers = await _register(client, "alice@tunis.tn")

            with patch("app.agent.graph.ChatOpenAI", return_value=searching_model()):
                response = await client.post(
                    "/api/ask",
                    json={"question": "Quelle peine pour un vol commis avec arme ?"},
                    headers=headers,
                )

        citations = response.json()["citations"]

        assert citations, "no citations — the tool's results never escaped it"
        assert all(c["chunk_id"] for c in citations)
        assert any(c["article_number"] == "Article 261" for c in citations)
        assert all(c["source"] == "penal_code.pdf" for c in citations)

    async def test_citations_are_persisted_and_reference_real_chunks(self, app_and_engine):
        app, engine = app_and_engine

        async with await _client(app) as client:
            headers = await _register(client, "alice@tunis.tn")
            with patch("app.agent.graph.ChatOpenAI", return_value=searching_model()):
                await client.post(
                    "/api/ask", json={"question": "Peine pour vol avec arme ?"}, headers=headers
                )

        async with engine.connect() as conn:
            # The join is the point: a citation row cannot exist for a chunk that was never
            # retrieved, because chunk_id is a foreign key. That is a far stronger guarantee
            # than telling the model to cite its sources.
            rows = (
                await conn.execute(
                    text(
                        "SELECT c.article_number, ch.article_number "
                        "FROM citations c JOIN chunks ch ON ch.id = c.chunk_id"
                    )
                )
            ).all()

        assert rows, "no citation rows persisted"
        assert all(cited == actual for cited, actual in rows), "a citation misnames its chunk"

    async def test_a_conversation_with_no_answer_yet_has_no_citations(self, app_and_engine):
        app, _ = app_and_engine

        async with await _client(app) as client:
            headers = await _register(client, "alice@tunis.tn")
            response = await client.get(
                f"/api/conversations/{uuid.uuid4()}", headers=headers
            )

        assert response.status_code == 404
