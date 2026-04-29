import re
from typing import List, Dict, Any, cast, LiteralString, Callable
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

    # @staticmethod
    # def _label_clause(archetype_label: str | None) -> str:
    #     """Return a safe Cypher label clause like ":Label" or empty string for invalid/None."""
    #     if not archetype_label:
    #         return ""
    #     # sanitize label to avoid injection and invalid labels
    #     cleaned = re.sub(r"[^A-Za-z0-9_]", "", archetype_label)
    #     if _SAFE_LABEL_RE.match(cleaned):
    #         return f":{cleaned}"
    #     logger.warning("Rejected invalid archetype_label: %s", archetype_label)
    #     return ""

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


    async def fetch_agent_node(self, name: str) -> Dict[str, Any] | None:
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

        async with self._driver.session(database=self._db) as session:
            cypher = """
            CALL db.index.vector.queryNodes('entity_embeddings', 100, $vector)
            YIELD node, score AS vector_score
            WHERE coalesce(node.dataset_id, '') = $dataset_id

            WITH node, vector_score
            OPTIONAL MATCH (n) WHERE id(n) = id(node)
            WHERE n.summary_context IS NOT NULL
              AND any(phrase IN $context_phrases WHERE n.summary_context CONTAINS phrase)
            WITH node, vector_score, (CASE WHEN exists(n.summary_context) THEN 1.0 ELSE 0.0 END) AS context_score

            UNWIND coalesce(node.domain_tags, []) AS tag
            RETURN 
                tag AS domain_tag, 
                sum(vector_score + context_score) AS total_relevance,
                collect(coalesce(node.name, ''))[..5] AS evidence_nodes,
                count(node) AS density
            ORDER BY total_relevance DESC
            LIMIT 10
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
        sector_results = await self.find_agent_sectors(llm_output, dataset_id)

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
        nodes_map = await self.fetch_nodes_by_names(agent_names)

        # Compute raw relevance per agent across the provided sector_results so we can normalize
        raw_relevance: Dict[str, float] = {name: 0.0 for name in agent_names}
        for res in (sector_results or []):
            score = float(res.get("total_relevance") or 0.0)
            for ev in (res.get("evidence_nodes") or []):
                if ev in raw_relevance:
                    raw_relevance[ev] += score

        max_relevance = max(raw_relevance.values()) if raw_relevance else 0.0

        # Build profiles concurrently with bounded parallelism
        semaphore = asyncio.Semaphore(8)

        async def _build_task(agent_name: str) -> AgentProfile:
            async with semaphore:
                node = nodes_map.get(agent_name) or await self.fetch_agent_node(agent_name) or {"name": agent_name}
                metrics = self._calculate_agent_metrics(agent_name, node, sector_results or [], max_relevance=max_relevance)
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
    # async def _build_single_agent_profile(
    # self,
    # agent_name: str,
    # user_query: str,
    # dataset_id: str,
    # sector_results: List[Dict[str, Any]],
    # llm_output: Dict[str, List[str]]
    # ) -> AgentProfile:
    #     """Build AgentProfile from graph node data"""
        
    #     # 1. Fetch raw node from repository
    #     node = await self.fetch_agent_node(
    #         name=agent_name
    #     )
        
    #     if not node:
    #         raise ValueError(f"Agent {agent_name} not found in graph")
        
    #     # 2. Calculate relevance from sector results
    #     agent_metrics = self._calculate_agent_metrics(
    #         agent_name, 
    #         node, 
    #         sector_results
    #     )
        
    #     # 3. Build PersonaIdentity (simplified)
    #     identity = PersonaIdentity(
    #         name=node.get("name", agent_name),
    #         archetype=node.get("archetype", node.get("type_name", "Strategic Analyst")),
    #         communication_style=node.get("communication_style", node.get("tone", "strategic and factual"))
    #     )
        
    #     # 4. Determine discovery type
    #     discovery_type = DiscoveryType.INTENT_DRIVEN if user_query else DiscoveryType.GRAPH_DISCOVERY
        
    #     # 5. Determine expertise level
    #     expertise_str = node.get("expertise_level", node.get("expertise", "Strategic"))
    #     try:
    #         expertise_level = ExpertiseLevel(expertise_str)
    #     except ValueError:
    #         expertise_level = ExpertiseLevel.STRATEGIC
        
    #     # 6. Extract domain tags
    #     domain_tags = node.get("domain_tags", node.get("tags", []))
    #     if isinstance(domain_tags, str):
    #         domain_tags = [t.strip() for t in domain_tags.split(",")]
        
    #     # 7. Build description and perspective
    #     description = node.get("description", node.get("summary", f"{agent_name} - Domain expert"))
        
    #     # Enhanced perspective using matched sectors
    #     matched_sectors = agent_metrics.get("matched_sectors", [])
    #     if matched_sectors:
    #         perspective = f"I specialize in {', '.join(matched_sectors[:3])}. {node.get('detailed_perspective', node.get('perspective', description))}"
    #     else:
    #         perspective = node.get("detailed_perspective", node.get("perspective", description))
        
    #     # 8. Calculate confidence and breakdown
    #     confidence = agent_metrics.get("confidence", 0.7)
    #     confidence_breakdown = ConfidenceBreakdown(
    #         source_breadth=node.get("source_count", node.get("provenance_count", 1)),
    #         node_density=agent_metrics.get("density", 1),
    #         relationship_connectivity=agent_metrics.get("connectivity", 0.5)
    #     )
        
    #     # 9. Extract provenance
    #     provenance = self._extract_provenance_from_node(node)
        
    #     # 10. Create final AgentProfile
    #     profile = AgentProfile(
    #         discovery_type=discovery_type,
    #         expertise_level=expertise_level,
    #         identity=identity,
    #         domain_tags=domain_tags,
    #         description=description,
    #         detailed_perspective=perspective,
    #         confidence=confidence,
    #         confidence_breakdown=confidence_breakdown,
    #         provenance=provenance
    #     )
        
    #     return profile

    async def _build_single_agent_profile_from_node(
        self,
        agent_name: str,
        node: Dict[str, Any],
        user_query: str,
        dataset_id: str,
        agent_metrics: Dict[str, Any],
        sector_results: List[Dict[str, Any]],
        llm_output: Dict[str, List[str]],
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
        provenance = self._extract_provenance_from_node(node)
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
    
    def _calculate_agent_metrics(
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
                matched_sectors.append(result.get("domain_tag"))
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

        # Node density (connections in graph or heuristic)
        try:
            node_density = int(node.get("connection_count") or node.get("degree") or (density_sum // max(1, num_matches)))
        except Exception:
            node_density = int(density_sum or 1)

        # Relationship connectivity (simplified)
        try:
            connectivity = float(node.get("centrality_score") or 0.5)
        except Exception:
            connectivity = 0.5

        return {
            "confidence": round(float(confidence), 3),
            "density": node_density,
            "connectivity": connectivity,
            "relevance_score": total_relevance,
            "matched_sectors": matched_sectors,
        }
        
        
    def _extract_provenance_from_node(self, node: Dict[str, Any]) -> List[ProvenanceLink]:
        """Extract provenance links from node properties"""
        provenance_list: List[ProvenanceLink] = []
        raw_prov = node.get("provenance", [])
        from uuid import UUID

        if raw_prov and isinstance(raw_prov, list):
            for idx, prov in enumerate(raw_prov[:10]):
                try:
                    doc_id = str(prov.get("doc_id") or prov.get("id") or "unknown")
                    title = str(prov.get("title") or prov.get("doc_title") or "Unknown Source")
                    breadcrumb = str(prov.get("breadcrumb") or prov.get("path") or "")
                    chunk_raw = prov.get("chunk_id")
                    if chunk_raw and isinstance(chunk_raw, str):
                        try:
                            chunk_id = UUID(chunk_raw)
                        except Exception:
                            # fallback to deterministic UUID5 using doc_id + index
                            chunk_id = _uuid.uuid5(_uuid.NAMESPACE_URL, f"{doc_id}:{idx}")
                    else:
                        chunk_id = _uuid.uuid5(_uuid.NAMESPACE_URL, f"{doc_id}:{idx}")

                    provenance_list.append(ProvenanceLink(doc_id=doc_id, title=title, breadcrumb=breadcrumb, chunk_id=chunk_id))
                except Exception:
                    continue

        # Fallback: create from source fields (deterministic chunk id)
        if not provenance_list and node.get("source_doc_id"):
            doc = str(node.get("source_doc_id"))
            try:
                chunk0 = _uuid.uuid5(_uuid.NAMESPACE_URL, doc)
            except Exception:
                chunk0 = uuid4()
            provenance_list.append(ProvenanceLink(
                doc_id=doc,
                title=str(node.get("source_title", "Graph Source")),
                breadcrumb=str(node.get("source_path", "")),
                chunk_id=chunk0,
            ))

        return provenance_list
    
    # Full pipeline execution
    async def create_agent_profiles_from_query(
        self,
        user_query: str,
        dataset_id: str = None,
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





    # @staticmethod
    # def _sanitize_relation_type(relation_type: str) -> str:
    #     cleaned = (relation_type or "").strip().upper().replace(" ", "_")
    #     if _SAFE_RELATION_RE.match(cleaned):
    #         return cleaned
    #     return "REACTED_TO"

    # async def write_reaction_edge(
    #     self,
    #     archetype_label: str | None,
    #     source_name: str,
    #     target_name: str,
    #     relation_type: str,
    #     summary: str,
    #     round_no: int,
    #     dataset_id: str,
    # ) -> None:
    #     """Write an edge representing a reaction from source_name to target_name with the given relation_type and summary."""
    #     if source_name == target_name:
    #         return

    #     safe_relation = self._sanitize_relation_type(relation_type)

    #     label_clause = self._label_clause(archetype_label)
    #     query = f"""
    #     MATCH (a{label_clause} {{name: $source_name}})
    #     MATCH (b {{name: $target_name}})
    #     MERGE (a)-[r:{safe_relation}]->(b)
    #     SET
    #       r.summary = $summary,
    #       r.round_no = $round_no,
    #       r.dataset_id = $dataset_id,
    #       r.timestamp = datetime().epochMillis
    #     """
    #     async with self._driver.session(database=self._db) as session:
    #         await session.run(
    #             cast(LiteralString, query),
    #             source_name=source_name,
    #             target_name=target_name,
    #             summary=summary,
    #             round_no=round_no,
    #             dataset_id=dataset_id,
    #         )
            
            
            
            
if __name__ == "__main__":
    import asyncio
    async def test():
        repo = PersonaRepository(neo4j_uri="neo4j://localhost:7687", neo4j_user="neo4j", neo4j_password="password", neo4j_database="neo4j")
        profile = await repo.create_agent_profiles_from_query(user_query="Simulate debate on AI ethics in healthcare", dataset_id="test_dataset", max_agents=5)
        print(profile)
    asyncio.run(test())