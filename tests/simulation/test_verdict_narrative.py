"""Task 7: the verdict narrative never degrades silently.

Covers the answer-writer contract added on top of the golden path:
  - a reply that never parses is retried (bounded) and then FLAGGED as a
    fallback (narrative == summary, narrative_status == "fallback"),
  - a later attempt that returns valid JSON wins, and the retried prompt
    restated the bare-JSON constraint,
  - a valid object wrapped in markdown fences / trailing prose is repaired,
  - the model and token budget come from LLMConfig and honor their env vars.

The LLM is mocked at the client seam (repository rule: never hit a real LLM).
"""
import os

import pytest

from src.llm.config_llm import get_llm_config
from src.persona.agent import (
    Agent,
    DiscoveryType,
    ExpertiseLevel,
    PersonaIdentity,
)
from src.simulation.pair_turn import AgentTurn, RoundResult
from src.simulation.verdict import (
    VERDICT_JSON_REINFORCEMENT,
    VERDICT_MAX_ATTEMPTS,
    VerdictSynthesizer,
)


# --- fixtures ---------------------------------------------------------------


def make_turn(agent_name: str, stance: str, content: str) -> AgentTurn:
    return AgentTurn(
        agent_id=f"id-{agent_name}",
        agent_name=agent_name,
        content=content,
        stance=stance,
        confidence=0.7,
        references=[],
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


def two_agent_debate() -> tuple[list[RoundResult], list[Agent]]:
    rounds = [
        make_round(1, [
            make_turn("Strategist", "POSITIVE", "Europe is attractive."),
            make_turn("Controller", "NEGATIVE", "Europe is costly."),
        ]),
    ]
    return rounds, [make_agent("Strategist"), make_agent("Controller")]


def valid_json(answer: str = "Expand, cautiously.") -> str:
    return (
        '{"answer": "%s", "reasoning": "Weighed the arguments.", '
        '"constraints_and_risks": "Cash burn.", '
        '"dissenting_views": [{"stance": "NEGATIVE", "view": "Wait."}], '
        '"evidence": [{"entity": "eu_pipeline", "claim": "demand"}], '
        '"confidence": 0.6}' % answer
    )


class _ScriptedLLM:
    """Mock LLMClient.generate: returns `replies` in order (last repeats).

    An `Exception` entry is raised instead of returned, so a crashing provider
    can be scripted alongside a bad reply.
    """

    def __init__(self, *replies):
        self.replies = list(replies) or [""]
        self.calls: list[dict] = []

    async def generate(self, system_prompt, user_prompt, **kwargs):
        self.calls.append({"system": system_prompt, "user": user_prompt, "kwargs": kwargs})
        idx = min(len(self.calls) - 1, len(self.replies) - 1)
        reply = self.replies[idx]
        if isinstance(reply, Exception):
            raise reply
        return reply


# --- bounded retry + repair, and the flag -----------------------------------


class TestBoundedRetryAndFlag:
    @pytest.mark.asyncio
    async def test_unparseable_reply_is_retried_then_flagged_as_fallback(self):
        rounds, profiles = two_agent_debate()
        llm = _ScriptedLLM("not json at all", "still no object here", "{unclosed")

        verdict = await VerdictSynthesizer().asynthesize(
            rounds=rounds, profiles=profiles, llm_client=llm,
            query="Should we expand to Europe?", run_id="run-42",
        )

        # the fallback happened and is flagged, not silent.
        assert verdict.narrative_status == "fallback"
        assert verdict.narrative == verdict.summary
        assert verdict.narrative  # never silently empty
        # bounded: exactly the attempt budget, no unbounded loop.
        assert len(llm.calls) == VERDICT_MAX_ATTEMPTS

    @pytest.mark.asyncio
    async def test_a_crashing_provider_also_falls_back_flagged(self):
        rounds, profiles = two_agent_debate()
        llm = _ScriptedLLM(*[RuntimeError("provider down")] * VERDICT_MAX_ATTEMPTS)

        verdict = await VerdictSynthesizer().asynthesize(
            rounds=rounds, profiles=profiles, llm_client=llm,
        )

        assert verdict.narrative_status == "fallback"
        assert verdict.narrative == verdict.summary
        assert len(llm.calls) == VERDICT_MAX_ATTEMPTS

    @pytest.mark.asyncio
    async def test_a_later_valid_attempt_wins_and_is_not_flagged(self):
        rounds, profiles = two_agent_debate()
        llm = _ScriptedLLM("no object in this reply", valid_json("Expand now."))

        verdict = await VerdictSynthesizer().asynthesize(
            rounds=rounds, profiles=profiles, llm_client=llm,
            query="Should we expand to Europe?",
        )

        assert verdict.narrative_status == "ok"
        assert verdict.narrative != verdict.summary
        assert "Expand now." in verdict.narrative
        # it retried exactly once: first attempt bad, second good.
        assert len(llm.calls) == 2

    @pytest.mark.asyncio
    async def test_the_retry_restates_the_json_only_constraint(self):
        rounds, profiles = two_agent_debate()
        llm = _ScriptedLLM("no object", valid_json())

        await VerdictSynthesizer().asynthesize(
            rounds=rounds, profiles=profiles, llm_client=llm,
        )

        # first attempt: unmodified prompt; retry: reinforced.
        assert VERDICT_JSON_REINFORCEMENT not in llm.calls[0]["user"]
        assert VERDICT_JSON_REINFORCEMENT in llm.calls[1]["user"]

    @pytest.mark.asyncio
    async def test_markdown_fence_and_trailing_prose_are_repaired(self):
        rounds, profiles = two_agent_debate()
        raw = (
            "Sure, here is the verdict:\n"
            "```json\n" + valid_json("Expand via a phased pilot.") + "\n```\n"
            "Let me know if you want more detail."
        )
        llm = _ScriptedLLM(raw)

        verdict = await VerdictSynthesizer().asynthesize(
            rounds=rounds, profiles=profiles, llm_client=llm,
        )

        assert verdict.narrative_status == "ok"
        assert "Expand via a phased pilot." in verdict.narrative
        assert "## Recommendation" in verdict.narrative
        # repaired on the first reply — no retry needed.
        assert len(llm.calls) == 1

    @pytest.mark.asyncio
    async def test_prose_between_the_fence_and_the_object_is_tolerated(self):
        rounds, profiles = two_agent_debate()
        llm = _ScriptedLLM("Here you go: " + valid_json("Answer A.") + " — done.")

        verdict = await VerdictSynthesizer().asynthesize(
            rounds=rounds, profiles=profiles, llm_client=llm,
        )

        assert verdict.narrative_status == "ok"
        assert "Answer A." in verdict.narrative


# --- config: model + token budget come from LLMConfig -----------------------


class TestVerdictConfig:
    def test_defaults_are_analysis_tier_and_3000_tokens(self, monkeypatch):
        monkeypatch.delenv("VERDICT_LLM_MODEL", raising=False)
        monkeypatch.delenv("VERDICT_MAX_TOKENS", raising=False)
        get_llm_config.cache_clear()
        try:
            cfg = get_llm_config()
            assert cfg.verdict_max_tokens == 3000
            assert cfg.verdict_model == os.getenv("ANALYSIS_LLM_MODEL", "claude-sonnet-5")
        finally:
            get_llm_config.cache_clear()

    def test_env_overrides_are_honored(self, monkeypatch):
        monkeypatch.setenv("VERDICT_MAX_TOKENS", "1234")
        monkeypatch.setenv("VERDICT_LLM_MODEL", "sentinel-verdict-model")
        get_llm_config.cache_clear()
        try:
            cfg = get_llm_config()
            assert cfg.verdict_max_tokens == 1234
            assert cfg.verdict_model == "sentinel-verdict-model"
        finally:
            get_llm_config.cache_clear()

    @pytest.mark.asyncio
    async def test_answer_writer_uses_the_configured_model_and_tokens(self, monkeypatch):
        monkeypatch.setenv("VERDICT_MAX_TOKENS", "2345")
        monkeypatch.setenv("VERDICT_LLM_MODEL", "sentinel-model")
        get_llm_config.cache_clear()
        try:
            rounds, profiles = two_agent_debate()
            llm = _ScriptedLLM(valid_json())

            await VerdictSynthesizer().asynthesize(
                rounds=rounds, profiles=profiles, llm_client=llm,
            )

            assert llm.calls[0]["kwargs"]["max_tokens"] == 2345
            assert llm.calls[0]["kwargs"]["model"] == "sentinel-model"
        finally:
            get_llm_config.cache_clear()
