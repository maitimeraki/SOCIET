"""DebateOrchestrator: coordinates the full debate pipeline with all 5 dependencies."""
import hashlib
from dataclasses import dataclass
from typing import Callable, Awaitable, Any, List, Optional

from src.persona.agent import Agent, Stance
from src.simulation.profile_synthesizer import ProfileSynthesizer
from src.simulation.topology import CommunicationTopology
from src.simulation.llm_batch import BatchedLLMRunner
from src.simulation.round_runner import RoundRunner
from src.simulation.verdict import VerdictSynthesizer
from src.simulation.society_memory import SocietyMemory
from src.simulation.debate_config import DebateConfig
from src.simulation.pair_turn import RoundResult
from src.utils.queryIntend import QueryIntent


@dataclass
class OrchestratedDebateResult:
    """Result from orchestrated debate."""
    converged: bool
    verdict: str
    final_stances: dict[str, str]
    warnings: list[str]
    rounds_executed: int
    intent: Optional[QueryIntent] = None


class DebateOrchestrator:
    """
    Coordinates the full debate pipeline:
    1. ProfileSynthesizer - synthesize agent profiles from graph
    2. CommunicationTopology - compute agent pairs via Cypher
    3. RoundRunner (with BatchedLLMRunner) - execute debate rounds
    4. VerdictSynthesizer - synthesize final verdict
    5. SocietyMemory - per-round commit to graph + society snapshot read-back
    """

    def __init__(
        self,
        profile_synthesizer: ProfileSynthesizer,
        topology: CommunicationTopology,
        llm_runner: BatchedLLMRunner,
        verdict_synthesizer: VerdictSynthesizer,
        society_memory: SocietyMemory,
    ):
        self._profile_synthesizer = profile_synthesizer
        self._topology = topology
        self._llm_runner = llm_runner
        self._verdict_synthesizer = verdict_synthesizer
        self._society_memory = society_memory

    async def run(
        self,
        query: str,
        dataset_id: str,
        config: DebateConfig,
        ws_broadcast: Callable[[dict[str, Any]], Awaitable[None]],
        llm_client: Optional[Any] = None,
        intent: Optional[QueryIntent] = None,
    ) -> OrchestratedDebateResult:
        """
        Run the full debate pipeline with WebSocket streaming.

        `llm_client` is optional; when supplied the verdict summary is
        produced by the LLM via `asynthesize` (no asyncio.run, no loop
        collision). When omitted a deterministic template summary is used.

        `intent` is the S3 query intent extracted by the caller (the debate
        job path); it is read-only here and is threaded into the round
        prompts and into S4 selection, and exposed on the result for later
        stages.
        """
        warnings: list[str] = []
        all_turns: list = []
        profiles: List[Agent] = []

        # Step 1: Synthesize profiles from graph (S4 selection consumes the intent)
        profiles = await self._profile_synthesizer.synthesize(
            query=query,
            dataset_id=dataset_id,
            max_agents=config.max_agents,
            intent=intent,
            config=config,
        )

        if not profiles:
            return OrchestratedDebateResult(
                converged=False,
                verdict="No agents could be synthesized for this query.",
                final_stances={},
                warnings=["No relevant entities found for query"],
                rounds_executed=0,
                intent=intent,
            )

        # Step 2: Run debate rounds
        rounds: list[RoundResult] = []
        round_runner = RoundRunner(_llm=self._llm_runner, ws_broadcast=ws_broadcast, intent=intent)
        debate_history: list[dict[str, Any]] = []
        snapshot = None  # graph-side society state, read at the start of rounds >= 2
        query_hash = hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]

        for round_num in range(1, config.max_rounds + 1):
            try:
                if round_num > 1:
                    try:
                        snapshot = await self._society_memory.read_snapshot(
                            dataset_id=dataset_id,
                            query_hash=query_hash,
                            through_round=round_num - 1,
                            top_k=config.snapshot_top_k,
                        )
                    except Exception as exc:
                        warnings.append(f"Round {round_num}: society snapshot read failed: {exc}")
                        snapshot = None

                pairs = await self._topology.compute_round_pairs(
                    profiles=profiles, dataset_id=dataset_id, round_num=round_num, config=config,
                )
                if not pairs:
                    warnings.append(f"Round {round_num}: No pairs computed")
                    continue

                if snapshot is not None:
                    share = self._weighted_share(rounds, profiles)
                    if share:
                        snapshot.consensus = {"stance": share[0], "weight_share": share[1]}

                round_result = await round_runner.execute_round(
                    profiles=profiles, pairs=pairs, round_num=round_num,
                    query=query, history=debate_history, society=snapshot,
                )
                rounds.append(round_result)

                for turn in round_result.turns:
                    debate_history.append({
                        "agent_name": turn.agent_name,
                        "agent_id": turn.agent_id,
                        "content": turn.content,
                        "stance": turn.stance,
                        "confidence": turn.confidence,
                        "round": round_num,
                    })
                    all_turns.append(turn)

                await ws_broadcast({
                    "type": "round",
                    "round": round_num,
                    "pairs": [
                        {"agent_a": p.agent_a, "agent_b": p.agent_b, "shared_entities": p.shared_entities}
                        for p in round_result.pairs
                    ],
                    "turns": [
                        {
                            "agent_id": t.agent_id,
                            "agent_name": t.agent_name,
                            "content": t.content,
                            "stance": t.stance,
                            "confidence": t.confidence,
                            "references": t.references,
                        }
                        for t in round_result.turns
                    ],
                })

                # Commit this round to the graph (idempotent; failure-isolated)
                try:
                    receipt = await self._society_memory.commit_round(
                        round_result=round_result,
                        dataset_id=dataset_id,
                        query_hash=query_hash,
                        profile_map={p.identity.name: p for p in profiles},
                    )
                    if receipt.get("failed"):
                        warnings.append(f"Round {round_num}: commit failed: {receipt.get('error')}")
                    else:
                        await ws_broadcast({"type": "commit", **receipt})
                except Exception as exc:
                    warnings.append(f"Round {round_num}: commit failed: {exc}")

                # Activation: pull related non-participants in (they debate from next round)
                if config.max_new_agents_per_round > 0 and len(profiles) < config.max_agents:
                    try:
                        candidates = await self._topology.find_activation_candidates(
                            participants=[p.identity.name for p in profiles],
                            dataset_id=dataset_id,
                            query_hash=query_hash,
                            last_round=round_num,
                            max_new=min(config.max_new_agents_per_round, config.max_agents - len(profiles)),
                        )
                        if candidates:
                            new_profiles = await self._profile_synthesizer.synthesize_from_names(
                                names=[c.agent_name for c in candidates],
                                query=query,
                                dataset_id=dataset_id,
                                relevance_by_name={
                                    c.agent_name: min(1.0, len(c.shared_entities) / 3.0)
                                    for c in candidates
                                },
                            )
                            # Every candidate may be unresolvable (synthesize_from_names
                            # returns []): then the roster did not grow, so no activation
                            # event and no warning — nothing was activated.
                            if new_profiles:
                                profiles.extend(new_profiles)
                                await ws_broadcast({
                                    "type": "activation",
                                    "round": round_num,
                                    "agents": [p.identity.name for p in new_profiles],
                                    "reasons": {c.agent_name: c.reason for c in candidates},
                                })
                                warnings.append(
                                    f"Round {round_num}: activated {len(new_profiles)} agents: "
                                    + ", ".join(p.identity.name for p in new_profiles)
                                )
                    except Exception as exc:
                        warnings.append(f"Round {round_num}: activation failed: {exc}")

                if self._check_convergence(rounds, profiles, config=config):
                    break

            except Exception as exc:
                warnings.append(f"Round {round_num} failed: {exc}")
                continue

        # Step 3: Synthesize verdict (async path -- no asyncio.run collision)
        verdict = await self._verdict_synthesizer.asynthesize(
            rounds=rounds, profiles=profiles, llm_client=llm_client
        )

        # Step 4: Collect final stances
        final_stances: dict[str, str] = {}
        for profile in profiles:
            for turn in reversed(all_turns):
                if turn.agent_name == profile.identity.name:
                    final_stances[profile.identity.name] = turn.stance
                    break
            else:
                final_stances[profile.identity.name] = "NEUTRAL"

        return OrchestratedDebateResult(
            converged=self._check_convergence(rounds, profiles, config=config),
            verdict=verdict.summary if verdict else "Debate completed.",
            final_stances=final_stances,
            warnings=warnings,
            rounds_executed=len(rounds),
            intent=intent,
        )

    def _weighted_share(self, rounds: list[RoundResult], profiles: List[Agent]) -> Optional[tuple[str, float]]:
        """(dominant stance, weight share) via CIOR weights. None when no turns."""
        clusters: dict[Stance, list] = {
            Stance.POSITIVE: [], Stance.NEGATIVE: [], Stance.NEUTRAL: [], Stance.AMBIVALENT: [],
        }
        for turn in (t for rnd in rounds for t in rnd.turns):
            try:
                stance = Stance(turn.stance) if isinstance(turn.stance, str) else turn.stance
                clusters[stance].append(turn)
            except ValueError:
                clusters[Stance.NEUTRAL].append(turn)
        total_turns = sum(len(v) for v in clusters.values())
        if total_turns == 0:
            return None
        if profiles:
            profile_map = {p.identity.name: p for p in profiles}
            weights = self._verdict_synthesizer._calibrate_cior(clusters, profile_map)
            total = sum(weights.values())
        else:
            weights = {s: len(v) for s, v in clusters.items()}
            total = float(total_turns)
        if total <= 0:
            return None
        dominant = max(weights, key=lambda s: weights[s])
        share_val = max(weights.values()) / total
        return (dominant.value if hasattr(dominant, "value") else str(dominant), share_val)

    def _check_convergence(
        self,
        rounds: list[RoundResult],
        profiles: Optional[List[Agent]] = None,
        config: Optional[DebateConfig] = None,
    ) -> bool:
        """Quality-weighted convergence on the LAST TWO rounds, with configured threshold."""
        if len(rounds) < 2:
            return False
        share = self._weighted_share(rounds[-2:], profiles)
        if share is None:
            return False
        threshold = config.convergence_threshold if config is not None else 0.8
        return share[1] >= threshold
