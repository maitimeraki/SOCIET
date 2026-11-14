"""ProfileSynthesizer: Graph-backed agent profile synthesis, seated by query relevance."""

import asyncio
import inspect
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import replace
from typing import Any

from src.persona.agent import SOURCE_EVIDENCE_MAX_SNIPPETS, Agent
from src.persona.graph_context import EntityNode, GraphContext
from src.persona.repository import PersonaRepository
from src.simulation.actor_filter import classify_actor_labels
from src.simulation.ranking import (
    Candidate,
    NoAgentsDerivableError,
    SeatDecision,
    SeatQueue,
    adjacency,
    percentile,
    personalized_pagerank,
    rrf_fuse,
)
from src.utils.queryIntend import QueryIntent

logger = logging.getLogger(__name__)

#: Fused chunks read per leg; the entities they mention form the candidate pool.
CHUNK_POOL = 200
#: Entity vector hits read; their similarity is percentile-ranked.
ENTITY_HITS = 100
#: Graph neighbours read per pool entity (PPR edges and evidence).
NEIGHBOURS_PER_SEED = 10
NO_COVERAGE_MESSAGE = "the graph does not cover this question"
_UNTYPED_LABELS = frozenset({"", "Entity", "__Entity__"})


def _type_label(node: EntityNode) -> str:
    """The entity's real type label, or "" when the graph carries none."""
    return "" if node.label in _UNTYPED_LABELS else node.label


def _embedding(node: EntityNode) -> tuple[float, ...]:
    """The entity's stored embedding, for the MMR diversity penalty; () when absent."""
    raw = node.properties.get("embedding")
    if isinstance(raw, (list, tuple)) and all(isinstance(x, (int, float)) for x in raw):
        return tuple(float(x) for x in raw)
    return ()


class ProfileSynthesizer:
    """Synthesizes canonical Agents from the graph's required nodes — one agent per node."""

    def __init__(self, persona_repo: PersonaRepository, graph_context: GraphContext):
        self._repo = persona_repo
        self._ctx = graph_context

    async def synthesize(
        self,
        query: str,
        dataset_id: str,
        max_agents: int = 5,
        intent: QueryIntent | None = None,
        warnings: list[str] | None = None,
        decisions: list[SeatDecision] | None = None,
        distill: bool = False,
        llm_client: Any = None,
        on_profile: "Callable[[Agent, int, int], Awaitable[None]] | None" = None,
    ) -> list[Agent]:
        """Synthesize agent profiles: seat the question's most relevant graph entities.

        `_seat` builds the candidate pool from the question's fused chunks and
        entity hits, scores it by query relevance, PageRank, grounding and the
        actor filter, and seats `max_agents` of it through `SeatQueue`. One Agent
        is then built per seat.

        Raises `NoAgentsDerivableError` when no candidate reaches the question. An
        empty roster is a failed job, not a debate with nobody in it.

        `warnings` is an optional caller-owned sink for degradations. `decisions`
        is an optional caller-owned sink for every candidate's seat decision.
        `llm_client` runs the actor filter; without it every entity type counts as
        an actor, and a warning says so.

        `distill=True` (the S5 gate, decided by the caller from the simulation
        depth) makes ONE batched distillation call for the whole seated set
        before any profile is built, feeding it the S3 stance axis; the returned
        `(description, perspective)` supplies that persona's
        `bio`/`detailed_perspective`, with a per-persona template fallback +
        warning. `False` (default) is exactly the pre-S5 path.
        """
        seats = await self._seat(
            query,
            dataset_id=dataset_id,
            max_agents=max_agents,
            warnings=warnings,
            llm_client=llm_client,
            decisions=decisions,
        )
        # Each seat's evidence is its node plus that node's one-hop neighbours. The
        # whole list reaches the build and the distillation.
        top_rows = [(candidate.name, evidence) for candidate, evidence in seats]

        # S5: ONE batched distillation call for the whole seated set — the S3
        # stance axis gives every persona a question-aware voice. Only runs when
        # the caller's depth gate asked for it; per-persona failures fall back to
        # the deterministic template and warn (never raise).
        distilled: dict[str, tuple[str, str]] = {}
        if distill:
            # T3: the persona's OWN chunk text — the grounding the EVIDENCE block
            # has been missing (entity nodes carry no `summary`). ONE call for the
            # whole batch, keyed by chunk id so each persona gets its own snippets
            # (R17). The fetch is deliberately uncapped in Cypher (R19): a global
            # cap over this persona-ordered union would let a chunk-heavy persona
            # starve the ones after it. `_own_source_snippets` caps each persona
            # instead. A roster with no chunk refs issues no query at all.
            batch_chunk_ids = list(
                dict.fromkeys(
                    chunk_id
                    for _, evidence in top_rows
                    for chunk_id in self._evidence_chunk_ids(evidence)
                )
            )
            snippets_by_chunk = (
                await self._repo.fetch_source_evidence_by_chunk(
                    batch_chunk_ids, dataset_id=dataset_id
                )
                if batch_chunk_ids
                else {}
            )
            distilled = await self._repo.distill_profiles(
                personas=[
                    self._distillation_entry(
                        name,
                        evidence,
                        self._own_source_snippets(evidence, snippets_by_chunk),
                    )
                    for name, evidence in top_rows
                ],
                query=query,
                core_question=intent.core_question if intent is not None else "",
                stance_axis=intent.stance_axis if intent is not None else "",
                warnings=warnings,
            )

        # Build one profile per required node
        # ONE batched node fetch serves every profile (was one query per profile).
        # The name list is the exact expression `_build_profile` resolves below,
        # so the pre-fetch cannot diverge from the per-profile lookups; a name
        # with no row keeps the node-properties fallback.
        nodes_by_name = await self._repo.fetch_nodes_by_names(
            [name for name, _ in top_rows], dataset_id=dataset_id
        )
        profiles: list[Agent] = []
        semaphore = asyncio.Semaphore(8)

        async def _build_profile(
            row_name: str, evidence: list[EntityNode]
        ) -> Agent | None:
            async with semaphore:
                # Use the most relevant entity in the evidence as representative
                representative = max(evidence, key=lambda e: e.relevance_score)
                agent_name = representative.name

                # Full node properties, served by the roster's single batch fetch.
                node = nodes_by_name.get(agent_name) or {
                    "name": agent_name,
                    **representative.properties,
                }
                # The entity's real type label is the build's archetype fallback;
                # properties alone never carry it.
                node = {**node, "label": representative.label}

                # Calculate metrics using repo method
                # For node-level synthesis, we construct synthetic sector_results
                sector_results = self._build_sector_results(evidence)

                max_relevance = (
                    max(e.relevance_score for e in evidence) if evidence else 1.0
                )

                metrics = await self._repo.calculate_agent_metrics_and_context_for_llm(
                    agent_name=agent_name,
                    node=node,
                    sector_results=sector_results,
                    max_relevance=max_relevance,
                    dataset_id=dataset_id,
                )

                # Task 1: the same `_effective_stance` precedence the build uses
                # (distilled → graph derivation → safe default) decides the value
                # persisted with the entity links, because Task 6's round-1
                # pairing reads `Persona.stance` before any opinion exists — the
                # persisted stance must equal the built Agent's.
                distilled_for_row = distilled.get(row_name) if distilled else None
                stance_to_persist = PersonaRepository._effective_stance(
                    node, metrics, distilled_for_row
                )[0].value

                # D2: write this persona's real provenance edges BEFORE the build,
                # so the `get_provenance` inside it finds them instead of falling
                # back to the uuid5 sector fabrication. Never raises into synthesis.
                chunk_ids = self._evidence_chunk_ids(evidence)
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
                            "provenance write failed for persona %r: %s",
                            agent_name,
                            exc,
                        )
                        if warnings is not None:
                            warnings.append(
                                f"provenance write failed for persona {agent_name!r} ({type(exc).__name__})"
                            )

                    # Topology prerequisite: without persona→entity links the
                    # round-1 pair scorer has no shared middle nodes to count.
                    try:
                        pending = self._repo.write_persona_entity_links(
                            persona_name=agent_name,
                            dataset_id=dataset_id,
                            chunk_node_ids=chunk_ids,
                            stance=stance_to_persist,
                        )
                        if inspect.iscoroutine(pending):
                            await pending
                    except Exception as exc:
                        logger.warning(
                            "entity-link write failed for persona %r: %s",
                            agent_name,
                            exc,
                        )
                        if warnings is not None:
                            warnings.append(
                                f"entity-link write failed for persona {agent_name!r} ({type(exc).__name__})"
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
                    distilled=distilled_for_row,
                    chunk_node_ids=chunk_ids,
                )

        # S9 visibility: one `agent` event per completed profile, in completion
        # order — the roster seats members one by one as they are built.
        completed = 0
        completed_lock = asyncio.Lock()

        async def _build_and_notify(
            name: str, entity_evidence: list[EntityNode]
        ) -> Agent | None:
            nonlocal completed
            profile = await _build_profile(name, entity_evidence)
            if profile is not None and on_profile is not None:
                async with completed_lock:
                    completed += 1
                    index = completed
                try:
                    await on_profile(profile, index, len(top_rows))
                except Exception as exc:
                    logger.warning(
                        "on_profile emitter failed for %r: %s",
                        profile.identity.name,
                        exc,
                    )
            return profile

        tasks = [
            _build_and_notify(name, entity_evidence) for name, entity_evidence in top_rows
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
        the same repository pipeline as query-driven synthesis.
        Joiners are deliberately **not** distilled (no mid-loop LLM calls), so
        they keep the template bio/perspective. Their identity is still derived
        from the graph rather than a hollow constant: `fetch_nodes_by_names`
        carries the node's real type label, so the build applies the same Task 5
        archetype/style/domain precedence the roster gets. They also get the
        same D2 provenance write as the initial roster when their node carries a
        `triplet_source_id`, with the same log-and-continue tolerance.
        """
        if not names:
            return []
        relevant = {str(k): float(v) for k, v in (relevance_by_name or {}).items()}
        # ONE batched node fetch for every joiner (was one query per name); the
        # per-name map keeps the same build-or-skip handling below.
        nodes_by_name = await self._repo.fetch_nodes_by_names(
            names, dataset_id=dataset_id
        )
        semaphore = asyncio.Semaphore(8)

        async def _build(name: str) -> Agent | None:
            async with semaphore:
                node = nodes_by_name.get(name)
                if node is None:
                    # No graph node backs this name. Skipping beats fabricating a
                    # default-archetype/-stance/-cior Agent from the bare string.
                    logger.warning(
                        "synthesize_from_names: %r has no graph node; skipped", name
                    )
                    return None
                if name not in relevant:
                    logger.warning(
                        "synthesize_from_names: %r has no relevance; skipped", name
                    )
                    return None
                relevance = max(0.05, min(1.0, relevant[name]))
                domain_tags = (
                    node.get("domain_tags")
                    if isinstance(node, dict)
                    else getattr(node, "domain_tags", []) or []
                )
                first_tag = (domain_tags[0] if domain_tags else None) or "general"
                sector_results = [
                    {
                        "domain_tag": first_tag,
                        "total_relevance": relevance,
                        "evidence_nodes": [name],
                        "density": 1,
                    }
                ]
                metrics = await self._repo.calculate_agent_metrics_and_context_for_llm(
                    agent_name=name,
                    node=node,
                    sector_results=sector_results,
                    max_relevance=1.0,
                    dataset_id=dataset_id,
                )

                # D2 on the activation path: write the joiner's real provenance
                # edge BEFORE the build (which reads it), tolerantly — a failed
                # write is logged and the profile still builds.
                chunk_id = (
                    node.get("triplet_source_id")
                    if isinstance(node, dict)
                    else getattr(node, "triplet_source_id", None)
                )
                chunk_ids = (
                    [chunk_id.strip()]
                    if isinstance(chunk_id, str) and chunk_id.strip()
                    else []
                )
                if chunk_ids:
                    try:
                        pending = self._repo.write_persona_provenance(
                            persona_name=name,
                            dataset_id=dataset_id,
                            chunk_node_ids=chunk_ids,
                        )
                        if inspect.iscoroutine(pending):
                            await pending
                    except Exception as exc:
                        logger.warning(
                            "provenance write failed for joiner %r: %s",
                            name,
                            exc,
                        )

                    # Same topology prerequisite as the initial roster: joiners
                    # need entity links or they can never pair either.
                    try:
                        pending = self._repo.write_persona_entity_links(
                            persona_name=name,
                            dataset_id=dataset_id,
                            chunk_node_ids=chunk_ids,
                        )
                        if inspect.iscoroutine(pending):
                            await pending
                    except Exception as exc:
                        logger.warning(
                            "entity-link write failed for joiner %r: %s",
                            name,
                            exc,
                        )

                return await self._repo.build_single_agent_profile_from_node(
                    agent_name=name,
                    node=node,
                    user_query=query,
                    dataset_id=dataset_id,
                    agent_metrics=metrics,
                    sector_results=sector_results,
                    llm_output=None,
                    chunk_node_ids=chunk_ids,
                )

        results = await asyncio.gather(*(_build(n) for n in names))
        return [p for p in results if p is not None]

    async def _subgraph_by_seed(
        self, nodes: list[EntityNode], dataset_id: str, limit: int
    ) -> dict[str, list[EntityNode]]:
        """Each node's 1-hop entity neighbours, keyed by node id — ONE query for
        the whole roster. A missing method, a raising fetch or a non-mapping
        answer degrades to no neighbours — logged, never raised.
        """
        fetch = getattr(self._ctx, "find_connected_nodes_by_seed", None)
        if not callable(fetch):
            return {}
        try:
            grouped = fetch(
                [node.id for node in nodes], dataset_id=dataset_id, limit=limit
            )
            if inspect.iscoroutine(grouped):
                grouped = await grouped
        except Exception as exc:
            logger.warning(
                "subgraph fetch failed; grounding personas on their own nodes only: %s",
                exc,
            )
            return {}
        return grouped if isinstance(grouped, Mapping) else {}

    async def _seat(
        self,
        query: str,
        dataset_id: str,
        max_agents: int,
        warnings: list[str] | None,
        llm_client: Any,
        decisions: list[SeatDecision] | None,
    ) -> list[tuple[Candidate, list[EntityNode]]]:
        """Seat up to `max_agents` candidates for the question, best first.

        The pool is the entities the top fused chunks mention plus the entity
        vector hits. Query relevance is the best fused chunk mentioning an entity;
        PageRank spreads it over the graph. `SeatQueue` accepts each draw at once,
        so the profile build that follows is the only step after seating.
        """
        search = await self._ctx.find_relevant_chunks(
            query, dataset_id=dataset_id, limit=CHUNK_POOL
        )
        chunk_hits = {hit.chunk_id: hit for hit in [*search.vector, *search.fulltext]}
        fused = rrf_fuse(
            [[hit.chunk_id for hit in search.vector], [hit.chunk_id for hit in search.fulltext]]
        )
        top_chunks = sorted(fused, key=lambda chunk_id: (-fused[chunk_id], chunk_id))[:CHUNK_POOL]
        peak = fused[top_chunks[0]] if top_chunks else 0.0

        query_relevance: dict[str, float] = {}
        chunk_count: dict[str, int] = defaultdict(int)
        doc_ids: dict[str, set[str]] = defaultdict(set)
        for chunk_id in top_chunks:
            hit = chunk_hits[chunk_id]
            for entity_id in hit.entity_ids:
                relevance = fused[chunk_id] / peak
                query_relevance[entity_id] = max(query_relevance.get(entity_id, 0.0), relevance)
                chunk_count[entity_id] += 1
                doc_ids[entity_id].add(hit.doc_id)

        entity_hits = await self._ctx.find_relevant_entities(
            query, dataset_id=dataset_id, limit=ENTITY_HITS
        )
        hit_by_id = {entity.id: entity for entity in entity_hits}
        similarity_population = [entity.relevance_score for entity in entity_hits]

        pool_ids = sorted(set(query_relevance) | set(hit_by_id))
        unfetched = [entity_id for entity_id in pool_ids if entity_id not in hit_by_id]
        fetched = (
            await self._ctx.find_entities_by_ids(unfetched, dataset_id=dataset_id)
            if unfetched
            else []
        )
        nodes = {entity.id: entity for entity in fetched}
        nodes.update(hit_by_id)
        pool = [nodes[entity_id] for entity_id in pool_ids if entity_id in nodes]
        if not any(query_relevance.get(node.id, 0.0) > 0 for node in pool):
            raise NoAgentsDerivableError(NO_COVERAGE_MESSAGE)

        neighbours = await self._subgraph_by_seed(
            pool, dataset_id=dataset_id, limit=NEIGHBOURS_PER_SEED
        )
        edges = [(node.id, n.id) for node in pool for n in neighbours.get(node.id, [])]
        seeds = {
            node.id: query_relevance[node.id]
            for node in pool
            if query_relevance.get(node.id, 0.0) > 0
        }
        ppr = personalized_pagerank(adjacency(edges), seeds)

        candidates = [
            Candidate(
                entity_id=node.id,
                name=node.name,
                type_label=_type_label(node),
                query_relevance=query_relevance.get(node.id, 0.0),
                entity_similarity=(
                    percentile(node.relevance_score, similarity_population)
                    if node.id in hit_by_id
                    else 0.0
                ),
                ppr=ppr.get(node.id, 0.0),
                doc_count=len(doc_ids.get(node.id, ())),
                chunk_count=chunk_count.get(node.id, 0),
                evidence_count=chunk_count.get(node.id, 0) + len(neighbours.get(node.id, [])),
                vector=_embedding(node),
            )
            for node in pool
        ]
        candidates = await self._classify_actors(candidates, llm_client, warnings)

        queue = SeatQueue(candidates, n=max_agents)
        seats: list[tuple[Candidate, list[EntityNode]]] = []
        while (drawn := queue.next()) is not None:
            queue.accept(drawn)
            node = nodes[drawn.entity_id]
            seats.append((drawn, [node, *neighbours.get(node.id, [])]))
        if decisions is not None:
            decisions.extend(queue.decisions())
        return seats

    async def _classify_actors(
        self,
        candidates: list[Candidate],
        llm_client: Any,
        warnings: list[str] | None,
    ) -> list[Candidate]:
        """Mark each candidate actor or not, by its entity type label, in one call.

        Without an LLM client every type counts as an actor, and the warning says
        so. A candidate with no type label keeps the actor default.
        """
        labels = sorted({c.type_label for c in candidates if c.type_label})
        if not labels:
            return candidates
        if llm_client is None:
            if warnings is not None:
                warnings.append(
                    "actor filter skipped: no LLM client, every entity type counts as an actor"
                )
            return candidates
        flags, degraded = await classify_actor_labels(llm_client, labels)
        if degraded and warnings is not None:
            warnings.append(
                "actor filter: unclassified entity types count as actors"
            )
        return [replace(c, is_actor=flags.get(c.type_label, True)) for c in candidates]

    @staticmethod
    def _own_source_snippets(
        evidence: list[EntityNode], snippets_by_chunk: Mapping[str, list[str]]
    ) -> list[str]:
        """This persona's own snippets, in its evidence's chunk order, capped.

        Reading only the chunks this persona's evidence names is what keeps one
        persona's source text out of another's distillation.
        """
        if not isinstance(snippets_by_chunk, Mapping):
            return []
        return [
            snippet
            for chunk_id in ProfileSynthesizer._evidence_chunk_ids(evidence)
            for snippet in (snippets_by_chunk.get(chunk_id) or [])
        ][:SOURCE_EVIDENCE_MAX_SNIPPETS]

    def _distillation_entry(
        self,
        name: str,
        evidence: list[EntityNode],
        source_snippets: list[str] | None = None,
    ) -> dict:
        """One persona's S5 distillation input: identity and the grounding synthesis
        already holds (the persona's real source snippets, node properties,
        matched sectors, node summaries). No extra graph reads — the entry is
        name-keyed, the same key profiles build under.
        """
        representative = (
            max(evidence, key=lambda e: e.relevance_score) if evidence else None
        )
        properties = (
            getattr(representative, "properties", None)
            if representative is not None
            else None
        )
        summaries = [
            e.summary.strip()
            for e in evidence
            if isinstance(getattr(e, "summary", None), str) and e.summary.strip()
        ]
        return {
            "name": name,
            "node": dict(properties) if isinstance(properties, dict) else {},
            "sector_results": self._build_sector_results(evidence),
            "evidence": list(source_snippets or []) + summaries,
        }

    @staticmethod
    def _evidence_chunk_ids(evidence: list[EntityNode]) -> list[str]:
        """The evidence's chunk node ids: each entity's `triplet_source_id`.

        Tolerant `Mapping` reads — a non-mapping `properties` or a missing/blank
        value contributes nothing; ids are stripped and deduped. Never invents.
        """
        ids: list[str] = []
        for entity in evidence:
            properties = getattr(entity, "properties", None)
            if not isinstance(properties, Mapping):
                continue
            value = properties.get("triplet_source_id")
            if isinstance(value, str) and value.strip():
                ids.append(value.strip())
        return list(dict.fromkeys(ids))

    def _build_sector_results(self, evidence: list[EntityNode]) -> list[dict[str, Any]]:
        """Build synthetic sector_results from one node's evidence."""
        if not evidence:
            return []

        # Use the top entity's domain tags as the sector
        primary = evidence[0]
        domain_tag = primary.domain_tags[0] if primary.domain_tags else primary.label

        # Collect all unique agent names from the evidence
        evidence_nodes = [e.name for e in evidence if e.name]
        total_relevance = sum(e.relevance_score for e in evidence)
        density = len(evidence)

        return [
            {
                "domain_tag": domain_tag,
                "total_relevance": total_relevance,
                "evidence_nodes": evidence_nodes,
                "density": density,
            }
        ]
