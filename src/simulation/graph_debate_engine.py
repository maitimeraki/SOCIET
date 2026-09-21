"""
Graph Debate Engine: Multi-round debate orchestration using AgentSpawner and CommunicationGraph.

This module implements the debate loop with convergence detection.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

from src.simulation.agent_node import AgentNode, Stance
from src.simulation.agent_spawner import AgentSpawner
from src.simulation.communication_graph import CommunicationGraph, CommPair
from src.simulation.debate_config import DebateConfig
from src.persona.graph_context import GraphContext


@dataclass
class AgentTurn:
    """Single agent turn in the debate."""
    agent_id: str
    agent_name: str
    content: str
    stance: str
    confidence: float
    references: List[str] = field(default_factory=list)


@dataclass
class RoundResult:
    """Result of a single debate round."""
    round_num: int
    turns: List[AgentTurn]
    pairs: List[CommPair]


@dataclass
class DebateResult:
    """Final result of a complete debate."""
    query: str
    rounds: List[RoundResult]
    converged: bool
    final_stances: Dict[str, str]
    verdict: str
    warnings: List[str] = field(default_factory=list)


@dataclass
class ClusterSummary:
    """Summary of an opinion cluster."""
    stance: Stance
    count: int
    total_weight: float
    avg_confidence: float
    avg_conviction: float
    agents: List[str]


@dataclass
class DebateVerdict:
    """Final verdict with weighted synthesis."""
    overall_stance: Stance
    confidence_score: float
    supporting_entities: List[str]
    opposing_entities: List[str]
    summary: str
    cluster_details: Dict[Stance, ClusterSummary]


class DebateEngine:
    """
    Multi-round debate engine using AgentSpawner and CommunicationGraph.

    Flow:
    1. Spawn agents from user query via AgentSpawner
    2. Compute communication pairs via CommunicationGraph
    3. Run rounds until convergence or max_rounds
    4. Generate final verdict
    """

    def __init__(
        self,
        spawner: AgentSpawner,
        comm_graph: Optional[CommunicationGraph] = None,
    ):
        """
        Initialize the debate engine.

        Args:
            spawner: AgentSpawner instance for creating agents from query.
            comm_graph: CommunicationGraph for computing pairs (default: new instance).
        """
        self.spawner = spawner
        self.comm_graph = comm_graph or CommunicationGraph()

    @classmethod
    def from_graph_context(
        cls,
        graph_context: GraphContext,
        max_agents: int = 8,
    ) -> "DebateEngine":
        """Factory to create DebateEngine with GraphContext."""
        spawner = AgentSpawner(graph_context=graph_context)
        return cls(spawner=spawner)

    async def run_debate(
        self,
        query: str,
        config: Optional[DebateConfig] = None,
    ) -> DebateResult:
        """
        Main entry point for running a multi-round debate.

        Args:
            query: The debate topic/question.
            config: Debate configuration (uses defaults if not provided).

        Returns:
            DebateResult with all rounds, stances, and final verdict.
        """
        config = config or DebateConfig()

        # Step 1: Spawn agents from query
        agents = await self.spawner.spawn_agents_from_query(
            query=query,
            max_agents=config.max_agents,
        )

        if not agents:
            return DebateResult(
                query=query,
                rounds=[],
                converged=False,
                final_stances={},
                verdict="No agents could be spawned for this query.",
                warnings=["No relevant entities found for query"],
            )

        # Step 2: Compute initial communication pairs
        pairs = self.comm_graph.compute_pairs(
            agents=agents,
            threshold=config.min_entity_overlap,
        )

        # Step 3: Initialize debate history
        debate_history: List[Dict[str, Any]] = []
        rounds: List[RoundResult] = []
        warnings: List[str] = []

        # Step 4: Run rounds until convergence or max_rounds
        for round_num in range(1, config.max_rounds + 1):
            # Get pairs for this round
            round_pairs = self.comm_graph.get_round_pairs(
                agents=agents,
                round_num=round_num,
                config=config,
            )

            # Execute round
            try:
                round_result = await self._run_round(
                    agents=agents,
                    pairs=round_pairs,
                    round_num=round_num,
                    query=query,
                    history=debate_history,
                )
                rounds.append(round_result)

                # Update debate history with this round's turns
                for turn in round_result.turns:
                    debate_history.append({
                        "agent_name": turn.agent_name,
                        "agent_id": turn.agent_id,
                        "content": turn.content,
                        "stance": turn.stance,
                        "confidence": turn.confidence,
                        "round": round_num,
                    })

                # Check convergence
                if self._check_convergence([r.turns for r in rounds]):
                    break

            except Exception as exc:
                warnings.append(f"Round {round_num} failed: {exc}")
                continue

        # Step 5: Generate final verdict
        verdict = self._generate_verdict(rounds, agents)

        # Collect final stances
        final_stances = {}
        for agent in agents:
            stance_key = str(agent.id)
            # Find latest turn for this agent
            for round_result in reversed(rounds):
                for turn in round_result.turns:
                    if turn.agent_id == stance_key:
                        final_stances[agent.name] = turn.stance
                        break
                if agent.name in final_stances:
                    break
            else:
                final_stances[agent.name] = self._get_stance_value(agent.stance)

        return DebateResult(
            query=query,
            rounds=rounds,
            converged=self._check_convergence([r.turns for r in rounds]),
            final_stances=final_stances,
            verdict=verdict,
            warnings=warnings,
        )

    async def _run_round(
        self,
        agents: List[AgentNode],
        pairs: List[CommPair],
        round_num: int,
        query: str,
        history: List[Dict[str, Any]],
    ) -> RoundResult:
        """
        Execute one round of agent interactions.

        For each pair, both agents speak to each other based on shared context.

        Args:
            agents: List of AgentNode instances.
            pairs: Communication pairs for this round.
            round_num: Current round number (1-indexed).
            query: The debate query.
            history: Previous debate history.

        Returns:
            RoundResult with all agent turns.
        """
        turns: List[AgentTurn] = []
        agent_map = {str(a.id): a for a in agents}

        # Process each pair - both agents speak
        for pair in pairs:
            agent_a = agent_map.get(pair.agent_a)
            agent_b = agent_map.get(pair.agent_b)

            if not agent_a or not agent_b:
                continue

            # Build shared context from pair
            shared_entities = ", ".join(pair.shared_entities[:5])
            context = {
                "query": query,
                "shared_entities": shared_entities,
                "history": history,
                "round_num": round_num,
                "opponent_name": agent_b.name,
                "opponent_stance": self._get_stance_value(agent_b.stance),
                "opponent_belief": agent_b.belief,
            }

            # Agent A speaks to Agent B
            try:
                turn_a = await self._agent_speaks(agent_a, context)
                turns.append(turn_a)
            except Exception as exc:
                turns.append(AgentTurn(
                    agent_id=str(agent_a.id),
                    agent_name=agent_a.name,
                    content=f"[Error: {exc}]",
                    stance=self._get_stance_value(agent_a.stance),
                    confidence=0.0,
                ))

            # Agent B speaks to Agent A
            context["opponent_name"] = agent_a.name
            context["opponent_stance"] = self._get_stance_value(agent_a.stance)
            context["opponent_belief"] = agent_a.belief

            try:
                turn_b = await self._agent_speaks(agent_b, context)
                turns.append(turn_b)
            except Exception as exc:
                turns.append(AgentTurn(
                    agent_id=str(agent_b.id),
                    agent_name=agent_b.name,
                    content=f"[Error: {exc}]",
                    stance=self._get_stance_value(agent_b.stance),
                    confidence=0.0,
                ))

        return RoundResult(round_num=round_num, turns=turns, pairs=pairs)

    async def _agent_speaks(
        self,
        agent: AgentNode,
        context: Dict[str, Any],
    ) -> AgentTurn:
        """
        Generate agent's response to another agent.

        Uses BCO + CIOR framework in the prompt.

        Args:
            agent: The speaking AgentNode.
            context: Debate context including query, history, opponent info.

        Returns:
            AgentTurn with the agent's response.
        """
        # Build the prompt with BCO/CIOR structure
        system_prompt = self._build_system_prompt(agent, context)
        user_prompt = self._build_user_prompt(agent, context)

        # Get LLM client (lazy import to avoid heavy deps at import time)
        from src.llm.client import LLMClient
        llm = LLMClient()

        try:
            response = await llm.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        except Exception as exc:
            raise RuntimeError(f"LLM generation failed: {exc}")

        # Parse response to extract stance and confidence
        stance, confidence = self._parse_response_stance(response, agent)

        return AgentTurn(
            agent_id=str(agent.id),
            agent_name=agent.name,
            content=response,
            stance=stance,
            confidence=confidence,
            references=self._extract_references(response),
        )

    def _get_stance_value(self, stance: Any) -> str:
        """Get stance as string, handling both enum and string values."""
        if isinstance(stance, str):
            return stance
        if hasattr(stance, 'value'):
            return stance.value
        return str(stance)

    def _build_system_prompt(
        self,
        agent: AgentNode,
        context: Dict[str, Any],
    ) -> str:
        """Build system prompt with BCO + CIOR framework."""
        stance_value = self._get_stance_value(agent.stance)
        return f"""SYSTEM:
You are {agent.name}, a {agent.archetype}.
Your role: {agent.role_description}
Your stance: {stance_value} (intensity: {agent.intensity:.2f})
Your belief: {agent.belief}
Your conviction: {agent.conviction:.2f}
Your CIOR: {agent.cior:+.2f}

Your instinct tags: {', '.join(agent.instinct_tags) if agent.instinct_tags else 'none'}
Your domain expertise: {', '.join(agent.domain_tags[:3]) if agent.domain_tags else 'general'}

You communicate with agents who share: {context.get('shared_entities', 'common interests')}

Remember: Your response should reflect your BCO (Belief-Conviction-Opinion) framework
and your CIOR (Certainty-Instinct Opinion Range) orientation.
Be consistent with your archetype but engage genuinely with opposing views."""

    def _build_user_prompt(
        self,
        agent: AgentNode,
        context: Dict[str, Any],
    ) -> str:
        """Build user prompt with debate context."""
        query = context.get("query", "")
        opponent_name = context.get("opponent_name", "the other participant")
        opponent_stance = context.get("opponent_stance", "unknown")
        opponent_belief = context.get("opponent_belief", "")
        history = context.get("history", [])
        round_num = context.get("round_num", 1)

        # Build conversation history string
        history_str = ""
        if history:
            recent = history[-6:]  # Last 6 turns
            history_lines = []
            for h in recent:
                history_lines.append(
                    f"- {h.get('agent_name', 'Unknown')}: {h.get('content', '')[:200]}"
                )
            history_str = "\n".join(history_lines)

        prompt = f"""DEBATE TOPIC: {query}

ROUND: {round_num}

You are responding to: {opponent_name}
Their stance: {opponent_stance}
Their belief: {opponent_belief}

CONVERSATION HISTORY:
{history_str if history_str else "(No previous turns)"}

Your task:
1. Respond to {opponent_name}'s perspective on the debate topic
2. Engage with their specific arguments (refer to them by name)
3. Present your own viewpoint based on your BCO framework
4. Show your CIOR orientation in how certain or uncertain you are

Respond with your perspective, referencing the other agent directly."""

        return prompt

    def _parse_response_stance(
        self,
        response: str,
        agent: AgentNode,
    ) -> tuple[str, float]:
        """Parse stance and confidence from agent response."""
        # Default to agent's programmed stance
        stance = self._get_stance_value(agent.stance)
        confidence = agent.confidence

        # Simple heuristics based on response content
        response_lower = response.lower()

        # Check for stance indicators
        if any(word in response_lower for word in ["support", "agree", "favor", "endorse", "positive"]):
            stance = "POSITIVE"
        elif any(word in response_lower for word in ["oppose", "disagree", "reject", "against", "negative"]):
            stance = "NEGATIVE"
        elif any(word in response_lower for word in ["neutral", "balanced", "both", "neither"]):
            stance = "NEUTRAL"

        # Confidence heuristics
        if any(word in response_lower for word in ["certain", "definitely", "clearly", "absolutely"]):
            confidence = min(1.0, confidence + 0.1)
        elif any(word in response_lower for word in ["maybe", "perhaps", "uncertain", "might", "could"]):
            confidence = max(0.0, confidence - 0.1)

        return stance, confidence

    def _extract_references(self, response: str) -> List[str]:
        """Extract agent references from response."""
        import re
        # Look for @mentions or quoted names
        mentions = re.findall(r'@(\w+)|"([^"]+)"|\'([^\']+)\'', response)
        refs = []
        for m in mentions:
            refs.extend([x for x in m if x])
        return refs[:5]  # Limit to 5 references

    def _check_convergence(self, round_turns: List[List[AgentTurn]]) -> bool:
        """
        Check if debate has converged.

        Convergence is detected when agent stances stabilize across rounds.

        Args:
            round_turns: List of turn lists, one per round.

        Returns:
            True if debate has converged.
        """
        if len(round_turns) < 2:
            return False

        # Group turns by agent
        agent_stances: Dict[str, List[str]] = {}
        for round_turns_list in round_turns:
            for turn in round_turns_list:
                if turn.agent_id not in agent_stances:
                    agent_stances[turn.agent_id] = []
                agent_stances[turn.agent_id].append(turn.stance)

        # Check if each agent's stance has stabilized
        stable_count = 0
        total_agents = len(agent_stances)

        for agent_id, stances in agent_stances.items():
            if len(stances) >= 2:
                # Check if last two stances are the same
                if stances[-1] == stances[-2]:
                    stable_count += 1
                # Also check overall consistency (all same)
                elif len(set(stances)) == 1:
                    stable_count += 1

        if total_agents == 0:
            return False

        stability_ratio = stable_count / total_agents
        return stability_ratio >= 0.8

    def _generate_verdict(
        self,
        rounds: List[RoundResult],
        agents: List[AgentNode],
    ) -> str:
        """Generate final verdict based on all rounds."""
        if not rounds:
            return "No debate occurred."

        # Count stance distribution
        stance_counts: Dict[str, int] = {}
        total_confidence = 0.0
        count = 0

        for round_result in rounds:
            for turn in round_result.turns:
                stance_counts[turn.stance] = stance_counts.get(turn.stance, 0) + 1
                total_confidence += turn.confidence
                count += 1

        if count == 0:
            return "No turns recorded."

        avg_confidence = total_confidence / count

        # Generate verdict summary
        dominant_stance = max(stance_counts, key=stance_counts.get)
        stance_pct = (stance_counts[dominant_stance] / count) * 100

        verdict = f"The debate concluded with {stance_pct:.0f}% of turns expressing {dominant_stance} stance. "
        verdict += f"Average agent confidence: {avg_confidence:.2f}. "

        if stance_pct >= 80:
            verdict += "There appears to be strong consensus on this topic."
        elif stance_pct >= 60:
            verdict += "A moderate consensus has emerged, though some disagreement remains."
        else:
            verdict += "The debate revealed diverse perspectives without clear consensus."

        return verdict

    # ---- Synthesis Methods ----

    def _cluster_opinions(self, results: List[AgentTurn]) -> Dict[Stance, List[AgentTurn]]:
        """
        Group agent responses by stance.

        Args:
            results: List of agent turns from debate.

        Returns:
            Dict mapping Stance to list of AgentTurns.
        """
        clusters: Dict[Stance, List[AgentTurn]] = {
            Stance.POSITIVE: [],
            Stance.NEGATIVE: [],
            Stance.NEUTRAL: [],
            Stance.AMBIVALENT: [],
        }
        for turn in results:
            try:
                stance = Stance(turn.stance) if isinstance(turn.stance, str) else turn.stance
            except ValueError:
                stance = Stance.NEUTRAL
            clusters[stance].append(turn)
        return clusters

    def _weight_by_relevance(
        self,
        clusters: Dict[Stance, List[AgentTurn]],
        agents: List[AgentNode],
    ) -> Dict[Stance, float]:
        """
        Weight each cluster by confidence × conviction.

        Higher conviction agents have more influence.

        Args:
            clusters: Opinion clusters from _cluster_opinions.
            agents: AgentNode instances for accessing conviction.

        Returns:
            Dict mapping Stance to aggregate weight.
        """
        agent_map = {str(a.id): a for a in agents}
        weights: Dict[Stance, float] = {s: 0.0 for s in Stance}

        for stance, turns in clusters.items():
            cluster_weight = 0.0
            for turn in turns:
                agent = agent_map.get(turn.agent_id)
                conviction = agent.conviction if agent else 0.5
                # weight = confidence × conviction
                cluster_weight += turn.confidence * conviction
            weights[stance] = cluster_weight

        return weights

    def _calibrate_cior(
        self,
        clusters: Dict[Stance, List[AgentTurn]],
        agents: List[AgentNode],
    ) -> Dict[Stance, float]:
        """
        Apply CIOR adjustment to weights.

        Gut instinct (CIOR=-1) weighted less than rational (CIOR=+1).
        Formula: weight = confidence × conviction × (1 + cior) / 2

        Args:
            clusters: Opinion clusters.
            agents: AgentNode instances for accessing cior.

        Returns:
            Dict mapping Stance to CIOR-adjusted weights.
        """
        agent_map = {str(a.id): a for a in agents}
        weights: Dict[Stance, float] = {s: 0.0 for s in Stance}

        for stance, turns in clusters.items():
            cluster_weight = 0.0
            for turn in turns:
                agent = agent_map.get(turn.agent_id)
                if agent:
                    # CIOR adjustment: (1 + cior) / 2 maps [-1, 1] to [0, 1]
                    cior_factor = (1 + agent.cior) / 2
                    cluster_weight += turn.confidence * agent.conviction * cior_factor
            weights[stance] = cluster_weight

        return weights

    def _generate_synthesis_verdict(
        self,
        rounds: List[RoundResult],
        agents: List[AgentNode],
    ) -> DebateVerdict:
        """
        Generate final verdict with weighted synthesis.

        Args:
            rounds: All debate rounds.
            agents: All participating agents.

        Returns:
            DebateVerdict with cluster analysis and verdict.
        """
        if not rounds:
            return DebateVerdict(
                overall_stance=Stance.NEUTRAL,
                confidence_score=0.0,
                supporting_entities=[],
                opposing_entities=[],
                summary="No debate occurred.",
                cluster_details={},
            )

        # Collect all turns
        all_turns: List[AgentTurn] = []
        for round_result in rounds:
            all_turns.extend(round_result.turns)

        if not all_turns:
            return DebateVerdict(
                overall_stance=Stance.NEUTRAL,
                confidence_score=0.0,
                supporting_entities=[],
                opposing_entities=[],
                summary="No turns recorded.",
                cluster_details={},
            )

        # Step 1: Cluster opinions
        clusters = self._cluster_opinions(all_turns)

        # Step 2: Build cluster summaries
        cluster_details: Dict[Stance, ClusterSummary] = {}
        for stance, turns in clusters.items():
            if not turns:
                continue
            agent_map = {str(a.id): a for a in agents}
            avg_conf = sum(t.confidence for t in turns) / len(turns)
            avg_conv = sum(
                agent_map.get(t.agent_id, MagicMock(conviction=0.5)).conviction
                for t in turns
            ) / len(turns)
            cluster_details[stance] = ClusterSummary(
                stance=stance,
                count=len(turns),
                total_weight=0.0,
                avg_confidence=avg_conf,
                avg_conviction=avg_conv,
                agents=[t.agent_name for t in turns],
            )

        # Step 3: Calculate CIOR-adjusted weights
        weights = self._calibrate_cior(clusters, agents)

        # Update cluster weights
        for stance in weights:
            if stance in cluster_details:
                cluster_details[stance] = ClusterSummary(
                    stance=stance,
                    count=cluster_details[stance].count,
                    total_weight=weights[stance],
                    avg_confidence=cluster_details[stance].avg_confidence,
                    avg_conviction=cluster_details[stance].avg_conviction,
                    agents=cluster_details[stance].agents,
                )

        # Step 4: Determine overall stance
        overall_stance = Stance.NEUTRAL
        max_weight = 0.0
        for stance, weight in weights.items():
            if weight > max_weight:
                max_weight = weight
                overall_stance = stance

        # Calculate confidence score
        total_weight = sum(weights.values())
        confidence_score = max_weight / total_weight if total_weight > 0 else 0.0

        # Collect supporting/opposing entities
        supporting = []
        opposing = []
        for turn in all_turns:
            try:
                turn_stance = Stance(turn.stance) if isinstance(turn.stance, str) else turn.stance
            except ValueError:
                turn_stance = Stance.NEUTRAL
            if turn_stance == overall_stance:
                supporting.extend(turn.references)
            else:
                opposing.extend(turn.references)

        # Generate summary
        dominant_pct = (cluster_details[overall_stance].count / len(all_turns) * 100
                        if overall_stance in cluster_details and all_turns else 0)
        summary = (
            f"The debate concluded with {dominant_pct:.0f}% of turns expressing "
            f"{overall_stance.value} stance. Confidence score: {confidence_score:.2f}."
        )

        return DebateVerdict(
            overall_stance=overall_stance,
            confidence_score=confidence_score,
            supporting_entities=list(set(supporting))[:10],
            opposing_entities=list(set(opposing))[:10],
            summary=summary,
            cluster_details=cluster_details,
        )


# ---- CLI Test ----

if __name__ == "__main__":
    import asyncio

    async def test():
        from src.persona.graph_context import GraphContext

        async with GraphContext() as ctx:
            engine = DebateEngine.from_graph_context(ctx, max_agents=5)
            config = DebateConfig(max_rounds=2, max_pairs_per_round=10)

            result = await engine.run_debate(
                query="What are the ethical implications of AI in healthcare?",
                config=config,
            )

            print(f"Debate on: {result.query}")
            print(f"Rounds: {len(result.rounds)}")
            print(f"Converged: {result.converged}")
            print(f"Verdict: {result.verdict}")
            print(f"Final stances: {result.final_stances}")
            if result.warnings:
                print(f"Warnings: {result.warnings}")

    asyncio.run(test())
