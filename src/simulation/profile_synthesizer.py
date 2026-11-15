"""ProfileSynthesizer: seat the question's most relevant graph entities, then generate one cited profile each.

Sequential: one candidate is drawn, its profile is generated and validated, and only then is the next
candidate drawn. A failed profile is rejected and frees its seat for the next draw; nothing is written
in its place.
"""

import hashlib
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from typing import Any
from uuid import uuid4

from src.llm.config_llm import get_llm_config
from src.persona.agent import Agent, DiscoveryType, PersonaIdentity, Stance
from src.persona.graph_context import EntityNode, GraphContext
from src.persona.repository import PersonaRepository
from src.simulation.actor_filter import classify_actor_labels
from src.simulation.agent_record import (
    AgentRecord,
    CiteIds,
    GenerationInfo,
    NodeInfo,
    RankInfo,
    RejectedClaim,
    UniquenessInfo,
    ValidationInfo,
    dossier_hash,
)
from src.simulation.evidence import (
    MAX_RELATIONS,
    ChunkRow,
    EvidencePack,
    RelationItem,
    build_pack,
)
from src.simulation.profile_generator import (
    PROFILE_PROMPT_VERSION,
    PROFILE_TEMPERATURE,
    GenerationResult,
    generate_profile,
)
from src.simulation.profile_validation import ProfileDraft
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
#: Graph neighbours read per pool entity (PPR edges), strongest first.
NEIGHBOURS_PER_SEED = 25
#: Neighbours that count as a candidate's evidence and reach its pack's relations.
#: evidence_count counts these capped neighbours, not the pack's own items (which build_pack caps at 12).
NEIGHBOUR_CAP = 5
NO_COVERAGE_MESSAGE = "the graph does not cover this question"
_UNTYPED_LABELS = frozenset({"", "Entity", "__Entity__"})


def _type_label(node: EntityNode) -> str:
    """The entity's real type label, or "" when the graph carries none."""
    return "" if node.label in _UNTYPED_LABELS else node.label


def _aliases(node: EntityNode) -> list[str]:
    raw = node.properties.get("aliases")
    if not isinstance(raw, (list, tuple)):
        return []
    return [str(alias).strip() for alias in raw if str(alias).strip()]


def _distinct_by_id(entities: list[EntityNode], own_id: str) -> list[EntityNode]:
    """Neighbours once each by entity id, the node itself left out.

    An entity whose id equals its name arrives under both keys of a grouped read.
    """
    seen: set[str] = {own_id}
    distinct: list[EntityNode] = []
    for entity in entities:
        if entity.id not in seen:
            seen.add(entity.id)
            distinct.append(entity)
    return distinct


def _embedding(node: EntityNode) -> tuple[float, ...]:
    """The entity's stored embedding, for the MMR diversity penalty; () when absent."""
    raw = node.properties.get("embedding")
    if isinstance(raw, (list, tuple)) and all(isinstance(x, (int, float)) for x in raw):
        return tuple(float(x) for x in raw)
    return ()


@dataclass
class _Pool:
    """The ranked candidates and the per-entity inputs a profile pack is built from."""

    candidates: list[Candidate]
    nodes: dict[str, EntityNode]
    neighbours: dict[str, list[EntityNode]]
    chunk_rows: dict[str, list[ChunkRow]]


@dataclass(frozen=True)
class _Attempt:
    """One drawn candidate's pass through generation: its pack, its result, and the seated Agent if any."""

    candidate: Candidate
    axis: str
    aliases: list[str]
    pack: EvidencePack
    generated: GenerationResult
    agent: Agent | None


def _rejection_reason(generated: GenerationResult) -> str:
    fields = ", ".join(sorted({r.field for r in generated.rejections})) or "no draft"
    return f"profile not seated ({fields})"


class ProfileSynthesizer:
    """Synthesizes canonical Agents: one seated, generated and validated profile per seat."""

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
        records: list[AgentRecord] | None = None,
        llm_client: Any = None,
        on_profile: "Callable[[Agent, int, int], Awaitable[None]] | None" = None,
    ) -> list[Agent]:
        """Seat up to `max_agents` candidates for the question and generate one profile per seat.

        Each drawn candidate gets a pack of its own chunks and relations, one generation
        call and a support judge. A profile that fails is rejected and its seat is redrawn.

        Raises `NoAgentsDerivableError` when no candidate reaches the question, or when every
        drawn candidate's profile failed. An empty roster with nothing drawn returns [].

        `records`, `decisions` and `warnings` are caller-owned sinks. `records` holds one
        AgentRecord for every candidate that reached generation, published or rejected.
        """
        if llm_client is None:
            raise ValueError("profile generation needs an llm_client")
        pool = await self._rank(query, dataset_id, warnings, llm_client)
        if not any(c.vector for c in pool.candidates):
            logger.info("MMR diversity penalty off: no entity embeddings in the candidate pool")

        queue = SeatQueue(pool.candidates, n=max_agents)
        axis = intent.stance_axis if intent is not None else ""
        run_id = uuid4().hex
        attempts: list[_Attempt] = []
        seated: list[Agent] = []
        while (drawn := queue.next()) is not None:
            resolved = False
            try:
                attempt = await self._attempt(drawn, pool, query, axis, dataset_id, llm_client)
                attempts.append(attempt)
                if attempt.agent is None:
                    queue.reject(drawn, _rejection_reason(attempt.generated))
                else:
                    queue.accept(drawn)
                resolved = True
            finally:
                if not resolved:
                    queue.reject(drawn, "generation interrupted")
            if attempt.agent is None:
                continue
            agent = attempt.agent
            seated.append(agent)
            await self._persist_links(agent, dataset_id, warnings)
            await self._notify(on_profile, agent, len(seated), max_agents)

        if decisions is not None:
            decisions.extend(queue.decisions())
        if records is not None:
            by_id = {d.entity_id: d for d in queue.decisions()}
            records.extend(self._record(run_id, query, a, by_id[a.candidate.entity_id]) for a in attempts)
        if attempts and not seated:
            raise NoAgentsDerivableError(
                "no profile could be seated: every drawn candidate failed profile generation or validation"
            )
        return seated

    async def synthesize_from_names(
        self,
        names: list[str],
        query: str,
        dataset_id: str,
        relevance_by_name: dict[str, float] | None = None,
    ) -> list[Agent]:
        """Joiner seating for activation. Not built yet.

        A joiner has to pass the same seat, generate and validate path as a roster member.
        That is task 2.6b. Until then this refuses rather than build a template Agent.
        """
        if not names:
            return []
        raise NotImplementedError(
            "joiner seating lands in task 2.6b: activation cannot seat a generated profile yet"
        )

    async def _rank(
        self,
        query: str,
        dataset_id: str,
        warnings: list[str] | None,
        llm_client: Any,
    ) -> _Pool:
        """Build and rank the candidate pool for the question. Raises when none reaches it."""
        search = await self._ctx.find_relevant_chunks(query, dataset_id=dataset_id, limit=CHUNK_POOL)
        chunk_hits = {hit.chunk_id: hit for hit in [*search.vector, *search.fulltext]}
        fused = rrf_fuse(
            [[hit.chunk_id for hit in search.vector], [hit.chunk_id for hit in search.fulltext]]
        )
        top_chunks = sorted(fused, key=lambda chunk_id: (-fused[chunk_id], chunk_id))[:CHUNK_POOL]
        peak = fused[top_chunks[0]] if top_chunks else 0.0

        query_relevance: dict[str, float] = {}
        chunk_count: dict[str, int] = defaultdict(int)
        doc_ids: dict[str, set[str]] = defaultdict(set)
        chunk_rows: dict[str, list[ChunkRow]] = defaultdict(list)
        for chunk_id in top_chunks:
            hit = chunk_hits[chunk_id]
            relevance = fused[chunk_id] / peak
            for entity_id in hit.entity_ids:
                query_relevance[entity_id] = max(query_relevance.get(entity_id, 0.0), relevance)
                chunk_count[entity_id] += 1
                doc_ids[entity_id].add(hit.doc_id)
                chunk_rows[entity_id].append(
                    ChunkRow(hit.chunk_id, hit.doc_id, hit.doc_title, hit.section, hit.text, fused[chunk_id])
                )

        entity_hits = await self._ctx.find_relevant_entities(query, dataset_id=dataset_id, limit=ENTITY_HITS)
        hit_by_id = {entity.id: entity for entity in entity_hits}
        similarity_population = [entity.relevance_score for entity in entity_hits]

        pool_ids = sorted(set(query_relevance) | set(hit_by_id))
        unfetched = [entity_id for entity_id in pool_ids if entity_id not in hit_by_id]
        fetched = (
            await self._ctx.find_entities_by_ids(unfetched, dataset_id=dataset_id) if unfetched else []
        )
        nodes = {entity.id: entity for entity in fetched}
        nodes.update(hit_by_id)
        pool = [nodes[entity_id] for entity_id in pool_ids if entity_id in nodes]
        if not any(query_relevance.get(node.id, 0.0) > 0 for node in pool):
            raise NoAgentsDerivableError(NO_COVERAGE_MESSAGE)

        grouped = await self._ctx.find_connected_nodes_by_seed(
            [node.id for node in pool], dataset_id=dataset_id, limit=NEIGHBOURS_PER_SEED
        )
        neighbours = {node.id: _distinct_by_id(grouped.get(node.id, []), node.id) for node in pool}
        # Undirected, one edge per pair: a pool-to-pool edge arrives from both ends.
        edges = sorted({tuple(sorted((node.id, n.id))) for node in pool for n in neighbours[node.id]})
        seeds = {node.id: query_relevance[node.id] for node in pool if query_relevance.get(node.id, 0.0) > 0}
        ppr = personalized_pagerank(adjacency(edges), seeds)

        candidates = [
            Candidate(
                entity_id=node.id,
                name=node.name,
                type_label=_type_label(node),
                query_relevance=query_relevance.get(node.id, 0.0),
                entity_similarity=(
                    percentile(node.relevance_score, similarity_population) if node.id in hit_by_id else 0.0
                ),
                ppr=ppr.get(node.id, 0.0),
                doc_count=len(doc_ids.get(node.id, ())),
                chunk_count=chunk_count.get(node.id, 0),
                evidence_count=chunk_count.get(node.id, 0) + len(neighbours[node.id][:NEIGHBOUR_CAP]),
                vector=_embedding(node),
            )
            for node in pool
        ]
        candidates = await self._classify_actors(candidates, llm_client, warnings)
        return _Pool(
            candidates=candidates,
            nodes=nodes,
            neighbours=neighbours,
            chunk_rows={entity_id: list(rows) for entity_id, rows in chunk_rows.items()},
        )

    async def _classify_actors(
        self,
        candidates: list[Candidate],
        llm_client: Any,
        warnings: list[str] | None,
    ) -> list[Candidate]:
        """Mark each candidate actor or not, by its entity type label, in one call.

        A candidate with no type label keeps the actor default.
        """
        labels = sorted({c.type_label for c in candidates if c.type_label})
        if not labels:
            return candidates
        flags, degraded = await classify_actor_labels(llm_client, labels)
        if degraded and warnings is not None:
            warnings.append("actor filter: unclassified entity types count as actors")
        return [replace(c, is_actor=flags.get(c.type_label, True)) for c in candidates]

    async def _attempt(
        self,
        drawn: Candidate,
        pool: _Pool,
        query: str,
        axis: str,
        dataset_id: str,
        llm_client: Any,
    ) -> _Attempt:
        """Build the drawn candidate's pack, generate its profile, and seat an Agent if it passes."""
        node = pool.nodes[drawn.entity_id]
        aliases = _aliases(node)
        counterpart_ids = [n.id for n in pool.neighbours[drawn.entity_id][:NEIGHBOUR_CAP]]
        relations = await self._relations_for(drawn.entity_id, counterpart_ids, dataset_id)
        pack = build_pack(drawn.name, aliases, pool.chunk_rows.get(drawn.entity_id, []), relations)
        generated = await generate_profile(
            llm_client,
            question=query,
            axis=axis,
            name=drawn.name,
            aliases=aliases,
            type_label=drawn.type_label,
            pack=pack,
        )
        agent = (
            self._agent(drawn, dataset_id, generated.draft, pack) if generated.draft is not None else None
        )
        return _Attempt(drawn, axis, aliases, pack, generated, agent)

    async def _relations_for(
        self, entity_id: str, counterpart_ids: list[str], dataset_id: str
    ) -> list[RelationItem]:
        """Scoped relations from the candidate to its capped neighbours; the pack keeps MAX_RELATIONS."""
        if not counterpart_ids:
            return []
        hits = await self._ctx.find_relations_for(
            entity_id, counterpart_ids, dataset_id=dataset_id, limit=MAX_RELATIONS
        )
        return [
            RelationItem(
                "",
                hit.type,
                "out" if hit.outgoing else "in",
                hit.counterpart_id,
                hit.counterpart_name,
                hit.chunk_id,
            )
            for hit in hits
        ]

    @staticmethod
    def _agent(drawn: Candidate, dataset_id: str, draft: ProfileDraft, pack: EvidencePack) -> Agent:
        """The slim Agent for a validated draft. Only the draft and the pack are read."""
        return Agent(
            node_id=drawn.entity_id,
            dataset_id=dataset_id,
            identity=PersonaIdentity(
                name=drawn.name,
                archetype="",
                communication_style="",
                type_label=drawn.type_label,
            ),
            discovery_type=DiscoveryType.GRAPH_DISCOVERY,
            role=draft.role,
            stance=Stance.parse(draft.stance),
            strength=draft.strength,
            confidence=draft.confidence,
            bio=draft.bio,
            details_raw=draft.details,
            evidence=list(pack.items),
            relations=list(pack.relations),
            cites=dict(draft.cites),
        )

    async def _persist_links(self, agent: Agent, dataset_id: str, warnings: list[str] | None) -> None:
        """Write the seated persona's provenance and entity links, which the topology reads.

        A failed write is logged and warned, never raised: the profile is already seated.
        """
        name = agent.identity.name
        chunk_ids = list(dict.fromkeys(item.chunk_id for item in agent.evidence))
        if not chunk_ids:
            return
        writes = (
            ("provenance", lambda: self._repo.write_persona_provenance(
                persona_name=name, dataset_id=dataset_id, chunk_node_ids=chunk_ids)),
            ("entity-link", lambda: self._repo.write_persona_entity_links(
                persona_name=name, dataset_id=dataset_id, chunk_node_ids=chunk_ids,
                stance=agent.stance.value)),
        )
        for label, write in writes:
            try:
                await write()
            except Exception as exc:
                logger.warning("%s write failed for persona %r: %s", label, name, exc)
                if warnings is not None:
                    warnings.append(f"{label} write failed for persona {name!r} ({type(exc).__name__})")

    @staticmethod
    async def _notify(
        on_profile: "Callable[[Agent, int, int], Awaitable[None]] | None",
        agent: Agent,
        index: int,
        total: int,
    ) -> None:
        if on_profile is None:
            return
        try:
            await on_profile(agent, index, total)
        except Exception as exc:
            logger.warning("on_profile emitter failed for %r: %s", agent.identity.name, exc)

    @staticmethod
    def _record(run_id: str, query: str, attempt: _Attempt, decision: SeatDecision) -> AgentRecord:
        """The backend-only record of one candidate's attempt. Never sent to a client."""
        draft = attempt.generated.draft
        rejections = attempt.generated.rejections
        candidate = attempt.candidate
        return AgentRecord(
            run_id=run_id,
            node_id=candidate.entity_id,
            query_hash=hashlib.sha256(query.encode("utf-8")).hexdigest(),
            question=query,
            decision_axis=attempt.axis,
            node=NodeInfo(
                name=candidate.name,
                aliases=attempt.aliases,
                type_label=candidate.type_label or None,
                type_source="graph" if candidate.type_label else "unknown",
            ),
            rank=RankInfo(
                features=decision.features,
                score=decision.score,
                seated=decision.seated,
                reason=decision.reason,
                order=decision.order,
            ),
            evidence=list(attempt.pack.items),
            relations=list(attempt.pack.relations),
            view=attempt.agent.view() if attempt.agent is not None else None,
            details_raw=draft.details if draft is not None else "",
            cites=CiteIds(**{k: v for k, v in (draft.cites if draft else {}).items() if k in CiteIds.model_fields}),
            validation=ValidationInfo(
                json_ok=not any(r.field == "json" for r in rejections),
                repairs=max(0, attempt.generated.attempts - 1),
                rejected=[RejectedClaim(field=r.field, reason=r.reason) for r in rejections],
                details_chars=len(draft.details) if draft is not None else 0,
                cites_valid=draft is not None,
            ),
            uniqueness=UniquenessInfo(),
            generation=GenerationInfo(
                model=attempt.generated.model,
                prompt_version=PROFILE_PROMPT_VERSION,
                temperature=PROFILE_TEMPERATURE,
                attempts=max(1, attempt.generated.attempts),
                latency_ms=attempt.generated.latency_ms,
            ),
            dossier_hash=dossier_hash(attempt.pack, get_llm_config()),
            status="published" if attempt.agent is not None else "rejected",
            reason=None if attempt.agent is not None else decision.reason,
        )
