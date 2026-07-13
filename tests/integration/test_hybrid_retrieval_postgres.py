"""Bug 1, proven against a real Postgres.

The unit tests in tests/test_retrieval.py exercise the same logic against in-memory
fakes, which proves the DESIGN is durable. This proves the IMPLEMENTATION is: real
pgvector, real tsvector, real SQL, and a retriever constructed in a process that never
indexed anything.

Skips when DATABASE_URL is unset, so a laptop without Docker still runs the suite; CI
provides a pgvector service, so it always runs there.
"""
import os

import pytest
import pytest_asyncio
from sqlalchemy import inspect, text

from app.domain.retrieval import FusionStrategy, HybridRetriever
from app.infra.db.models import Base, Chunk, Document
from app.infra.db.repositories.chunk_repo import PostgresChunkRepository
from tests.fakes import FakeEmbedder

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="no DATABASE_URL; integration tests need Postgres"
)

CORPUS = [
    ("Article 264", "Le vol simple est puni d'une peine de prison de six mois."),
    ("Article 265", "Le vol aggrave est puni d'une peine de prison de dix ans."),
    ("Article 75", "Le president de la republique est elu au suffrage universel."),
    ("Article 31", "La liberte d'opinion est garantie par la constitution."),
]


@pytest_asyncio.fixture
async def session():
    """A session against the MIGRATED schema.

    Deliberately does NOT call Base.metadata.create_all(). Doing so would build the
    tables from the ORM models and quietly test a schema that is not the one Alembic
    produces — so a divergence between model and migration would pass CI and only
    surface in production. (That divergence was real: the ORM used a Python-side
    `default=`, which never reaches the DDL, so create_all() emitted columns with no
    database default while the migration emitted them with one.)

    The schema must therefore already exist: `alembic upgrade head`. Isolation between
    tests is by TRUNCATE, which is also faster than dropping and recreating.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(os.environ["DATABASE_URL"])

    async with engine.begin() as conn:
        tables = await conn.run_sync(
            lambda sync_conn: inspect(sync_conn).get_table_names()
        )
        missing = {t.name for t in Base.metadata.sorted_tables} - set(tables)
        if missing:
            pytest.fail(f"schema not migrated (missing {missing}) — run: alembic upgrade head")

        await conn.execute(text("TRUNCATE documents, chunks RESTART IDENTITY CASCADE"))

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s

    # Truncate on the way OUT as well as on the way in. Cleaning up only at setup leaves
    # the last test's fixture rows sitting in the corpus, where they silently pollute
    # `python -m eval.ablation` and a locally running API — which is exactly what happened.
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE documents, chunks RESTART IDENTITY CASCADE"))

    await engine.dispose()


@pytest_asyncio.fixture
async def populated(session):
    """Index the corpus, then throw the indexing process away."""
    embedder = FakeEmbedder()

    document = Document(title="penal_code.pdf", sha256="deadbeef", status="indexed")
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
    return session


class TestBug1AgainstRealPostgres:
    async def test_hybrid_retrieval_survives_a_cold_process(self, populated):
        # Nothing was indexed by THIS retriever. It holds no BM25 index, no embedding
        # matrix, no corpus state at all — everything comes from Postgres. This is the
        # exact scenario the old code silently failed: it would have degraded to
        # dense-only and reported retrieval_type="chroma_semantic".
        embedder = FakeEmbedder()
        retriever = HybridRetriever(embedder, PostgresChunkRepository(populated))

        results = await retriever.search("peine pour vol simple", top_k=3, weight_bm25=0.4)

        assert results
        assert all(r.retrieval_type == "hybrid" for r in results)

    async def test_the_lexical_arm_really_queries_postgres_fts(self, populated):
        repository = PostgresChunkRepository(populated)

        candidates = await repository.lexical_candidates("vol prison", limit=10)

        # Non-empty means the tsvector column, the GIN index and the french_unaccent
        # config are all genuinely wired up.
        assert candidates
        assert all(score > 0 for score in candidates.values())

    async def test_the_lexical_arm_answers_a_full_sentence_question(self, populated):
        """Regression: the lexical arm must OR the query's lexemes, not AND them.

        This used websearch_to_tsquery, which ANDs unquoted terms. A natural-language
        question then compiles to 'quel' & 'pein' & 'vol' & 'comm' & 'arme' and requires
        every stem in one chunk — which matched ZERO chunks across the whole corpus. The
        lexical arm silently returned nothing for every real question, so hybrid search
        collapsed back to dense-only. Keyword queries still worked, so a keyword-shaped
        test would have passed while the system was broken for its actual users.
        """
        repository = PostgresChunkRepository(populated)

        candidates = await repository.lexical_candidates(
            "Quelle est la peine de prison pour un vol simple ?", limit=10
        )

        assert candidates, "the lexical arm matched nothing on a full-sentence question"

    async def test_the_lexical_arm_is_unaccented(self, populated):
        # Users type "aggrave", the corpus says "aggravé". Stock 'french' would not match
        # them; french_unaccent must.
        repository = PostgresChunkRepository(populated)

        assert await repository.lexical_candidates("vol aggrave", limit=10)

    async def test_an_empty_query_returns_no_candidates_rather_than_erroring(self, populated):
        # to_tsquery('') raises a syntax error in Postgres.
        repository = PostgresChunkRepository(populated)

        assert await repository.lexical_candidates("   ", limit=10) == {}

    async def test_lexical_only_retrieval_actually_finds_the_right_article(self, populated):
        # The end-to-end assertion the ablation should have been able to make from day
        # one: with weight_bm25=1.0 the dense arm is switched off entirely, so a non-zero
        # score here proves the lexical arm is carrying real signal on its own.
        embedder = FakeEmbedder()
        retriever = HybridRetriever(embedder, PostgresChunkRepository(populated))

        results = await retriever.search(
            "Quelle est la peine pour un vol ?", top_k=3, weight_bm25=1.0
        )

        assert results
        assert any(r.article_number in {"Article 264", "Article 265"} for r in results)

    async def test_the_dense_arm_returns_similarity_not_distance(self, populated):
        # THE TRAP. pgvector's <=> is cosine DISTANCE (0 = identical). If the repository
        # forgot the `1 - distance` conversion, the ranking would be exactly inverted —
        # and would still return plausible French legal text, so nothing would look
        # broken. Similarity for a matching query must be high, and must not be negative.
        embedder = FakeEmbedder()
        repository = PostgresChunkRepository(populated)

        embedding = await embedder.embed_query("vol peine prison")
        candidates = await repository.dense_candidates(embedding, limit=4)

        assert candidates
        assert max(candidates.values()) > 0.5, "similarity is inverted — <=> is a DISTANCE"
        assert all(-0.01 <= s <= 1.01 for s in candidates.values())

    async def test_the_theft_article_outranks_the_constitution_article(self, populated):
        embedder = FakeEmbedder()
        retriever = HybridRetriever(embedder, PostgresChunkRepository(populated))

        results = await retriever.search("peine prison pour vol", top_k=2, weight_bm25=0.4)

        assert results[0].article_number in {"Article 264", "Article 265"}

    async def test_citations_carry_article_numbers_out_of_the_database(self, populated):
        embedder = FakeEmbedder()
        retriever = HybridRetriever(embedder, PostgresChunkRepository(populated))

        results = await retriever.search("vol", top_k=1, weight_bm25=1.0)

        assert results[0].article_number is not None
        assert results[0].source == "penal_code.pdf"

    async def test_rrf_works_against_real_candidates(self, populated):
        embedder = FakeEmbedder()
        retriever = HybridRetriever(embedder, PostgresChunkRepository(populated))

        results = await retriever.search("vol peine", top_k=3, fusion=FusionStrategy.RRF)

        assert results
        assert all(r.retrieval_type == "rrf" for r in results)
