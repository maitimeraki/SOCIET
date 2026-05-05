from typing import Optional
from src.persona.repository import PersonaRepository
from src.persona.models_persona import AgentProfile, PersonaIdentity, ConfidenceBreakdown, ProvenanceLink
from uuid import uuid4


class PersonaFetcher:
    """Lightweight facade around PersonaRepository to provide per-turn persona contexts.

    The GraphAgent expects `get_persona_context(agent_name, user_query)` to
    return an `AgentProfile` instance suitable for prompt construction.
    """

    def __init__(self, repo: PersonaRepository, agent_name: Optional[str] = None):
        self.repo = repo
        self.agent_name = agent_name

    async def get_persona_context(self, agent_name: str, user_query: str) -> AgentProfile:
        # try to build a rich profile using repository helpers
        try:
            node = await self.repo.fetch_agent_node_props(agent_name) or {"name": agent_name} # Get properties of the agent node, fallback to minimal dict if not found
            # compute lightweight metrics (no sector results in per-turn fetch)
            metrics = await self.repo._calculate_agent_metrics(agent_name, node, sector_results=[], max_relevance=None)
            profile = await self.repo._build_single_agent_profile_from_node(
                agent_name=agent_name,
                node=node,
                user_query=user_query,
                dataset_id=None,  # dataset_id is not relevant for per-turn context, set to None
                agent_metrics=metrics,
                sector_results=[],
                llm_output={},
            )
            return profile
        except Exception:
            # graceful fallback: synthesize minimal AgentProfile
            identity = PersonaIdentity(name=agent_name, archetype="Unknown", communication_style="strategic and factual")
            cb = ConfidenceBreakdown(source_breadth=0, node_density=0, relationship_connectivity=0.0)
            prov = [ProvenanceLink(doc_id="runtime", title="runtime", breadcrumb="", chunk_id=uuid4())]
            return AgentProfile(
                discovery_type="graph_discovery",
                expertise_level="Strategic",
                identity=identity,
                domain_tags=["unknown"],
                description=f"{agent_name} (unspecified)",
                detailed_perspective=f"I am {agent_name}. No persona data available.",
                confidence=0.5,
                confidence_breakdown=cb,
                provenance=prov,
            )
