"""Dataset-scoped graph snapshot for reconnect (Task 8).

A browser reconnecting mid-build has missed every prior GraphDelta, so Task 9's
WebSocket route sends this snapshot as its opening frame: every stored entity and
relation for the dataset, plus the dataset's full label set so the legend
survives the refresh.

Dataset scoping is a traversal, not a property: `dataset_id` is written on the
`:Document` node (`graph_build._write_documents`), and every extracted concept is
linked to it by `graph_build._link_concepts_to_documents`, which MERGEs
`(e:__Entity__)-[:DERIVED_FROM]->(d:Document {dataset_id})`. llama-index never
copies the source document's metadata onto the entities it extracts, so the
`DERIVED_FROM` hop is the only property an entity can be scoped by.

R5: reads llama-index's own store — `:__Entity__` nodes and the relationships its
`upsert_relations` MERGEs between them (this llama-index stores relations as
relationships via `apoc.merge.relationship`, not as `:__Relation__` nodes). The
second writer (`GraphNormalizationStage`'s `{labels}` + `entity_id` +
ALIAS_OF/SAME_AS) is out of scope.

Read-only: issues no writes.
"""
import asyncio

from llama_index.graph_stores.neo4j import Neo4jPropertyGraphStore

from src.api.graph_stream import GraphDelta
from src.graph.config_graph import GraphConfig

# An entity's type is the non-base node label llama-index adds via
# `apoc.create.addLabels(e, [row.label])`; this is the same expression
# llama-index's own schema / rel-map queries use to project a node's type.
_TYPE = "[l IN labels(e) WHERE NOT l IN ['__Entity__', '__Node__']][0]"

_NODES = f"""
MATCH (e:__Entity__)-[:DERIVED_FROM]->(:Document {{dataset_id: $dataset_id}})
RETURN e.id AS id, e.name AS label, {_TYPE} AS type
ORDER BY id
"""

_EDGES = f"""
MATCH (a:__Entity__)-[r]->(b:__Entity__)
WHERE (a)-[:DERIVED_FROM]->(:Document {{dataset_id: $dataset_id}})
  AND (b)-[:DERIVED_FROM]->(:Document {{dataset_id: $dataset_id}})
RETURN a.id AS source, b.id AS target, type(r) AS label
ORDER BY source, target, label
"""

_STORE: Neo4jPropertyGraphStore | None = None


def _get_store() -> Neo4jPropertyGraphStore:
    """One store per process — a reconnect is frequent; a driver each is not."""
    global _STORE
    if _STORE is None:
        cfg = GraphConfig()
        _STORE = Neo4jPropertyGraphStore(
            username=cfg.neo4j_username,
            password=cfg.neo4j_password,
            url=cfg.neo4j_uri,
            database=cfg.neo4j_database,
        )
    return _STORE


def _read(store: Neo4jPropertyGraphStore, dataset_id: str) -> tuple[list[dict], list[dict]]:
    params = {"dataset_id": dataset_id}
    node_rows = store.structured_query(_NODES, param_map=params)
    edge_rows = store.structured_query(_EDGES, param_map=params)
    nodes = [{"id": r["id"], "label": r["label"], "type": r["type"]} for r in node_rows]
    edges = [{"source": r["source"], "target": r["target"], "label": r["label"]} for r in edge_rows]
    return nodes, edges


async def read_snapshot(dataset_id: str) -> GraphDelta:
    """Every stored entity + relation for `dataset_id`, plus its full label set."""
    nodes, edges = await asyncio.to_thread(_read, _get_store(), dataset_id)
    # The vocabulary: order-stable, de-duplicated distinct types, so the
    # reconnecting client rebuilds its legend from the snapshot alone.
    new_labels = list(dict.fromkeys(n["type"] for n in nodes if n["type"]))
    return GraphDelta(nodes=nodes, edges=edges, new_labels=new_labels)
