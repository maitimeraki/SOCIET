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
