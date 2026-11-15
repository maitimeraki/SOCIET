"""Format checks for questions.json and targets.json. Non-live: they run in CI."""

import json

import pytest

from tests.simulation.golden.dataset import is_sample_only, load_questions, load_targets

VALID_ROW = {
    "dataset": "golden-sample-x",
    "question": "q?",
    "relevant": {"A": 2},
    "stance": {"A": "POSITIVE"},
}


def _write(tmp_path, payload):
    path = tmp_path / "questions.json"
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


def test_a_question_with_nothing_relevant_is_rejected(tmp_path):
    row = {**VALID_ROW, "relevant": {"A": 0}}
    with pytest.raises(ValueError):
        load_questions(_write(tmp_path, [row]))


def test_an_unknown_stance_is_rejected(tmp_path):
    row = {**VALID_ROW, "stance": {"A": "positive"}}
    with pytest.raises(ValueError):
        load_questions(_write(tmp_path, [row]))


def test_the_shipped_targets_are_all_unset():
    assert load_targets() == {"ndcg_at_10": None, "recall_at_n": None, "brier_max": None}
