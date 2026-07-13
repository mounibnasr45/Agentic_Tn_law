import numpy as np

from app.domain.fusion import align_candidates, reciprocal_rank_fusion


class TestAlignCandidates:
    def test_unions_the_two_candidate_sets(self):
        ids, _, _ = align_candidates(lexical={1: 5.0, 2: 3.0}, dense={2: 0.9, 3: 0.8})

        assert ids == [1, 2, 3]

    def test_produces_index_aligned_vectors(self):
        ids, lexical, dense = align_candidates({1: 5.0, 2: 3.0}, {2: 0.9, 3: 0.8})

        assert len(ids) == len(lexical) == len(dense)
        np.testing.assert_allclose(lexical, [5.0, 3.0, 0.0])
        np.testing.assert_allclose(dense, [0.0, 0.9, 0.8])

    def test_a_chunk_missing_from_one_arm_scores_zero_for_that_arm(self):
        # The documented truncation bias. Chunk 1 was absent from the dense top-N, so
        # it gets 0.0 there — which is NOT the same as "its cosine similarity was low".
        # We never asked. This is inherent to score-level fusion over truncated lists,
        # and is exactly what RRF avoids.
        _, _, dense = align_candidates(lexical={1: 5.0}, dense={2: 0.9})

        assert dense[0] == 0.0

    def test_both_arms_empty_yields_empty_vectors(self):
        ids, lexical, dense = align_candidates({}, {})

        assert ids == []
        assert lexical.size == dense.size == 0

    def test_identical_candidate_sets_need_no_padding(self):
        ids, lexical, dense = align_candidates({1: 2.0, 2: 1.0}, {1: 0.5, 2: 0.4})

        assert ids == [1, 2]
        np.testing.assert_allclose(lexical, [2.0, 1.0])
        np.testing.assert_allclose(dense, [0.5, 0.4])


class TestReciprocalRankFusion:
    def test_a_chunk_ranked_first_by_both_arms_wins(self):
        fused = reciprocal_rank_fusion({1: 100.0, 2: 1.0}, {1: 0.99, 2: 0.1})

        assert max(fused, key=fused.get) == 1

    def test_score_magnitudes_are_ignored_only_order_matters(self):
        # The point of RRF. BM25 scores are unbounded and corpus-dependent; cosine is
        # bounded [0,1]. Blending them by magnitude compares incomparable scales. Here
        # one arm's scores are 1000x the other's, and the fused result is unchanged.
        modest = reciprocal_rank_fusion({1: 2.0, 2: 1.0}, {1: 0.9, 2: 0.8})
        enormous = reciprocal_rank_fusion({1: 2000.0, 2: 1000.0}, {1: 0.9, 2: 0.8})

        assert modest == enormous

    def test_a_chunk_found_by_both_arms_beats_one_found_by_only_the_best_arm(self):
        # Chunk 2 is rank-2 in both arms; chunk 1 is rank-1 in one arm and absent from
        # the other. Agreement across arms is the signal RRF is built to reward.
        fused = reciprocal_rank_fusion({1: 10.0, 2: 5.0}, {2: 0.9, 3: 0.8})

        assert fused[2] > fused[1]

    def test_k_damps_the_dominance_of_the_top_rank(self):
        # With k=0, rank 1 scores 1.0 and rank 2 scores 0.5 — a 2x gap that lets a single
        # arm's mistake dominate. k=60 compresses that to roughly 1.6%.
        sharp = reciprocal_rank_fusion({1: 2.0, 2: 1.0}, k=0)
        damped = reciprocal_rank_fusion({1: 2.0, 2: 1.0}, k=60)

        assert sharp[1] / sharp[2] == 2.0
        assert damped[1] / damped[2] < 1.02

    def test_empty_rankings_fuse_to_nothing(self):
        assert reciprocal_rank_fusion({}, {}) == {}

    def test_a_single_arm_still_fuses(self):
        fused = reciprocal_rank_fusion({1: 5.0, 2: 3.0})

        assert fused[1] > fused[2]
