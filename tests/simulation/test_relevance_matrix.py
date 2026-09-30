"""Tests for the S4 relevance matrix — the one scoring/blend both surfaces use."""
import logging

import pytest

from src.simulation.debate_config import DebateConfig
from src.simulation.relevance_matrix import (
    SelectionCandidate,
    blended_score,
    density_component,
    intent_terms,
    rank_candidates,
    semantic_component,
)
from src.utils.queryIntend import QueryIntent

_MATRIX_LOGGER = "src.simulation.relevance_matrix"


def _intent(**kwargs) -> QueryIntent:
    base = dict(direct_keywords=[], latent_sectors=[], search_perspectives=[])
    base.update(kwargs)
    return QueryIntent(**base)


class _Node:
    """Stands in for an entity node: the density adapter reads `.relevance_score`."""

    def __init__(self, score: float):
        self.relevance_score = score


def _candidates():
    """One dense-but-irrelevant candidate and one lighter but on-topic candidate."""
    return [
        SelectionCandidate(name="dense", text="quarterly logistics report", evidence=[_Node(2.0)]),
        SelectionCandidate(name="on_topic", text="carbon tax policy", evidence=[_Node(1.0)]),
    ]


def test_density_component_sums_node_and_sector_evidence():
    """The single density entry point reads both surfaces' graph rows."""
    assert density_component([_Node(0.9), _Node(0.5)]) == pytest.approx(1.4)
    assert density_component([{"total_relevance": 2.5, "density": 3}]) == pytest.approx(2.5)
    assert density_component([{"relevance_score": 0.25}]) == pytest.approx(0.25)
    assert density_component([]) == 0.0
    assert density_component([{"total_relevance": None}]) == 0.0


def test_blended_score_is_the_documented_formula():
    config = DebateConfig()
    assert blended_score(0.5, 0.25, config) == pytest.approx(config.w1 * 0.5 + config.w2 * 0.25)


def test_semantic_component_scores_intent_term_coverage():
    assert semantic_component(["carbon"], "carbon tax") == 1.0
    assert semantic_component(["carbon", "energy"], "carbon tax") == 0.5
    assert semantic_component(["energy"], "carbon tax") == 0.0
    # word variants (hyphen, plural) still match on tokens
    assert semantic_component(["carbon tax"], "a carbon-tax debate") == 1.0
    # word-bounded: a short term does not match inside a longer word
    assert semantic_component(["ai"], "chairman of the board") == 0.0
    # nothing to score either way
    assert semantic_component([], "carbon tax") == 0.0
    assert semantic_component(["carbon"], "") == 0.0


def test_intent_terms_reads_the_intent_object_and_its_mapping_form():
    intent = _intent(direct_keywords=["carbon"], entity_frame=["Acme"], domain_tags=["legal"])
    assert intent_terms(intent) == ["carbon", "Acme", "legal"]
    assert intent_terms({"direct_keywords": ["carbon"], "domain_tags": ["legal"]}) == ["carbon", "legal"]
    assert intent_terms(None) == []


def test_rows_carry_both_components_and_the_documented_blend():
    config = DebateConfig()
    rows = rank_candidates(_candidates(), _intent(direct_keywords=["carbon", "tax"]), config)

    by_name = {row.name: row for row in rows}
    assert by_name["dense"].semantic == 0.0
    assert by_name["dense"].density == pytest.approx(1.0)  # normalized against the batch peak
    assert by_name["on_topic"].semantic == 1.0
    assert by_name["on_topic"].density == pytest.approx(0.5)
    for row in rows:
        assert row.blended == pytest.approx(config.w1 * row.semantic + config.w2 * row.density)

    # the on-topic candidate clears the threshold and outranks the denser one
    assert [row.name for row in rows] == ["on_topic", "dense"]


def test_two_intents_produce_two_different_orderings():
    """P2-T1: selection changes when the intent changes."""
    config = DebateConfig()
    by_carbon = rank_candidates(_candidates(), _intent(direct_keywords=["carbon"]), config)
    by_logistics = rank_candidates(_candidates(), _intent(direct_keywords=["logistics"]), config)

    assert [row.name for row in by_carbon] == ["on_topic", "dense"]
    assert [row.name for row in by_logistics] == ["dense", "on_topic"]


def test_no_candidate_clears_the_threshold_falls_back_to_density_ordering(caplog):
    config = DebateConfig(selection_score_threshold=0.99)
    with caplog.at_level(logging.WARNING, logger=_MATRIX_LOGGER):
        rows = rank_candidates(_candidates(), _intent(direct_keywords=["carbon", "tax"]), config)

    assert [row.name for row in rows] == ["dense", "on_topic"]
    assert rows[0].blended < config.selection_score_threshold
    assert "falling back to density-only ordering" in caplog.text


def test_no_intent_is_density_only_ordering_and_does_not_warn(caplog):
    with caplog.at_level(logging.WARNING, logger=_MATRIX_LOGGER):
        rows = rank_candidates(_candidates(), None, DebateConfig())

    assert [row.name for row in rows] == ["dense", "on_topic"]
    assert all(row.semantic == 0.0 for row in rows)
    assert "density-only" not in caplog.text
