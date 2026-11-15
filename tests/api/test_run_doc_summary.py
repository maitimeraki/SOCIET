"""The run list's verdict stance: one tie-break, and no stance when no cluster carries weight."""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

import src.api.run_doc as run_doc


@pytest.mark.parametrize(
    "clusters, expected",
    [
        ({"POSITIVE": {"stance": "POSITIVE", "total_weight": 0.0}}, None),
        (
            {
                "NEUTRAL": {"stance": "NEUTRAL", "total_weight": 0.5},
                "NEGATIVE": {"stance": "NEGATIVE", "total_weight": 0.5},
            },
            "NEGATIVE",
        ),
        (
            {
                "NEUTRAL": {"stance": "NEUTRAL", "total_weight": 0.5},
                "POSITIVE": {"stance": "POSITIVE", "total_weight": 0.5},
            },
            "POSITIVE",
        ),
    ],
)
def test_list_summary_stance_uses_the_consensus_tie_break(clusters, expected):
    run = SimpleNamespace(
        id=uuid.uuid4(),
        created_at=datetime(2026, 10, 1, tzinfo=UTC),
        query="q",
        corpus_label="c",
        status="complete",
        verdict={"cluster_details": clusters},
    )
    assert run_doc._summarize(run, None, {}, 0)["verdict_stance"] == expected


def _run(clusters: dict) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        created_at=datetime(2026, 10, 1, tzinfo=UTC),
        query="q",
        corpus_label="c",
        status="complete",
        verdict={"cluster_details": clusters},
    )


def test_a_stored_legacy_stance_key_is_ignored_and_the_normal_dominant_stance_is_kept():
    clusters = {
        "AMBIVALENT": {"stance": "AMBIVALENT", "total_weight": 9.0},
        "NEGATIVE": {"stance": "NEGATIVE", "total_weight": 0.4},
        "POSITIVE": {"stance": "POSITIVE", "total_weight": 0.3},
    }
    assert run_doc._summarize(_run(clusters), None, {}, 0)["verdict_stance"] == "NEGATIVE"


def test_a_run_holding_only_a_legacy_stance_key_has_no_verdict_stance():
    clusters = {"AMBIVALENT": {"stance": "AMBIVALENT", "total_weight": 0.5}}
    assert run_doc._summarize(_run(clusters), None, {}, 0)["verdict_stance"] is None
