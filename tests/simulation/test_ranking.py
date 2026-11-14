import os
import random
import subprocess
import sys
from pathlib import Path

import pytest

from src.simulation.ranking import (Candidate, SeatQueue, adjacency, cluster_key,
                                    personalized_pagerank, rrf_fuse, score)


def cand(name, **kw):
    base = dict(entity_id=name, name=name, query_relevance=0.5, entity_similarity=0.5, ppr=0.5,
                doc_count=2, chunk_count=4, evidence_count=3)
    return Candidate(**{**base, **kw})


def seat_order(candidates, n):
    q = SeatQueue(candidates, n=n)
    order = []
    while (c := q.next()) is not None:
        q.accept(c)
        order.append(c.name)
    return order


def test_rrf_rewards_agreement_between_lists():
    fused = rrf_fuse([["a", "b"], ["a", "c"]])
    assert fused["a"] > fused["b"] and fused["a"] > fused["c"]


def test_ppr_hub_far_from_the_question_scores_below_a_seed_neighbour():
    adj = adjacency([("seed", "near"), ("near", "far"), ("far", "hub"),
                     ("hub", "x1"), ("hub", "x2"), ("hub", "x3"), ("hub", "x4")])
    ppr = personalized_pagerank(adj, {"seed": 1.0})
    assert ppr["near"] > ppr["hub"]


def test_ppr_is_bit_identical_under_shuffled_input_order():
    rng = random.Random(7)
    names = [f"n{i}" for i in range(60)]
    edges = sorted({tuple(sorted(rng.sample(names, 2))) for _ in range(150)})
    seeds = {n: rng.random() for n in names[::7]}
    shuffled = [(b, a) if rng.random() < 0.5 else (a, b) for a, b in rng.sample(edges, len(edges))]
    reordered_seeds = dict(reversed(list(seeds.items())))
    assert personalized_pagerank(adjacency(edges), seeds) == personalized_pagerank(
        adjacency(shuffled), reordered_seeds)


def test_ppr_does_not_depend_on_pythonhashseed():
    script = (
        "from src.simulation.ranking import adjacency, personalized_pagerank\n"
        "names = [f'n{i}' for i in range(60)]\n"
        "edges = [(names[i], names[(i * 7 + 3) % 60]) for i in range(60)]"
        " + [(names[i], names[(i * 11 + 5) % 60]) for i in range(60)]\n"
        "seeds = {n: 1.0 / (i + 1) for i, n in enumerate(names[::5])}\n"
        "print(repr(sorted(personalized_pagerank(adjacency(edges), seeds).items())))\n"
    )
    root = Path(__file__).resolve().parents[2]
    outputs = {
        subprocess.run([sys.executable, "-c", script], cwd=root, check=True, capture_output=True, text=True,
                       env={**os.environ, "PYTHONHASHSEED": seed}).stdout
        for seed in ("0", "1", "2", "3")
    }
    assert len(outputs) == 1


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


def test_first_seat_goes_to_the_highest_scoring_candidate():
    a = cand("A", ppr=0.9, vector=(1.0, 0.0))
    b = cand("B", ppr=0.85, vector=(1.0, 0.0))
    c = cand("C", ppr=0.7, vector=(0.0, 1.0))
    q = SeatQueue([a, b, c], n=2)
    assert q.next().name == "A"


def test_second_seat_prefers_a_different_view():
    a = cand("A", ppr=0.9, vector=(1.0, 0.0))
    b = cand("B", ppr=0.85, vector=(1.0, 0.0))
    c = cand("C", ppr=0.7, vector=(0.0, 1.0))
    q = SeatQueue([a, b, c], n=2)
    q.accept(q.next())
    assert q.next().name == "C"


def test_a_rejected_profile_hands_the_seat_to_the_next_candidate():
    q = SeatQueue([cand("A", ppr=0.9), cand("B", ppr=0.8)], n=1)
    first = q.next()
    q.reject(first, "bio failed validation")
    assert q.next().name == "B"


def test_same_input_gives_the_same_order():
    pool = [cand("A", ppr=0.7), cand("B", ppr=0.7), cand("C", ppr=0.7)]
    run = lambda: [d.name for d in sorted(SeatQueue(pool, n=3).decisions(), key=lambda d: d.name)]
    assert run() == run()


def test_same_pool_seats_the_same_order_regardless_of_input_order():
    pool = [cand("A", ppr=0.7, vector=(1.0, 0.0)), cand("B", ppr=0.7, vector=(1.0, 0.0)),
            cand("C", ppr=0.7, vector=(0.0, 1.0)), cand("D", ppr=0.7)]
    assert seat_order(pool, n=3) == seat_order(list(reversed(pool)), n=3)


def test_seat_bound_stops_the_queue_after_n_accepts():
    q = SeatQueue([cand("A", ppr=0.9), cand("B", ppr=0.8), cand("C", ppr=0.7)], n=2)
    q.accept(q.next())
    q.accept(q.next())
    assert q.next() is None


def test_accept_without_a_draw_raises():
    q = SeatQueue([cand("A")], n=1)
    with pytest.raises(ValueError):
        q.accept(cand("A"))


def test_double_accept_raises():
    q = SeatQueue([cand("A"), cand("B")], n=2)
    a = q.next()
    q.accept(a)
    with pytest.raises(ValueError):
        q.accept(a)


def test_reject_after_accept_raises():
    q = SeatQueue([cand("A"), cand("B")], n=2)
    a = q.next()
    q.accept(a)
    with pytest.raises(ValueError):
        q.reject(a, "too late")


def test_accept_beyond_the_seat_bound_raises():
    q = SeatQueue([cand("A", ppr=0.9), cand("B", ppr=0.8)], n=1)
    a, b = q.next(), q.next()
    q.accept(a)
    with pytest.raises(ValueError):
        q.accept(b)


def test_duplicate_entity_ids_raise_at_construction():
    with pytest.raises(ValueError):
        SeatQueue([cand("A"), cand("B", entity_id="A")], n=2)


def test_a_drawn_but_unresolved_candidate_is_not_reported_as_not_reached():
    q = SeatQueue([cand("A", ppr=0.9), cand("B", ppr=0.8)], n=2)
    q.next()
    reasons = {d.name: d.reason for d in q.decisions()}
    assert reasons == {"A": "drawn, unresolved", "B": "eligible, not reached"}
