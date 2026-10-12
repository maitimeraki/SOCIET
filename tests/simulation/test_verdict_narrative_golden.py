"""Task 7: golden-path acceptance for the answer-writing narrative.

Proves the verdict is grounded in the user's query, not a generic summary:
  - a long, multi-section JSON reply yields a narrative > 1200 chars with
    several `## ` headings,
  - the query subject reaches the synthesis prompt (the model *sees* the question),
  - a non-JSON reply degrades to `.narrative == .summary` (never silently empty).
"""
import json

import pytest

from src.persona.agent import (
    Agent,
    DiscoveryType,
    ExpertiseLevel,
    PersonaIdentity,
    Stance,
)
from src.simulation.pair_turn import AgentTurn, RoundResult
from src.simulation.verdict import VerdictSynthesizer


# --- fixtures ---------------------------------------------------------------


def make_turn(agent_name: str, stance: str, content: str, reasoning: str = "") -> AgentTurn:
    return AgentTurn(
        agent_id=f"id-{agent_name}",
        agent_name=agent_name,
        content=content,
        stance=stance,
        confidence=0.7,
        references=[],
        reasoning=reasoning,
    )


def make_round(num: int, turns: list[AgentTurn]) -> RoundResult:
    return RoundResult(round_num=num, turns=turns, pairs=[])


def make_agent(name: str) -> Agent:
    return Agent(
        identity=PersonaIdentity(
            name=name, archetype="Expert", communication_style="direct"
        ),
        discovery_type=DiscoveryType.GRAPH_DISCOVERY,
        expertise_level=ExpertiseLevel.STRATEGIC,
        conviction=1.0,
        cior=1.0,
        summary_provenance=[],
    )


class _SpyLLM:
    """Mock LLMClient.generate that records the prompts it was handed."""

    def __init__(self, reply: str):
        self.reply = reply
        self.calls: list[dict] = []

    async def generate(self, system_prompt, user_prompt, **kwargs):
        self.calls.append({"system": system_prompt, "user": user_prompt})
        return self.reply

    @property
    def last_user_prompt(self) -> str:
        return self.calls[-1]["user"]


_SUBJECT = "Europe"


def _long_verdict_json() -> str:
    """A multi-section verdict whose fields are long enough to clear 1200 chars."""
    return json.dumps({
        "answer": (
            "Recommend entering Europe through a phased pilot: begin with the "
            "Nordics and DACH, where the demand signals are strongest, and hold "
            "a decision gate at month nine before committing to a full rollout. "
            "The measured approach captures the upside while keeping the downside "
            "contained if the regulatory climate tightens. Sequence the launch as "
            "three waves, each with its own budget envelope and success criteria, "
            "so that an early miss in one market does not force a retreat from "
            "the others. Staff the first wave with a small, senior team drawn from "
            "existing market leads who already understand the product's nuances."
        ),
        "reasoning": (
            "The positive cluster points to concrete traction: inbound pipeline, "
            "channel partnerships, and a customer base that already asks for EU "
            "coverage. The negative cluster counters that the compliance surface "
            "(GDPR, local data residency, VAT) is heavier than the team currently "
            "models and that a rushed launch would divert engineering from the "
            "core product. Weighing both, the evidence supports entering Europe, "
            "but only at a pace the operations and legal functions can absorb. "
            "The tie-breaker is reversibility: a pilot is cheap to unwind, while "
            "a full commitment is not, so the asymmetry favors starting now and "
            "scaling only when the leading indicators confirm the thesis."
        ),
        "constraints_and_risks": (
            "Cash burn rises while the EU entity is sub-scale; a hard regulatory "
            "misstep in one jurisdiction could taint the brand across the bloc; "
            "and key hires for the regional go-to-market take longer than the "
            "revenue model assumes. Data residency obligations may force a "
            "separate infrastructure footprint, adding fixed cost before any "
            "revenue lands. Currency exposure and local pricing pressure could "
            "compress margins below the plan in the first four quarters."
        ),
        "dissenting_views": [
            {"stance": "NEGATIVE", "view": "Wait until the core market hits breakeven."}
        ],
        "evidence": [{"entity": "eu_pipeline", "claim": "inbound demand"}],
        "confidence": 0.66,
    })


# --- golden path ------------------------------------------------------------


class TestGoldenPathNarrative:
    @pytest.mark.asyncio
    async def test_narrative_is_substantial_and_on_topic(self):
        rounds = [
            make_round(1, [
                make_turn(
                    "Strategist", "POSITIVE",
                    "Expanding to Europe opens a large new market.",
                    reasoning="Europe has strong demand signals for us.",
                ),
                make_turn(
                    "Controller", "NEGATIVE",
                    "Expanding to Europe brings heavy compliance costs.",
                    reasoning="GDPR and data residency raise our costs.",
                ),
            ]),
            make_round(2, [
                make_turn(
                    "Operator", "POSITIVE",
                    "A phased Europe entry balances upside and risk.",
                    reasoning="Pilot in the Nordics first.",
                ),
            ]),
        ]
        profiles = [make_agent("Strategist"), make_agent("Controller"), make_agent("Operator")]
        llm = _SpyLLM(_long_verdict_json())

        verdict = await VerdictSynthesizer().asynthesize(
            rounds=rounds,
            profiles=profiles,
            llm_client=llm,
            query="Should we expand to Europe?",
        )

        # (1) substantial: exceeds the ~1200-char bar.
        assert len(verdict.narrative) > 1200
        # (2) structured: several markdown section headings.
        assert verdict.narrative.count("## ") >= 3
        # (3) on-topic: the query subject appears in the answer itself.
        assert _SUBJECT in verdict.narrative
        # the short summary is still carried for the job field.
        assert verdict.summary

    @pytest.mark.asyncio
    async def test_query_subject_reaches_the_synthesis_prompt(self):
        rounds = [
            make_round(1, [
                make_turn("Strategist", "POSITIVE", "Europe is attractive."),
                make_turn("Controller", "NEGATIVE", "Europe is costly."),
            ]),
        ]
        profiles = [make_agent("Strategist"), make_agent("Controller")]
        llm = _SpyLLM(_long_verdict_json())

        await VerdictSynthesizer().asynthesize(
            rounds=rounds,
            profiles=profiles,
            llm_client=llm,
            query="Should we expand to Europe?",
        )

        # the user's question (and its subject) is handed to the model.
        prompt = llm.last_user_prompt
        assert "Should we expand to Europe?" in prompt
        assert _SUBJECT in prompt
        assert "QUESTION:" in prompt
        # the transcript rides along, so the answer can cite the argument.
        assert "Europe is attractive." in prompt
        assert "Europe is costly." in prompt

    @pytest.mark.asyncio
    async def test_non_json_reply_falls_back_to_summary(self):
        rounds = [
            make_round(1, [
                make_turn("Strategist", "POSITIVE", "Europe is attractive."),
                make_turn("Controller", "NEGATIVE", "Europe is costly."),
            ]),
        ]
        profiles = [make_agent("Strategist"), make_agent("Controller")]
        llm = _SpyLLM(reply="The society leaned positive on Europe.")

        verdict = await VerdictSynthesizer().asynthesize(
            rounds=rounds,
            profiles=profiles,
            llm_client=llm,
            query="Should we expand to Europe?",
        )

        # a bad reply must not silently empty the output.
        assert verdict.narrative == verdict.summary
        assert verdict.narrative
        assert verdict.overall_stance == Stance.POSITIVE
