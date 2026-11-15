"""Format checks for questions.json and targets.json. Non-live: they run in CI."""

import json

import pytest

from tests.simulation.golden.dataset import (
    TARGET_KEYS,
    Question,
    is_sample_only,
    load_questions,
    load_targets,
    require_labelled_set,
)

VALID_ROW = {
    "dataset": "golden-sample-x",
    "question": "q?",
    "relevant": {"A": 2},
    "stance": {"A": "POSITIVE"},
}
LABELLED_ROW = {**VALID_ROW, "dataset": "golden-run-1"}


def _write(tmp_path, payload, name="questions.json"):
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_the_shipped_questions_are_three_sample_rows():
    questions = load_questions()
    assert len(questions) == 3
    assert is_sample_only(questions)


def test_a_relevance_label_outside_0_to_3_is_rejected(tmp_path):
    row = {**VALID_ROW, "relevant": {"A": 4}}
    with pytest.raises(ValueError):
        load_questions(_write(tmp_path, [row]))


def test_a_boolean_relevance_label_is_rejected(tmp_path):
    row = {**VALID_ROW, "relevant": {"A": True}}
    with pytest.raises(ValueError):
        load_questions(_write(tmp_path, [row]))


def test_a_question_with_nothing_relevant_is_rejected(tmp_path):
    row = {**VALID_ROW, "relevant": {"A": 0}}
    with pytest.raises(ValueError):
        load_questions(_write(tmp_path, [row]))


def test_an_unknown_stance_is_rejected(tmp_path):
    row = {**VALID_ROW, "stance": {"A": "positive"}}
    with pytest.raises(ValueError):
        load_questions(_write(tmp_path, [row]))


def test_a_stance_on_an_entity_not_in_relevant_is_rejected(tmp_path):
    row = {**VALID_ROW, "stance": {"B": "POSITIVE"}}
    with pytest.raises(ValueError):
        load_questions(_write(tmp_path, [row]))


def test_a_dataset_without_the_golden_prefix_is_rejected(tmp_path):
    row = {**LABELLED_ROW, "dataset": "production-customers"}
    with pytest.raises(ValueError):
        load_questions(_write(tmp_path, [row]))


def test_a_mixed_set_is_not_a_labelled_set():
    questions = [
        Question("golden-run-1", "q?", {"A": 1}, {}),
        Question("golden-sample-x", "q?", {"A": 1}, {}),
    ]
    assert not is_sample_only(questions)


def test_a_labelled_run_refuses_a_mixed_set():
    questions = [
        Question("golden-run-1", "q?", {"A": 1}, {}),
        Question("golden-sample-x", "q?", {"A": 1}, {}),
    ]
    with pytest.raises(ValueError, match="sample row"):
        require_labelled_set(questions)


def test_a_labelled_run_accepts_a_set_without_sample_rows():
    questions = [Question("golden-run-1", "q?", {"A": 1}, {})]
    assert require_labelled_set(questions) == questions


def test_the_shipped_targets_have_the_expected_keys_and_sane_values():
    targets = load_targets()
    assert set(targets) == set(TARGET_KEYS)
    assert all(value is None or 0.0 <= value <= 1.0 for value in targets.values())


def test_a_target_outside_zero_to_one_is_rejected(tmp_path):
    path = tmp_path / "targets.json"
    path.write_text(json.dumps({"ndcg_at_10": 1.5, "recall_at_n": None, "brier_max": None}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_targets(path)


def test_a_target_with_the_wrong_keys_is_rejected(tmp_path):
    path = tmp_path / "targets.json"
    path.write_text(json.dumps({"ndcg_at_10": 0.5}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_targets(path)
