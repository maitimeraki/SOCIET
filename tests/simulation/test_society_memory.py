"""Tests for SocietyMemory (per-round commit + snapshot read)."""
import logging
import uuid
import pytest
from unittest.mock import MagicMock

from src.simulation.society_memory import SocietyMemory, SocietySnapshot
from src.simulation.pair_turn import AgentTurn, RoundResult, CommPair


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    async def data(self):
        return self._rows


class FakeTx:
    def __init__(self, session):
        self._session = session

    async def run(self, query, **kwargs):
        if self._session._run_se:
            raise self._session._run_se
        self._session.calls.append((query, kwargs))

    async def commit(self):
        self._session.committed = True


class FakeSession:
    def __init__(self, rows=None, run_side_effect=None):
        self.calls = []
        self.committed = False
        self._rows = rows or []
        self._run_se = run_side_effect

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def run(self, query, **kwargs):
        if self._run_se:
            raise self._run_se
        self.calls.append((query, kwargs))
        return FakeResult(self._rows)

    async def begin_transaction(self):
        return FakeTx(self)


def _turn(name, content, stance="POSITIVE", conf=0.8):
    return AgentTurn(agent_id=str(uuid.uuid4()), agent_name=name, content=content,
                     stance=stance, confidence=conf, references=[])


def _round(n, turns, pairs):
    return RoundResult(round_num=n, turns=turns, pairs=pairs)


class FakeProfile:
    def __init__(self, name, conviction=0.5, cior=0.0):
        self.identity = type("I", (), {"name": name})()
        self.conviction = conviction
        self.cior = cior


@pytest.mark.asyncio
async def test_commit_round_writes_opinions_and_round_keyed_edges():
    session = FakeSession()
    driver = MagicMock()
    driver.session.return_value = session
    svc = SocietyMemory(driver, "db")
    rnd = _round(1, [_turn("Alice", "a content", stance="POSITIVE"),
                     _turn("Bob", "b content", stance="NEGATIVE")],
                 [CommPair(agent_a="Alice", agent_b="Bob")])
    receipt = await svc.commit_round(rnd, "ds1", "qh1",
                                     {"Alice": FakeProfile("Alice"), "Bob": FakeProfile("Bob")})
    assert receipt == {"round": 1, "opinions": 2, "edges": 2, "failed": False}
    assert session.committed
    queries = [q for (q, _) in session.calls]
    assert any(":Opinion" in q for q in queries)
    assert any("STATED" in q for q in queries)
    rx = next(q for q in queries if "REACTED_TO" in q)
    assert "round_no: r.round_no" in rx          # round-keyed MERGE — no overwrite across rounds
    assert "query_hash: $query_hash" in rx       # ...and query-keyed — no overwrite across debates
    rx_params = next(kw for (q, kw) in session.calls if "REACTED_TO" in q)
    assert rx_params["query_hash"] == "qh1"
    assert any("current_stance" in q for q in queries)
    # weight math: 0.8 * 0.5 * (1 + 0) / 2 = 0.2
    _, params = session.calls[0]
    assert abs(params["opinions"][0]["weight"] - 0.2) < 1e-9


@pytest.mark.asyncio
async def test_commit_round_failure_isolated():
    session = FakeSession(run_side_effect=RuntimeError("connection lost"))
    driver = MagicMock()
    driver.session.return_value = session
    svc = SocietyMemory(driver, "db")
    rnd = _round(1, [_turn("A", "a")], [CommPair(agent_a="A", agent_b="B")])
    receipt = await svc.commit_round(rnd, "ds", "qh", {})
    assert receipt["failed"] is True and receipt["opinions"] == 1


@pytest.mark.asyncio
async def test_commit_round_no_turns_noop():
    driver = MagicMock()
    svc = SocietyMemory(driver, "db")
    receipt = await svc.commit_round(_round(1, [], [CommPair(agent_a="A", agent_b="B")]), "ds", "qh", {})
    assert receipt["opinions"] == 0
    driver.session.assert_not_called()


@pytest.mark.asyncio
async def test_read_snapshot_maps_rows_and_buzz():
    rows = [
        {"agent": "Alice", "round_no": 2, "stance": "POSITIVE", "confidence": 0.9,
         "weight": 0.45, "summary": "s1", "entities": ["carbon"]},
        {"agent": "Bob", "round_no": 1, "stance": "NEGATIVE", "confidence": 0.8,
         "weight": 0.40, "summary": "s2", "entities": ["carbon"]},
    ]
    n_rows = [{"src": "Alice", "neighbors": ["Bob"]}]
    session = FakeSession(rows=rows)  # first run gets opinion rows, second run
    # neighbor rows need a second FakeResult — emulate via run returning rows then neighbor rows:
    class TwoStageSession(FakeSession):
        async def run(self, query, **kwargs):
            self.calls.append((query, kwargs))
            if "OPPOSES|SUPPORTS" in query:
                return FakeResult(n_rows)
            return FakeResult(rows)

    driver = MagicMock()
    sess = TwoStageSession()
    driver.session.return_value = sess
    svc = SocietyMemory(driver, "db")
    snap = await svc.read_snapshot("ds1", "qh1", through_round=2, top_k=8)
    assert snap.round == 2
    assert [e["agent"] for e in snap.entries] == ["Alice", "Bob"]  # weight-desc order preserved
    assert snap.neighbor_map == {"Alice": ["Bob"]}
    # REACTED_TO neighbours are narrowed to this debate; OPPOSES/SUPPORTS stay static
    nq, nparams = next((q, kw) for (q, kw) in sess.calls if "OPPOSES|SUPPORTS" in q)
    assert "type(r) <> 'REACTED_TO' OR r.query_hash = $query_hash" in nq
    assert nparams["query_hash"] == "qh1"
    assert snap.buzz == [{"entity": "carbon", "mentions": 2}]
    assert snap.version == "r2:2"
    assert snap.to_prompt(speaker="Alice", opponent="Bob") != ""
    prompt = snap.to_prompt(speaker="Alice", opponent="Bob")
    assert "Bob" in prompt and "Alice)" not in prompt[:len("SOCIETY")]  # own lines excluded via agent check below


def test_to_prompt_excludes_own_entries():
    snap = SocietySnapshot(round=1, entries=[
        {"agent": "Alice", "round": 1, "stance": "POSITIVE", "confidence": 0.9, "weight": 0.5, "summary": "own"},
        {"agent": "Bob", "round": 1, "stance": "NEGATIVE", "confidence": 0.8, "weight": 0.4, "summary": "other"},
    ])
    prompt = snap.to_prompt(speaker="Alice", opponent="Bob")
    assert "other" in prompt and "own" not in prompt


@pytest.mark.asyncio
async def test_commit_round_multi_pair_agent_text_not_duplicated():
    """An agent speaking in several pairs must be committed exactly once."""
    session = FakeSession()
    driver = MagicMock()
    driver.session.return_value = session
    svc = SocietyMemory(driver, "db")
    rnd = _round(1,
                 [_turn("Alice", "alice speaks", stance="POSITIVE"),
                  _turn("Bob", "bob speaks", stance="NEGATIVE"),
                  _turn("Carol", "carol speaks", stance="NEUTRAL")],
                 [CommPair(agent_a="Alice", agent_b="Bob"),
                  CommPair(agent_a="Alice", agent_b="Carol"),
                  CommPair(agent_a="Alice", agent_b="Bob")])  # duplicate pair must not inflate edges
    receipt = await svc.commit_round(rnd, "ds", "qh", {})
    opinions = session.calls[0][1]["opinions"]
    alice = next(o for o in opinions if o["agent_name"] == "Alice")
    assert alice["text"] == "alice speaks"          # exactly once — not "alice speaks\n\nalice speaks"
    assert receipt["opinions"] == 3
    assert receipt["edges"] == 4                    # Alice->Bob, Bob->Alice, Alice->Carol, Carol->Alice


@pytest.mark.asyncio
async def test_commit_round_self_pair_writes_no_reaction():
    """A self-pair (agent_a == agent_b) is not a reaction: REACTED_TO needs two distinct Personas."""
    session = FakeSession()
    driver = MagicMock()
    driver.session.return_value = session
    svc = SocietyMemory(driver, "db")
    rnd = _round(1, [_turn("X", "x content")], [CommPair(agent_a="X", agent_b="X")])
    receipt = await svc.commit_round(rnd, "ds", "qh", {})
    assert receipt["opinions"] == 1
    assert receipt["edges"] == 0
    _, params = next((q, kw) for (q, kw) in session.calls if "REACTED_TO" in q)
    assert params["reactions"] == []


@pytest.mark.asyncio
async def test_commit_round_zero_conviction_keeps_zero_weight():
    """conviction == 0.0 is a real value; CIOR weight must not fabricate 0.5 for it."""
    session = FakeSession()
    driver = MagicMock()
    driver.session.return_value = session
    svc = SocietyMemory(driver, "db")
    rnd = _round(1, [_turn("Zero", "z content", stance="NEUTRAL", conf=0.8)],
                 [CommPair(agent_a="Zero", agent_b="Other")])
    await svc.commit_round(rnd, "ds", "qh",
                           {"Zero": FakeProfile("Zero", conviction=0.0, cior=0.0)})
    op = session.calls[0][1]["opinions"][0]
    assert op["conviction"] == 0.0
    assert op["weight"] == 0.0                      # not 0.8 * 0.5 * (1 + 0) / 2 == 0.2


@pytest.mark.asyncio
async def test_commit_round_missing_profile_warns(caplog):
    """A speaker absent from profile_map gets the fallback weight — observably (P0-T4)."""
    session = FakeSession()
    driver = MagicMock()
    driver.session.return_value = session
    svc = SocietyMemory(driver, "db")
    rnd = _round(1, [_turn("Ghost", "g content", conf=0.8)],
                 [CommPair(agent_a="Ghost", agent_b="Other")])
    with caplog.at_level(logging.WARNING, logger="src.simulation.society_memory"):
        await svc.commit_round(rnd, "ds", "qh", {})
    records = [r for r in caplog.records if "absent from profile_map" in r.getMessage()]
    assert len(records) == 1
    assert records[0].levelno == logging.WARNING
    assert "Ghost" in records[0].getMessage()
    op = session.calls[0][1]["opinions"][0]
    assert op["weight"] == pytest.approx(0.8 * 0.5 * (1 + 0.0) / 2)  # unchanged fallback math
