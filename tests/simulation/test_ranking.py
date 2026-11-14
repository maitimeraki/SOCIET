import pytest

from src.simulation.ranking import (Candidate, SeatQueue, adjacency, cluster_key,
                                    personalized_pagerank, rrf_fuse, score)


def cand(name, **kw):
    base = dict(entity_id=name, name=name, query_relevance=0.5, entity_similarity=0.5, ppr=0.5,
                doc_count=2, chunk_count=4, evidence_count=3)
    return Candidate(**{**base, **kw})


def test_rrf_rewards_agreement_between_lists():
    fused = rrf_fuse([["a", "b"], ["a", "c"]])
    assert fused["a"] > fused["b"] and fused["a"] > fused["c"]


def test_ppr_hub_far_from_the_question_scores_below_a_seed_neighbour():
    adj = adjacency([("seed", "near"), ("near", "far"), ("far", "hub"),
                     ("hub", "x1"), ("hub", "x2"), ("hub", "x3"), ("hub", "x4")])
    ppr = personalized_pagerank(adj, {"seed": 1.0})
    assert ppr["near"] > ppr["hub"]


def test_ppr_is_max_normalised():
    ppr = personalized_pagerank(adjacency([("a", "b")]), {"a": 1.0})
    assert max(ppr.values()) == pytest.approx(1.0)


def test_zero_grounding_halves_the_core_score():
    assert score(cand("Z", doc_count=0, chunk_count=0)) == pytest.approx(0.25)


def test_name_variants_collapse_to_one_cluster():
    assert cluster_key("WisprFlow_700M") == cluster_key("WisprFlow_2B") == "wisprflow"
    assert cluster_key("Acme Inc.") == cluster_key("ACME")


def test_ineligible_candidates_carry_a_reason():
    q = SeatQueue([cand("Metric", is_actor=False), cand("Thin", evidence_count=1), cand("Ok")], n=3)
    assert q.next().name == "Ok"
    assert q.next() is None
    reasons = {d.name: d.reason for d in q.decisions()}
    assert reasons["Metric"] == "not an actor"
    assert reasons["Thin"].startswith("evidence 1")


def test_name_variants_share_one_seat():
    q = SeatQueue([cand("WisprFlow_700M", ppr=0.9), cand("WisprFlow_2B", ppr=0.8)], n=2)
    assert q.next().name == "WisprFlow_700M"
    assert q.next() is None


def test_second_seat_prefers_a_different_view():
    a = cand("A", ppr=0.9, vector=(1.0, 0.0))
    b = cand("B", ppr=0.85, vector=(1.0, 0.0))
    c = cand("C", ppr=0.7, vector=(0.0, 1.0))
    q = SeatQueue([a, b, c], n=2)
    first = q.next()
    q.accept(first)
    assert (first.name, q.next().name) == ("A", "C")


def test_a_rejected_profile_hands_the_seat_to_the_next_candidate():
    q = SeatQueue([cand("A", ppr=0.9), cand("B", ppr=0.8)], n=1)
    first = q.next()
    q.reject(first, "bio failed validation")
    assert q.next().name == "B"


def test_same_input_gives_the_same_order():
    pool = [cand("A", ppr=0.7), cand("B", ppr=0.7), cand("C", ppr=0.7)]
    run = lambda: [d.name for d in sorted(SeatQueue(pool, n=3).decisions(), key=lambda d: d.name)]
    assert run() == run()
