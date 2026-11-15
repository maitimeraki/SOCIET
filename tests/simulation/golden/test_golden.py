"""Golden-set harness: seating quality on a labelled question set, run against live Neo4j.

What it measures, per question, from the real seating (`ProfileSynthesizer.synthesize`):
  * NDCG@10 of the ranking (seated agents first, then the rest by score), graded labels 0-3.
  * recall@n, n = the seat count (`DebateConfig().max_agents`), over the labelled entities.
  * Brier of each seated agent's confidence against whether its stance matches the label.
    Labels "ABSTAIN" and unlabelled entities are left out of the Brier score.
  The three numbers are the mean NDCG, the mean recall, and the Brier over every scored pair.

Run it:
    GOLDEN_LLM=1 .venv/Scripts/python.exe -m pytest -m live tests/simulation/golden/test_golden.py -s
  It skips (never errors) unless all of these hold:
  * Neo4j answers `RETURN 1` at the GraphConfig address;
  * golden/questions.json holds a labelled set, not only the sample rows
    (sample datasets start with "golden-sample-");
  * GOLDEN_LLM=1 is set. Profile generation calls the configured LLM once per seat,
    so the run spends LLM tokens and the operator opts in explicitly.

Side effect: seating writes persona provenance and entity links for each question's
dataset (the same writes a debate makes). Point questions.json at a dataset you can
afford to have those links in.

Questions: golden/questions.json is a list of
  {"dataset", "question", "relevant": {entity name: 0-3}, "stance": {entity name: POSITIVE|NEGATIVE|NEUTRAL|ABSTAIN}}.
The shipped file holds 3 sample rows against the fixture datasets "golden-sample-*" so the
format is exercised. The product owner replaces them with the 25-40 labelled questions.

Targets: golden/targets.json holds `ndcg_at_10` (minimum), `recall_at_n` (minimum) and
`brier_max` (maximum). A null target is report-only and the run prints that it is unset.
The shipped targets are all null. Set them BEFORE tuning, so the gate measures the tuning
and not the numbers chosen after seeing the results.

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
)
from tests.simulation.golden.metrics import brier, ndcg_at_k, recall_at_n

SEATS = DebateConfig().max_agents
NDCG_K = 10


class _Unreachable(Exception):
    """Neo4j did not answer; the test skips instead of failing."""


@dataclass(frozen=True)
class Report:
    ndcg: float
    recall: float
    brier: float | None
    lines: list[str]


async def _seat(synth: ProfileSynthesizer, question: Question, llm: LLMClient):
    """Return (ranking names, seated agents) for one question.

    A question the graph refuses has no ranking and no agents, so its metrics are zero.
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


async def _measure(questions: list[Question]):
    cfg = GraphConfig()
    llm = LLMClient()
    async with GraphContext(cfg) as ctx:
        try:
            async with ctx._driver.session(database=cfg.neo4j_database) as session:
                await session.run("RETURN 1")
        except Exception as exc:
            raise _Unreachable(f"Neo4j not available at {cfg.neo4j_uri}: {exc}") from exc
        repo = PersonaRepository(
            neo4j_uri=cfg.neo4j_uri,
            neo4j_user=cfg.neo4j_username,
            neo4j_password=cfg.neo4j_password,
            neo4j_database=cfg.neo4j_database,
            llm_client=llm,
        )
        synth = ProfileSynthesizer(repo, ctx)
        try:
            return [(question, *await _seat(synth, question, llm)) for question in questions]
        finally:
            await repo.close()


def _brier_pairs(agents, stance: dict[str, str]) -> list[tuple[float, bool]]:
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
        question_pairs = _brier_pairs(agents, question.stance)
        ndcgs.append(ndcg)
        recalls.append(recall)
        pairs.extend(question_pairs)
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
    targets = load_targets()
    try:
        results = asyncio.run(_measure(questions))
    except _Unreachable as exc:
        pytest.skip(str(exc))
    _gate(_report(results), targets)
