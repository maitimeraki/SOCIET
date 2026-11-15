"""ProfileSynthesizer: seat the question's most relevant graph entities, then generate one cited profile each.

Candidates are drawn in batches of `llm_concurrency`. A batch's profiles are generated concurrently,
then resolved in draw order, so the seat order does not depend on which call finishes first. A
failed profile is rejected and frees its seat for the next batch. Once the roster is full, any two
seated profiles that are too alike are settled: the later one is regenerated once against the earlier
one's claims, and unseated if it is still too alike.
"""

import asyncio
import hashlib
import logging
import math
from collections import defaultdict
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, replace
from typing import Any
from uuid import uuid4

from src.billing.metering import MeteringError
from src.llm.config_llm import get_llm_config
from src.persona.agent import Agent, PersonaIdentity, Stance
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
from src.simulation.debate_config import DebateConfig
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
from src.simulation.profile_validation import (
    ProfileDraft,
    UniquenessReport,
    check_uniqueness,
    split_sentences,
    strip_markers,
)
from src.simulation.ranking import (
    Candidate,
    NoAgentsDerivableError,
    SeatDecision,
    SeatQueue,
    adjacency,
    percentile,
    personalized_pagerank,
    rrf_fuse,
    score,
)
from src.utils.queryIntend import QueryIntent

logger = logging.getLogger(__name__)

#: Fused chunks read per leg; the entities they mention form the candidate pool.
CHUNK_POOL = 200
#: Entity vector hits read; their similarity is percentile-ranked.
ENTITY_HITS = 100
#: Graph neighbours read per pool entity (PPR edges), strongest first.
NEIGHBOURS_PER_SEED = 25
#: Draws beyond the seat count that a run may make: bounds the profile calls, since a rejected draw costs calls.
DRAW_SLACK = 2
#: Candidates the pool keeps, best first: bounds the actor-classification calls per run.
POOL_CAP = 300
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


def _usable_vector(vector: tuple[float, ...]) -> bool:
    """A bio vector the uniqueness check can trust: configured width, finite, non-zero."""
    return (
        len(vector) == get_llm_config().embedding_dimensions
        and all(math.isfinite(x) for x in vector)
        and any(x != 0.0 for x in vector)
    )


@dataclass(frozen=True)
class _ChunkEvidence:
    """What the question's chunks say about each entity: relevance, counts, and the rows a pack is built from."""

    query_relevance: dict[str, float]
    chunk_count: dict[str, int]
    doc_ids: dict[str, set[str]]
    chunk_rows: dict[str, list[ChunkRow]]


def _candidate(
    node: EntityNode,
    evidence: _ChunkEvidence,
    neighbours: list[EntityNode],
    *,
    similarity: float,
    ppr: float,
) -> Candidate:
    chunks = evidence.chunk_count.get(node.id, 0)
    return Candidate(
        entity_id=node.id,
        name=node.name,
        type_label=_type_label(node),
        query_relevance=evidence.query_relevance.get(node.id, 0.0),
        entity_similarity=similarity,
        ppr=ppr,
        doc_count=len(evidence.doc_ids.get(node.id, ())),
        chunk_count=chunks,
        evidence_count=chunks + len(neighbours[:NEIGHBOUR_CAP]),
        vector=_embedding(node),
    )


@dataclass
class _Pool:
    """The ranked candidates and the per-entity inputs a profile pack is built from."""

    candidates: list[Candidate]
    nodes: dict[str, EntityNode]
    neighbours: dict[str, list[EntityNode]]
    chunk_rows: dict[str, list[ChunkRow]]


@dataclass(frozen=True)
class _Run:
    """What every profile call in one synthesis shares."""

    query: str
    dataset_id: str
    axis: str
    llm_client: Any


@dataclass(frozen=True)
class _Attempt:
    """One generation for a drawn candidate: its pack, its result, and the seated Agent if it passed.

    `rejected_reason` is "" when the attempt produced an Agent.
    """

    candidate: Candidate
    axis: str
    aliases: list[str]
    pack: EvidencePack
    generated: GenerationResult
    agent: Agent | None
    vector: tuple[float, ...]
    rejected_reason: str


@dataclass
class _Seat:
    """A seated profile. `regenerated` is set once its one uniqueness regeneration has been spent."""

    candidate: Candidate
    attempt: _Attempt
    regenerated: bool = False

    @property
    def agent(self) -> Agent:
        if self.attempt.agent is None:
            raise RuntimeError("a seat always holds an agent")
        return self.attempt.agent


def _rejection_reason(generated: GenerationResult) -> str:
    fields = ", ".join(sorted({r.field for r in generated.rejections})) or "no draft"
    return f"profile not seated ({fields})"


async def _gather_in_order(awaitables: Sequence[Awaitable[_Attempt]]) -> list[_Attempt]:
    """Run one batch concurrently and return the results in input order.

    A MeteringError from any member is raised as soon as it completes, whatever failed before it;
    the rest of the batch is cancelled. Otherwise the batch settles and the first failure in draw
    order is raised. Either way no call outlives the batch.
    """
    # A generic failure does not cancel its siblings: the batch settles, so a run that is already
    # doomed can still spend calls. That spend is bounded by the draw cap (DRAW_SLACK).
    tasks = [asyncio.ensure_future(awaitable) for awaitable in awaitables]
    pending = set(tasks)
    try:
        while pending:
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                if not task.cancelled() and isinstance(task.exception(), MeteringError):
                    raise task.exception()
        failures = [task.exception() for task in tasks if not task.cancelled() and task.exception() is not None]
        if failures:
            raise failures[0]
        return [task.result() for task in tasks]
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


Entry = tuple[ProfileDraft, tuple[float, ...]]


def _entries(fixed: Sequence[Entry], seats: Sequence["_Seat"]) -> list[Entry]:
    """Roster entries for the uniqueness check: the fixed roster members first, then the seats."""
    return [*fixed, *((seat.attempt.generated.draft, seat.attempt.vector) for seat in seats)]


def _uniqueness(seats: Sequence["_Seat"], fixed: Sequence[Entry] = ()) -> UniquenessReport:
    """The uniqueness report over the fixed roster and the seats. Entries are keyed by their index."""
    entries = _entries(fixed, seats)
    return check_uniqueness(
        {str(i): draft for i, (draft, _) in enumerate(entries)},
        {str(i): vector for i, (_, vector) in enumerate(entries)},
    )


def _duplicate_pairs(seats: Sequence["_Seat"], fixed: Sequence[Entry] = ()) -> list[tuple[int, int]]:
    """Index pairs (earlier, later) of too-alike entries that involve a seat, earliest first.

    The fixed roster precedes every seat, so a pair's later entry is a seat. Two fixed members
    are never settled here: the roster was settled before the joiners were seated.
    """
    report = _uniqueness(seats, fixed)
    pairs = [(min(int(a), int(b)), max(int(a), int(b))) for a, b in report.failing_pairs]
    return sorted(pair for pair in pairs if pair[1] >= len(fixed))


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
        llm_concurrency: int | None = None,
    ) -> list[Agent]:
        """Seat up to `max_agents` candidates for the question and generate one profile per seat.

        Each drawn candidate gets a pack of its own chunks and relations, one generation
        call and a support judge. A profile that fails is rejected and its seat is redrawn.
        Profiles are generated `llm_concurrency` at a time. Draws stop at `max_agents +
        DRAW_SLACK`, which bounds the profile calls. Duplicate profiles are settled before
        anything is persisted or emitted.

        Raises `NoAgentsDerivableError` when no candidate reaches the question, or when no
        profile could be seated. An empty roster with nothing drawn returns [].

        `records`, `decisions` and `warnings` are caller-owned sinks. `records` holds one
        AgentRecord per candidate that reached generation, published or rejected.
        """
        if llm_client is None:
            raise ValueError("profile generation needs an llm_client")
        width = llm_concurrency or DebateConfig().llm_concurrency
        pool = await self._rank(query, dataset_id, warnings, llm_client)
        if not any(c.vector for c in pool.candidates):
            logger.info("MMR diversity penalty off: no entity embeddings in the candidate pool")

        run = _Run(query, dataset_id, intent.stance_axis if intent is not None else "", llm_client)
        queue = SeatQueue(pool.candidates, n=max_agents, max_draws=max_agents + DRAW_SLACK)
        latest: dict[str, _Attempt] = {}
        seats = await self._roster(queue, pool, run, width, latest, fixed=())

        for index, seat in enumerate(seats, start=1):
            await self._persist_links(seat.agent, dataset_id, warnings)
            await self._notify(on_profile, seat.agent, index, len(seats))

        if decisions is not None:
            decisions.extend(queue.decisions())
        if records is not None:
            self._emit_records(records, queue, query, latest, seats)
        if latest and not seats:
            raise NoAgentsDerivableError(
                "no profile could be seated (every drawn candidate was rejected)"
            )
        return [seat.agent for seat in seats]

    async def synthesize_from_names(
        self,
        names: list[str],
        query: str,
        dataset_id: str,
        relevance_by_name: dict[str, float] | None = None,
        *,
        roster: Sequence[Agent] = (),
        intent: QueryIntent | None = None,
        warnings: list[str] | None = None,
        llm_client: Any = None,
        llm_concurrency: int | None = None,
        records: list[AgentRecord] | None = None,
        seat_offset: int = 0,
    ) -> list[Agent]:
        """Seat the activation joiners named in `names`, through the same path as a roster member.

        Each joiner is drawn, generated, validated and checked for uniqueness against the roster
        and the other joiners. Only a joiner is ever regenerated or unseated: a roster member is
        fixed. A joiner that cannot be seated is absent from the result; the caller warns.

        `records` is the caller-owned sink for one AgentRecord per joiner that reached generation,
        seated or rejected. `seat_offset` is the number of agents already seated, so a seated
        joiner's record carries the next contiguous seat number.
        """
        wanted = list(dict.fromkeys(names))
        if not wanted:
            return []
        if llm_client is None:
            raise ValueError("joiner seating needs an llm_client")
        width = llm_concurrency or DebateConfig().llm_concurrency
        fixed = [await self._fixed_entry(agent) for agent in roster]
        pool = await self._joiner_pool(wanted, query, dataset_id, relevance_by_name or {}, warnings, llm_client)
        run = _Run(query, dataset_id, intent.stance_axis if intent is not None else "", llm_client)
        queue = SeatQueue(pool.candidates, n=len(wanted), max_draws=len(wanted) + DRAW_SLACK)
        latest: dict[str, _Attempt] = {}
        seats = await self._roster(queue, pool, run, width, latest, fixed=fixed)
        for seat in seats:
            await self._persist_links(seat.agent, dataset_id, warnings)
        if records is not None:
            self._emit_records(records, queue, query, latest, seats, seat_offset)
        return [seat.agent for seat in seats]

    async def _fixed_entry(self, agent: Agent) -> Entry:
        """A roster member as a fixed uniqueness entry. Its bio must embed usably: otherwise the joiners cannot be checked."""
        draft = ProfileDraft.model_construct(
            role=agent.role,
            stance=agent.stance.value.lower(),
            strength=agent.strength,
            bio=agent.bio,
            details=agent.details_raw,
            confidence=agent.confidence,
            cites=dict(agent.cites),
        )
        vector = await self._embed(agent.bio)
        if not _usable_vector(vector):
            raise ValueError("roster bio embedding unusable: joiners cannot be checked for uniqueness")
        return draft, vector

    async def _embed(self, text: str) -> tuple[float, ...]:
        return tuple(float(x) for x in await self._ctx._get_embedding(text))

    async def _roster(
        self,
        queue: SeatQueue,
        pool: _Pool,
        run: _Run,
        width: int,
        latest: dict[str, _Attempt],
        fixed: Sequence[Entry],
    ) -> list[_Seat]:
        """Fill the seats, settle duplicates, and refill any seat a duplicate freed, until the roster is unique."""
        seats: list[_Seat] = []
        while True:
            await self._fill(queue, pool, run, width, seats, latest)
            if not await self._deduplicate(queue, run, seats, latest, fixed):
                return seats

    async def _fill(
        self,
        queue: SeatQueue,
        pool: _Pool,
        run: _Run,
        width: int,
        seats: list[_Seat],
        latest: dict[str, _Attempt],
    ) -> None:
        while batch := queue.draw(width):
            await self._seat_batch(queue, batch, pool, run, seats, latest)

    async def _seat_batch(
        self,
        queue: SeatQueue,
        batch: list[Candidate],
        pool: _Pool,
        run: _Run,
        seats: list[_Seat],
        latest: dict[str, _Attempt],
    ) -> None:
        """Generate one batch concurrently, then resolve every draw in draw order.

        Every draw is resolved exactly once: accepted or rejected here, or rejected in the
        finally when the batch is interrupted.
        """
        resolved: set[str] = set()
        try:
            attempts = await _gather_in_order([self._attempt(c, pool, run) for c in batch])
            for drawn, attempt in zip(batch, attempts):
                latest[drawn.entity_id] = attempt
                if attempt.agent is None:
                    queue.reject(drawn, attempt.rejected_reason)
                else:
                    queue.accept(drawn)
                    seats.append(_Seat(drawn, attempt))
                resolved.add(drawn.entity_id)
        finally:
            for drawn in batch:
                if drawn.entity_id not in resolved:
                    queue.reject(drawn, "generation interrupted")

    async def _deduplicate(
        self,
        queue: SeatQueue,
        run: _Run,
        seats: list[_Seat],
        latest: dict[str, _Attempt],
        fixed: Sequence[Entry],
    ) -> bool:
        """Settle every too-alike pair that involves a seat: regenerate the later seat once, then unseat it if still too alike.

        Returns True when a seat was freed and the roster needs refilling.
        """
        freed = False
        while pairs := _duplicate_pairs(seats, fixed):
            entries = _entries(fixed, seats)
            earlier_index, later_index = pairs[0]
            earlier = entries[earlier_index][0]
            later = seats[later_index - len(fixed)]
            if later.regenerated:
                self._unseat(queue, seats, later, "too alike to a seated profile")
                freed = True
            else:
                later.regenerated = True
                taken = split_sentences(strip_markers(earlier.details))
                prior = later.attempt
                attempt = await self._generate(prior.candidate, prior.aliases, prior.pack, run, taken=taken)
                latest[later.candidate.entity_id] = attempt
                if attempt.agent is None:
                    self._unseat(queue, seats, later, attempt.rejected_reason)
                    freed = True
                else:
                    later.attempt = attempt
        return freed

    @staticmethod
    def _unseat(queue: SeatQueue, seats: list[_Seat], seat: _Seat, reason: str) -> None:
        queue.unseat(seat.candidate, reason)
        seats[:] = [s for s in seats if s is not seat]

    async def _rank(
        self,
        query: str,
        dataset_id: str,
        warnings: list[str] | None,
        llm_client: Any,
    ) -> _Pool:
        """Build and rank the candidate pool for the question. Raises when none reaches it."""
        evidence = await self._chunk_evidence(query, dataset_id)
        entity_hits = await self._ctx.find_relevant_entities(query, dataset_id=dataset_id, limit=ENTITY_HITS)
        hit_by_id = {entity.id: entity for entity in entity_hits}
        similarity_population = [entity.relevance_score for entity in entity_hits]

        pool_ids = sorted(set(evidence.query_relevance) | set(hit_by_id))
        unfetched = [entity_id for entity_id in pool_ids if entity_id not in hit_by_id]
        fetched = (
            await self._ctx.find_entities_by_ids(unfetched, dataset_id=dataset_id) if unfetched else []
        )
        nodes = {entity.id: entity for entity in fetched}
        nodes.update(hit_by_id)
        pool = [nodes[entity_id] for entity_id in pool_ids if entity_id in nodes]
        if not any(evidence.query_relevance.get(node.id, 0.0) > 0 for node in pool):
            raise NoAgentsDerivableError(NO_COVERAGE_MESSAGE)

        grouped = await self._ctx.find_connected_nodes_by_seed(
            [node.id for node in pool], dataset_id=dataset_id, limit=NEIGHBOURS_PER_SEED
        )
        neighbours = {node.id: _distinct_by_id(grouped.get(node.id, []), node.id) for node in pool}
        # Undirected, one edge per pair: a pool-to-pool edge arrives from both ends.
        edges = sorted({tuple(sorted((node.id, n.id))) for node in pool for n in neighbours[node.id]})
        seeds = {
            node.id: evidence.query_relevance[node.id]
            for node in pool
            if evidence.query_relevance.get(node.id, 0.0) > 0
        }
        ppr = personalized_pagerank(adjacency(edges), seeds)

        candidates = [
            _candidate(
                node,
                evidence,
                neighbours[node.id],
                similarity=(
                    percentile(node.relevance_score, similarity_population) if node.id in hit_by_id else 0.0
                ),
                ppr=ppr.get(node.id, 0.0),
            )
            for node in pool
        ]
        ranked = sorted(candidates, key=lambda c: (-score(c), c.name, c.entity_id))
        if len(ranked) > POOL_CAP:
            logger.info("candidate pool capped: kept %d of %d candidates", POOL_CAP, len(ranked))
        candidates = ranked[:POOL_CAP]
        candidates = await self._classify_actors(candidates, llm_client, warnings)
        return _Pool(candidates=candidates, nodes=nodes, neighbours=neighbours, chunk_rows=evidence.chunk_rows)

    async def _joiner_pool(
        self,
        names: list[str],
        query: str,
        dataset_id: str,
        relevance_by_name: dict[str, float],
        warnings: list[str] | None,
        llm_client: Any,
    ) -> _Pool:
        """The activation joiners as candidates: their own chunks, capped neighbours and actor flag.

        Activation's shared-entity share stands in for the PPR score the question pool has.
        """
        nodes = {node.id: node for node in await self._ctx.find_entities_by_names(names, dataset_id=dataset_id)}
        evidence = await self._chunk_evidence(query, dataset_id)
        grouped = (
            await self._ctx.find_connected_nodes_by_seed(
                sorted(nodes), dataset_id=dataset_id, limit=NEIGHBOURS_PER_SEED
            )
            if nodes
            else {}
        )
        neighbours = {entity_id: _distinct_by_id(grouped.get(entity_id, []), entity_id) for entity_id in nodes}
        candidates = [
            _candidate(node, evidence, neighbours[node.id], similarity=0.0, ppr=relevance_by_name.get(node.name, 0.0))
            for node in nodes.values()
        ]
        candidates = await self._classify_actors(candidates, llm_client, warnings)
        return _Pool(candidates=candidates, nodes=nodes, neighbours=neighbours, chunk_rows=evidence.chunk_rows)

    async def _chunk_evidence(self, query: str, dataset_id: str) -> _ChunkEvidence:
        """Per-entity evidence from the question's fused top chunks: relevance, counts and the rows a pack is built from."""
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
        return _ChunkEvidence(
            query_relevance=query_relevance,
            chunk_count=dict(chunk_count),
            doc_ids=dict(doc_ids),
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

    async def _attempt(self, drawn: Candidate, pool: _Pool, run: _Run) -> _Attempt:
        """Build the drawn candidate's pack and generate its profile."""
        node = pool.nodes[drawn.entity_id]
        aliases = _aliases(node)
        counterpart_ids = [n.id for n in pool.neighbours[drawn.entity_id][:NEIGHBOUR_CAP]]
        relations = await self._relations_for(drawn.entity_id, counterpart_ids, run.dataset_id)
        pack = build_pack(drawn.name, aliases, pool.chunk_rows.get(drawn.entity_id, []), relations)
        return await self._generate(drawn, aliases, pack, run)

    async def _generate(
        self,
        drawn: Candidate,
        aliases: list[str],
        pack: EvidencePack,
        run: _Run,
        taken: Sequence[str] = (),
    ) -> _Attempt:
        """One generation for a candidate. It seats an Agent only if the draft passes and its bio embeds."""
        generated = await generate_profile(
            run.llm_client,
            question=run.query,
            axis=run.axis,
            name=drawn.name,
            aliases=aliases,
            type_label=drawn.type_label,
            pack=pack,
            taken=taken,
        )
        if generated.draft is None:
            return _Attempt(drawn, run.axis, aliases, pack, generated, None, (), _rejection_reason(generated))
        agent = self._agent(drawn, run.dataset_id, generated.draft, pack)
        vector = await self._embed(agent.bio)
        if not _usable_vector(vector):
            return _Attempt(drawn, run.axis, aliases, pack, generated, None, (), "bio embedding unusable")
        return _Attempt(drawn, run.axis, aliases, pack, generated, agent, vector, "")

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
            identity=PersonaIdentity(name=drawn.name, type_label=drawn.type_label),
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
                    warnings.append(f"{label} write failed")

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

    @classmethod
    def _emit_records(
        cls,
        sink: list[AgentRecord],
        queue: SeatQueue,
        query: str,
        latest: dict[str, _Attempt],
        seats: list[_Seat],
        seat_offset: int = 0,
    ) -> None:
        """Append one record per candidate that reached generation, with the final roster's uniqueness."""
        report = _uniqueness(seats)
        info = UniquenessInfo(
            max_bio_sim=report.max_bio_sim,
            max_details_sim=report.max_details_sim,
            max_cite_overlap=report.max_cite_overlap,
        )
        run_id = uuid4().hex
        by_id = {d.entity_id: d for d in queue.decisions()}
        sink.extend(
            cls._record(run_id, query, attempt, by_id[entity_id], info, seat_offset)
            for entity_id, attempt in latest.items()
        )

    @staticmethod
    def _record(
        run_id: str,
        query: str,
        attempt: _Attempt,
        decision: SeatDecision,
        uniqueness: UniquenessInfo,
        seat_offset: int = 0,
    ) -> AgentRecord:
        """The backend-only record of one candidate's final attempt. Never sent to a client."""
        draft = attempt.generated.draft
        rejections = attempt.generated.rejections
        candidate = attempt.candidate
        seated = decision.seated and attempt.agent is not None
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
                order=None if decision.order is None else decision.order + seat_offset,
            ),
            evidence=list(attempt.pack.items),
            relations=list(attempt.pack.relations),
            view=attempt.agent.view() if seated and attempt.agent is not None else None,
            details_raw=draft.details if draft is not None else "",
            cites=CiteIds(**{k: v for k, v in (draft.cites if draft else {}).items() if k in CiteIds.model_fields}),
            validation=ValidationInfo(
                json_ok=not any(r.field == "json" for r in rejections),
                repairs=max(0, attempt.generated.attempts - 1),
                rejected=[RejectedClaim(field=r.field, reason=r.reason) for r in rejections],
                details_chars=len(draft.details) if draft is not None else 0,
                cites_valid=draft is not None,
            ),
            uniqueness=uniqueness,
            generation=GenerationInfo(
                model=attempt.generated.model,
                prompt_version=PROFILE_PROMPT_VERSION,
                temperature=PROFILE_TEMPERATURE,
                attempts=max(1, attempt.generated.attempts),
                latency_ms=attempt.generated.latency_ms,
            ),
            dossier_hash=dossier_hash(attempt.pack, get_llm_config()),
            status="published" if seated else "rejected",
            reason=None if seated else decision.reason,
        )
