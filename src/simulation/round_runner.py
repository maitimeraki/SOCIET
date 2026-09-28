"""RoundRunner: dispatches pair prompts via BatchedLLMRunner and assembles RoundResult."""
from dataclasses import dataclass
from typing import Optional, Callable

from src.persona.agent import Agent
from src.simulation.llm_batch import BatchedLLMRunner, PairPrompt
from src.simulation.pair_turn import AgentTurn, RoundResult, CommPair


def _parse_response_stance(
    response: str, default_stance: str, default_confidence: float
) -> tuple[str, float]:
    """Parse stance and confidence from agent response using simple heuristics."""
    stance = default_stance
    confidence = default_confidence
    response_lower = response.lower()

    if any(word in response_lower for word in ["support", "agree", "favor", "endorse", "positive"]):
        stance = "POSITIVE"
    elif any(word in response_lower for word in ["oppose", "disagree", "reject", "against", "negative"]):
        stance = "NEGATIVE"
    elif any(word in response_lower for word in ["neutral", "balanced", "both", "neither"]):
        stance = "NEUTRAL"

    if any(word in response_lower for word in ["certain", "definitely", "clearly", "absolutely"]):
        confidence = min(1.0, confidence + 0.1)
    elif any(word in response_lower for word in ["maybe", "perhaps", "uncertain", "might", "could"]):
        confidence = max(0.0, confidence - 0.1)

    return stance, confidence


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


def _build_system_prompt(agent: Agent, opponent: Agent, shared_entities: list[str]) -> str:
    domains = ", ".join(agent.domain_tags[:3])
    shared = ", ".join(shared_entities[:3]) if shared_entities else "none"
    cb = agent.confidence_breakdown
    provenance_summary = (
        ", ".join([p.title for p in agent.summary_provenance[:3]])
        if agent.summary_provenance
        else "none"
    )
    return (
        f"You are {agent.identity.name}, an expert in {domains}.\n"
        f"Archetype: {agent.identity.archetype}. Communication style: {agent.identity.communication_style}.\n"
        f"Your perspective: {agent.detailed_perspective[:500]}\n"
        f"Bio: {agent.bio[:300]}\n"
        f"Stance on this topic: {agent.stance.value} (intensity {agent.intensity:.2f}).\n"
        f"Confidence breakdown: sources={cb.source_breadth}, nodes={cb.node_density}, connectivity={cb.relationship_connectivity:.2f}\n"
        f"Provenance: {provenance_summary}\n"
        f"You share these entities with your opponent: {shared}\n"
        f"Engage genuinely with opposing viewpoints while staying true to your expertise."
    )


def _build_user_prompt(
    agent: Agent, opponent: Agent, query: str, history: list[dict]
) -> str:
    history_str = ""
    if history:
        recent = history[-4:]
        lines = [f"- {h['agent_name']}: {h['content'][:150]}" for h in recent]
        history_str = "\n".join(lines)
    return (
        f"DEBATE TOPIC: {query}\n\n"
        f"You are responding to: {opponent.identity.name}\n"
        f"Their stance: (review conversation history below)\n\n"
        f"CONVERSATION HISTORY:\n{history_str or '(No previous turns)'}\n\n"
        f"Respond to {opponent.identity.name}'s perspective, engaging with specific arguments."
    )


@dataclass
class RoundRunner:
    """Executes one debate round: builds prompts, runs LLM batch, assembles RoundResult."""

    _llm: BatchedLLMRunner
    ws_broadcast: Optional[Callable] = None

    async def execute_round(
        self,
        profiles: list[Agent],
        pairs: list[CommPair],
        round_num: int,
        query: str,
        history: list[dict],
    ) -> RoundResult:
        prompts: list[PairPrompt] = []
        profile_map = {p.identity.name: p for p in profiles}
        prompt_meta: dict[str, dict] = {}

        # Use the first profile's dataset_id so pair_ids are tenant-scoped.
        # All profiles in a debate share the same dataset_id; this guards
        # against collisions if two datasets ever share agent names.
        dataset_id = profiles[0].graph_snapshot.dataset_id if profiles else "default"

        for pair in pairs:
            agent_a = profile_map.get(pair.agent_a)
            agent_b = profile_map.get(pair.agent_b)
            if not agent_a or not agent_b:
                continue

            shared = [str(e) for e in (pair.shared_entities or [])]

            meta_a = {"pair": pair, "speaker": agent_a, "opponent": agent_b}
            prompt_a = PairPrompt(
                system_prompt=_build_system_prompt(agent_a, agent_b, shared),
                user_prompt=_build_user_prompt(agent_a, agent_b, query, history),
                pair_id=f"{dataset_id}:{pair.agent_a}:{pair.agent_b}",
            )
            prompts.append(prompt_a)
            prompt_meta[prompt_a.pair_id] = meta_a

            meta_b = {"pair": pair, "speaker": agent_b, "opponent": agent_a}
            prompt_b = PairPrompt(
                system_prompt=_build_system_prompt(agent_b, agent_a, shared),
                user_prompt=_build_user_prompt(agent_b, agent_a, query, history),
                pair_id=f"{dataset_id}:{pair.agent_b}:{pair.agent_a}",
            )
            prompts.append(prompt_b)
            prompt_meta[prompt_b.pair_id] = meta_b

        turns: list[AgentTurn] = []
        collected_pairs: list[CommPair] = []

        async for result in self._llm.gather(prompts):
            if self.ws_broadcast:
                await self.ws_broadcast(
                    {
                        "type": "pair_turn",
                        "pair_id": result.pair_id,
                        "response": result.response,
                        "error": result.error,
                    }
                )

            meta = prompt_meta.get(result.pair_id)
            if meta is None or result.error:
                continue

            stance, confidence = _parse_response_stance(
                result.response,
                default_stance="NEUTRAL",
                default_confidence=meta["speaker"].confidence,
            )
            turn = AgentTurn(
                agent_id=str(meta["speaker"].agent_id),
                agent_name=meta["speaker"].identity.name,
                content=result.response,
                stance=stance,
                confidence=confidence,
                references=_extract_references(
                    result.response,
                    list(dict.fromkeys(
                        (meta["pair"].shared_entities or [])
                        + [meta["opponent"].identity.name]
                    )),
                ),
            )
            turns.append(turn)

            pair = meta["pair"]
            if pair not in collected_pairs:
                collected_pairs.append(pair)

        return RoundResult(round_num=round_num, turns=turns, pairs=collected_pairs)
