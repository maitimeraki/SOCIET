"""Unit tests for the golden-set metrics. Non-live: they run in CI."""

import pytest

from tests.simulation.golden.metrics import brier, ndcg_at_k, recall_at_n


def test_perfect_ranking_has_ndcg_one():
    assert ndcg_at_k(["a", "b"], {"a": 2, "b": 1}) == pytest.approx(1.0)


def test_swapped_ranking_scores_lower():
    assert ndcg_at_k(["b", "a"], {"a": 2, "b": 1}) < 1.0


def test_recall_counts_relevant_in_top_n():
    assert recall_at_n(["a", "x", "b"], {"a": 1, "b": 1}, 2) == 0.5


def test_brier_of_a_perfect_forecast_is_zero():
    assert brier([(1.0, True), (0.0, False)]) == 0.0


def test_ndcg_of_an_empty_ranking_is_zero():
    assert ndcg_at_k([], {"a": 2}) == 0.0


def test_ndcg_with_no_positive_label_is_zero_not_a_division_error():
    assert ndcg_at_k(["a", "b"], {"a": 0, "b": 0}) == 0.0


def test_ndcg_scores_only_the_top_k():
    assert ndcg_at_k(["x", "a"], {"a": 1}, k=1) == 0.0


def test_ndcg_with_k_larger_than_the_list_scores_the_whole_list():
    assert ndcg_at_k(["a", "b"], {"a": 2, "b": 1}, k=50) == pytest.approx(ndcg_at_k(["a", "b"], {"a": 2, "b": 1}, k=2))


def test_ndcg_rejects_k_below_one():
    with pytest.raises(ValueError):
        ndcg_at_k(["a"], {"a": 1}, k=0)


def test_recall_with_nothing_relevant_is_zero():
    assert recall_at_n(["a"], {}, 1) == 0.0


def test_recall_with_n_larger_than_the_list_counts_all_found():
    assert recall_at_n(["a"], {"a": 1, "b": 1}, 10) == 0.5


def test_recall_ignores_entities_labelled_zero():
    assert recall_at_n(["a", "b"], {"a": 0, "b": 1}, 2) == 1.0


def test_recall_rejects_n_below_one():
    with pytest.raises(ValueError):
        recall_at_n(["a"], {"a": 1}, 0)


def test_brier_of_a_constant_half_forecast_is_a_quarter():
    assert brier([(0.5, True), (0.5, False)]) == 0.25


def test_brier_of_nothing_raises():
    with pytest.raises(ValueError):
        brier([])


def test_brier_rejects_a_probability_outside_the_unit_interval():
    with pytest.raises(ValueError):
        brier([(1.2, True)])


def test_brier_rejects_a_nan_probability():
    with pytest.raises(ValueError):
        brier([(float("nan"), True)])


def test_brier_scores_a_true_outcome_as_one():
    assert brier([(0.0, True)]) == 1.0


def test_a_duplicate_name_does_not_push_ndcg_above_one():
    assert ndcg_at_k(["a", "a"], {"a": 1}) == pytest.approx(1.0)


def test_a_repeated_name_does_not_take_a_second_recall_slot():
    assert recall_at_n(["a", "a", "b"], {"a": 1, "b": 1}, 2) == 1.0


def test_a_repeated_name_counts_once_for_recall():
    assert recall_at_n(["a", "a"], {"a": 1, "b": 1}, 2) == 0.5


def test_ndcg_rejects_a_label_above_three():
    with pytest.raises(ValueError):
        ndcg_at_k(["a"], {"a": 4})


def test_ndcg_rejects_a_negative_label():
    with pytest.raises(ValueError):
        ndcg_at_k(["a"], {"a": -1})


def test_recall_rejects_a_label_above_three():
    with pytest.raises(ValueError):
        recall_at_n(["a"], {"a": 4}, 1)


def test_a_boolean_label_is_rejected():
    with pytest.raises(ValueError):
        ndcg_at_k(["a"], {"a": True})
