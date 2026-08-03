import numpy as np
import pytest

from app.domain.scoring import combine_scores, normalize_bm25, normalize_semantic, top_k_indices


class TestNormalizeBM25:
    def test_maps_range_onto_zero_one(self):
        result = normalize_bm25([2.0, 4.0, 6.0])

        assert result.min() == 0.0
        assert result.max() == 1.0
        np.testing.assert_allclose(result, [0.0, 0.5, 1.0])

    def test_query_matching_nothing_scores_all_zero_without_dividing_by_zero(self):
        # rank_bm25 returns all-zero scores when no query term is in the corpus.
        result = normalize_bm25([0.0, 0.0, 0.0])

        np.testing.assert_array_equal(result, [0.0, 0.0, 0.0])
        assert not np.isnan(result).any()

    def test_uniform_nonzero_scores_all_map_to_one(self):
        result = normalize_bm25([3.0, 3.0, 3.0])

        np.testing.assert_array_equal(result, [1.0, 1.0, 1.0])

    def test_empty_corpus_returns_empty(self):
        assert normalize_bm25([]).size == 0


class TestNormalizeSemantic:
    def test_negative_cosine_similarity_is_clipped_to_zero(self):
        result = normalize_semantic([-0.8, 0.0, 0.5, 1.0])

        np.testing.assert_allclose(result, [0.0, 0.0, 0.5, 1.0])

    def test_values_already_in_range_are_untouched(self):
        np.testing.assert_allclose(normalize_semantic([0.2, 0.9]), [0.2, 0.9])


class TestCombineScores:
    def test_weight_one_ignores_the_semantic_signal(self):
        result = combine_scores(bm25_scores=[1.0, 0.0], semantic_scores=[0.0, 1.0], weight_bm25=1.0)

        np.testing.assert_allclose(result, [1.0, 0.0])

    def test_weight_zero_ignores_the_lexical_signal(self):
        result = combine_scores(bm25_scores=[1.0, 0.0], semantic_scores=[0.0, 1.0], weight_bm25=0.0)

        np.testing.assert_allclose(result, [0.0, 1.0])

    def test_project_default_weight_blends_both(self):
        # config.HYBRID_WEIGHT_BM25 = 0.4 -> 0.4 lexical + 0.6 semantic
        result = combine_scores(bm25_scores=[1.0, 0.0], semantic_scores=[0.0, 1.0], weight_bm25=0.4)

        np.testing.assert_allclose(result, [0.4, 0.6])

    def test_weights_always_sum_to_one(self):
        result = combine_scores(bm25_scores=[1.0], semantic_scores=[1.0], weight_bm25=0.3)

        np.testing.assert_allclose(result, [1.0])

    @pytest.mark.parametrize("bad_weight", [-0.1, 1.5])
    def test_weight_outside_zero_one_is_rejected(self, bad_weight):
        with pytest.raises(ValueError, match="weight_bm25"):
            combine_scores([1.0], [1.0], weight_bm25=bad_weight)

    def test_misaligned_score_vectors_are_rejected(self):
        with pytest.raises(ValueError, match="align"):
            combine_scores(bm25_scores=[1.0, 0.0], semantic_scores=[1.0], weight_bm25=0.5)


class TestTopKIndices:
    def test_returns_indices_best_first(self):
        assert top_k_indices([0.1, 0.9, 0.5], k=3) == [1, 2, 0]

    def test_never_returns_more_results_than_documents(self):
        assert top_k_indices([0.4, 0.6], k=20) == [1, 0]

    def test_k_of_zero_returns_nothing(self):
        assert top_k_indices([0.4, 0.6], k=0) == []

    def test_empty_corpus_returns_nothing(self):
        assert top_k_indices([], k=5) == []


class TestNaNIsNeverPropagated:
    """A NaN similarity must not survive normalisation.

    Cosine distance is undefined against a zero-magnitude vector, so pgvector returns NaN
    and `1 - NaN` is NaN. np.clip PROPAGATES NaN rather than bounding it, so without an
    explicit guard the value travels all the way to the API — where JSON serialises it as
    `null` on a field the schema declares non-nullable, and the client renders a blank
    score several layers from the cause.

    Every comparison against NaN is also False, so a NaN in a ranked list sorts
    unpredictably: it is not merely an ugly number, it is a silently wrong ordering.
    """

    def test_nan_becomes_zero(self):
        out = normalize_semantic(np.array([0.9, np.nan, 0.4]))
        assert not np.isnan(out).any(), "NaN survived normalisation"
        assert out[1] == 0.0, "an undefined similarity should score 0, not the nearest bound"

    def test_infinities_are_bounded(self):
        out = normalize_semantic(np.array([np.inf, -np.inf]))
        assert out.tolist() == [1.0, 0.0]

    def test_ordinary_values_are_untouched(self):
        out = normalize_semantic(np.array([0.0, 0.5, 1.0]))
        assert out.tolist() == [0.0, 0.5, 1.0]

    def test_out_of_range_similarities_are_still_clipped(self):
        out = normalize_semantic(np.array([-0.3, 1.7]))
        assert out.tolist() == [0.0, 1.0]
