from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import uuid
from neo4j import AsyncGraphDatabase
from src.graph.config_graph import GraphConfig
from src.logging.setup_logging import setup_logging
import logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = setup_logging()

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

    def __init__(self, config: GraphConfig):
        self.config = config
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

    async def _run(self, query: str, parameters: dict = None):
        async with self.driver.session(database=self.config.neo4j_database) as session:
            return await session.run(query, parameters or {})

    # ---------- Candidate detection ----------
    async def find_surface_duplicates(self, dataset_id: str) -> List[List[MergeCandidate]]:
        """
        Finds groups of nodes that share the same canonical surface form.
        Returns groups with length > 1.
        """
        q = """
        MATCH (n)
        WHERE n.dataset_id = $dataset_id AND n.name IS NOT NULL
        WITH toLower(trim(n.name)) AS key, collect({
            id: id(n),
            labels: labels(n),
            props: properties(n)
        }) AS nodes
        WHERE size(nodes) > 1
        RETURN key, nodes
        """
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
            neighbor_score = await self._neighbor_label_jaccard(a.node_id, b.node_id)
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
        q = """
        MATCH (a) WHERE id(a) = $id_a
        MATCH (b) WHERE id(b) = $id_b
        // Use pattern matching to find all neighbors
        MATCH (a)-[]-(na)
        MATCH (b)-[]-(nb)
        WITH collect(DISTINCT labels(na)) AS la, collect(DISTINCT labels(nb)) AS lb
        RETURN apoc.coll.toSet(la) AS la_set, apoc.coll.toSet(lb) AS lb_set
        """
        try:
            res = await self._run(q, {"id_a": id_a, "id_b": id_b})
            rec = await res.single()
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
        create_q = f"""
        UNWIND $originals AS o
        MERGE (canon:{canonical_label} {{ canonical_id: $canonical_id, dataset_id: $dataset_id }})
        ON CREATE SET canon += $canon_props
        WITH canon, o
        MATCH (orig) WHERE id(orig) = o.id
        MERGE (orig)-[r:ALIAS_OF]->(canon)
        ON CREATE SET r.created_at = timestamp(), r.audit_note = $audit_note
        RETURN id(canon) as canon_id
        """
        originals_param = [{"id": c.node_id} for c in originals]
        await self._run(create_q, {"originals": originals_param, "canonical_id": canonical_id, "dataset_id": canonical_props.get("dataset_id"), "canon_props": canonical_props, "audit_note": audit_note})

    async def soft_link_same_as(self, a_id: int, b_id: int, confidence: float, reason: Optional[str] = None):
        q = """
        MATCH (a) WHERE id(a) = $a_id
        MATCH (b) WHERE id(b) = $b_id
        MERGE (a)-[r:SAME_AS]->(b)
        ON CREATE SET r.confidence = $confidence, r.reason = $reason, r.created_at = timestamp()
        RETURN r
        """
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
                async with session.begin_transaction() as tx:
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
                            MATCH (n) WHERE id(n) IN $node_ids
                            WITH collect(n) AS nodes
                            CALL apoc.refactor.mergeNodes(nodes, {properties: "combine", mergeRels: true}) YIELD node AS merged
                            SET merged.merged_from = $merged_from, merged.merge_audit = $audit_id
                            RETURN id(merged) AS merged_id
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
        q = """
        CREATE (q:MergeReview {
            review_id: $review_id,
            created_at: timestamp(),
            group: $group,
            signals: $signals,
            reason: $reason
        })
        RETURN q.review_id AS id
        """
        review_id = str(uuid.uuid4())
        group_payload = [{"id": n.node_id, "labels": n.labels, "props": n.properties} for n in group]
        res = await self._run(q, {"review_id": review_id, "group": group_payload, "signals": signals, "reason": reason})
        return review_id