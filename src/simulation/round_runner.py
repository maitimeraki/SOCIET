"""RoundRunner: dispatches pair prompts via BatchedLLMRunner and assembles RoundResult."""

from dataclasses import dataclass, field, replace
from typing import Callable, Optional

from src.billing import metering
from src.llm.config_llm import LLMConfig
from src.persona.agent import Agent
from src.simulation.llm_batch import BatchedLLMRunner, PairPrompt, PairResult
from src.simulation.pair_turn import AgentTurn, CommPair, RoundResult
from src.simulation.profile_generator import attr_text, evidence_block
from src.simulation.society_memory import SocietySnapshot
from src.simulation.turn_protocol import (
    PositionState,
    TurnParse,
    accept_position,
    parse_turn,
)
from src.utils.queryIntend import QueryIntent

OPPONENT_STATEMENT_CHARS = 600

#: Evidence items rendered into one agent's turn prompt.
PROMPT_EVIDENCE_MAX = 12

#: Sampling temperature for every debate turn call.
ROUND_TEMPERATURE = 0.7

#: The reason a turn carries when its LLM call raised; such a turn is not retried.
LLM_FAILED = "the LLM call failed"
#: The reason a turn carries when its batch returned no result for it.
NO_REPLY = "no reply came back"

RETRY_NOTE = (
    "Your previous reply did not follow the required form and was discarded. "
    "Reply again in exactly this form:"
)


def _format_instruction(opponent_name: str) -> str:
    """The declared turn form. The only place it is written; the retry restates it verbatim."""
    return (
        "Reply in exactly this form, one label per line, in this order, with nothing before REASONING:\n"
        "REASONING: <your private thinking, at most 60 words>\n"
        "POSITION: <POSITIVE|NEGATIVE|NEUTRAL|ABSTAIN> <strength from 0 to 1>\n"
        "CITES: <ids from the evidence above, comma separated, or leave empty>\n"
        f"ANSWER: <your reply to {opponent_name}, engaging with specific arguments>"
    )


def _read_reply(result: Optional[PairResult], own_ids: set[str]) -> tuple[Optional[TurnParse], str]:
    """(parsed, "") for a valid reply; otherwise (None, reason), where reason is a fixed class string."""
    if result is None:
        return None, NO_REPLY
    if result.error:
        return None, LLM_FAILED
    try:
        return parse_turn(result.response, own_ids), ""
    except ValueError as exc:
        return None, str(exc)


def _with_retry_note(prompt: PairPrompt, opponent: Agent) -> PairPrompt:
    """The prompt for the one retry: the same prompt with the declared form restated."""
    return replace(
        prompt,
        user_prompt=(
            f"{prompt.user_prompt}\n\n{RETRY_NOTE}\n"
            + _format_instruction(opponent.identity.name)
        ),
    )


def _extract_references(content: str, candidates: list[str]) -> list[str]:
    """Entities a turn references: known candidate names appearing in the content. Cap 5.

    ponytail: name-containment heuristic; upgrade to ontology-aware entity
    resolution if precision matters.
    """
    lower = content.lower()
    refs: list[str] = []
    for cand in candidates:
        name = (cand or "").strip()
        if name and name.lower() in lower and name not in refs:
            refs.append(name)
    return refs[:5]


def _truncate_snippet(text: str, budget: int) -> str:
    """Whitespace-normalised snippet, cut to `budget` at a word boundary."""
    text = " ".join(str(text).split())
    if len(text) <= budget:
        return text
    cut = text[:budget]
    return cut.rsplit(" ", 1)[0] if " " in cut else cut


def _shown_evidence_ids(agent: Agent) -> set[str]:
    """The evidence ids the agent's system prompt shows: the ids a turn may cite."""
    return {attr_text(item.id) for item in agent.evidence[:PROMPT_EVIDENCE_MAX]}


def _build_system_prompt(agent: Agent, shared_entities: list[str]) -> str:
    """The agent's own voice: role, bio, the full profile, stance and its evidence.

    Evidence renders as fenced `<evidence>` blocks (the same fence the profile
    generator uses), at most PROMPT_EVIDENCE_MAX of them.
    """
    shared = ", ".join(shared_entities[:3]) if shared_entities else "none"
    fenced = [
        line
        for item in agent.evidence[:PROMPT_EVIDENCE_MAX]
        for line in evidence_block(item)
    ]
    evidence = "\n".join(fenced) if fenced else "none"
    return (
        f"You are {agent.identity.name}. Role: {agent.role}\n"
        f"Bio: {agent.bio}\n"
        f"Your full profile:\n{agent.details_raw}\n"
        f"Stance on this topic: {agent.stance.value} (strength {agent.strength:.2f}).\n"
        f"Confidence: {agent.confidence:.2f}\n"
        f"YOUR EVIDENCE (the documents you were built from):\n{evidence}\n"
        f"You share these entities with your opponent: {shared}\n"
        f"Engage genuinely with opposing viewpoints while staying true to your expertise."
    )


def _intent_context_block(intent: Optional[QueryIntent]) -> str:
    """Compact intent context for the prompt: restated question + what support/oppose mean here.

    Empty string when there is no intent (older callers) or the intent carries
    neither field — prompts stay valid either way.
    """
    if intent is None:
        return ""
    lines = []
    if intent.core_question:
        lines.append(f"Core question: {intent.core_question}")
    if intent.stance_axis:
        lines.append(
            f'Stance axis (what "support" vs "oppose" means for this question): {intent.stance_axis}'
        )
    return "INTENT CONTEXT:\n" + "\n".join(lines) if lines else ""


def _build_user_prompt(
    agent: Agent,
    opponent: Agent,
    query: str,
    history: list[dict],
    society: Optional[SocietySnapshot] = None,
    intent: Optional[QueryIntent] = None,
    max_opinions: int = 6,
) -> str:
    history_str = ""
    if history:
        recent = history[-4:]
        lines = [f"- {h['agent_name']}: {h['content'][:150]}" for h in recent]
        history_str = "\n".join(lines)

    opp_last = next(
        (h for h in reversed(history) if h.get("agent_name") == opponent.identity.name),
        None,
    )
    their_stance = opp_last.get("stance") if opp_last else None
    their_line = (
        f"{their_stance} (latest on record)" if their_stance else "no position yet"
    )

    opponent_str = ""
    if opp_last and opp_last.get("content"):
        said = _truncate_snippet(opp_last["content"], OPPONENT_STATEMENT_CHARS)
        if said:
            opponent_str = f"WHAT {opponent.identity.name} JUST ARGUED:\n{said}\n\n"

    society_str = ""
    self_str = ""
    if society is not None:
        block = society.to_prompt(
            speaker=agent.identity.name,
            opponent=opponent.identity.name,
            max_opinions=max_opinions,
        )
        if block:
            society_str = f"{block}\n\n"
        own = society.self_prompt(speaker=agent.identity.name)
        if own:
            self_str = f"{own}\n\n"

    intent_block = _intent_context_block(intent)
    intent_str = f"{intent_block}\n\n" if intent_block else ""

    return (
        f"DEBATE TOPIC: {query}\n\n"
        f"{intent_str}"
        f"You are responding to: {opponent.identity.name}\n"
        f"Their stance: {their_line}\n\n"
        f"{opponent_str}"
        f"{society_str}"
        f"{self_str}"
        f"CONVERSATION HISTORY:\n{history_str or '(No previous turns)'}\n\n"
        f"{_format_instruction(opponent.identity.name)}"
    )


@dataclass
class RoundRunner:
    """Executes one debate round: builds prompts, runs LLM batch, assembles RoundResult."""

    _llm: BatchedLLMRunner
    ws_broadcast: Optional[Callable] = None
    intent: Optional[QueryIntent] = None
    #: Each speaker's held position across the rounds of one debate (one RoundRunner per run).
    _positions: dict[str, PositionState] = field(default_factory=dict)

    async def execute_round(
        self,
        profiles: list[Agent],
        pairs: list[CommPair],
        round_num: int,
        query: str,
        history: list[dict],
        society: Optional[SocietySnapshot] = None,
        max_opinions: int = 6,
    ) -> RoundResult:
        prompts: list[PairPrompt] = []
        profile_map = {p.identity.name: p for p in profiles}
        prompt_meta: dict[str, dict] = {}

        # Use the first profile's dataset_id so pair_ids are tenant-scoped.
        # All profiles in a debate share the same dataset_id; this guards
        # against collisions if two datasets ever share agent names.
        dataset_id = profiles[0].dataset_id if profiles else "default"

        for pair in pairs:
            agent_a = profile_map.get(pair.agent_a)
            agent_b = profile_map.get(pair.agent_b)
            if not agent_a or not agent_b:
                continue

            shared = [str(e) for e in (pair.shared_entities or [])]
            for speaker, opponent, speaker_name, opponent_name in (
                (agent_a, agent_b, pair.agent_a, pair.agent_b),
                (agent_b, agent_a, pair.agent_b, pair.agent_a),
            ):
                prompt = PairPrompt(
                    system_prompt=_build_system_prompt(speaker, shared),
                    user_prompt=_build_user_prompt(
                        speaker,
                        opponent,
                        query,
                        history,
                        society=society,
                        intent=self.intent,
                        max_opinions=max_opinions,
                    ),
                    pair_id=f"{dataset_id}:{speaker_name}:{opponent_name}",
                    model=LLMConfig.debate_model,
                    temperature=ROUND_TEMPERATURE,
                    max_tokens=LLMConfig.max_output_tokens,
                )
                prompts.append(prompt)
                prompt_meta[prompt.pair_id] = {
                    "pair": pair,
                    "speaker": speaker,
                    "opponent": opponent,
                    "own_ids": _shown_evidence_ids(speaker),
                }

        turns: list[AgentTurn] = []
        collected_pairs: list[CommPair] = []
        warnings: list[str] = []
        with metering.source_scope("debate"):
            replies = await self._replies(prompts, prompt_meta)
            retries = [
                _with_retry_note(prompt, prompt_meta[prompt.pair_id]["opponent"])
                for prompt in prompts
                if replies[prompt.pair_id][1] not in ("", LLM_FAILED)
            ]
            if retries:
                replies.update(await self._replies(retries, prompt_meta))

        # Applied in prompt order, never completion order: a speaker in two pairs of one round
        # takes its held position from the same sequence on every run.
        for prompt in prompts:
            meta = prompt_meta[prompt.pair_id]
            parsed, reason = replies[prompt.pair_id]
            if parsed is None:
                warnings.append(f"{meta['speaker'].identity.name}: turn dropped, {reason}")
                continue
            turns.append(self._turn(meta, parsed))
            if meta["pair"] not in collected_pairs:
                collected_pairs.append(meta["pair"])

        return RoundResult(
            round_num=round_num,
            turns=turns,
            pairs=collected_pairs,
            warnings=warnings,
        )

    async def _replies(
        self, prompts: list[PairPrompt], prompt_meta: dict[str, dict]
    ) -> dict[str, tuple[Optional[TurnParse], str]]:
        """Run one batch and read every reply, keyed by pair_id (results arrive in completion order)."""
        results: dict[str, PairResult] = {}
        async for result in self._llm.gather(prompts):
            if self.ws_broadcast:
                await self.ws_broadcast({"type": "pair_turn", "pair_id": result.pair_id})
            results[result.pair_id] = result
        return {
            prompt.pair_id: _read_reply(
                results.get(prompt.pair_id), prompt_meta[prompt.pair_id]["own_ids"]
            )
            for prompt in prompts
        }

    def _turn(self, meta: dict, parsed: TurnParse) -> AgentTurn:
        speaker = meta["speaker"]
        name = speaker.identity.name
        held = self._positions.get(name)
        stance, reason = accept_position(held, parsed)
        cites_used = (held.cites_used if held else set()) | set(parsed.cites)
        self._positions[name] = PositionState(stance, cites_used)
        return AgentTurn(
            agent_id=str(speaker.agent_id),
            agent_name=name,
            content=parsed.answer,
            stance=stance.value,
            confidence=speaker.confidence,
            strength=parsed.strength,
            cites=parsed.cites,
            position_reason=reason,
            references=_extract_references(
                parsed.answer,
                list(
                    dict.fromkeys(
                        (meta["pair"].shared_entities or [])
                        + [meta["opponent"].identity.name]
                    )
                ),
            ),
        )
