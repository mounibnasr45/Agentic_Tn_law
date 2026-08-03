"""The reflection checkpoint, proven against a real Postgres.

Mirrors test_chat.py's approach: the LLM is scripted so CI needs no API key and the tests
are deterministic, but Postgres, pgvector, the LangGraph checkpointer, the retrieval tool
and the citation rows are all real. The interesting behaviour lives in those.

WHAT THESE TESTS ACTUALLY ASSERT. Not "does the model spot the term" — that is a prompt
quality question, it needs the eval set, and it cannot be a deterministic CI gate. These
assert the ENGINEERING contract around the model:

  1. a named term causes a second retrieval, and the definition it finds becomes a citation
  2. RIEN leaves the draft byte-identical and issues no extra retrieval
  3. every failure mode returns the draft rather than a 502  <- the load-bearing one
  4. the feature flag actually disables the feature
"""
import os
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# Same sys.modules stubbing as test_chat.py, and for the same reason: app.agent.graph
# imports langgraph.checkpoint.postgres.aio at module load, so the fakes must be registered
# before that import happens on a machine without the real packages.
# Optional-dependency stubbing lives in conftest.py, which pytest imports before
# this module — see the explanation there of why setdefault-on-sys.modules was wrong.
from app.agent.graph import create_checkpointer  # noqa: E402
from app.core.config import get_settings
from app.infra.db.models import Chunk, Document
from app.main import create_app  # noqa: E402
from tests.fakes import FakeEmbedder

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="no DATABASE_URL; integration tests need Postgres"
)

# The premeditation case from eval/golden_set.json id 5, reduced to its essentials: an
# article that sets a penalty and names a term of art, and a SEPARATE article that defines
# that term. Article 201 does not define préméditation — that is the whole gap.
CORPUS = [
    ("Article 201", "Est puni de mort le meurtre commis avec premeditation ou guet-apens."),
    ("Article 202", "La premeditation consiste dans le dessein forme avant l'action "
                    "d'attenter a la personne d'un individu determine."),
    ("Article 258", "Quiconque soustrait frauduleusement une chose qui ne lui appartient "
                    "pas est coupable de vol."),
]

DRAFT = "Selon l'article 201, le meurtre avec premeditation est puni de mort."


class ScriptedChatModel(BaseChatModel):
    """A real BaseChatModel whose replies are scripted, recording what it was asked.

    Subclassing rather than duck-typing is not optional: create_react_agent composes the
    model into a Runnable chain, and anything that is not a genuine Runnable fails with
    `TypeError: Expected a Runnable`.

    `prompts_seen` is the addition over test_chat.py's version — several tests below need to
    prove a call did NOT happen, and counting prompts is how.
    """

    replies: list[AIMessage] = []
    fail_with: Exception | None = None
    prompts_seen: list[str] = []

    model_config = {"arbitrary_types_allowed": True}

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **_kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **_kwargs) -> ChatResult:
        self.prompts_seen.append(str(messages[-1].content) if messages else "")

        if self.fail_with is not None:
            raise self.fail_with

        reply = self.replies.pop(0) if self.replies else AIMessage(content="")
        return ChatResult(generations=[ChatGeneration(message=reply)])

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        return self._generate(messages, stop, run_manager, **kwargs)


def scripted(*replies: str | AIMessage, fail_with: Exception | None = None):
    """Build a model that plays the given replies in order.

    One model instance serves BOTH the agent and the reflection checkpoint, because
    chat_service builds them through the same patched `app.agent.graph.ChatOpenAI`. The
    script is therefore the full call sequence for one request:

        1. agent: tool call    2. agent: draft    3. reflection    4. finalize
    """
    return ScriptedChatModel(
        replies=[r if isinstance(r, AIMessage) else AIMessage(content=r) for r in replies],
        fail_with=fail_with,
        prompts_seen=[],
    )


def tool_call(query: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {"name": "rechercher_textes_juridiques", "args": {"query": query}, "id": "call_1"}
        ],
    )


@pytest_asyncio.fixture(autouse=True)
def _reset_settings_cache():
    """get_settings is lru_cached; tests that patch env must clear it both ways."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def app_and_engine():
    engine = create_async_engine(os.environ["DATABASE_URL"])

    truncate = (
        "TRUNCATE users, refresh_tokens, conversations, messages, citations, "
        "documents, chunks RESTART IDENTITY CASCADE"
    )
    async with engine.begin() as conn:
        await conn.execute(text(truncate))

    embedder = FakeEmbedder()
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        document = Document(title="penal_code.pdf", sha256="reflectionfixture", status="indexed")
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
        await conn.execute(text(truncate))
    await engine.dispose()


async def _client(app) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _register(client, email: str = "alice@tunis.tn") -> dict:
    response = await client.post(
        "/api/auth/register", json={"email": email, "password": "correct-horse-battery"}
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _ask(client, model, headers, question: str = "Peine pour meurtre avec premeditation ?"):
    with patch("app.agent.graph.ChatOpenAI", return_value=model):
        return await client.post("/api/ask", json={"question": question}, headers=headers)


class TestGapFound:
    """The premeditation case: the draft names a term the retrieved article never defines."""

    async def test_the_definition_article_is_retrieved_and_cited(self, app_and_engine):
        """The load-bearing integration point.

        The definition must not merely appear in the prose — it must arrive as a citation,
        which only happens because reflection reuses the agent's retrieval tool and runs
        inside the ContextVar window. Retrieve it any other way and the answer would cite
        Article 202 with no citation row behind it.
        """
        app, _ = app_and_engine

        model = scripted(
            tool_call("premeditation"),                 # 1. agent searches
            DRAFT,                                       # 2. agent drafts (no definition)
            "premeditation",                             # 3. reflection names the gap
            f"{DRAFT} Au sens de l'article 202, la premeditation est le dessein forme "
            "avant l'action.",                           # 4. finalize folds it in
        )

        async with await _client(app) as client:
            headers = await _register(client)
            response = await _ask(client, model, headers)

        assert response.status_code == 200
        body = response.json()

        cited = {c["article_number"] for c in body["citations"]}
        assert "Article 201" in cited, "lost the article the draft was built on"
        assert "Article 202" in cited, (
            "the definition article was never cited — reflection's retrieval did not reach "
            "the citation list"
        )
        assert "202" in body["answer"], "the rewrite did not make it into the answer"

    async def test_the_definition_citation_is_persisted_with_a_real_chunk_id(
        self, app_and_engine
    ):
        """Same guarantee as bug 4's test, extended to the reflection path: a citation row
        cannot exist for a chunk that was never retrieved, because chunk_id is a foreign key.
        """
        app, engine = app_and_engine

        model = scripted(
            tool_call("premeditation"),
            DRAFT,
            "premeditation",
            f"{DRAFT} Au sens de l'article 202, il s'agit d'un dessein forme a l'avance.",
        )

        async with await _client(app) as client:
            headers = await _register(client)
            await _ask(client, model, headers)

        async with engine.connect() as conn:
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
        assert any(cited == "Article 202" for cited, _ in rows), (
            "the definition article has no persisted citation row"
        )


class TestNoGap:
    async def test_rien_leaves_the_draft_untouched(self, app_and_engine):
        """The common path — most answers have no gap, and must cost exactly one extra call
        and zero extra retrievals."""
        app, _ = app_and_engine

        model = scripted(tool_call("vol"), DRAFT, "RIEN")

        async with await _client(app) as client:
            headers = await _register(client)
            response = await _ask(client, model, headers)

        assert response.status_code == 200
        assert response.json()["answer"] == DRAFT, "the draft was modified despite RIEN"
        # 3 calls: tool call, draft, reflection. A 4th would mean a finalize ran on RIEN.
        assert len(model.prompts_seen) == 3, f"unexpected call count: {model.prompts_seen}"

    async def test_a_refusal_draft_skips_reflection_entirely(self, app_and_engine):
        """An answer with no citations has nothing to ground. Reflecting on it would spend a
        call to be told there is nothing to do."""
        app, _ = app_and_engine

        refusal = "Je n'ai pas trouve de disposition applicable."
        model = scripted(refusal)  # answers directly, never calls the tool

        async with await _client(app) as client:
            headers = await _register(client)
            response = await _ask(client, model, headers, question="Quelle est la meteo ?")

        assert response.status_code == 200
        assert response.json()["answer"] == refusal
        assert len(model.prompts_seen) == 1, "reflection ran on a draft with no citations"


class TestFailsOpen:
    """The invariant that matters most: reflection can improve an answer, never withhold one.

    Each test drives a different failure INTO the checkpoint and asserts the user still gets
    their draft with a 200 — never the 502 that chat_service raises for genuine agent
    failures.
    """

    async def test_a_reflection_crash_still_returns_the_draft(self, app_and_engine):
        app, _ = app_and_engine

        class FailAfterDraft(ScriptedChatModel):
            """Answers the agent normally, then explodes on the reflection call."""

            def _generate(self, messages, stop=None, run_manager=None, **_kwargs):
                self.prompts_seen.append("")
                if len(self.prompts_seen) > 2:  # 1 = tool call, 2 = draft, 3 = reflection
                    raise RuntimeError("reflection upstream exploded")
                reply = self.replies.pop(0) if self.replies else AIMessage(content="")
                return ChatResult(generations=[ChatGeneration(message=reply)])

        model = FailAfterDraft(
            replies=[tool_call("premeditation"), AIMessage(content=DRAFT)], prompts_seen=[]
        )

        async with await _client(app) as client:
            headers = await _register(client)
            response = await _ask(client, model, headers)

        assert response.status_code == 200, "a reflection failure became a 502"
        assert response.json()["answer"] == DRAFT

    async def test_an_unparseable_reflection_reply_returns_the_draft(self, app_and_engine):
        """A model that ignores the format and writes an essay must not have that essay
        parsed as search terms."""
        app, _ = app_and_engine

        essay = (
            "Après analyse approfondie de la réponse fournie, je constate que le texte "
            "utilise plusieurs notions qui mériteraient d'être approfondies, notamment en "
            "ce qui concerne la qualification juridique des faits, et il conviendrait de "
            "préciser davantage les éléments constitutifs de l'infraction visée par "
            "l'article, ce qui suppose une analyse détaillée de la jurisprudence."
        )
        model = scripted(tool_call("premeditation"), DRAFT, essay)

        async with await _client(app) as client:
            headers = await _register(client)
            response = await _ask(client, model, headers)

        assert response.status_code == 200
        assert response.json()["answer"] == DRAFT, "an essay was parsed as terms"

    async def test_a_collapsed_rewrite_is_rejected_in_favour_of_the_draft(self, app_and_engine):
        """The rewrite lost the legal content instead of adding to it — the 'summarised
        instead of rewriting' failure. The draft wins."""
        app, _ = app_and_engine

        model = scripted(tool_call("premeditation"), DRAFT, "premeditation", "Oui.")

        async with await _client(app) as client:
            headers = await _register(client)
            response = await _ask(client, model, headers)

        assert response.status_code == 200
        assert response.json()["answer"] == DRAFT, "a collapsed rewrite replaced the answer"

    async def test_an_agent_failure_is_still_a_502(self, app_and_engine):
        """The complement, and the reason the broad except lives in reflection.py rather than
        around the whole block: failing open must not swallow real agent failures. Bug 3
        stays dead."""
        app, _ = app_and_engine

        model = scripted(fail_with=RuntimeError("agent exploded"))

        async with await _client(app) as client:
            headers = await _register(client)
            response = await _ask(client, model, headers)

        assert response.status_code == 502


class TestFeatureFlag:
    async def test_disabling_reflection_skips_the_call_entirely(self, app_and_engine):
        """The free-tier kill switch. If this does not hold, turning the feature off under
        load does nothing."""
        app, _ = app_and_engine

        model = scripted(tool_call("premeditation"), DRAFT)

        async with await _client(app) as client:
            headers = await _register(client)
            with patch.dict(os.environ, {"REFLECTION_ENABLED": "false"}):
                get_settings.cache_clear()
                response = await _ask(client, model, headers)

        assert response.status_code == 200
        assert response.json()["answer"] == DRAFT
        assert len(model.prompts_seen) == 2, "reflection ran while disabled"


class TestTrace:
    """The trace is the UI's evidence that this is not one-shot RAG, so it has to be true.

    These assert the trace reflects what ACTUALLY happened — the agent's own query, real
    scores, the reflection outcome — rather than a decorative log the frontend could have
    invented.
    """

    async def test_the_trace_records_the_query_the_agent_wrote(self, app_and_engine):
        app, _ = app_and_engine

        # The agent searches for something different from what the user typed. That gap is
        # the whole point of showing both.
        model = scripted(tool_call("definition premeditation"), DRAFT, "RIEN")

        async with await _client(app) as client:
            headers = await _register(client)
            response = await _ask(
                client, model, headers, question="Peine pour meurtre avec premeditation ?"
            )

        trace = response.json()["trace"]
        retrieval = [s for s in trace["steps"] if s["kind"] == "retrieval"]

        assert retrieval, "no retrieval step recorded"
        assert retrieval[0]["query"] == "definition premeditation", (
            "the trace must show the AGENT's query, not the user's question"
        )
        assert retrieval[0]["results"], "retrieval recorded no ranked results"
        # Real numbers, not NaN. A NaN similarity survives np.clip, then serialises to
        # JSON as `null` on a field the schema declares non-nullable — which is exactly
        # what this assertion caught the first time it ran.
        assert all(
            isinstance(r["score"], float) and 0.0 <= r["score"] <= 1.0
            for r in retrieval[0]["results"]
        ), f'non-finite score in the trace: {retrieval[0]["results"]}'
        assert [r["rank"] for r in retrieval[0]["results"]] == sorted(
            r["rank"] for r in retrieval[0]["results"]
        ), "results are not in rank order"

    async def test_the_trace_reports_the_iteration_budget(self, app_and_engine):
        app, _ = app_and_engine
        model = scripted(tool_call("vol"), DRAFT, "RIEN")

        async with await _client(app) as client:
            headers = await _register(client)
            response = await _ask(client, model, headers)

        trace = response.json()["trace"]
        assert trace["iterations_used"] == 1
        assert trace["max_iterations"] == 4, "the cap must be the real MAX_ITERATIONS"

    async def test_the_trace_shows_the_reflection_checkpoint_firing(self, app_and_engine):
        """The most demo-visible behaviour: draft -> spotted an undefined term -> searched
        again -> regrounded."""
        app, _ = app_and_engine

        model = scripted(
            tool_call("premeditation"),
            DRAFT,
            "premeditation",
            f"{DRAFT} Au sens de l'article 202, il s'agit d'un dessein forme a l'avance.",
        )

        async with await _client(app) as client:
            headers = await _register(client)
            response = await _ask(client, model, headers)

        trace = response.json()["trace"]
        kinds = [s["kind"] for s in trace["steps"]]

        assert trace["regrounded"] is True
        assert "reflection" in kinds, "the reflection step is missing from the trace"
        assert "answer" in kinds, "the regrounding step is missing from the trace"
        # Two searches: the original question, then the definition lookup.
        assert trace["iterations_used"] == 2
        reflection = next(s for s in trace["steps"] if s["kind"] == "reflection")
        assert "premeditation" in (reflection["detail"] or "")

    async def test_no_gap_leaves_the_trace_honest(self, app_and_engine):
        """RIEN must produce a reflection step that says so — not a missing step, and not a
        regrounded flag."""
        app, _ = app_and_engine
        model = scripted(tool_call("vol"), DRAFT, "RIEN")

        async with await _client(app) as client:
            headers = await _register(client)
            response = await _ask(client, model, headers)

        trace = response.json()["trace"]
        assert trace["regrounded"] is False
        reflection = [s for s in trace["steps"] if s["kind"] == "reflection"]
        assert len(reflection) == 1
        assert "Aucun terme" in (reflection[0]["detail"] or "")
