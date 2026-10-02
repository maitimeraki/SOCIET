import re
from dataclasses import asdict
from typing import TYPE_CHECKING, List, Dict, Any, cast, LiteralString, Callable, Sequence, Tuple, Optional
from uuid import uuid4
import uuid as _uuid
import asyncio
import inspect
import hashlib
from datetime import datetime
from src.persona.agent import (
    Agent,
    Agent as AgentProfile,  # back-compat alias — old name in same module
    ConfidenceBreakdown,
    DiscoveryType,
    ExpertiseLevel,
    GraphSnapshot,
    PersonaIdentity,
    ProvenanceLink,
    Stance,
    agent_profile_to_agent,
)
from neo4j import AsyncGraphDatabase
from llama_index.embeddings.ollama import OllamaEmbedding
from src.logging.setup_logging import setup_logging
from src.simulation.debate_config import DebateConfig
from src.simulation.relevance_matrix import SelectionCandidate, rank_candidates

if TYPE_CHECKING:
    from src.utils.queryIntend import QueryIntent

logger = setup_logging()



class PersonaRepository:
    def __init__(
        self,
        neo4j_uri: str,
        neo4j_user: str,
        neo4j_password: str,
        neo4j_database: str,
        llm_client: Any | None = None,
    ):
        self.llm_client = llm_client
        self.embed_model = OllamaEmbedding(
            model_name="nomic-embed-text:v1.5",
            base_url="http://localhost:11434",
            ollama_additional_kwargs={"mirostat": 0},
        )
        self._driver = AsyncGraphDatabase.driver(
            neo4j_uri,
            auth=(neo4j_user, neo4j_password),
        )
        self._db = neo4j_database

    async def close(self) -> None:
        await self._driver.close()

    @staticmethod
    def _node_props(node: Any) -> Dict[str, Any]:
        """Safely read node properties from various neo4j driver node representations."""
        if node is None:
            return {}
        try:
            # mapping-like object (recorded dict)
            if isinstance(node, dict):
                return dict(node)
            # py2neo-style or neo4j node with ._properties
            if hasattr(node, "_properties"):
                return dict(node._properties)
            # neo4j v5 node has .properties
            if hasattr(node, "properties"):
                return dict(node.properties)
            # fallback: cast to dict
            return dict(node)
        except Exception:
            logger.exception("Failed to read node properties")
            return {}


    async def fetch_agent_node_props(self, name: str) -> Dict[str, Any] | None:
        """Return all properties for a node with the given name and optional archetype label."""
        # label_clause = self._label_clause(archetype_label)
        query = f"""
        MATCH (n {{name: $name}})
        RETURN n LIMIT 1
        """
        async with self._driver.session(database=self._db) as session:
            res = await session.run(cast(LiteralString, query), name=name)
            row = await res.single()
        if not row:
            return None
        node = row.get("n")
        return self._node_props(node) if node else None

    async def fetch_recent_memories(self, name: str, memory_limit: int = 30) -> List[Dict[str, Any]]:
        """Retrieve recent relationships/memories from agent that Maintains conversation context and agent memory across rounds"""
        query = f"""
            MATCH (n {{name: $name}})
            OPTIONAL MATCH (n)-[r]->(m)
            WHERE m.name IS NOT NULL
            RETURN
            type(r) AS relation_type,
            m.name AS target_name,
            coalesce(r.summary, "") AS summary,
            coalesce(r.timestamp, "") AS timestamp
            ORDER BY coalesce(r.timestamp, "") DESC
            LIMIT $memory_limit
            """
        async with self._driver.session(database=self._db) as session:
            res = await session.run(cast(LiteralString, query), name=name, memory_limit=memory_limit)
            rows = await res.data()
        # Attach lightweight target node properties to each row to provide richer context
        try:
            targets = [r.get("target_name") for r in rows if r.get("target_name")]
            # preserve order, unique
            unique_targets = list(dict.fromkeys([t for t in targets if t]))
            if unique_targets:
                nodes_map = await self.fetch_nodes_by_names(unique_targets)
            else:
                nodes_map = {}
            enriched: List[Dict[str, Any]] = []
            for r in rows:
                tr = dict(r)
                tn = tr.get("target_name")
                if tn and tn in nodes_map:
                    tr["target_props"] = nodes_map.get(tn, {})
                else:
                    tr["target_props"] = {}
                # create a compact relation summary for prompts
                rel = (tr.get("relation_type") or "RELATED_TO").upper()
                summ = (tr.get("summary") or "").strip()
                tr["relation_summary"] = f"{rel}: {summ}" if summ else rel
                enriched.append(tr)  
                
                
            return enriched # return -> dist={ relation_type, target_name, summary, timestamp, target_props, relation_summary }
        except Exception:
            return rows


    async def find_agent_sectors(
        self,
        llm_output: Dict[str, List[str]],
        dataset_id: str,
        intent: Optional["QueryIntent"] = None,
        config: Optional[DebateConfig] = None,
    ) -> List[Dict[str, Any]]:
        """Discover agent sectors by grouping Persona nodes by domain tags.

        S4: sectors are ranked by the intent-semantic + density blend and each
        row carries its decomposition under `selection`. `intent` is the S3
        intent; without it the keyword/entity frame is read from `llm_output`,
        and with neither the ordering is the previous density-only one.

        Returns list of sector dicts with keys: domain_tag, total_relevance,
        evidence_nodes, density, selection.
        """
        query = """
        MATCH (n:Persona)
        WHERE coalesce(n.dataset_id, '') = $dataset_id
          AND size(coalesce(n.domain_tags, [])) > 0
        UNWIND n.domain_tags AS tag
        WITH tag, n,
             size(n.domain_tags) AS tag_count,
             coalesce(n.relevance_score, 0.5) AS node_relevance
        RETURN tag AS domain_tag,
               sum(node_relevance) AS total_relevance,
               collect(DISTINCT n.name) AS evidence_nodes,
               count(DISTINCT n) AS density
        ORDER BY total_relevance DESC
        LIMIT 20
        """
        async with self._driver.session(database=self._db) as session:
            res = await session.run(query, dataset_id=dataset_id)
            rows = await res.data()

        sectors = [
            {
                "domain_tag": r["domain_tag"],
                "total_relevance": float(r["total_relevance"] or 0),
                "evidence_nodes": r["evidence_nodes"],
                "density": int(r["density"] or 0),
            }
            for r in rows
        ]

        candidates = [
            SelectionCandidate(
                name=str(sector["domain_tag"]),
                text=" ".join(
                    [str(sector["domain_tag"])]
                    + [str(node) for node in (sector["evidence_nodes"] or [])]
                ),
                evidence=[sector],
            )
            for sector in sectors
        ]
        ranked = rank_candidates(
            candidates,
            intent if intent is not None else llm_output,
            config or DebateConfig(),
        )

        sectors_by_tag = {candidate.name: sector for candidate, sector in zip(candidates, sectors)}
        for row in ranked:
            sectors_by_tag[row.name]["selection"] = asdict(row)
        return [sectors_by_tag[row.name] for row in ranked]

    async def _get_embedding(self, text: str, embedding_service: Any | None = None) -> List[float]:
        """Compatibility wrapper: support async and sync embedding providers.

        If an `embedding_service` is provided it will be used; otherwise falls back
        to `self.embed_model` (synchronous OllamaEmbedding in this repo).
        """
        provider = embedding_service or getattr(self, "embed_model", None)
        if provider is None:
            raise RuntimeError("No embedding provider available")

        # common method names
        func = None
        for name in ("get_embedding", "get_text_embedding", "embed", "encode"):
            if hasattr(provider, name):
                func = getattr(provider, name)
                break

        if func is None:
            raise RuntimeError("Embedding provider has no recognizable method")

        if inspect.iscoroutinefunction(func):
            return await func(text)

        # sync function: run in threadpool to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, func, text)

    async def fetch_nodes_by_names(self, names: List[str]) -> Dict[str, Dict[str, Any]]:
        """Batch-fetch nodes by their `name` property and return a map name->props.

        A name can be held by both a `:Persona` (round commits) and a
        `:__Entity__` node. The entity row wins whatever order the driver
        returns rows in, so entity props (`triplet_source_id` etc.) are never
        shadowed by a persona's.
        """
        if not names:
            return {}

        query = """
        MATCH (n)
        WHERE n.name IN $names
        RETURN n.name AS name, n, n:__Entity__ AS is_entity
        """
        async with self._driver.session(database=self._db) as session:
            res = await session.run(cast(LiteralString, query), names=names)
            rows = await res.data()

        out: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            name = r.get("name")
            node = r.get("n")
            if not node or not name:
                continue
            if name not in out or r.get("is_entity"):
                out[name] = self._node_props(node)
        return out

    async def build_agent_profiles_from_sectors(
        self,
        llm_output: Dict[str, List[str]],
        dataset_id: str,
        user_query: str,
        max_agents: int = 5,
        intent: Optional["QueryIntent"] = None,
    ) -> List[Agent]:
        """Build canonical Agents from `find_agent_sectors` output.

        This implementation is optimized for production: it collects top evidence
        agent names, batch-fetches nodes, computes metrics from sector results,
        and constructs profiles in parallel with a bounded concurrency.

        `intent` is the S3 intent, forwarded so sector ranking consumes it.
        """
        sector_results = await self.find_agent_sectors(llm_output, dataset_id, intent=intent) # return type: List[Dict[str, Any]] with keys: domain_tag, total_relevance, evidence_nodes, density, selection
        
        """Here sector_results should be cashed such that we can further use these agent name and their data."""

        # Collect unique agent names from the top sectors (preserve order)
        evidence_names: List[str] = []
        for res in (sector_results or [])[:10]:
            for ev in (res.get("evidence_nodes") or []):
                if ev and ev not in evidence_names:
                    evidence_names.append(ev)

        agent_names = evidence_names[:max_agents]
        if not agent_names:
            return []

        # Batch-fetch agent nodes to minimize DB round-trips
        nodes_map = await self.fetch_nodes_by_names(agent_names) # return type : Dict[str, Dict[str, Any]] mapping agent name to node properties

        # Compute raw relevance per agent across the provided sector_results so we can normalize
        raw_relevance: Dict[str, float] = {name: 0.0 for name in agent_names}
        for res in (sector_results or []):
            score = float(res.get("total_relevance") or 0.0)
            for ev in (res.get("evidence_nodes") or []):
                if ev in raw_relevance:
                    raw_relevance[ev] += score # THere is the problem that the same agent can appear in multiple sectors with different relevance scores, we need to sum them up to get a total relevance score per agent

        max_relevance = max(raw_relevance.values()) if raw_relevance else 0.0

        # Build profiles concurrently with bounded parallelism
        semaphore = asyncio.Semaphore(8)

        async def _build_task(agent_name: str) -> Agent:
            async with semaphore:
                node = nodes_map.get(agent_name) or await self.fetch_agent_node_props(agent_name) or {"name": agent_name} # return Type: Dict[str, Any] where we fetch the node properties for the agent name, if not found we create a minimal dict with just the name to avoid None issues
                metrics = await self.calculate_agent_metrics_and_context_for_llm(agent_name, node, sector_results or [], max_relevance=max_relevance)
                return await self.build_single_agent_profile_from_node(
                    agent_name=agent_name,
                    node=node,
                    user_query=user_query,
                    dataset_id=dataset_id,
                    agent_metrics=metrics,
                    sector_results=sector_results or [],
                    llm_output=llm_output,
                )

        tasks = [asyncio.create_task(_build_task(n)) for n in agent_names]
        profiles = await asyncio.gather(*tasks)
        return profiles

    async def build_single_agent_profile_from_node(
        self,
        agent_name: str,
        node: Dict[str, Any],
        user_query: str,
        dataset_id: Optional[str],
        agent_metrics: Dict[str, Any],
        sector_results: List[Dict[str, Any]],
        llm_output: Optional[Dict[str, List[str]]],
        distilled: Optional[Tuple[str, str]] = None,
    ) -> Agent:
        """Build the canonical Agent from an already-fetched node (avoids extra DB calls).

        Populates every behavioral field (stance, conviction, cior, intensity,
        belief, opinion, communication_radius, instinct_tags, entity_affinity,
        expertise_areas) so downstream consumers — verdict CIOR weighting,
        round-runner prompt construction, topology pair scoring — never
        silently fall back to a default.

        `distilled` is the S5 batch-distillation result for this persona
        (`(description, perspective)`); when supplied it is the sole source of
        `bio`/`detailed_perspective`. `None` keeps the metrics-derived text.
        """
        # Identity
        identity = PersonaIdentity(
            name=node.get("name", agent_name),
            archetype=node.get("archetype") or node.get("type_name", "Strategic Analyst"),
            communication_style=node.get("communication_style") or node.get("tone", "strategic and factual"),
        )

        discovery_type = DiscoveryType.INTENT_DRIVEN if user_query and user_query.strip() else DiscoveryType.GRAPH_DISCOVERY

        # Expertise
        expertise_str = node.get("expertise_level") or node.get("expertise") or "Strategic"
        try:
            expertise_level = ExpertiseLevel(expertise_str)
        except Exception:
            try:
                expertise_level = ExpertiseLevel(str(expertise_str).capitalize())
            except Exception:
                expertise_level = ExpertiseLevel.STRATEGIC

        # Domain tags
        domain_tags = node.get("domain_tags") or node.get("tags") or agent_metrics.get("matched_sectors", [])
        if isinstance(domain_tags, str):
            domain_tags = [t.strip() for t in domain_tags.split(",") if t.strip()]

        # Description and perspective — the S5 distillation wins when supplied
        description = agent_metrics.get("context_text") or node.get("summary") or f"{agent_name} - Domain expert"
        matched_sectors = agent_metrics.get("matched_sectors", [])
        if distilled is not None:
            description, perspective = str(distilled[0]), str(distilled[1])
        elif matched_sectors:
            perspective = f"I specialize in {', '.join(matched_sectors[:3])}. {agent_metrics.get('neighbor_context', node.get('perspective', description))+agent_metrics.get('context_text', '')}"
        else:
            perspective = node.get("context_text") or node.get("perspective") or description

        # Confidence & breakdown
        confidence = float(agent_metrics.get("confidence", 0.7))
        confidence_breakdown = ConfidenceBreakdown(
            source_breadth=int(node.get("source_count", node.get("provenance_count", 1))),
            node_density=int(agent_metrics.get("density", 1)),
            relationship_connectivity=float(agent_metrics.get("connectivity", 0.5)),
        )

        # Provenance
        provenance = await self.get_provenance(agent_name,limit=5)
        # If node doesn't include provenance, attempt to synthesize from sector evidence
        if not provenance:
            docs = []
            for res in sector_results:
                if agent_name in (res.get("evidence_nodes") or []):
                    docs.append(res)
            for d in docs[:3]:
                doc_id = f"sector:{d.get('domain_tag')}@{dataset_id}"
                chunk_id = _uuid.uuid5(_uuid.NAMESPACE_URL, doc_id)
                provenance.append(ProvenanceLink(doc_id=doc_id, title=str(d.get('domain_tag') or 'sector'), breadcrumb='', chunk_id=chunk_id))

        # Behavioral core — every field read by verdict / round / topology
        stance = self._safe_stance(node.get("stance"))
        intensity = self._safe_float(node.get("intensity"), 0.5, 0.0, 1.0)
        conviction = self._safe_float(node.get("conviction"), 0.5, 0.0, 1.0)
        cior = self._safe_float(node.get("cior"), 0.0, -1.0, 1.0)
        belief = str(node.get("belief") or node.get("world_model") or "")
        opinion = str(node.get("opinion") or node.get("current_take") or perspective[:500])
        communication_radius = self._safe_int(node.get("communication_radius"), 1, 1, 5)

        instinct_tags = self._safe_list(node.get("instinct_tags"))
        entity_affinity = self._safe_list(node.get("entity_affinity")) or list(domain_tags)
        expertise_areas = self._safe_list(node.get("expertise_areas")) or list(domain_tags)

        # last_updated
        last_updated_raw = node.get("last_updated") or node.get("updated_at")
        try:
            last_updated = datetime.fromisoformat(last_updated_raw) if last_updated_raw else datetime.utcnow()
        except Exception:
            last_updated = datetime.utcnow()

        # Graph snapshot — used for staleness checks and auditability.
        # version_hash = sha256 of (dataset_id + sorted provenance doc_ids).
        snapshot_input = (
            str(dataset_id or "unknown")
            + "|"
            + ",".join(sorted({p.doc_id for p in provenance}))
        )
        version_hash = hashlib.sha256(snapshot_input.encode("utf-8")).hexdigest()
        graph_snapshot = GraphSnapshot(
            dataset_id=str(dataset_id or "unknown"),
            ontology_id=node.get("ontology_id"),
            chunk_count=int(node.get("chunk_count") or len(provenance)),
            version_hash=version_hash,
        )

        return Agent(
            identity=identity,
            discovery_type=discovery_type,
            expertise_level=expertise_level,
            last_updated=last_updated,
            bio=str(description)[:1000],                # bio = description
            detailed_perspective=str(perspective)[:4000],
            role_description=str(node.get("role_description") or description)[:300],
            stance=stance,
            intensity=intensity,
            confidence=confidence,
            conviction=conviction,
            belief=belief,
            opinion=opinion,
            cior=cior,
            instinct_tags=instinct_tags,
            domain_tags=domain_tags,
            entity_affinity=entity_affinity,
            expertise_areas=expertise_areas,
            communication_radius=communication_radius,
            summary_provenance=provenance,
            confidence_breakdown=confidence_breakdown,
            graph_snapshot=graph_snapshot,
        )

    @staticmethod
    def _safe_stance(v: Any) -> Stance:
        if isinstance(v, Stance):
            return v
        if isinstance(v, str):
            try:
                return Stance(v.upper())
            except ValueError:
                return Stance.NEUTRAL
        return Stance.NEUTRAL

    @staticmethod
    def _safe_float(v: Any, default: float, lo: float, hi: float) -> float:
        try:
            f = float(v)
            return max(lo, min(hi, f))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_int(v: Any, default: int, lo: int, hi: int) -> int:
        try:
            i = int(v)
            return max(lo, min(hi, i))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_list(v: Any) -> List[str]:
        if v is None:
            return []
        if isinstance(v, (list, tuple)):
            return [str(t).strip() for t in v if str(t).strip()]
        if isinstance(v, str):
            return [t.strip() for t in v.split(",") if t.strip()]
        return []

    async def calculate_agent_metrics_and_context_for_llm(
        self,
        agent_name: str,
        node: Dict[str, Any],
        sector_results: List[Dict[str, Any]],
        max_relevance: float | None = None,
    ) -> Dict[str, Any]:
        """Calculate relevance and metrics based on sector matching.

        If `max_relevance` is provided, confidence is normalized continuously
        across agents (uses linear scaling into the [0.4, 0.95] range). Falls
        back to the match-count heuristic when `max_relevance` is not available.
        """
        total_relevance = 0.0
        matched_sectors: List[str] = []
        density_sum = 0

        # Find all sectors where this agent appears as evidence
        for result in (sector_results or []):
            if agent_name in (result.get("evidence_nodes") or []):
                try:
                    total_relevance += float(result.get("total_relevance") or 0.0)
                except Exception:
                    total_relevance += 0.0
                matched_sectors.append(result.get("domain_tag",[]))
                density_sum += int(result.get("density") or 1)

        # Normalize confidence using max_relevance when available
        num_matches = len(matched_sectors)
        confidence = 0.4
        if max_relevance and max_relevance > 0:
            norm = min(1.0, total_relevance / float(max_relevance))
            # map normalized relevance into [0.4, 0.95]
            confidence = 0.4 + 0.55 * norm
        else:
            # heuristic fallback based on sector match counts
            if num_matches >= 3:
                confidence = 0.9
            elif num_matches == 2:
                confidence = 0.75
            elif num_matches == 1:
                confidence = 0.6

        # Node density & connectivity: prefer stored analytics; otherwise query the graph at runtime
        node_density = None
        connectivity = None

        try:
            if node.get("connection_count") is not None:
                node_density = int(node.get("connection_count", node.get("degree", 1)))
            elif node.get("degree") is not None:
                node_density = int(node.get("degree", 1))
        except Exception:
            node_density = None

        try:
            if node.get("centrality_score") is not None:
                connectivity = float(node.get("centrality_score", 0.5))
        except Exception:
            connectivity = None

        # If either metric is missing, derive neighbor info from recent memories
        mem_rows: List[Dict[str, Any]] = []
        try:
            mem_rows = await self.fetch_recent_memories(agent_name, memory_limit=200)
            targets = {r.get("target_name") for r in (mem_rows or []) if r.get("target_name")}
            neighbor_count = len(targets)
            total_relations = len(mem_rows or [])

            if node_density is None:
                node_density = neighbor_count

            if connectivity is None:
                # heuristic: fraction of unique neighbors to total relations, scaled to [0,1]
                if total_relations > 0:
                    connectivity = min(1.0, neighbor_count / float(total_relations))
                else:
                    connectivity = 0.0
        except Exception:
            if node_density is None:
                node_density = int(density_sum or 1)
            if connectivity is None:
                connectivity = 0.5

        # final safety defaults
        try:
            node_density = int(node_density or (density_sum or 1))
        except Exception:
            node_density = int(density_sum or 1)
        try:
            connectivity = float(connectivity or 0.5)
        except Exception:
            connectivity = 0.5

        # Build neighbor context summaries for prompts
        neighbor_context: List[str] = []
        try:
            # mem_rows may include 'target_props' from fetch_recent_memories
            # Group relation summaries by target
            rels_by_target: Dict[str, List[str]] = {}
            for r in (mem_rows or [])[:200]:
                tgt = r.get("target_name")
                if not tgt:
                    continue
                rels_by_target.setdefault(tgt, []).append(r.get("relation_summary") or (r.get("relation_type") or "RELATED_TO"))

            # choose top neighbors by number of relations
            sorted_targets = sorted(rels_by_target.keys(), key=lambda t: -len(rels_by_target.get(t, [])))[:6]
            # fetch neighbor props if mem_rows didn't include them
            neighbor_props_map = {}
            try:
                names_to_fetch = [t for t in sorted_targets if not any((r.get("target_props") for r in (mem_rows or []) if r.get("target_name") == t))]
                if names_to_fetch:
                    neighbor_props_map = await self.fetch_nodes_by_names(names_to_fetch)
            except Exception:
                neighbor_props_map = {}

            for t in sorted_targets:
                # try to find target_props from mem_rows first
                tprops = None
                for r in (mem_rows or []):
                    if r.get("target_name") == t and r.get("target_props"):
                        tprops = r.get("target_props")
                        break
                if not tprops:
                    tprops = neighbor_props_map.get(t, {})

                t_summary = (tprops.get("context") or tprops.get("canonical_description") or "").strip()
                tags = tprops.get("domain_tags") or tprops.get("tags") or []
                tags_text = ", ".join(tags) if isinstance(tags, (list, tuple)) else str(tags)
                rels = rels_by_target.get(t, [])[:3]
                rel_text = "; ".join([r for r in rels if r])
                snippet = f"{t} (tags: {tags_text})" + (f": {t_summary[:180]}" if t_summary else "") + (f" — relations: {rel_text}" if rel_text else "")
                
                neighbor_context.append(snippet) # one element are -> "NeighborName (tags: tag1, tag2): short summary... — relations: REL1; REL2"
        except Exception:
            neighbor_context = []

        # Compact context_text to pass into LLMs: include top matched sectors and neighbor snippets and latest relation summaries
        try:
            sector_hint = ", ".join([s for s in matched_sectors[:4] if s]) or ", ".join(node.get("domain_tags") or [])
            recent_rel_summaries = [r.get("relation_summary") for r in (mem_rows or []) if r.get("relation_summary")][:6]
            recent_text = " | ".join([s for s in recent_rel_summaries if s])
            context_text = f"Matched sectors: {sector_hint}. Top neighbors: {'; '.join(neighbor_context[:4])}. Recent relations: {recent_text}"
        except Exception:
            context_text = ""

        return {
            "confidence": round(float(confidence), 3),
            "density": node_density,
            "connectivity": connectivity,
            "relevance_score": total_relevance,
            "matched_sectors": matched_sectors,
            "recent_memories": mem_rows,
            "neighbor_context": neighbor_context,
            "context_text": context_text,
        }

    @staticmethod
    def _template_profile_text(
        agent_name: str,
        evidence: List[str],
        matched_text: str,
        neighbor_names: List[str],
    ) -> Tuple[str, str]:
        """The deterministic `(description, perspective)` template.

        The S5 batch distillation's fallback, so template text is produced in
        exactly one place.
        """
        head = evidence[0] if evidence else ""
        neighbor_hint = ", ".join([n for n in (list(dict.fromkeys(neighbor_names))[:3])])
        desc_fb = f"{agent_name}: { head.split('.')[:1][0] if head else ('Expert in ' + (matched_text or 'multiple domains')) }"
        pers_fb = f"I am {agent_name}. I specialize in {matched_text or 'multiple domains'}. I frequently interact with {neighbor_hint or 'related nodes'}. {' '.join(head.split('.')[:2])}"
        return desc_fb[:1000], pers_fb[:4000]

    #: Bounded prompt: at most this many evidence snippets / anchors per persona.
    _DISTILL_EVIDENCE_CAP = 3
    _DISTILL_ANCHOR_CAP = 4
    _DISTILL_SNIPPET_CHARS = 200

    async def distill_profiles(
        self,
        personas: List[Dict[str, Any]],
        query: str,
        core_question: str = "",
        stance_axis: str = "",
        warnings: Optional[List[str]] = None,
    ) -> Dict[str, Tuple[str, str]]:
        """S5: ONE batched LLM call that gives every selected persona its question-aware voice.

        `personas` is the ordered selection set — each entry a mapping with:
          * `name`           the persona's graph name (required)
          * `node`           its node properties (domain tags / summary text)
          * `sector_results` its matched-sector rows
          * `evidence`       grounding snippets synthesis already holds
          * `anchors`        the S4 provenance anchors of its selection row
        The run-level question context (`query`, `core_question`, `stance_axis`)
        frames the whole prompt. No per-persona graph reads happen here.

        Returns `{name: (description, perspective)}` for EVERY persona. Fallback
        matrix: no client / no callable client method / the call raising → every
        persona gets the deterministic template plus ONE warning; a persona whose
        block is missing or unparseable gets the template plus a warning naming
        it. `warnings` is the caller-owned sink. Never raises.

        The prompt is bounded: at most `_DISTILL_EVIDENCE_CAP` snippets
        (`_DISTILL_SNIPPET_CHARS` chars each) and `_DISTILL_ANCHOR_CAP` anchors
        are shown per persona.
        """
        results: Dict[str, Tuple[str, str]] = {}
        if not personas:
            return results

        def _entry_node(entry: Dict[str, Any]) -> Dict[str, Any]:
            node = entry.get("node")
            return node if isinstance(node, dict) else {}

        def _template(entry: Dict[str, Any]) -> Tuple[str, str]:
            node = _entry_node(entry)
            sectors = [
                str(row.get("domain_tag"))
                for row in (entry.get("sector_results") or [])
                if isinstance(row, dict) and row.get("domain_tag")
            ]
            matched_text = ", ".join(sectors) or ", ".join(
                str(tag) for tag in (node.get("domain_tags") or []) if str(tag).strip()
            )
            evidence = [str(e) for e in (entry.get("evidence") or []) if str(e).strip()]
            return self._template_profile_text(str(entry.get("name") or ""), evidence, matched_text, [])

        def _block(entry: Dict[str, Any]) -> str:
            node = _entry_node(entry)
            name = str(entry.get("name") or "")
            lines = [f"PERSONA: {name}"]
            tags = ", ".join(str(tag) for tag in (node.get("domain_tags") or []) if str(tag).strip())
            if tags:
                lines.append(f"DOMAIN TAGS: {tags}")
            sectors = [
                str(row.get("domain_tag"))
                for row in (entry.get("sector_results") or [])
                if isinstance(row, dict) and row.get("domain_tag")
            ]
            if sectors:
                lines.append(f"MATCHED SECTORS: {', '.join(sectors)}")
            evidence = [str(e).strip() for e in (entry.get("evidence") or []) if str(e).strip()]
            if evidence:
                lines.append("EVIDENCE:")
                lines.extend(f"- {e[: self._DISTILL_SNIPPET_CHARS]}" for e in evidence[: self._DISTILL_EVIDENCE_CAP])
            anchors = [a for a in (entry.get("anchors") or []) if isinstance(a, dict)]
            if anchors:
                lines.append("ANCHORS:")
                for anchor in anchors[: self._DISTILL_ANCHOR_CAP]:
                    ref = anchor.get("id") or anchor.get("name") or ""
                    lines.append(f"- {anchor.get('kind', 'ref')}:{ref}")
            lines.append("")
            return "\n".join(lines)

        system_prompt = (
            "You write the public profile of each debate participant listed below, "
            "for a multi-agent debate on the given question. Ground every statement in "
            "the participant's own evidence; make clear what the question means from "
            "that participant's perspective.\n"
            "Reply with one block per participant, in the given order, exactly in this "
            "form and nothing else:\n"
            "PERSONA: <name>\n"
            "DESCRIPTION: <one concise UI-friendly sentence, 10-25 words>\n"
            "PERSPECTIVE: <a 5-8 sentence first-person worldview grounded in the "
            "evidence and the question>"
        )
        header = [f"QUERY: {query}", f"CORE QUESTION: {core_question or query}"]
        if stance_axis:
            header.append(f"STANCE AXIS: {stance_axis}")
        user_prompt = "\n".join(header) + "\n\n" + "\n".join(_block(entry) for entry in personas)

        llm = getattr(self, "llm_client", None)
        llm_func = None
        if llm is not None:
            for name in ("generate", "chat", "complete", "invoke"):
                if hasattr(llm, name):
                    llm_func = getattr(llm, name)
                    break

        call_error: Optional[str] = None
        text_out: Optional[str] = None
        if llm is None:
            call_error = "no LLM client configured"
        elif llm_func is None:
            call_error = "the LLM client has no generate/chat/complete/invoke method"
        else:
            try:
                if inspect.iscoroutinefunction(llm_func):
                    resp = await llm_func(system_prompt=system_prompt, user_prompt=user_prompt)
                else:
                    loop = asyncio.get_event_loop()
                    resp = await loop.run_in_executor(
                        None,
                        lambda: llm_func(system_prompt=system_prompt, user_prompt=user_prompt),
                    )
                text_out = resp if isinstance(resp, str) else getattr(resp, "text", str(resp))
            except Exception as exc:
                call_error = f"batch call failed: {exc}"

        if call_error is not None or not text_out:
            reason = call_error or "the batch call returned no text"
            if warnings is not None:
                warnings.append(
                    f"S5 distillation: {reason}; all {len(personas)} personas fell back to "
                    "the deterministic template."
                )
            return {str(entry.get("name") or ""): _template(entry) for entry in personas}

        # Parse the per-persona blocks out of the single response.
        blocks_by_name: Dict[str, str] = {}
        current_name: Optional[str] = None
        current_lines: List[str] = []
        for line in text_out.splitlines():
            stripped = line.strip()
            if stripped.upper().startswith("PERSONA:"):
                if current_name is not None:
                    blocks_by_name[current_name] = "\n".join(current_lines)
                current_name = stripped.split(":", 1)[1].strip()
                current_lines = []
            elif current_name is not None:
                current_lines.append(line)
        if current_name is not None:
            blocks_by_name[current_name] = "\n".join(current_lines)
        blocks_by_key = {
            " ".join(name.split()).casefold(): block for name, block in blocks_by_name.items()
        }

        for entry in personas:
            name = str(entry.get("name") or "")
            block = blocks_by_key.get(" ".join(name.split()).casefold(), "")
            desc = pers = ""
            if block:
                parts = block.split("DESCRIPTION:")
                if len(parts) > 1:
                    dparts = parts[1].split("PERSPECTIVE:")
                    desc = dparts[0].strip()
                    pers = dparts[1].strip() if len(dparts) > 1 else ""
                else:
                    sents = block.strip().split(". ")
                    desc = sents[0].strip() + ("." if not sents[0].endswith(".") else "")
                    pers = " ".join(sents[1:]).strip()
            if desc:
                results[name] = (desc, pers or desc)
            else:
                if warnings is not None:
                    warnings.append(
                        f"S5 distillation: no parseable output for persona {name!r}; "
                        "the deterministic template was used."
                    )
                results[name] = _template(entry)
        return results

    #: Bound on the provenance write: at most this many chunk ids per persona, per call.
    _PROVENANCE_CHUNK_CAP = 20

    async def write_persona_provenance(
        self,
        persona_name: str,
        dataset_id: str,
        chunk_node_ids: Sequence[str],
    ) -> int:
        """D2: write the `(Persona)-[:MENTIONS]->(Chunk)` edges `get_provenance` reads.

        `chunk_node_ids` are graph chunk node ids — each entity's
        `triplet_source_id`. Ids are stripped, deduped and capped at
        `_PROVENANCE_CHUNK_CAP`, then written in ONE idempotent statement; empty
        input issues no query and returns 0. The Persona MERGE keys match
        `SocietyMemory.commit_round` exactly, so this composes with the
        round-commit node instead of shadowing it. Returns the number of edges
        ensured (ids with no matching chunk node are skipped).
        """
        chunk_ids = list(
            dict.fromkeys(str(cid).strip() for cid in chunk_node_ids if str(cid or "").strip())
        )[: self._PROVENANCE_CHUNK_CAP]
        if not chunk_ids:
            return 0

        cypher = """
        UNWIND $chunk_ids AS cid
        MATCH (c:__Node__ {id: cid})
        MERGE (p:Persona {name: $name, dataset_id: $dataset_id})
        MERGE (p)-[:MENTIONS]->(c)
        RETURN count(*) AS written
        """

        async with self._driver.session(database=self._db) as session:
            result = await session.run(
                cypher, chunk_ids=chunk_ids, name=persona_name, dataset_id=dataset_id,
            )
            rows = await result.data()

        return int(rows[0]["written"]) if rows else 0

    async def get_provenance(self, agent_name: str, limit: int = 5) -> List[ProvenanceLink]:
        """Single, efficient provenance fetch."""
        from uuid import UUID
        
        # Optimized query: fixed path, indexed lookup
        cypher = """
        MATCH (a:Persona {name: $name})
        MATCH (a)-[:MENTIONS]->(chunk:Chunk)
        WHERE chunk.doc_id IS NOT NULL
        RETURN DISTINCT
            chunk.doc_id AS doc_id,
            chunk.title AS title,
            chunk.breadcrumb AS breadcrumb,
            chunk.chunk_id AS chunk_id
        LIMIT $limit
        """
        
        async with self._driver.session(database=self._db) as session:
            result = await session.run(cypher, name=agent_name, limit=limit)
            rows = await result.data()
        
        return [
            ProvenanceLink(
                doc_id=row["doc_id"],
                title=row["title"] or "Unknown Source",
                breadcrumb=row["breadcrumb"] or "",
                chunk_id=UUID(row["chunk_id"]) if row.get("chunk_id") else uuid4()
            )
            for row in rows
            if row.get("doc_id")
        ]
    
    # Full pipeline execution
    async def create_agent_profiles_from_query(
        self,
        user_query: str,
        dataset_id: str ,
        max_agents: int = 5
    ) -> List[Agent]:
        """Main entry point: Query → Intent → Sectors → Agents"""
        from src.utils.queryIntend import QueryIntend
        intent_extractor = QueryIntend()
        
        # 1. Extract intent using LLM (from your QueryIntentExtractor)
        intent = await intent_extractor.expand_user_query(user_query)
        if not intent:
            return []
        
        # 2. Convert to dict format for find_agent_sectors
        llm_output = {
            "direct_keywords": intent.direct_keywords,
            "latent_sectors": intent.latent_sectors,
            "search_perspectives": intent.search_perspectives
        }
        
        # 4. Build complete agent profiles (sector ranking consumes the intent)
        profiles = await self.build_agent_profiles_from_sectors(
            llm_output=llm_output,
            dataset_id=dataset_id,
            user_query=user_query,
            max_agents=max_agents,
            intent=intent,
        )
        
        return profiles
    
    
    @staticmethod
    def _sanitize_relation_type(relation_type: str) -> str:
        cleaned = (relation_type or "").strip().upper().replace(" ", "_")
        if cleaned and re.match(r"^[A-Z_][A-Z0-9_]*$", cleaned):
            return cleaned
        return "REACTED_TO"

if __name__ == "__main__":
    import asyncio
    async def test():
        repo = PersonaRepository(neo4j_uri="neo4j://localhost:7687", neo4j_user="neo4j", neo4j_password="password", neo4j_database="neo4j")
        profile = await repo.create_agent_profiles_from_query(user_query="Simulate debate on AI ethics in healthcare", dataset_id="test_dataset", max_agents=5)
        print(profile)
    asyncio.run(test())