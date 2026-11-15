"""Golden-set harness: seating quality on a labelled question set, run against live Neo4j.

What it measures, per question, from the real seating (`ProfileSynthesizer.synthesize`):
  * NDCG@10 of the ranking: the seat decisions in order (seated first, then the rest by
    score), graded labels 0-3. Ranking quality does not depend on profile success, so
    a question whose every profile failed still has its ranking measured.
  * recall@n, n = the seat count (`DebateConfig().max_agents`), over the labelled entities.
  * Brier of each seated agent's confidence against whether its stance matches the label.
    Only seated agents with a label other than ABSTAIN are scored. An agent stance the
    labels cannot express (AMBIVALENT) never matches a label, so it scores as wrong.
    A question with no seated agent adds no Brier pairs.
  The three numbers are the mean NDCG, the mean recall, and the Brier over every scored pair.

Run it:
    GOLDEN_LLM=1 .venv/Scripts/python.exe -m pytest -m live tests/simulation/golden/test_golden.py -s
  It skips (never errors) when any of these holds:
  * the NEO4J_* config is missing, or Neo4j does not answer `RETURN 1`;
  * golden/questions.json holds only the sample rows;
  * GOLDEN_LLM is not 1. Profile generation calls the configured LLM once per seat,
    so the run spends LLM tokens and the operator opts in explicitly.
  It errors (a broken file, not a skip) when questions.json mixes sample rows into a
  labelled set.

Dataset guard: every question's dataset must start with "golden-". Loading refuses any
other name, so the live run can never write persona links into an arbitrary dataset.
Seating writes persona provenance and entity links for each question's dataset (the same
writes a debate makes). Use a scratch "golden-" dataset for those writes.

Questions: golden/questions.json is a list of
  {"dataset", "question", "relevant": {entity name: 0-3}, "stance": {entity name: POSITIVE|NEGATIVE|NEUTRAL|ABSTAIN}}.
The shipped file holds 3 sample rows against "golden-sample-*" datasets so the format is
exercised. The product owner replaces them with the 25-40 labelled questions.

Targets: golden/targets.json holds `ndcg_at_10` (minimum), `recall_at_n` (minimum) and
`brier_max` (maximum), each null or a number in [0, 1]. A null target is report-only and
the run prints that it is unset. The shipped targets are all null. Set them BEFORE tuning,
so the gate measures the tuning and not the numbers chosen after seeing the results.

Tuning procedure (change one thing at a time):
  1. Change one of W_QUERY, W_ENTITY, W_PPR, MMR_LAMBDA in src/simulation/ranking.py.
  2. Run the harness and record NDCG@10, recall@n and the Brier score.
  3. Keep the change only if NDCG@10 improves without recall dropping.
  4. Repeat for the next constant.

Confidence calibration (only if Brier stays above target after tuning): bin the seated
agents' confidence into reliability bins, then fit a Platt or isotonic mapping from
confidence to the observed stance-correct rate. Refit the mapping on a split of the labelled
set, never on the questions it is judged on.
"""

import asyncio
import os
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from src.graph.config_graph import GraphConfig
from src.llm.client import LLMClient
from src.persona.graph_context import GraphContext
from src.persona.repository import PersonaRepository
from src.simulation.debate_config import DebateConfig
from src.simulation.profile_synthesizer import ProfileSynthesizer
from src.simulation.ranking import NoAgentsDerivableError, SeatDecision
from tests.simulation.golden.dataset import (
    Question,
    is_sample_only,
    load_questions,
    load_targets,
    require_labelled_set,
)
from tests.simulation.golden.metrics import brier, ndcg_at_k, recall_at_n

SEATS = DebateConfig().max_agents
NDCG_K = 10


class _Unreachable(Exception):
    """Neo4j or its config is unavailable; the test skips instead of failing."""


@dataclass(frozen=True)
class Report:
    ndcg: float
    recall: float
    brier: float | None
    lines: list[str]


async def _seat(synth: ProfileSynthesizer, question: Question, llm: LLMClient):
    """Return (ranking names, seated agents) for one question.

    The ranking is the seat decisions in order. The synthesizer records decisions before it
    refuses a run where every drawn profile failed, so that question keeps its ranking, with
    no agents and therefore no Brier pairs. A question the graph does not cover has no
    decisions, so its ranking is empty and its metrics are zero.
    """
    decisions: list[SeatDecision] = []
    try:
        agents = await synth.synthesize(
            question.question,
            question.dataset,
            max_agents=SEATS,
            decisions=decisions,
            llm_client=llm,
        )
    except NoAgentsDerivableError:
        agents = []
    return [d.name for d in decisions], agents


def _graph_config() -> GraphConfig:
    """GraphConfig reads NEO4J_* when it is built. A missing value is a skip, not an error."""
    try:
        return GraphConfig()
    except ValueError as exc:
        raise _Unreachable(f"graph config unavailable: {exc}") from exc


async def _measure(questions: list[Question]):
    cfg = _graph_config()
    llm = LLMClient()
    async with GraphContext(cfg) as ctx:
        try:
            async with ctx._driver.session(database=cfg.neo4j_database) as session:
                await session.run("RETURN 1")
        except Exception as exc:
            raise _Unreachable(f"Neo4j not available at {cfg.neo4j_uri}: {exc}") from exc
        repo = None
        try:
            repo = PersonaRepository(
                neo4j_uri=cfg.neo4j_uri,
                neo4j_user=cfg.neo4j_username,
                neo4j_password=cfg.neo4j_password,
                neo4j_database=cfg.neo4j_database,
                llm_client=llm,
            )
            synth = ProfileSynthesizer(repo, ctx)
            return [(question, *await _seat(synth, question, llm)) for question in questions]
        finally:
            if repo is not None:
                await repo.close()


def _brier_pairs(agents, stance: dict[str, str]) -> list[tuple[float, bool]]:
    """(confidence, stance matches label) for each seated agent with a non-ABSTAIN label."""
    pairs = []
    for agent in agents:
        label = stance.get(agent.identity.name)
        if label in (None, "ABSTAIN"):
            continue
        pairs.append((agent.confidence, agent.stance.value == label))
    return pairs


def _report(results) -> Report:
    ndcgs, recalls, pairs, lines = [], [], [], []
    for question, ranked, agents in results:
        ndcg = ndcg_at_k(ranked, question.relevant, k=NDCG_K)
        recall = recall_at_n(ranked, question.relevant, SEATS)
        ndcgs.append(ndcg)
        recalls.append(recall)
        pairs.extend(_brier_pairs(agents, question.stance))
        lines.append(f"  {question.dataset}: ndcg@10 {ndcg:.3f}  recall@{SEATS} {recall:.3f}  seated {len(agents)}")
    count = len(results)
    return Report(
        ndcg=sum(ndcgs) / count,
        recall=sum(recalls) / count,
        brier=brier(pairs) if pairs else None,
        lines=lines,
    )


def _gate(report: Report, targets: dict[str, float | None]) -> None:
    print("\n".join(report.lines))
    print(f"mean NDCG@10 {report.ndcg:.3f}  mean recall@{SEATS} {report.recall:.3f}")
    print(f"Brier {report.brier:.3f}" if report.brier is not None else "Brier: no labelled seated agent, not measured")

    if targets["ndcg_at_10"] is None:
        print("ndcg_at_10: target unset in targets.json, report only")
    else:
        assert report.ndcg >= targets["ndcg_at_10"], f"NDCG@10 {report.ndcg:.3f} < target {targets['ndcg_at_10']}"

    if targets["recall_at_n"] is None:
        print("recall_at_n: target unset in targets.json, report only")
    else:
        assert report.recall >= targets["recall_at_n"], f"recall@{SEATS} {report.recall:.3f} < target {targets['recall_at_n']}"

    if targets["brier_max"] is None:
        print("brier_max: target unset in targets.json, report only")
    elif report.brier is None:
        pytest.fail("brier_max is set but no seated agent carried a labelled stance to score")
    else:
        assert report.brier <= targets["brier_max"], f"Brier {report.brier:.3f} > max {targets['brier_max']}"


@pytest.mark.live
def test_golden_set_seating_metrics():
    questions = load_questions()
    if is_sample_only(questions):
        pytest.skip("golden/questions.json holds only the sample rows; the labelled set is not in place")
    if os.getenv("GOLDEN_LLM") != "1":
        pytest.skip("set GOLDEN_LLM=1: each question generates profiles through the configured LLM")
    labelled = require_labelled_set(questions)
    targets = load_targets()
    try:
        results = asyncio.run(_measure(labelled))
    except _Unreachable as exc:
        pytest.skip(str(exc))
    _gate(_report(results), targets)


# Non-live: fakes only, no Neo4j and no LLM.


class _FakeSynth:
    """Records the decisions it is given, then refuses, as the real synthesizer does."""

    def __init__(self, decisions: list[SeatDecision], error: Exception):
        self._decisions = decisions
        self._error = error

    async def synthesize(self, query, dataset_id, *, max_agents, decisions, llm_client):
        decisions.extend(self._decisions)
        raise self._error


def _question(**overrides) -> Question:
    base = dict(
        dataset="golden-fake",
        question="q?",
        relevant={"Alpha": 3, "Beta": 1},
        stance={"Alpha": "POSITIVE"},
    )
    base.update(overrides)
    return Question(**base)


def test_a_question_whose_profiles_all_failed_keeps_its_ranking_and_adds_no_brier_pairs():
    decisions = [SeatDecision("e1", "Alpha", 0.9), SeatDecision("e2", "Beta", 0.5)]
    question = _question()
    synth = _FakeSynth(decisions, NoAgentsDerivableError("no profile could be seated"))
    ranked, agents = asyncio.run(_seat(synth, question, None))
    assert ranked == ["Alpha", "Beta"]
    assert agents == []
    assert _brier_pairs(agents, question.stance) == []


def test_a_question_the_graph_does_not_cover_has_an_empty_ranking():
    synth = _FakeSynth([], NoAgentsDerivableError("the graph does not cover this question"))
    ranked, agents = asyncio.run(_seat(synth, _question(), None))
    assert (ranked, agents) == ([], [])


def test_an_ambivalent_agent_scores_as_wrong_against_any_label():
    agent = SimpleNamespace(identity=SimpleNamespace(name="Alpha"), confidence=0.8, stance=SimpleNamespace(value="AMBIVALENT"))
    assert _brier_pairs([agent], {"Alpha": "POSITIVE"}) == [(0.8, False)]


def test_missing_neo4j_config_skips_the_live_run_without_connecting(monkeypatch):
    for name in ("NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD", "NEO4J_DATABASE"):
        monkeypatch.delenv(name, raising=False)
    real_config = GraphConfig
    # GraphConfig reads NEO4J_* as import-time defaults, so the empty fields are passed
    # explicitly: that is what a missing environment produces, and __post_init__ rejects it.
    monkeypatch.setitem(
        globals(),
        "GraphConfig",
        lambda: real_config(neo4j_uri="", neo4j_username="", neo4j_password="", neo4j_database=""),
    )
    monkeypatch.setitem(globals(), "load_questions", lambda: [_question(dataset="golden-run-1")])
    monkeypatch.setenv("GOLDEN_LLM", "1")
    with pytest.raises(pytest.skip.Exception, match="graph config unavailable"):
        test_golden_set_seating_metrics()
