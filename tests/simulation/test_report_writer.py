"""The final report: board facts, the bundle, the stored shape, and the orchestrator path (spec §13)."""

import json
import os
import re
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.billing.metering import MeteringError
from src.llm.config_llm import get_llm_config
from src.persona.agent import Stance
from src.simulation.debate_config import DebateConfig
from src.simulation.evidence import EvidenceItem
from src.simulation.llm_batch import BatchedLLMRunner, PairResult
from src.simulation.orchestrator import DebateOrchestrator
from src.simulation.pair_turn import AgentTurn, CommPair, RoundResult
from src.simulation.profile_synthesizer import ProfileSynthesizer
from src.simulation.society_memory import SocietyMemory, SocietySnapshot
from src.simulation.topology import CommunicationTopology
from src.simulation.turn_protocol import consensus_window, weighted_share
from src.simulation.verdict import (
    NO_AGREEMENT_GAP,
    NOT_PRODUCED,
    PRODUCED,
    REPORT_MAX_ATTEMPTS,
    BoardFacts,
    VerdictSynthesizer,
    board_facts,
    board_position_line,
    build_report_bundle,
    write_board_report,
)
from tests.agent_factory import slim_agent
from tests.simulation.test_orchestrator import _ok_receipt

_FALLBACK_TEXT = ("The debate concluded", "Confidence score", "No verdict", "Debate completed", "NO_VERDICT")


def _evidence(item_id: str, document: str, section: str, text: str) -> EvidenceItem:
    return EvidenceItem(item_id, str(uuid.uuid4()), f"doc-{document}", document, section,
                        (0, len(text)), text, "own", 0.9)


def _agent(name: str, confidence: float, evidence=()):
    return slim_agent(name, confidence=confidence, evidence=list(evidence))


def _turn(name: str, stance: str, cites=(), strength: float = 0.8) -> AgentTurn:
    return AgentTurn(
        agent_id=f"id-{name}", agent_name=name, content=f"{name} answers.", stance=stance,
        confidence=0.8, strength=strength, references=[], cites=tuple(cites),
    )


def _round(num: int, *turns: AgentTurn) -> RoundResult:
    return RoundResult(round_num=num, turns=list(turns), pairs=[])


def _two_source_board():
    alice = _agent("Alice", 0.9, [_evidence("e1", "Market memo", "Pricing", "The price cut is temporary.")])
    bob = _agent("Bob", 0.8, [_evidence("e1", "Trade report", "Tariffs", "Tariffs rose in June.")])
    rounds = [_round(1, _turn("Alice", "POSITIVE", cites=["e1"]), _turn("Bob", "NEGATIVE", cites=["e1"]))]
    return rounds, [alice, bob]


# --- board facts -------------------------------------------------------------


def test_room_counts_each_final_stance_and_an_agent_with_no_window_turn_is_abstain():
    profiles = [_agent("Alice", 0.9), _agent("Bob", 0.8), _agent("Carol", 0.7)]
    rounds = [_round(1, _turn("Alice", "POSITIVE"), _turn("Bob", "NEGATIVE"))]

    facts = board_facts(rounds, profiles, converged=False)

    assert facts.room == {"POSITIVE": 1, "NEGATIVE": 1, "NEUTRAL": 0, "ABSTAIN": 1}


def test_the_share_and_position_are_the_weighted_share_over_the_consensus_window():
    profiles = [_agent("Alice", 0.9), _agent("Bob", 0.8)]
    rounds = [_round(1, _turn("Bob", "NEGATIVE", strength=0.2)), _round(2, _turn("Alice", "POSITIVE"), _turn("Bob", "NEGATIVE"))]
    profile_map = {p.identity.name: p for p in profiles}
    expected = weighted_share(consensus_window(rounds), profile_map)

    facts = board_facts(rounds, profiles, converged=False)

    assert facts.position is expected[0]
    assert facts.share == expected[1]


def test_the_state_is_settled_only_when_the_stop_test_converged():
    rounds, profiles = _two_source_board()

    assert board_facts(rounds, profiles, converged=True).state == "settled"
    assert board_facts(rounds, profiles, converged=False).state == "not settled (round limit)"


def test_gaps_name_each_abstainer_and_add_the_threshold_line_when_unsettled():
    profiles = [_agent("Alice", 0.9), _agent("Bob", 0.8), _agent("Carol", 0.7)]
    rounds = [_round(1, _turn("Alice", "POSITIVE"), _turn("Bob", "ABSTAIN"))]

    facts = board_facts(rounds, profiles, converged=False)

    assert facts.gaps == ["Bob took no position", "Carol took no position", NO_AGREEMENT_GAP]


def test_a_settled_board_where_everyone_spoke_has_no_gaps():
    rounds, profiles = _two_source_board()

    assert board_facts(rounds, profiles, converged=True).gaps == []


def test_a_board_with_no_position_has_no_position_and_zero_share():
    profiles = [_agent("Alice", 0.9), _agent("Bob", 0.8)]
    rounds = [_round(1, _turn("Alice", "ABSTAIN"), _turn("Bob", "ABSTAIN"))]

    facts = board_facts(rounds, profiles, converged=False)

    assert facts.position is None
    assert facts.share == 0.0
    assert board_position_line(facts) == "Position: NO POSITION, 0%, not settled (round limit)"


def test_the_position_line_rounds_the_share_once_in_one_place():
    facts = BoardFacts(Stance.POSITIVE, 0.8249, {"POSITIVE": 1, "NEGATIVE": 0, "NEUTRAL": 0, "ABSTAIN": 0},
                       "settled", [])

    assert board_position_line(facts) == "Position: POSITIVE, 82%, settled"


# --- the bundle: numbering, switches, the public and backend-only maps -------


def test_sources_are_numbered_in_order_of_first_appearance():
    rounds, profiles = _two_source_board()

    bundle, refs = build_report_bundle(rounds, profiles, "q", "")

    assert bundle.sources["1"].document == "Market memo"
    assert bundle.sources["2"].document == "Trade report"
    assert refs == {
        "1": {"node_id": "node-Alice", "evidence_id": "e1"},
        "2": {"node_id": "node-Bob", "evidence_id": "e1"},
    }


def test_the_same_board_gives_the_same_bundle():
    first_rounds, first_profiles = _two_source_board()
    second_rounds, second_profiles = _two_source_board()

    first, first_refs = build_report_bundle(first_rounds, first_profiles, "q", "ctx")
    second, second_refs = build_report_bundle(second_rounds, second_profiles, "q", "ctx")

    assert first.sources == second.sources
    assert first.citizens == second.citizens
    assert first_refs == second_refs


def test_span_text_is_in_the_bundle_and_never_in_the_backend_refs():
    rounds, profiles = _two_source_board()

    bundle, refs = build_report_bundle(rounds, profiles, "q", "")

    assert bundle.sources["1"].text == "The price cut is temporary."
    assert "The price cut" not in json.dumps(refs)


def test_a_switch_names_the_new_source_it_cites():
    alice = _agent("Alice", 0.9, [
        _evidence("e1", "Market memo", "Pricing", "The price cut is temporary."),
        _evidence("e2", "Trade report", "Tariffs", "Tariffs rose in June."),
    ])
    rounds = [
        _round(1, _turn("Alice", "POSITIVE", cites=["e1"])),
        _round(2, _turn("Alice", "NEGATIVE", cites=["e2"])),
    ]

    bundle, _ = build_report_bundle(rounds, [alice], "q", "")

    assert bundle.switches == ["Round 2: Alice moved from POSITIVE to NEGATIVE, citing [1]"]


# --- the stored shape --------------------------------------------------------


@pytest.mark.asyncio
async def test_without_a_client_nothing_is_stored_as_text():
    rounds, profiles = _two_source_board()

    report = await write_board_report(
        None, rounds=rounds, profiles=profiles, query="q", scenario="", converged=True
    )

    assert report == {
        "title": None, "markdown": None, "position": "POSITIVE", "sources": {}, "source_refs": {},
        "attempts": 0, "checks": [], "status": NOT_PRODUCED,
    }


# --- the report writer, with a scripted client -------------------------------


class _ReportLLM:
    """Answers each call in turn. A reply is text, a function of the prompt, or an exception to raise."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.prompts: list[str] = []
        self.kwargs: list[dict] = []

    async def generate(self, system_prompt, user_prompt, **kwargs):
        self.prompts.append(user_prompt)
        self.kwargs.append(kwargs)
        reply = self.replies[min(len(self.prompts), len(self.replies)) - 1]
        if isinstance(reply, BaseException):
            raise reply
        return reply(user_prompt) if callable(reply) else reply


def _good_report(prompt: str) -> str:
    """A report that passes every check: it echoes the board line and cites the first source it is given."""
    line = re.search(r"must read exactly: (Position: [^\n]*)", prompt).group(1)
    cited = re.findall(r'<evidence id="(\d+)"', prompt)
    gaps = re.search(r"Gaps:\n(.*?)\nThe first Recommendation", prompt, re.S).group(1)
    point = (
        f"Point: the price cut may not last [{cited[0]}] (from the documents)"
        if cited
        else "Point: the price cut may not last (judgement)"
    )
    body = [
        "# Enter Berlin?",
        "## Recommendation",
        line,
        "Enter in stages.",
        "Watch the price cut.",
        "Revisit in two quarters.",
        "Confidence is moderate.",
        "## Timing",
        point,
        "Against:",
        "The cut may be a short tactic.",
        "Waiting may avoid the discount.",
        "The sources do not say how long it lasts.",
        "The timing rests on one assumption.",
        "A fast launch is a bet on it.",
        "Opinion: the timing is strong only if the cut lasts.",
        "Result: track the price for two quarters.",
    ]
    if gaps.strip() != "none":
        body += ["## Unknowns", "Whether the cut lasts."]
    return "\n".join(body)


def _bad_report(prompt: str) -> str:
    return "Just some prose, with no shape at all."


@pytest.mark.asyncio
async def test_a_good_first_reply_is_stored_with_public_sources_and_backend_refs():
    rounds, profiles = _two_source_board()
    llm = _ReportLLM(_good_report)

    report = await write_board_report(
        llm, rounds=rounds, profiles=profiles, query="Enter Berlin?", scenario="", converged=False
    )

    assert report["status"] == PRODUCED
    assert report["title"] == "Enter Berlin?"
    assert report["markdown"].startswith("# Enter Berlin?")
    assert report["sources"] == {
        "1": {"document": "Market memo", "section": "Pricing"},
        "2": {"document": "Trade report", "section": "Tariffs"},
    }
    assert set(report["source_refs"]) == {"1", "2"}
    assert report["attempts"] == 1
    assert report["checks"] == []


@pytest.mark.asyncio
async def test_a_failed_check_is_retried_with_its_error_and_counted_in_attempts():
    rounds, profiles = _two_source_board()
    llm = _ReportLLM(_bad_report, _good_report)

    report = await write_board_report(
        llm, rounds=rounds, profiles=profiles, query="q", scenario="", converged=False
    )

    assert report["status"] == PRODUCED
    assert report["attempts"] == 2
    assert report["checks"] and report["checks"][0].startswith("attempt 1:")
    assert "failed these checks" in llm.prompts[1]
    assert "failed these checks" not in llm.prompts[0]


@pytest.mark.asyncio
async def test_every_attempt_failing_stores_not_produced_with_no_text():
    rounds, profiles = _two_source_board()
    llm = _ReportLLM(_bad_report)

    report = await write_board_report(
        llm, rounds=rounds, profiles=profiles, query="q", scenario="", converged=False
    )

    assert len(llm.prompts) == REPORT_MAX_ATTEMPTS
    assert report["status"] == NOT_PRODUCED
    assert report["markdown"] is None
    assert report["title"] is None
    assert report["sources"] == {}
    assert report["attempts"] == REPORT_MAX_ATTEMPTS
    assert not any(text in json.dumps(report) for text in _FALLBACK_TEXT)


@pytest.mark.asyncio
async def test_a_metering_error_from_the_report_is_raised_and_never_counted_as_an_attempt():
    rounds, profiles = _two_source_board()
    llm = _ReportLLM(MeteringError("usage limit reached"))

    with pytest.raises(MeteringError):
        await write_board_report(llm, rounds=rounds, profiles=profiles, query="q", scenario="", converged=False)

    assert len(llm.prompts) == 1


@pytest.mark.asyncio
async def test_the_report_call_uses_the_configured_model_and_tokens(monkeypatch):
    monkeypatch.setenv("VERDICT_MAX_TOKENS", "2345")
    monkeypatch.setenv("VERDICT_LLM_MODEL", "sentinel-model")
    get_llm_config.cache_clear()
    try:
        rounds, profiles = _two_source_board()
        llm = _ReportLLM(_good_report)

        await write_board_report(llm, rounds=rounds, profiles=profiles, query="q", scenario="", converged=False)

        assert llm.kwargs[0]["max_tokens"] == 2345
        assert llm.kwargs[0]["model"] == "sentinel-model"
    finally:
        get_llm_config.cache_clear()


def test_the_verdict_model_defaults_to_the_analysis_tier_and_3000_tokens(monkeypatch):
    monkeypatch.delenv("VERDICT_LLM_MODEL", raising=False)
    monkeypatch.delenv("VERDICT_MAX_TOKENS", raising=False)
    get_llm_config.cache_clear()
    try:
        cfg = get_llm_config()
        assert cfg.verdict_max_tokens == 3000
        assert cfg.verdict_model == os.getenv("ANALYSIS_LLM_MODEL", "claude-sonnet-5")
    finally:
        get_llm_config.cache_clear()


# --- the orchestrator path: a real VerdictSynthesizer, a scripted debate, the report client ---

_SCRIPT = {"Alice": ("POSITIVE", ("e1",)), "Bob": ("NEGATIVE", ("e1",))}


def _protocol_reply(stance: str, cites: tuple[str, ...]) -> str:
    cited = ", ".join(cites)
    return (
        "REASONING: private thinking, dropped.\n"
        f"POSITION: {stance} 0.8\n"
        f"CITES: {cited}\n"
        f"ANSWER: The {stance.lower()} case stands."
    )


def _board_profiles():
    return [
        _agent("Alice", 0.9, [_evidence("e1", "Market memo", "Pricing", "The price cut is temporary.")]),
        _agent("Bob", 0.8, [_evidence("e1", "Trade report", "Tariffs", "Tariffs rose in June.")]),
    ]


def _orchestrator(profiles, script):
    synth = AsyncMock(spec=ProfileSynthesizer)
    synth.synthesize.return_value = profiles
    topo = AsyncMock(spec=CommunicationTopology)
    topo.compute_round_pairs.side_effect = lambda *a, **kw: [
        CommPair(agent_a=profiles[0].identity.name, agent_b=profiles[1].identity.name, shared_entities=[], score=0.5)
    ]
    society_memory = AsyncMock(spec=SocietyMemory)
    society_memory.read_snapshot.return_value = SocietySnapshot(round=0)
    society_memory.read_self_history.return_value = []
    society_memory.commit_round.return_value = _ok_receipt()

    async def gather(prompts):
        for prompt in prompts:
            speaker = prompt.pair_id.split(":")[1]
            stance, cites = script[speaker]
            yield PairResult(pair_id=prompt.pair_id, response=_protocol_reply(stance, cites))

    llm_runner = MagicMock(spec=BatchedLLMRunner)
    llm_runner.gather = MagicMock(side_effect=gather)
    return DebateOrchestrator(
        profile_synthesizer=synth,
        topology=topo,
        llm_runner=llm_runner,
        verdict_synthesizer=VerdictSynthesizer(),
        society_memory=society_memory,
    )


async def _run(report_llm, *, script=None, profiles=None, max_rounds=2):
    orch = _orchestrator(profiles or _board_profiles(), script or _SCRIPT)
    return await orch.run(
        "Should we enter Berlin?",
        "ds1",
        DebateConfig(max_agents=5, max_rounds=max_rounds),
        AsyncMock(),
        llm_client=report_llm,
    )


@pytest.mark.asyncio
async def test_a_produced_report_is_in_the_result_with_public_sources_and_backend_refs():
    report_llm = _ReportLLM(_good_report)

    result = await _run(report_llm)

    assert result.report["status"] == PRODUCED
    assert result.report["markdown"].startswith("# Enter Berlin?")
    assert result.report["sources"] == {
        "1": {"document": "Market memo", "section": "Pricing"},
        "2": {"document": "Trade report", "section": "Tariffs"},
    }
    assert result.report["source_refs"] == {
        "1": {"node_id": "node-Alice", "evidence_id": "e1"},
        "2": {"node_id": "node-Bob", "evidence_id": "e1"},
    }
    assert len(report_llm.prompts) == 1


@pytest.mark.asyncio
async def test_the_same_board_gives_the_same_report_bundle_and_numbering():
    first = _ReportLLM(_good_report)
    second = _ReportLLM(_good_report)

    result_a = await _run(first)
    result_b = await _run(second)

    assert first.prompts[0] == second.prompts[0]
    assert result_a.report["sources"] == result_b.report["sources"]


@pytest.mark.asyncio
async def test_all_attempts_failing_still_completes_the_run_with_no_report_text():
    report_llm = _ReportLLM(_bad_report)

    result = await _run(report_llm)

    assert result.rounds_executed == 2
    assert result.report["status"] == NOT_PRODUCED
    assert result.report["markdown"] is None
    assert result.report["title"] is None
    assert len(report_llm.prompts) == REPORT_MAX_ATTEMPTS
    assert not any(text in json.dumps(result.report) for text in _FALLBACK_TEXT)


@pytest.mark.asyncio
async def test_a_metering_error_from_the_report_stops_the_run():
    report_llm = _ReportLLM(MeteringError("usage limit reached"))

    with pytest.raises(MeteringError):
        await _run(report_llm)


@pytest.mark.asyncio
async def test_a_board_with_no_position_asks_for_a_report_with_no_position():
    report_llm = _ReportLLM(_good_report)
    script = {"Alice": ("ABSTAIN", ()), "Bob": ("ABSTAIN", ())}

    result = await _run(report_llm, script=script)

    assert "Position: NO POSITION, 0%, not settled (round limit)" in report_llm.prompts[0]
    assert result.report["position"] is None
    assert result.report["status"] == PRODUCED


@pytest.mark.asyncio
async def test_an_abstainer_is_named_in_the_gaps_the_report_reads():
    report_llm = _ReportLLM(_good_report)
    script = {"Alice": ("POSITIVE", ("e1",)), "Bob": ("ABSTAIN", ())}

    result = await _run(report_llm, script=script)

    assert "Gaps:\n- Bob took no position\n" in report_llm.prompts[0]
    assert result.report["status"] == PRODUCED


@pytest.mark.asyncio
async def test_a_board_below_the_threshold_adds_the_threshold_gap():
    report_llm = _ReportLLM(_good_report)

    await _run(report_llm)

    assert NO_AGREEMENT_GAP in report_llm.prompts[0]


# --- fix round 1: no ids, no UUIDs, no long verbatim copies in the served report ----

_LONG_SPAN = (
    "The price cut is temporary and the rollout depends on the Berlin pilot results, "
    "which the board has not yet seen in full."
)


def _board_with_text(text: str):
    alice = _agent("Alice", 0.9, [_evidence("e1", "Market memo", "Pricing", text)])
    bob = _agent("Bob", 0.8, [_evidence("e1", "Trade report", "Tariffs", "Tariffs rose in June.")])
    rounds = [_round(1, _turn("Alice", "POSITIVE", cites=["e1"]), _turn("Bob", "NEGATIVE", cites=["e1"]))]
    return rounds, [alice, bob]


def _with_line(line: str):
    """The good report with one extra line in the first Against."""
    return lambda prompt: _good_report(prompt).replace("Opinion:", f"{line}\nOpinion:", 1)


@pytest.mark.asyncio
async def test_an_evidence_id_in_brackets_fails_and_the_retry_names_the_rule():
    rounds, profiles = _board_with_text(_LONG_SPAN)
    llm = _ReportLLM(_with_line("Support is in [e1]."), _good_report)

    report = await write_board_report(llm, rounds=rounds, profiles=profiles, query="q", scenario="", converged=False)

    assert report["status"] == PRODUCED
    assert report["attempts"] == 2
    assert "an id in brackets is not a source marker" in report["checks"][0]
    assert "an id in brackets is not a source marker" in llm.prompts[1]


@pytest.mark.asyncio
async def test_a_uuid_in_the_text_fails_and_the_retry_names_the_rule():
    rounds, profiles = _board_with_text(_LONG_SPAN)
    llm = _ReportLLM(_with_line("Record 0c0ffee0-0000-4000-8000-0000000000c1 backs this."), _good_report)

    report = await write_board_report(llm, rounds=rounds, profiles=profiles, query="q", scenario="", converged=False)

    assert report["attempts"] == 2
    assert "a UUID or 32-character hex id appears in the text" in report["checks"][0]
    assert "a UUID or 32-character hex id appears in the text" in llm.prompts[1]


@pytest.mark.asyncio
async def test_a_pasted_span_of_90_characters_fails_and_the_retry_names_the_rule():
    rounds, profiles = _board_with_text(_LONG_SPAN)
    llm = _ReportLLM(_with_line(f"Quote: {_LONG_SPAN[:90]}."), _good_report)

    report = await write_board_report(llm, rounds=rounds, profiles=profiles, query="q", scenario="", converged=False)

    assert report["attempts"] == 2
    assert "the report copies source text verbatim: shorten quotes to a short phrase" in report["checks"][0]
    assert "copies source text verbatim" in llm.prompts[1]


@pytest.mark.asyncio
async def test_a_span_copied_with_different_spacing_is_still_a_verbatim_copy():
    rounds, profiles = _board_with_text(_LONG_SPAN)
    spaced = _LONG_SPAN[:90].replace(" ", "  ")
    llm = _ReportLLM(_with_line(f"Quote: {spaced}."), _good_report)

    report = await write_board_report(llm, rounds=rounds, profiles=profiles, query="q", scenario="", converged=False)

    assert report["attempts"] == 2
    assert "copies source text verbatim" in report["checks"][0]


@pytest.mark.asyncio
async def test_a_short_quote_under_80_characters_passes_on_the_first_attempt():
    rounds, profiles = _board_with_text(_LONG_SPAN)
    llm = _ReportLLM(_with_line(f"Quote: {_LONG_SPAN[:60]}."))

    report = await write_board_report(llm, rounds=rounds, profiles=profiles, query="q", scenario="", converged=False)

    assert report["status"] == PRODUCED
    assert report["attempts"] == 1
    assert report["checks"] == []
