import re
from typing import List, Dict, Any, cast, LiteralString, Callable, Tuple, Optional
from uuid import uuid4
import uuid as _uuid
import asyncio
import inspect
from datetime import datetime
from src.persona.models_persona import (
    AgentProfile,
    PersonaIdentity,
    DiscoveryType,
    ExpertiseLevel,
    ConfidenceBreakdown,
    ProvenanceLink,
)
from neo4j import AsyncGraphDatabase
from llama_index.embeddings.ollama import OllamaEmbedding
from src.logging.setup_logging import setup_logging

logger = setup_logging()



class PersonaRepository:
    def __init__(self, neo4j_uri: str, neo4j_user: str, neo4j_password: str, neo4j_database: str):
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

    # async def list_agent_names(self, archetype_label: Optional[str] = None, limit: int = 100) -> List[str]:
    #     """Return a list of agent names. If `archetype_label` is provided, filter by node property or label."""
    #     if archetype_label:
    #         query = """
    #         MATCH (n)
    #         WHERE coalesce(n.archetype, '') = $label OR $label IN labels(n)
    #         RETURN DISTINCT n.name AS name
    #         ORDER BY coalesce(n.last_updated, datetime().epochMillis) DESC
    #         LIMIT $limit
    #         """
    #         params = {"label": archetype_label, "limit": limit}
    #     else:
    #         query = """
    #         MATCH (n:Persona)
    #         RETURN DISTINCT n.name AS name
    #         ORDER BY coalesce(n.last_updated, datetime().epochMillis) DESC
    #         LIMIT $limit
    #         """
    #         params = {"limit": limit}

    #     async with self._driver.session(database=self._db) as session:
    #         res = await session.run(cast(LiteralString, query), **params)
    #         rows = await res.data()

    #     names: List[str] = []
    #     for r in rows:
    #         n = r.get("name")
    #         if n:
    #             names.append(n)
    #     return names


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
            return enriched
        except Exception:
            return rows


    async def find_agent_sectors(self, llm_output: Dict[str, List[str]], dataset_id: str) -> List[Dict[str, Any]]:
        """Hybrid context-first + vector search.

        embedding_service: object exposing async `get_embedding(text) -> List[float]`.
        Returns list of domain tag rows with relevance and evidence_nodes.
        """
        # 1. Prepare the Search Context
        context_query = " ".join((llm_output.get('direct_keywords') or []) + (llm_output.get('latent_sectors') or []))

        # 2. Generate Embedding for the Vector Stream (sync or async provider supported)
        query_vector = await self._get_embedding(context_query)

        async with  self._driver.session(database=self._db) as session:
            cypher = """
            CALL db.index.vector.queryNodes('entity_embeddings', 100, $vector)
            YIELD node, score AS vector_score
            WHERE coalesce(node.dataset_id, '') = $dataset_id

            WITH node, vector_score
            OPTIONAL MATCH (n) WHERE id(n) = id(node)
            WHERE n.summary_context IS NOT NULL
              AND any(phrase IN $context_phrases WHERE n.summary_context CONTAINS phrase)
            WITH node, vector_score, (CASE WHEN exists(n.summary_context) THEN 1.0 ELSE 0.0 END) AS context_score

                await session.run(
                    cast(LiteralString, query),
                    agent_name=source_name,
                    target_name=target_name,
                    summary=summary,
                    round_no=round_no,
                    dataset_id=dataset_id,
                )
            """

            res = await session.run(cypher, vector=query_vector, context_phrases=llm_output.get('latent_sectors', []), dataset_id=dataset_id)
            rows = await res.data()
        # normalize rows to dicts
        out: List[Dict[str, Any]] = []
        for r in rows:
            out.append({k: r.get(k) for k in r.keys()})
        return out

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
        """Batch-fetch nodes by their `name` property and return a map name->props."""
        if not names:
            return {}

        query = """
        MATCH (n)
        WHERE n.name IN $names
        RETURN n.name AS name, n
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
            out[name] = self._node_props(node) if node else {}
        return out

    async def build_agent_profiles_from_sectors(
        self,
        llm_output: Dict[str, List[str]],
        dataset_id: str,
        user_query: str,
        max_agents: int = 5,
    ) -> List[AgentProfile]:
        """Build AgentProfiles from `find_agent_sectors` output.

        This implementation is optimized for production: it collects top evidence
        agent names, batch-fetches nodes, computes metrics from sector results,
        and constructs profiles in parallel with a bounded concurrency.
        """
        sector_results = await self.find_agent_sectors(llm_output, dataset_id) # return type: List[Dict[str, Any]] with keys: domain_tag, total_relevance, evidence_nodes, density

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

        async def _build_task(agent_name: str) -> AgentProfile:
            async with semaphore:
                node = nodes_map.get(agent_name) or await self.fetch_agent_node_props(agent_name) or {"name": agent_name} # return Type: Dict[str, Any] where we fetch the node properties for the agent name, if not found we create a minimal dict with just the name to avoid None issues
                metrics = await self._calculate_agent_metrics_and_context_for_llm(agent_name, node, sector_results or [], max_relevance=max_relevance)
                return await self._build_single_agent_profile_from_node(
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

    async def _build_single_agent_profile_from_node(
        self,
        agent_name: str,
        node: Dict[str, Any],
        user_query: str,
        dataset_id: Optional[str],
        agent_metrics: Dict[str, Any],
        sector_results: List[Dict[str, Any]],
        llm_output: Optional[Dict[str, List[str]]],
    ) -> AgentProfile:
        """Build an AgentProfile from an already-fetched node (avoids extra DB calls)."""
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

        # Description and perspective
        description = node.get("description") or node.get("summary") or f"{agent_name} - Domain expert"
        matched_sectors = agent_metrics.get("matched_sectors", [])
        if matched_sectors:
            perspective = f"I specialize in {', '.join(matched_sectors[:3])}. {node.get('detailed_perspective', node.get('perspective', description))}"
        else:
            perspective = node.get("detailed_perspective") or node.get("perspective") or description

        # Confidence & breakdown
        confidence = float(agent_metrics.get("confidence", 0.7))
        confidence_breakdown = ConfidenceBreakdown(
            source_breadth=int(node.get("source_count", node.get("provenance_count", 1))),
            node_density=int(agent_metrics.get("density", 1)),
            relationship_connectivity=float(agent_metrics.get("connectivity", 0.5)),
        )

        # Provenance
        provenance = await self.get_provenance(agent_name,limit=5) # return type: List[ProvenanceLink] where we fetch the provenance links for the agent, if not found we will attempt to synthesize them from the sector results
        # If node doesn't include provenance, attempt to synthesize from sector evidence
        if not provenance:
            # find evidence entries mentioning this agent
            docs = []
            for res in sector_results:
                if agent_name in (res.get("evidence_nodes") or []):
                    docs.append(res)
            # synthesize minimal provenance links from found docs
            for d in docs[:3]:
                # use domain tag + dataset as fallback doc id
                doc_id = f"sector:{d.get('domain_tag')}@{dataset_id}"
                chunk_id = _uuid.uuid5(_uuid.NAMESPACE_URL, doc_id)
                provenance.append(ProvenanceLink(doc_id=doc_id, title=str(d.get('domain_tag') or 'sector'), breadcrumb='', chunk_id=chunk_id))

        # Generate per-agent description/perspective from graph evidence (LLM if available, deterministic fallback)
        try:
            gen_desc, gen_perspective = await self._generate_description_and_perspective(
                agent_name=agent_name,
                node=node,
                sector_results=sector_results or [],
                provenance=provenance or [],
                user_query=user_query,
            )
            if gen_desc:
                description = gen_desc
            if gen_perspective:
                perspective = gen_perspective
        except Exception:
            # if generation fails, keep existing description/perspective
            pass

        # last_updated
        last_updated_raw = node.get("last_updated") or node.get("updated_at")
        try:
            last_updated = datetime.fromisoformat(last_updated_raw) if last_updated_raw else datetime.utcnow()
        except Exception:
            last_updated = datetime.utcnow()

        profile = AgentProfile(
            discovery_type=discovery_type,
            expertise_level=expertise_level,
            identity=identity,
            domain_tags=domain_tags,
            description=str(description)[:1000],
            detailed_perspective=str(perspective)[:4000],
            confidence=confidence,
            confidence_breakdown=confidence_breakdown,
            provenance=provenance,
            last_updated=last_updated,
        )

        return profile
    
    async def _calculate_agent_metrics_and_context_for_llm(
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

                t_summary = (tprops.get("summary_context") or tprops.get("summary") or "").strip()
                tags = tprops.get("domain_tags") or tprops.get("tags") or []
                tags_text = ", ".join(tags) if isinstance(tags, (list, tuple)) else str(tags)
                rels = rels_by_target.get(t, [])[:3]
                rel_text = "; ".join([r for r in rels if r])
                snippet = f"{t} (tags: {tags_text})" + (f": {t_summary[:180]}" if t_summary else "") + (f" — relations: {rel_text}" if rel_text else "")
                neighbor_context.append(snippet)
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

    async def _generate_description_and_perspective(
        self,
        agent_name: str,
        node: Dict[str, Any],
        sector_results: List[Dict[str, Any]],
        provenance: List[ProvenanceLink],
        user_query: Optional[str] = None,
        recent_memories: List[Dict[str, Any]] | None = None,
        neighbors_map: Dict[str, Dict[str, Any]] | None = None,
    ) -> Tuple[str, str]:
        """Produce a short `description` and a first-person `detailed_perspective`.

        Attempts to use an injected async `llm_client` if available; otherwise falls
        back to a deterministic template-based synthesizer using node text,
        matched sectors, and provenance titles.
        """
        # collect matched sectors
        matched = [r.get("domain_tag") for r in (sector_results or node.get("domain_tags") or []) if agent_name in (r.get("evidence_nodes") or [agent_name] or [])]

        # gather evidence snippets (prefer summary_context)
        evidence: List[str] = []
        # summary = node.get("summary_context") or node.get("summary") or ""
        # if summary:
        #     evidence.append(summary.strip()[:800])

        # provenance titles as lightweight evidence
        for p in (provenance or [])[:3]:
            try:
                evidence.append(f"{p.title} (source={p.doc_id})")
            except Exception:
                continue

        # If recent_memories not provided, fetch a modest window to ground perspective
        try:
            mem_rows = recent_memories if recent_memories is not None else await self.fetch_recent_memories(agent_name, memory_limit=50)
        except Exception:
            mem_rows = []

        # Build neighbor context from mem_rows and optional neighbors_map
        neighbor_context: List[str] = []
        relation_map: Dict[str, List[str]] = {}
        neighbor_names = []
        for r in (mem_rows or []):
            tgt = r.get("target_name")
            if not tgt:
                continue
            neighbor_names.append(tgt)
            rel = r.get("relation_type") or r.get("type") or "RELATED_TO"
            summ = (r.get("summary") or "").strip()
            relation_map.setdefault(tgt, []).append(f"{rel}: {summ}" if summ else rel)

        # fetch neighbor node props if not supplied
        try:
            if neighbors_map is None and neighbor_names:
                neighbors_map = await self.fetch_nodes_by_names(list(dict.fromkeys(neighbor_names)))
        except Exception:
            neighbors_map = neighbors_map or {}

        # summarize neighbor context: include tag and short summary for top neighbors
        for n in list(dict.fromkeys(neighbor_names))[:6]:
            nprops = (neighbors_map or {}).get(n) or {}
            n_summary = nprops.get("summary") or nprops.get("summary_context") or ""
            tags = nprops.get("domain_tags") or nprops.get("tags") or []
            tags_text = ", ".join(tags) if isinstance(tags, (list, tuple)) else str(tags)
            rels = relation_map.get(n, [])
            rel_text = "; ".join(rels[:2]) if rels else ""
            snippet = f"{n} (tags: {tags_text})" + (f": {n_summary[:200]}" if n_summary else "") + (f" — relations: {rel_text}" if rel_text else "")
            neighbor_context.append(snippet)

        # build a compact prompt/text block including neighbor context
        matched_text = ", ".join([m for m in matched if m]) or ", ".join(node.get("domain_tags") or [])

        # try to use injected LLM client if present
        llm = getattr(self, "llm_client", None)
        llm_func = None
        if llm:
            for name in ("chat", "generate", "complete", "invoke"):
                if hasattr(llm, name):
                    llm_func = getattr(llm, name)
                    break

        prompt_parts = [
            f"Agent: {agent_name}",
            f"Expertise: {node.get('expertise_level') or node.get('expertise') or ''}",
            f"Matched Sectors: {matched_text}",
            "Evidence:",
        ]
        for ev in evidence[:3]:
            prompt_parts.append(f"- {ev}")

        if neighbor_context:
            prompt_parts.append("Neighbor Context:")
            for nc in neighbor_context:
                prompt_parts.append(f"- {nc}")

        prompt_parts.append(f"User query: {user_query or ''}")
        prompt_parts.append("")
        prompt_parts.append("Produce two outputs:\nDESCRIPTION: one concise UI-friendly sentence (10-25 words).\nPERSPECTIVE: a 5-8 sentence first-person worldview that references neighbor context, relations, and provenance.")

        prompt = "\n".join(prompt_parts)

        text_out = None
        try:
            if llm_func and inspect.iscoroutinefunction(llm_func):
                resp = await llm_func(prompt)
                text_out = resp if isinstance(resp, str) else getattr(resp, "text", str(resp))
            elif llm_func:
                loop = asyncio.get_event_loop()
                resp = await loop.run_in_executor(None, llm_func, prompt)
                text_out = resp if isinstance(resp, str) else getattr(resp, "text", str(resp))
        except Exception:
            text_out = None

        if text_out:
            # parse DESCRIPTION: and PERSPECTIVE:
            desc = ""
            pers = ""
            try:
                parts = text_out.split("DESCRIPTION:")
                if len(parts) > 1:
                    rest = parts[1]
                    dparts = rest.split("PERSPECTIVE:")
                    desc = dparts[0].strip()
                    pers = dparts[1].strip() if len(dparts) > 1 else ""
                else:
                    # fallback: first sentence -> desc, rest -> perspective
                    sents = text_out.strip().split(". ")
                    desc = sents[0].strip() + ("." if not sents[0].endswith(".") else "")
                    pers = " ".join(sents[1:]).strip()
            except Exception:
                desc = (evidence[0].split(".")[0] if evidence else agent_name)[:200]
                pers = (f"I am {agent_name}. I focus on {matched_text}. " + (evidence[0] or ""))[:1000]

            if desc:
                return desc, pers or desc

        # deterministic fallback that includes neighbor hints
        neighbor_hint = ", ".join([n for n in (list(dict.fromkeys(neighbor_names))[:3])])
        desc_fb = f"{agent_name}: { (evidence[0].split('.')[:1][0] if evidence else ('Expert in ' + (matched_text or 'multiple domains'))) }"
        pers_fb = f"I am {agent_name}. I specialize in {matched_text or 'multiple domains'}. I frequently interact with {neighbor_hint or 'related nodes'}. { (evidence[0].split('.')[:2] and ' '.join(evidence[0].split('.')[:2])) or '' }"
        return desc_fb[:1000], pers_fb[:4000]
        
        
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
    ) -> List[AgentProfile]:
        """Main entry point: Query → Intent → Sectors → Profiles"""
        from src.utils.queryIntend import QueryIntend
        intent_extractor = QueryIntend(model="gemma4:e4b")
        
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
        
        # 4. Build complete agent profiles
        profiles = await self.build_agent_profiles_from_sectors(
            llm_output=llm_output,
            dataset_id=dataset_id,
            user_query=user_query,
            max_agents=max_agents
        )
        
        return profiles
    
    
    @staticmethod
    def _sanitize_relation_type(relation_type: str) -> str:
        cleaned = (relation_type or "").strip().upper().replace(" ", "_")
        if cleaned and re.match(r"^[A-Z_][A-Z0-9_]*$", cleaned):
            return cleaned
        return "REACTED_TO"

    async def write_reaction_edge(
        self,
        agent_name: str | None,
        source_name: str,
        target_name: str,
        relation_type: str,
        summary: str,
        round_no: int,
        dataset_id: str,
    ) -> None:
        """Write an edge representing a reaction from source_name to target_name with the given relation_type and summary."""
        if source_name == target_name:
            return

        safe_relation = self._sanitize_relation_type(relation_type)

        query = f"""
        MATCH (a:Persona {{name: $agent_name}})
        MATCH (b {{name: $target_name}})
        MERGE (a)-[r:{safe_relation}]->(b)
        SET
          r.summary = $summary,
          r.round_no = $round_no,
          r.dataset_id = $dataset_id,
          r.timestamp = datetime().epochMillis
        """
        async with self._driver.session(database=self._db) as session:
            await session.run(
                cast(LiteralString, query),
                source_name=source_name,
                target_name=target_name,
                summary=summary,
                round_no=round_no,
                dataset_id=dataset_id,
            )


    # async def write_profile_to_node(
    #     self,
    #     agent_name: str,
    #     description: str | None = None,
    #     detailed_perspective: str | None = None,
    #     summary_provenance: Dict[str, Any] | None = None,
    #     last_summary_at: Optional[str] = None,
    # ) -> None:
    #     """Persist generated profile fields back onto the graph node (best-effort).

    #     Writes `description`, `detailed_perspective`, `summary_provenance`, and
    #     `last_summary_at` if provided. Silent on failure to avoid blocking simulation.
    #     """
    #     try:
    #         sets: List[str] = []
    #         params: Dict[str, Any] = {"name": agent_name}
    #         if description is not None:
    #             sets.append("n.description = $description")
    #             params["description"] = str(description)
    #         if detailed_perspective is not None:
    #             sets.append("n.detailed_perspective = $detailed_perspective")
    #             params["detailed_perspective"] = str(detailed_perspective)
    #         if summary_provenance is not None:
    #             sets.append("n.summary_provenance = $summary_provenance")
    #             params["summary_provenance"] = summary_provenance
    #         if last_summary_at is not None:
    #             sets.append("n.last_summary_at = $last_summary_at")
    #             params["last_summary_at"] = last_summary_at

    #         if not sets:
    #             return

    #         cypher = f"""
    #         MATCH (n {{name: $name}})
    #         SET {', '.join(sets)}
    #         RETURN id(n) AS node_id
    #         """
    #         async with self._driver.session(database=self._db) as session:
    #             await session.run(cast(LiteralString, cypher), **params)
    #     except Exception:
    #         logger.exception("Failed to persist profile fields for %s", agent_name)


    # async def generate_and_persist_if_missing(
    #     self,
    #     agent_name: str,
    #     node: Dict[str, Any] | None = None,
    #     force: bool = False,
    # ) -> Tuple[str, str]:
    #     """Generate `description` and `detailed_perspective` only when missing (best-effort).

    #     - If `node` is not provided, fetch it.
    #     - If fields already exist and `force` is False, returns existing values.
    #     - Otherwise calls `_generate_description_and_perspective`, persists results,
    #       and returns them.
    #     """
    #     if node is None:
    #         node = await self.fetch_agent_node_props(agent_name) or {"name": agent_name}

    #     existing_desc = node.get("description") or node.get("summary")
    #     existing_persp = node.get("detailed_perspective") or node.get("perspective")

    #     if not force and existing_desc and existing_persp:
    #         return str(existing_desc), str(existing_persp)

    #     # prepare grounding: fetch recent memories and neighbor props
    #     try:
    #         recent_memories = await self.fetch_recent_memories(agent_name, memory_limit=80)
    #     except Exception:
    #         recent_memories = []

    #     neighbor_names = [r.get("target_name") for r in (recent_memories or []) if r.get("target_name")]
    #     neighbor_map = {}
    #     try:
    #         if neighbor_names:
    #             neighbor_map = await self.fetch_nodes_by_names(neighbor_names)
    #     except Exception:
    #         neighbor_map = {}

    #     try:
    #         desc, persp = await self._generate_description_and_perspective(
    #             agent_name=agent_name,
    #             node=node or {},
    #             sector_results=[],
    #             provenance=await self.get_provenance(agent_name, limit=5),
    #             user_query=None,
    #             recent_memories=recent_memories,
    #             neighbors_map=neighbor_map,
    #         )
    #     except Exception:
    #         # fallback deterministic
    #         desc = existing_desc or f"{agent_name} - domain expert"
    #         persp = existing_persp or desc

    #     # persist best-effort
    #     try:
    #         now_iso = datetime.utcnow().isoformat()
    #         prov = {"generated_at": now_iso, "method": "on_demand_generation"}
    #         await self.write_profile_to_node(
    #             agent_name=agent_name,
    #             description=desc,
    #             detailed_perspective=persp,
    #             summary_provenance=prov,
    #             last_summary_at=now_iso,
    #         )
    #     except Exception:
    #         logger.exception("Failed to write generated profile for %s", agent_name)

    #     return desc, persp


            
            
            
if __name__ == "__main__":
    import asyncio
    async def test():
        repo = PersonaRepository(neo4j_uri="neo4j://localhost:7687", neo4j_user="neo4j", neo4j_password="password", neo4j_database="neo4j")
        profile = await repo.create_agent_profiles_from_query(user_query="Simulate debate on AI ethics in healthcare", dataset_id="test_dataset", max_agents=5)
        print(profile)
    asyncio.run(test())