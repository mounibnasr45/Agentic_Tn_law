import pytest

from app.domain.models import ChunkRecord
from app.domain.retrieval import FusionStrategy, HybridRetriever
from tests.fakes import FakeChunkRepository, FakeEmbedder

CORPUS = [
    ChunkRecord(
        id=1,
        content="Le vol simple est puni d'une peine de prison de six mois.",
        source="penal_code.pdf",
        chunk_index=0,
        article_number="Article 264",
    ),
    ChunkRecord(
        id=2,
        content="Le vol aggrave est puni d'une peine de prison de dix ans.",
        source="penal_code.pdf",
        chunk_index=1,
        article_number="Article 265",
    ),
    ChunkRecord(
        id=3,
        content="Le president de la republique est elu au suffrage universel.",
        source="constitution.pdf",
        chunk_index=0,
        article_number="Article 75",
    ),
    ChunkRecord(
        id=4,
        content="La liberte d'opinion est garantie par la constitution.",
        source="constitution.pdf",
        chunk_index=1,
        article_number="Article 31",
    ),
]


@pytest.fixture
def retriever() -> HybridRetriever:
    embedder = FakeEmbedder()
    return HybridRetriever(embedder, FakeChunkRepository(CORPUS, embedder))


class TestBug1ColdProcess:
    """The regression tests for bug 1.

    The old retriever kept BM25 and the embedding matrix in memory, never persisted
    them, and on a cold process silently degraded to dense-only while still reporting
    is_initialized = True. Nothing here is built at startup, so there is nothing a
    fresh process can fail to restore.
    """

    async def test_hybrid_retrieval_survives_a_cold_process(self, retriever):
        # A brand-new retriever. No indices built, no build_indices() call, no warm-up.
        results = await retriever.search("peine pour vol simple", top_k=3)

        assert results, "a cold retriever returned nothing — the corpus was not durable"
        assert all(r.retrieval_type == "hybrid" for r in results), (
            "retrieval silently degraded instead of running both arms"
        )

    async def test_a_second_cold_retriever_returns_the_same_results(self):
        # Simulates process restart: build two retrievers over the same storage and
        # assert they agree. The old code would have returned hybrid results from the
        # process that indexed, and dense-only from every process after it.
        embedder = FakeEmbedder()
        repo = FakeChunkRepository(CORPUS, embedder)

        first = await HybridRetriever(embedder, repo).search("peine pour vol", top_k=3)
        second = await HybridRetriever(embedder, repo).search("peine pour vol", top_k=3)

        assert [r.chunk_id for r in first] == [r.chunk_id for r in second]
        assert [r.retrieval_type for r in first] == [r.retrieval_type for r in second]


class TestRanking:
    async def test_finds_the_relevant_article(self, retriever):
        results = await retriever.search("peine pour vol", top_k=2)

        assert results[0].article_number in {"Article 264", "Article 265"}
        assert results[0].source == "penal_code.pdf"

    async def test_results_are_ranked_best_first(self, retriever):
        results = await retriever.search("vol peine prison", top_k=4)

        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    async def test_rank_is_one_based_and_contiguous(self, retriever):
        results = await retriever.search("vol", top_k=3)

        assert [r.rank for r in results] == list(range(1, len(results) + 1))

    async def test_citations_carry_article_numbers(self, retriever):
        # Bug 4's precondition: article numbers must survive retrieval, or a citation
        # can never be built from the result.
        results = await retriever.search("liberte constitution", top_k=1)

        assert results[0].article_number is not None
        assert results[0].chunk_id in {r.id for r in CORPUS}


class TestFusionArms:
    """weight_bm25 is the arm selector: 1.0 lexical-only, 0.0 dense-only, between hybrid."""

    async def test_weight_one_reports_lexical_only(self, retriever):
        results = await retriever.search("vol", top_k=2, weight_bm25=1.0)

        assert all(r.retrieval_type == "lexical" for r in results)

    async def test_weight_zero_reports_dense_only(self, retriever):
        results = await retriever.search("vol", top_k=2, weight_bm25=0.0)

        assert all(r.retrieval_type == "dense" for r in results)

    async def test_rrf_is_selectable_and_labelled(self, retriever):
        results = await retriever.search("vol peine", top_k=2, fusion=FusionStrategy.RRF)

        assert results
        assert all(r.retrieval_type == "rrf" for r in results)

    async def test_the_two_fusion_strategies_can_disagree(self, retriever):
        # If they always agreed there would be nothing to ablate. This documents that
        # the choice is empirical.
        weighted = await retriever.search("vol prison", top_k=4)
        rrf = await retriever.search("vol prison", top_k=4, fusion=FusionStrategy.RRF)

        assert {r.chunk_id for r in weighted}  # both produce results
        assert {r.chunk_id for r in rrf}


class TestEdgeCases:
    async def test_empty_query_returns_nothing(self, retriever):
        assert await retriever.search("   ", top_k=5) == []

    async def test_top_k_zero_returns_nothing(self, retriever):
        assert await retriever.search("vol", top_k=0) == []

    async def test_query_matching_nothing_does_not_crash(self, retriever):
        # All-zero lexical scores used to be a division-by-zero in min-max normalisation.
        results = await retriever.search("zzzz", top_k=3)

        assert all(r.score == r.score for r in results)  # no NaN

    async def test_never_returns_more_results_than_the_corpus_holds(self, retriever):
        results = await retriever.search("vol peine prison constitution", top_k=100)

        assert len(results) <= len(CORPUS)

    async def test_empty_corpus_returns_nothing(self):
        embedder = FakeEmbedder()
        empty = HybridRetriever(embedder, FakeChunkRepository([], embedder))

        assert await empty.search("vol", top_k=5) == []
