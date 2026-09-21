from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import uuid
import itertools
from neo4j import AsyncGraphDatabase, Query
from src.graph.config_graph import GraphConfig
from src.logging.setup_logging import setup_logging
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = setup_logging()


@dataclass
class EntityNode:
    """Represents an entity node to be written to Neo4j."""
    id: Optional[str] = None
    labels: List[str] = field(default_factory=list)
    properties: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.id is None:
            self.id = str(uuid.uuid4())


@dataclass
class RelationEdge:
    """Represents a relationship edge to be written to Neo4j."""
    source_id: str
    target_id: str
    relation_type: str
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MergeCandidate:
    node_id: int
    labels: List[str]
    properties: Dict[str, Any]

class GraphNormalizationStage:
    """
    Safe graph merge manager:
    - computes multi-signal confidence
    - prefers soft-links/canonical nodes
    - performs destructive merges only when safe and audited
    """

    def __init__(self, config: GraphConfig, batch_size: int = 10):
        self.config = config
        self.batch_size = batch_size
        self.driver = AsyncGraphDatabase.driver(
            config.neo4j_uri,
            auth=(config.neo4j_username, config.neo4j_password),
        )

    async def close(self):
        await self.driver.close()

    # ---------- Utilities ----------
    @staticmethod
    def canonicalize_name(name: str) -> str:
        return name.strip().lower() if name else ""

    async def _run(self, query: Query, parameters: dict):
        async with self.driver.session(database=self.config.neo4j_database) as session:
            return await session.run(query, parameters or {})

    # ---------- Candidate detection ----------
    async def find_surface_duplicates(self, dataset_id: str) -> List[List[MergeCandidate]]:
        """
        Finds groups of nodes that share the same canonical surface form.
        Returns groups with length > 1.
        """
        q = Query("""
        MATCH (n)
        WHERE n.dataset_id = $dataset_id AND n.name IS NOT NULL
        WITH toLower(trim(n.name)) AS key, collect({
            id: elementId(n),
            labels: labels(n),
            props: properties(n)
        }) AS nodes
        WHERE size(nodes) > 1
        RETURN key, nodes
        """)
        result = await self._run(q, {"dataset_id": dataset_id})
        groups = []
        async for record in result:
            nodes = [MergeCandidate(node_id=int(n["id"]), labels=n["labels"], properties=n["props"]) for n in record["nodes"]]
            groups.append(nodes)
        return groups

    # ---------- Evidence scoring ----------
    async def compute_signals(self, group: List[MergeCandidate]) -> Dict[str, Any]:
        """
        Compute evidence for a group of nodes that appear similar.
        Returns a dict with per-pair signals and an aggregate confidence.
        Signals used:
         - type_match (labels overlap)
         - neighbor_overlap (Jaccard on neighboring node labels)
         - provenance_match (same source system)
         - embedding_similarity (optional external, placeholder here)
        """
        # fast checks between first two nodes (can be expanded)
        signals = {"pairs": [], "aggregate_confidence": 0.0}
        # For simplicity compute pairwise for all pairs and average
        import itertools
        scores = []
        for a, b in itertools.combinations(group, 2):
            type_score = 1.0 if set(a.labels) & set(b.labels) else 0.0
            provenance_score = 1.0 if a.properties.get("source") and a.properties.get("source") == b.properties.get("source") else 0.0
            # neighbor overlap: fetch neighboring labels
            neighbor_score = await self._neighbor_label_jaccard(str(a.node_id), str(b.node_id))
            # embedding similarity placeholder (0..1) - user must implement actual embed service
            embed_score = await self._embedding_similarity(a.properties.get("name", ""), b.properties.get("name", ""))
            # weighted sum
            weight = 0.25 * type_score + 0.25 * provenance_score + 0.3 * neighbor_score + 0.2 * embed_score
            scores.append(weight)
            signals["pairs"].append({
                "a": a.node_id,
                "b": b.node_id,
                "type_score": type_score,
                "provenance_score": provenance_score,
                "neighbor_score": neighbor_score,
                "embed_score": embed_score,
                "pair_confidence": weight,
            })
        if scores:
            signals["aggregate_confidence"] = float(sum(scores) / len(scores))
        return signals

    async def _neighbor_label_jaccard(self, id_a: str, id_b: str) -> float:
        """
        Calculates Jaccard similarity of neighboring node labels.
        """
        q = Query("""
        MATCH (a) WHERE elementId(a) = $id_a
        MATCH (b) WHERE elementId(b) = $id_b
        // Use pattern matching to find all neighbors
        MATCH (a)-[]-(na)
        MATCH (b)-[]-(nb)
        WITH collect(DISTINCT labels(na)) AS la, collect(DISTINCT labels(nb)) AS lb
        RETURN apoc.coll.toSet(la) AS la_set, apoc.coll.toSet(lb) AS lb_set
        """)
        try:
            res = await self._run(q, {"id_a": id_a, "id_b": id_b})
            rec = await res.single()
            if res is not None and rec:
                la_set = rec["la_set"] or []
                lb_set = rec["lb_set"] or []
            
            # FIX: APOC returns lists of lists/sets, we need to flatten and convert to set
            la_set = set(item for sublist in la_set for item in sublist)
            lb_set = set(item for sublist in lb_set for item in sublist)

            if not la_set and not lb_set:
                return 0.0
            
            inter = la_set & lb_set
            union = la_set | lb_set
            return float(len(inter) / len(union)) if union else 0.0
        except Exception as e:
            logger.warning(f"Could not calculate neighbor Jaccard similarity: {e}")
            return 0.0

    async def _embedding_similarity(self, a: str, b: str) -> float:
        """
        Placeholder — in prod call your embeddings service and compute cosine similarity.
        Return value in [0,1].
        """
        # VERY naive fallback: exact match -> 1.0, substring -> 0.6, else 0.0
        if not a or not b:
            return 0.0
        a_low = a.lower()
        b_low = b.lower()
        if a_low == b_low:
            return 1.0
        if a_low in b_low or b_low in a_low:
            return 0.6
        return 0.0

    # ---------- Non-destructive operations ----------
    async def create_alias_relationships(self, canonical_label: str, canonical_props: dict, originals: List[MergeCandidate], audit_note: Optional[str] = None) -> None:
        """
        Create a canonical node and connect originals to it via :ALIAS_OF (non-destructive).
        """
        canonical_id = str(uuid.uuid4())
        create_q = Query("""
        UNWIND $originals AS o
        MERGE (canon:{canonical_label} {{ canonical_id: $canonical_id, dataset_id: $dataset_id }})
        ON CREATE SET canon += $canon_props
        WITH canon, o
        MATCH (orig) WHERE elementId(orig) = o.id
        MERGE (orig)-[r:ALIAS_OF]->(canon)
        ON CREATE SET r.created_at = timestamp(), r.audit_note = $audit_note
        RETURN elementId(canon) as canon_id
        """)
        originals_param = [{"id": c.node_id} for c in originals]
        await self._run(create_q, {"originals": originals_param, "canonical_id": canonical_id, "dataset_id": canonical_props.get("dataset_id"), "canon_props": canonical_props, "audit_note": audit_note})

    async def soft_link_same_as(self, a_id: int, b_id: int, confidence: float, reason: Optional[str] = None):
        q = Query("""
        MATCH (a) WHERE elementId(a) = $a_id
        MATCH (b) WHERE elementId(b) = $b_id
        MERGE (a)-[r:SAME_AS]->(b)
        ON CREATE SET r.confidence = $confidence, r.reason = $reason, r.created_at = timestamp()
        RETURN r
        """)
        await self._run(q, {"a_id": a_id, "b_id": b_id, "confidence": confidence, "reason": reason})

    # ---------- Destructive merge (audited, reversible) ----------
    async def destructive_merge(self, survivors: MergeCandidate, to_merge: List[MergeCandidate], merge_author: str = "system", min_confidence: float = 0.95) -> Dict[str, Any]:
        """
        Perform a destructive merge using APOC but only when safe:
         - all nodes share a compatible label/type
         - computed aggregate_confidence >= min_confidence
        The function:
         1) Logs a MergeAudit node with merge details and before/after snapshots
         2) Calls apoc.refactor.mergeNodes
         3) Stores merged_from metadata on the survivor
        Returns audit metadata.
        """
        # compute signals
        group = [survivors] + to_merge
        signals = await self.compute_signals(group)
        agg = signals.get("aggregate_confidence", 0.0)
        labels = set(survivors.labels)
        for n in to_merge:
            labels &= set(n.labels)
        if agg < min_confidence:
            raise ValueError(f"Aggregate confidence {agg:.3f} < min_confidence {min_confidence}")

        if not labels:
            raise ValueError("No common label/type across nodes - abort merge")

        # Create audit record pre-merge (node ids and properties)
        audit_id = str(uuid.uuid4())
        pre_snapshot = [{"id": n.node_id, "labels": n.labels, "props": n.properties} for n in group]
        try:
            async with self.driver.session(database=self.config.neo4j_database) as session:
                #  begin_transaction() returns a coroutine, not a context manager -> update to Await the transaction first
                async with await session.begin_transaction() as tx:
                    await tx.run(
                        """
                        CREATE (m:MergeAudit {
                            audit_id: $audit_id,
                            dataset_id: $dataset_id,
                            created_at: timestamp(),
                            author: $author,
                            aggregate_confidence: $agg,
                            nodes_before: $pre_snapshot
                        })
                        """,
                        {"audit_id": audit_id, "dataset_id": survivors.properties.get("dataset_id"), "author": merge_author, "agg": agg, "pre_snapshot": pre_snapshot}
                    )

                    # Try apoc merge (best-effort). If APOC missing, raise and abort.
                    node_ids = [n.node_id for n in group]
                    try:
                        await tx.run(
                            """
                            MATCH (n) WHERE elementId(n) IN $node_ids
                            WITH collect(n) AS nodes
                            CALL apoc.refactor.mergeNodes(nodes, {properties: "combine", mergeRels: true}) YIELD node AS merged
                            SET merged.merged_from = $merged_from, merged.merge_audit = $audit_id
                            RETURN elementId(merged) AS merged_id
                            """,
                            {"node_ids": node_ids, "merged_from": [n.node_id for n in group], "audit_id": audit_id}
                        )
                    except Exception as apoc_ex:
                        # APOC missing or failing -- roll back by raising so transaction aborts.
                        logger.exception("APOC merge failed", exc_info=apoc_ex)
                        raise

                    # record post-merge snapshot (best-effort)
                    await tx.run(
                        """
                        MATCH (m:MergeAudit {audit_id: $audit_id})
                        SET m.completed_at = timestamp()
                        """,
                        {"audit_id": audit_id}
                    )
                    await tx.commit()
            return {"audit_id": audit_id, "aggregate_confidence": agg, "status": "merged"}
        except Exception as e:
            logger.exception("Destructive merge failed")
            return {"audit_id": audit_id, "aggregate_confidence": agg, "status": "failed", "error": str(e)}

    # ---------- Human-review queue ----------
    async def enqueue_for_review(self, group: List[MergeCandidate], signals: Dict[str, Any], reason: Optional[str] = None) -> str:
        q = Query("""
        CREATE (q:MergeReview {
            review_id: $review_id,
            created_at: timestamp(),
            group: $group,
            signals: $signals,
            reason: $reason
        })
        RETURN q.review_id AS id
        """)
        review_id = str(uuid.uuid4())
        group_payload = [{"id": n.node_id, "labels": n.labels, "props": n.properties} for n in group]
        res = await self._run(q, {"review_id": review_id, "group": group_payload, "signals": signals, "reason": reason})
        return review_id
    
    
    async def run(self, dataset_id: str):
        """
        Orchestrate detection and merging in batches. Destructive merges are deferred and only executed
        when confidence and type checks pass.
        """
        groups = await self.find_surface_duplicates(dataset_id)
        # process in batches to control DB load
        for i in range(0, len(groups), self.batch_size):
            batch = groups[i:i + self.batch_size]
            for group in batch:
                signals = await self.compute_signals(group)
                agg = signals.get("aggregate_confidence", 0.0)
                # prefer canonicalization to destructive merge where possible
                if agg >= 0.95:
                    # pick a survivor heuristically: prefer node with most properties
                    survivor = max(group, key=lambda g: len(g.properties or {}))
                    to_merge = [g for g in group if g.node_id != survivor.node_id]
                    try:
                        await self.destructive_merge(survivor, to_merge, merge_author="auto")
                    except Exception:
                        # fallback to canonicalization if destructive merge fails
                        await self.create_alias_relationships("CanonicalEntity", {"dataset_id": dataset_id, "created_by": "auto"}, group, audit_note="fallback-to-canonical")
                elif agg >= 0.75:
                    await self.create_alias_relationships("CanonicalEntity", {"dataset_id": dataset_id, "created_by": "auto"}, group, audit_note="auto-canonical")
                elif agg >= 0.6:
                    # soft-link high-confidence pairs
                    for a, b in itertools.combinations(group, 2):
                        await self.soft_link_same_as(a.node_id, b.node_id, confidence=0.6, reason="auto-soft-link")
                else:
                    await self.enqueue_for_review(group, signals, reason="low-confidence")
        await self.close()

    # ---------- Write operations ----------
    async def write_entities(self, entities: List[EntityNode], graph_id: str) -> List[str]:
        """Write entity nodes to Neo4j using MERGE for idempotency."""
        written_ids = []
        for entity in entities:
            labels = ":".join(entity.labels) if entity.labels else "Entity"
            props = dict(entity.properties)
            props["graph_id"] = graph_id
            props["entity_id"] = entity.id

            q = Query(f"""
                MERGE (n:{labels} {{entity_id: $entity_id}})
                SET n += $props,
                    n.graph_id = $graph_id,
                    n.created_at = COALESCE(n.created_at, timestamp())
                RETURN elementId(n) AS neo_id
            """)
            result = await self._run(q, {
                "entity_id": entity.id,
                "props": props,
                "graph_id": graph_id
            })
            record = await result.single()
            if record:
                written_ids.append(record["neo_id"])
        return written_ids

    async def write_relations(self, relations: List[RelationEdge], graph_id: str) -> int:
        """Write relation edges to Neo4j using MATCH + MERGE."""
        count = 0
        for rel in relations:
            props = dict(rel.properties)
            props["graph_id"] = graph_id

            q = Query("""
                MATCH (source) WHERE source.entity_id = $source_id
                MATCH (target) WHERE target.entity_id = $target_id
                MERGE (source)-[r:`{rel_type}`]->(target)
                SET r += $props,
                    r.graph_id = $graph_id,
                    r.created_at = COALESCE(r.created_at, timestamp())
            """.format(rel_type=rel.relation_type))
            await self._run(q, {
                "source_id": rel.source_id,
                "target_id": rel.target_id,
                "props": props,
                "graph_id": graph_id
            })
            count += 1
        return count

    async def validate_entities(self, entities: List[EntityNode]) -> List[str]:
        """Validate entities and return list of error messages."""
        errors = []
        for entity in entities:
            if not entity.labels:
                errors.append(f"Entity {entity.id}: must have at least one label")
            if not entity.id:
                errors.append(f"Entity: missing id")
            # Validate property types
            for key, value in entity.properties.items():
                if not isinstance(key, str):
                    errors.append(f"Entity {entity.id}: property key must be string, got {type(key)}")
        return errors

    async def validate_relations(self, relations: List[RelationEdge], valid_entity_ids: List[str]) -> List[str]:
        """Validate relations and return list of error messages."""
        errors = []
        valid_ids = set(valid_entity_ids)
        for rel in relations:
            if not rel.source_id:
                errors.append(f"Relation: missing source_id")
            if not rel.target_id:
                errors.append(f"Relation: missing target_id")
            if not rel.relation_type:
                errors.append(f"Relation: missing relation_type")
            if rel.source_id not in valid_ids:
                errors.append(f"Relation: source_id '{rel.source_id}' not in valid entity IDs")
            if rel.target_id not in valid_ids:
                errors.append(f"Relation: target_id '{rel.target_id}' not in valid entity IDs")
        return errors


async def normalize_and_write(entities: List[EntityNode], relations: List[RelationEdge]) -> str:
    """Merge duplicates, validate, and write to Neo4j.

    Args:
        entities: List of EntityNode to write
        relations: List of RelationEdge to write

    Returns:
        graph_id: A unique identifier for the written graph
    """
    config = GraphConfig()
    stage = GraphNormalizationStage(config)
    graph_id = str(uuid.uuid4())

    try:
        # 1. Validate input
        entity_errors = await stage.validate_entities(entities)
        if entity_errors:
            raise ValueError(f"Entity validation errors: {entity_errors}")

        entity_ids = [e.id for e in entities]
        relation_errors = await stage.validate_relations(relations, entity_ids)
        if relation_errors:
            raise ValueError(f"Relation validation errors: {relation_errors}")

        # 2. Merge duplicate entities (by id)
        seen: Dict[str, EntityNode] = {}
        for entity in entities:
            if entity.id in seen:
                # Merge properties, preferring non-empty values
                for key, value in entity.properties.items():
                    if key not in seen[entity.id].properties or seen[entity.id].properties[key] is None:
                        seen[entity.id].properties[key] = value
            else:
                seen[entity.id] = entity
        merged_entities = list(seen.values())

        # 3. Write entities and relations to Neo4j
        await stage.write_entities(merged_entities, graph_id)
        await stage.write_relations(relations, graph_id)

        return graph_id
    finally:
        await stage.close()