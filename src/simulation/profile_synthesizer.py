"""ProfileSynthesizer: Graph-backed agent profile synthesis from entity clusters."""
import asyncio
import inspect
import logging
import math
from collections import defaultdict
from collections.abc import Mapping
from typing import Any

from src.persona.agent import Agent
from src.persona.graph_context import GraphContext, EntityNode
from src.persona.repository import PersonaRepository
from src.simulation.debate_config import DebateConfig
from src.simulation.relevance_matrix import (
    NoAgentsDerivableError,
    SelectionCandidate,
    SelectionRow,
    rank_candidates,
)
from src.utils.queryIntend import QueryIntent

logger = logging.getLogger(__name__)


class ProfileSynthesizer:
    """Synthesizes canonical Agents from graph entity clusters."""

    def __init__(self, persona_repo: PersonaRepository, graph_context: GraphContext):
        self._repo = persona_repo
        self._ctx = graph_context

    async def _safe_provenance(self, entity_id: str) -> list:
        """Fetch entity provenance; tolerate unconfigured/mocked contexts."""
        try:
            if hasattr(self._ctx, "get_provenance"):
                result = self._ctx.get_provenance(entity_id)
                if inspect.iscoroutine(result):
                    result = await result
                return list(result) if isinstance(result, (list, tuple)) else []
        except Exception:
            return []
        return []

    async def synthesize(
        self,
        query: str,
        dataset_id: str,
        max_agents: int = 5,
        intent: QueryIntent | None = None,
        config: DebateConfig | None = None,
        warnings: list[str] | None = None,
        selection_rows: list[SelectionRow] | None = None,
        distill: bool = False,
    ) -> list[Agent]:
        """Synthesize agent profiles from relevant graph entities.

        1. Vector-search entities by query
        2. Group entities by shared chunk provenance (co-occurrence clustering)
        3. Rank clusters by the S4 score (intent-semantic + density blend); with
           no intent this is exactly the previous density-only ordering
        4. Take top clusters (adaptive count)
        5. Build Agent for each cluster representative

        `intent` is the read-only S3 intent (None for older callers); `config`
        carries the S4 blend weights. Raises `NoAgentsDerivableError` when the
        graph yields no candidate at all — an empty roster is a failed job, not
        a debate with nobody in it.

        `warnings` and `selection_rows` are optional caller-owned sinks the S4
        degradation message and the full ranked decomposition (all rows, best
        first — not just the ones cut into agents) are written to, so the run
        result can explain the roster (S9).

        `distill=True` (the S5 gate, decided by the caller from the simulation
        depth) makes ONE batched distillation call for the whole selection set
        before any profile is built, feeding it the S3 stance axis and each
        persona's S4 anchors; the returned `(description, perspective)` supplies
        that persona's `bio`/`detailed_perspective`, with a per-persona template
        fallback + warning. `False` (default) is exactly the pre-S5 path.
        """
        # Adaptive target: sqrt(n) * 4, capped at max_agents
        search_limit = max_agents * 3
        entities = await self._ctx.find_relevant_entities(query, limit=search_limit)
        relevant_entity_count = len(entities)
        target = min(max_agents, int(math.sqrt(relevant_entity_count) * 4))

        if not entities:
            raise NoAgentsDerivableError(
                f"no agents derivable from graph: no candidate entities for query {query!r} "
                f"in dataset {dataset_id!r}"
            )

        # Co-occurrence clustering: entities sharing source chunks cluster together.
        # Provenance fetch bounded by search_limit = max_agents * 3.
        prov_keys: list[tuple] = []
        for entity in entities:
            prov = await self._safe_provenance(entity.id)
            doc_ids = sorted({p.doc_id for p in prov if getattr(p, "doc_id", None)})
            if doc_ids:
                prov_keys.append(tuple(doc_ids))
            else:
                # Empty provenance → unique key (preserves one-cluster-per-entity path).
                prov_keys.append(("__solo__", entity.id))

        initial: dict[tuple, list[EntityNode]] = defaultdict(list)
        for entity, key in zip(entities, prov_keys):
            initial[key].append(entity)

        # Merge clusters sharing any doc_id.
        # ponytail: O(n^2) pairwise union-find; n bounded by max_agents * 3 ≤ 50.
        key_list = list(initial.keys())
        parent = {i: i for i in range(len(key_list))}

        def _find(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        for i in range(len(key_list)):
            if "__solo__" in key_list[i]:
                continue
            set_i = set(key_list[i])
            for j in range(i + 1, len(key_list)):
                if "__solo__" in key_list[j]:
                    continue
                if set_i & set(key_list[j]):
                    ri, rj = _find(i), _find(j)
                    if ri != rj:
                        parent[ri] = rj

        clusters: dict[int, list[EntityNode]] = defaultdict(list)
        for i, key in enumerate(key_list):
            clusters[_find(i)].extend(initial[key])

        # S4: rank clusters by the intent-semantic + density blend. No intent →
        # no terms → density-only ordering, which reproduces the previous
        # `sort(key=sum(relevance_score), reverse=True)` exactly (the density
        # component is a monotonic scaling of that sum and the sort is stable).
        candidates = [
            SelectionCandidate(
                name=max(ents, key=lambda e: e.relevance_score).name,
                text=self._candidate_text(ents),
                evidence=ents,
            )
            for ents in clusters.values()
        ]
        rows = rank_candidates(candidates, intent, config or DebateConfig(), warnings=warnings)
        if selection_rows is not None:
            selection_rows.extend(rows)
        # Pair each ranked row with its own cluster — candidates and clusters are
        # positionally aligned (built by the same comprehension), so a name-keyed
        # collapse is never needed: each row consumes its cluster from a per-name
        # bucket in rank order, and two clusters whose representative entities
        # share a name both survive (P2-A m1).
        clusters_by_name: dict[str, list[list[EntityNode]]] = defaultdict(list)
        for candidate, ents in zip(candidates, clusters.values()):
            clusters_by_name[candidate.name].append(ents)
        top_clusters = [
            (row, clusters_by_name[row.name].pop(0)) for row in rows[:target]
        ]

        # S5: ONE batched distillation call for the whole selection set — the S3
        # stance axis plus each row's anchors give every persona a question-aware
        # voice. Only runs when the caller's depth gate asked for it; per-persona
        # failures fall back to the deterministic template and warn (never raise).
        distilled: dict[str, tuple[str, str]] = {}
        if distill:
            distilled = await self._repo.distill_profiles(
                personas=[
                    self._distillation_entry(row, cluster_entities)
                    for row, cluster_entities in top_clusters
                ],
                query=query,
                core_question=intent.core_question if intent is not None else "",
                stance_axis=intent.stance_axis if intent is not None else "",
                warnings=warnings,
            )

        # Build profiles for each cluster
        profiles: list[Agent] = []
        semaphore = asyncio.Semaphore(8)

        async def _build_profile(
            cluster_id: str, cluster_entities: list[EntityNode]
        ) -> Agent | None:
            async with semaphore:
                # Use the most relevant entity in the cluster as representative
                representative = max(cluster_entities, key=lambda e: e.relevance_score)
                agent_name = representative.name

                # Fetch full node properties
                nodes_map = await self._repo.fetch_nodes_by_names([agent_name])
                node = nodes_map.get(agent_name) or {
                    "name": agent_name,
                    **representative.properties,
                }

                # Calculate metrics using repo method
                # For cluster-based synthesis, we construct synthetic sector_results
                sector_results = self._build_sector_results_from_cluster(cluster_entities)

                max_relevance = max(
                    e.relevance_score for e in cluster_entities
                ) if cluster_entities else 1.0

                metrics = await self._repo.calculate_agent_metrics_and_context_for_llm(
                    agent_name=agent_name,
                    node=node,
                    sector_results=sector_results,
                    max_relevance=max_relevance,
                )

                # D2: write this persona's real provenance edges BEFORE the build,
                # so the `get_provenance` inside it finds them instead of falling
                # back to the uuid5 sector fabrication. Never raises into synthesis.
                chunk_ids = self._cluster_chunk_ids(cluster_entities)
                if chunk_ids:
                    try:
                        pending = self._repo.write_persona_provenance(
                            persona_name=agent_name,
                            dataset_id=dataset_id,
                            chunk_node_ids=chunk_ids,
                        )
                        if inspect.iscoroutine(pending):
                            await pending
                    except Exception as exc:
                        logger.warning(
                            "provenance write failed for persona %r: %s", agent_name, exc,
                        )
                        if warnings is not None:
                            warnings.append(
                                f"provenance write failed for persona {agent_name!r}: {exc}"
                            )

                # Build profile
                return await self._repo.build_single_agent_profile_from_node(
                    agent_name=agent_name,
                    node=node,
                    user_query=query,
                    dataset_id=dataset_id,
                    agent_metrics=metrics,
                    sector_results=sector_results,
                    llm_output=None,
                    distilled=distilled.get(cluster_id) if distilled else None,
                )

        # Process clusters in parallel
        tasks = [
            _build_profile(row.name, cluster_entities)
            for row, cluster_entities in top_clusters
        ]
        results = await asyncio.gather(*tasks)
        profiles = [p for p in results if p is not None]

        return profiles

    async def synthesize_from_names(
        self,
        names: list[str],
        query: str,
        dataset_id: str,
        relevance_by_name: dict[str, float] | None = None,
    ) -> list[Agent]:
        """Build full Agent profiles for explicitly-named graph Personas.

        Activation path: candidates surfaced by topology are converted through
        the same repository pipeline as query-driven synthesis, minus clustering.
        Joiners are deliberately **not** distilled (no mid-loop LLM calls), so
        they keep the template bio/perspective; they do get the same D2
        provenance write as the initial roster when their node carries a
        `triplet_source_id`, with the same log-and-continue tolerance.
        """
        if not names:
            return []
        relevant = {str(k): float(v) for k, v in (relevance_by_name or {}).items()}
        semaphore = asyncio.Semaphore(8)

        async def _build(name: str) -> Agent | None:
            async with semaphore:
                nodes_map = await self._repo.fetch_nodes_by_names([name])
                node = nodes_map.get(name)
                if node is None:
                    # No graph node backs this name. Skipping beats fabricating a
                    # default-archetype/-stance/-cior Agent from the bare string.
                    logger.warning("synthesize_from_names: %r has no graph node; skipped", name)
                    return None
                relevance = max(0.05, min(1.0, relevant.get(name, 0.33)))
                domain_tags = node.get("domain_tags") if isinstance(node, dict) else getattr(node, "domain_tags", []) or []
                first_tag = (domain_tags[0] if domain_tags else None) or "general"
                sector_results = [{
                    "domain_tag": first_tag,
                    "total_relevance": relevance,
                    "evidence_nodes": [name],
                    "density": 1,
                }]
                metrics = await self._repo.calculate_agent_metrics_and_context_for_llm(
                    agent_name=name, node=node, sector_results=sector_results, max_relevance=1.0,
                )

                # D2 on the activation path: write the joiner's real provenance
                # edge BEFORE the build (which reads it), tolerantly — a failed
                # write is logged and the profile still builds.
                chunk_id = (
                    node.get("triplet_source_id") if isinstance(node, dict)
                    else getattr(node, "triplet_source_id", None)
                )
                if isinstance(chunk_id, str) and chunk_id.strip():
                    try:
                        pending = self._repo.write_persona_provenance(
                            persona_name=name,
                            dataset_id=dataset_id,
                            chunk_node_ids=[chunk_id.strip()],
                        )
                        if inspect.iscoroutine(pending):
                            await pending
                    except Exception as exc:
                        logger.warning(
                            "provenance write failed for joiner %r: %s", name, exc,
                        )

                return await self._repo.build_single_agent_profile_from_node(
                    agent_name=name, node=node, user_query=query, dataset_id=dataset_id,
                    agent_metrics=metrics, sector_results=sector_results, llm_output=None,
                )

        results = await asyncio.gather(*(_build(n) for n in names))
        return [p for p in results if p is not None]

    def _distillation_entry(self, row: SelectionRow, cluster_entities: list[EntityNode]) -> dict:
        """One persona's S5 distillation input: identity, the grounding synthesis
        already holds (node properties, matched sectors, cluster summaries) and
        the S4 provenance anchors of its selection row. No extra graph reads —
        the entry is name-keyed by `row.name`, the same key profiles build under.
        """
        representative = (
            max(cluster_entities, key=lambda e: e.relevance_score) if cluster_entities else None
        )
        properties = getattr(representative, "properties", None) if representative is not None else None
        summaries = [
            e.summary.strip()
            for e in cluster_entities
            if isinstance(getattr(e, "summary", None), str) and e.summary.strip()
        ]
        return {
            "name": row.name,
            "node": dict(properties) if isinstance(properties, dict) else {},
            "sector_results": self._build_sector_results_from_cluster(cluster_entities),
            "evidence": summaries,
            "anchors": [dict(anchor) for anchor in row.anchors],
        }

    @staticmethod
    def _candidate_text(cluster_entities: list[EntityNode]) -> str:
        """The S4 semantic text of a cluster: its entities' names, domain tags and summaries."""
        parts: list[str] = []
        for entity in cluster_entities:
            parts.append(str(getattr(entity, "name", "") or ""))
            parts.extend(str(tag) for tag in (getattr(entity, "domain_tags", None) or []))
            parts.append(str(getattr(entity, "summary", "") or ""))
        return " ".join(part for part in parts if part)

    @staticmethod
    def _cluster_chunk_ids(cluster_entities: list[EntityNode]) -> list[str]:
        """The cluster's chunk node ids: each entity's `triplet_source_id`.

        Tolerant `Mapping` reads — a non-mapping `properties` or a missing/blank
        value contributes nothing; ids are stripped and deduped. Never invents.
        """
        ids: list[str] = []
        for entity in cluster_entities:
            properties = getattr(entity, "properties", None)
            if not isinstance(properties, Mapping):
                continue
            value = properties.get("triplet_source_id")
            if isinstance(value, str) and value.strip():
                ids.append(value.strip())
        return list(dict.fromkeys(ids))

    def _build_sector_results_from_cluster(
        self, cluster_entities: list[EntityNode]
    ) -> list[dict[str, Any]]:
        """Build synthetic sector_results from a cluster of entities."""
        if not cluster_entities:
            return []

        # Use the top entity's domain tags as the sector
        primary = cluster_entities[0]
        domain_tag = primary.domain_tags[0] if primary.domain_tags else primary.label

        # Collect all unique agent names from cluster
        evidence_nodes = [e.name for e in cluster_entities if e.name]
        total_relevance = sum(e.relevance_score for e in cluster_entities)
        density = len(cluster_entities)

        return [
            {
                "domain_tag": domain_tag,
                "total_relevance": total_relevance,
                "evidence_nodes": evidence_nodes,
                "density": density,
            }
        ]
