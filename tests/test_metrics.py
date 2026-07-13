import pytest

from eval.metrics import evaluate, hit_at_k, ndcg_at_k, reciprocal_rank

THEFT = ("penal_code.pdf", "Article 258")
MURDER = ("penal_code.pdf", "Article 201")
LIBERTY = ("Constitution_fr.pdf", "Article 31")


class TestHitAtK:
    def test_answer_at_rank_one_is_a_hit_at_every_k(self):
        retrieved = [THEFT, MURDER, LIBERTY]

        assert hit_at_k(retrieved, THEFT, k=1)
        assert hit_at_k(retrieved, THEFT, k=10)

    def test_answer_at_rank_three_is_missed_at_k_of_two(self):
        retrieved = [MURDER, LIBERTY, THEFT]

        assert not hit_at_k(retrieved, THEFT, k=2)
        assert hit_at_k(retrieved, THEFT, k=3)

    def test_answer_absent_is_never_a_hit(self):
        assert not hit_at_k([MURDER, LIBERTY], THEFT, k=10)

    def test_empty_retrieval_is_never_a_hit(self):
        assert not hit_at_k([], THEFT, k=10)

    def test_the_right_article_from_the_wrong_document_is_not_a_hit(self):
        # Both codes have an "Article 31". Matching on the article number alone would
        # score a constitutional article as a correct answer to a penal question.
        assert not hit_at_k([("Constitution_fr.pdf", "Article 258")], THEFT, k=5)


class TestReciprocalRank:
    @pytest.mark.parametrize(
        ("position", "expected_rr"),
        [(0, 1.0), (1, 0.5), (2, 1 / 3), (9, 0.1)],
    )
    def test_score_is_the_reciprocal_of_the_rank(self, position, expected_rr):
        retrieved = [MURDER] * 20
        retrieved[position] = THEFT

        assert reciprocal_rank(retrieved, THEFT) == pytest.approx(expected_rr)

    def test_absent_answer_scores_zero(self):
        assert reciprocal_rank([MURDER, LIBERTY], THEFT) == 0.0

    def test_it_rewards_ranking_high_not_merely_finding(self):
        # The whole point of MRR. Both systems have hit_rate@10 == 1.0; only one of them
        # puts the answer where the LLM will actually read it.
        top = [THEFT] + [MURDER] * 9
        buried = [MURDER] * 9 + [THEFT]

        assert reciprocal_rank(top, THEFT) == 1.0
        assert reciprocal_rank(buried, THEFT) == pytest.approx(0.1)
        assert hit_at_k(top, THEFT, 10) == hit_at_k(buried, THEFT, 10)  # identical hit-rate


class TestNdcg:
    def test_rank_one_is_perfect(self):
        assert ndcg_at_k([THEFT], THEFT, k=10) == 1.0

    def test_it_discounts_more_gently_than_mrr(self):
        # At rank 2, MRR says 0.50 and nDCG says 0.63. They disagree about how much a
        # near-miss costs, which is exactly why both are reported.
        retrieved = [MURDER, THEFT]

        assert reciprocal_rank(retrieved, THEFT) == pytest.approx(0.5)
        assert ndcg_at_k(retrieved, THEFT, k=10) == pytest.approx(0.6309, abs=1e-4)

    def test_beyond_k_scores_zero(self):
        retrieved = [MURDER] * 10 + [THEFT]

        assert ndcg_at_k(retrieved, THEFT, k=10) == 0.0


class TestEvaluate:
    def test_a_perfect_system_scores_one_everywhere(self):
        results = [([THEFT], THEFT), ([MURDER], MURDER)]

        metrics = evaluate(results)

        assert metrics.n == 2
        assert metrics.hit_rate_at_1 == 1.0
        assert metrics.mrr == 1.0
        assert metrics.ndcg_at_10 == 1.0

    def test_a_system_that_finds_nothing_scores_zero_everywhere(self):
        results = [([LIBERTY], THEFT), ([LIBERTY], MURDER)]

        metrics = evaluate(results)

        assert metrics.hit_rate_at_10 == 0.0
        assert metrics.mrr == 0.0

    def test_metrics_are_means_over_queries(self):
        # One query nails it, one misses entirely -> exactly half.
        results = [([THEFT], THEFT), ([LIBERTY], MURDER)]

        metrics = evaluate(results)

        assert metrics.hit_rate_at_1 == 0.5
        assert metrics.mrr == 0.5

    def test_hit_rate_is_monotonic_in_k(self):
        # A larger k can only ever help. If this inverts, the metric is wrong.
        results = [([MURDER, LIBERTY, THEFT], THEFT)]

        m = evaluate(results)

        assert m.hit_rate_at_1 <= m.hit_rate_at_3 <= m.hit_rate_at_5 <= m.hit_rate_at_10

    def test_empty_evaluation_does_not_divide_by_zero(self):
        metrics = evaluate([])

        assert metrics.n == 0
        assert metrics.mrr == 0.0
