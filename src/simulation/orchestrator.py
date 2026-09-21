"""DebateOrchestrator: coordinates the full debate pipeline with all 5 dependencies."""
from dataclasses import dataclass
from typing import Callable, Awaitable, Any

from src.persona.repository import PersonaRepository
from src.persona.graph_context import GraphContext
from src.simulation.profile_synthesizer import ProfileSynthesizer
from src.simulation.topology import CommunicationTopology
from src.simulation.llm_batch import BatchedLLMRunner
from src.simulation.round_runner import RoundRunner
from src.simulation.verdict import VerdictSynthesizer
from src.simulation.writeback import WriteBackService
from src.simulation.debate_config import DebateConfig
from src.simulation.pair_turn import RoundResult, DebateVerdict
from src.simulation.agent_node import Stance


@dataclass
class OrchestratedDebateResult:
    """Result from orchestrated debate."""
    converged: bool
    verdict: str
    final_stances: dict[str, str]
    warnings: list[str]
    rounds_executed: int


class DebateOrchestrator:
    """
    Coordinates the full debate pipeline:
    1. ProfileSynthesizer - synthesize agent profiles from graph
    2. CommunicationTopology - compute agent pairs via Cypher
    3. RoundRunner (with BatchedLLMRunner) - execute debate rounds
    4. VerdictSynthesizer - synthesize final verdict
    5. WriteBackService - persist results to graph
    """

    def __init__(
        self,
        profile_synthesizer: ProfileSynthesizer,
        topology: CommunicationTopology,
        llm_runner: BatchedLLMRunner,
        verdict_synthesizer: VerdictSynthesizer,
        writeback: WriteBackService,
    ):
        self._profile_synthesizer = profile_synthesizer
        self._topology = topology
        self._llm_runner = llm_runner
        self._verdict_synthesizer = verdict_synthesizer
        self._writeback = writeback

    async def run(
        self,
        query: str,
        dataset_id: str,
        config: DebateConfig,
        ws_broadcast: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> OrchestratedDebateResult:
        """
        Run the full debate pipeline with WebSocket streaming.
        """
        warnings: list[str] = []
        all_turns: list = []

        # Step 1: Synthesize profiles from graph
        profiles = await self._profile_synthesizer.synthesize(
            query=query,
            dataset_id=dataset_id,
            max_agents=config.max_agents,
        )

        if not profiles:
            return OrchestratedDebateResult(
                converged=False,
                verdict="No agents could be synthesized for this query.",
                final_stances={},
                warnings=["No relevant entities found for query"],
                rounds_executed=0,
            )

        # Step 2: Run debate rounds
        rounds: list[RoundResult] = []
        round_runner = RoundRunner(_llm=self._llm_runner, ws_broadcast=ws_broadcast)
        debate_history: list[dict[str, Any]] = []

        for round_num in range(1, config.max_rounds + 1):
            try:
                # Compute pairs for this round
                pairs = await self._topology.compute_round_pairs(
                    profiles=profiles,
                    dataset_id=dataset_id,
                    round_num=round_num,
                    config=config,
                )

                if not pairs:
                    warnings.append(f"Round {round_num}: No pairs computed")
                    continue

                # Execute round
                round_result = await round_runner.execute_round(
                    profiles=profiles,
                    pairs=pairs,
                    round_num=round_num,
                    query=query,
                    history=debate_history,
                )
                rounds.append(round_result)

                # Update history
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

                # Stream round via WebSocket
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

                # Check convergence
                if self._check_convergence(rounds):
                    break

            except Exception as exc:
                warnings.append(f"Round {round_num} failed: {exc}")
                continue

        # Step 3: Synthesize verdict
        verdict = self._verdict_synthesizer.synthesize(rounds=rounds, profiles=profiles)

        # Step 4: Collect final stances
        final_stances: dict[str, str] = {}
        for profile in profiles:
            for turn in reversed(all_turns):
                if turn.agent_name == profile.identity.name:
                    final_stances[profile.identity.name] = turn.stance
                    break
            else:
                final_stances[profile.identity.name] = "NEUTRAL"

        # Step 5: Persist to graph
        try:
            await self._writeback.persist_round_turns(rounds=rounds, dataset_id=dataset_id)
        except Exception as exc:
            warnings.append(f"Writeback failed: {exc}")

        return OrchestratedDebateResult(
            converged=self._check_convergence(rounds),
            verdict=verdict.summary if verdict else "Debate completed.",
            final_stances=final_stances,
            warnings=warnings,
            rounds_executed=len(rounds),
        )

    def _check_convergence(self, rounds: list[RoundResult]) -> bool:
        """Check if debate has converged based on stance uniformity."""
        if len(rounds) < 2:
            return False

        all_stances: dict[str, int] = {}
        for rnd in rounds[-2:]:  # Check last 2 rounds
            for turn in rnd.turns:
                try:
                    stance = Stance(turn.stance) if isinstance(turn.stance, str) else turn.stance
                    all_stances[stance] = all_stances.get(stance, 0) + 1
                except ValueError:
                    pass

        if not all_stances:
            return False

        total = sum(all_stances.values())
        dominant = max(all_stances.values())
        return (dominant / total) >= 0.8
