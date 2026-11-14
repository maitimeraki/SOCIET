"""Two datasets that share an entity name never see each other's properties, edges or chunks.

llama-index keys `__Entity__` nodes by bare name, so an unnamespaced "Apple" from
dataset B would MERGE onto dataset A's node. Entity ids are namespaced
`<dataset_id>:<name>` at construction (`graph_build._scope_entities`); `name` stays
the bare display name.

The unit checks run the real llama-index entity types through `_extract_chunk`
with a stand-in extractor, so they need no Neo4j. The live check runs the full
`GraphExtractionStage` against Neo4j with a stubbed LLM and reads back through the
Task 0.2 scope predicate; it skips when Neo4j is unavailable.
"""

import asyncio
import json
import os
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import neo4j
import pytest
import pytest_asyncio
from llama_index.core.embeddings import MockEmbedding
from llama_index.core.graph_stores.types import (
    KG_NODES_KEY,
    KG_RELATIONS_KEY,
    EntityNode,
    Relation,
)
from llama_index.core.llms import MockLLM
from llama_index.core.schema import TextNode
from llama_index.graph_stores.neo4j import Neo4jPropertyGraphStore

from src.graph.config_graph import GraphConfig
from src.graph.models_graph import LocalOntology, OntologyMetadata, ProcessedChunk
from src.graph.scope import entity_in_dataset

APPLE_TEXT = "Apple ships a phone. Apple partners with Foxconn."
SAMSUNG_TEXT = "Apple lost a lawsuit. Apple sues Samsung."

# Fragment of the chunk text -> the (head, relation, tail) the stub LLM reports.
_TRIPLES = {
    "Apple partners with Foxconn": ("Apple", "PARTNERS_WITH", "Foxconn"),
    "Apple sues Samsung": ("Apple", "SUES", "Samsung"),
}

_ENTITIES = f"""
MATCH (e:__Entity__)
WHERE {entity_in_dataset("e")}
RETURN e.id AS id, e.name AS name
"""

_EDGES = f"""
MATCH (a:__Entity__)-[r]->(b:__Entity__)
WHERE {entity_in_dataset("a")} AND {entity_in_dataset("b")}
RETURN a.id AS source, b.id AS target, type(r) AS label
"""

_CLEANUP_ENTITIES_AND_CHUNKS = """
MATCH (n) WHERE any(p IN $prefixes WHERE n.id STARTS WITH p)
DETACH DELETE n
"""

_CLEANUP_DOCUMENTS = """
MATCH (d:Document) WHERE d.dataset_id IN $datasets
DETACH DELETE d
"""


def _new_dataset_id(label: str) -> str:
    return f"iso-{uuid.uuid4().hex[:12]}-{label}"


def _ontology() -> LocalOntology:
    return LocalOntology(
        metadata=OntologyMetadata(ontology_id="test-ontology"),
        entity_types=[],
        relation_types=[],
    )


def _chunk(dataset_id: str, text: str) -> ProcessedChunk:
    return ProcessedChunk(
        chunk_id=f"{dataset_id}-chunk-0",
        parent_doc_id=f"{dataset_id}-doc",
        chunk_index=0,
        content_hash="hash-0",
        content=text,
        summary_context="summary",
        breadcrumb="doc",
        domain_tags=["test"],
        expertise_level="Technical",
    )


def _stage_without_neo4j():
    import src.graph.graph_build as gb

    with (
        patch.object(gb, "OpenAILike", MagicMock()),
        patch.object(gb, "OllamaEmbedding", MagicMock()),
        patch.object(gb, "Neo4jPropertyGraphStore", MagicMock()),
    ):
        return gb.GraphExtractionStage(GraphConfig())


def _extractor_reporting(triples):
    """A stand-in extractor: stamps the entities and relations llama-index's own
    extractor would, built from the real `EntityNode` and `Relation` types."""

    def _extract(nodes):
        for node in nodes:
            entities, relations = [], []
            for head, relation, tail in triples:
                h = EntityNode(name=head, label="Company")
                t = EntityNode(name=tail, label="Company")
                entities.extend([h, t])
                relations.append(
                    Relation(label=relation, source_id=h.id, target_id=t.id)
                )
            node.metadata[KG_NODES_KEY] = entities
            node.metadata[KG_RELATIONS_KEY] = relations
        return nodes

    return _extract


def _extract(stage, dataset_id: str, triples):
    doc = SimpleNamespace(metadata={})
    _, _, _, delta_nodes, delta_edges = stage._extract_chunk(
        doc, [_extractor_reporting(triples)], dataset_id=dataset_id
    )
    return delta_nodes, delta_edges


class TestEntityIdsAreNamespacedAtConstruction:
    """Non-live: the entity-construction path with a mocked extractor."""

    def test_entity_ids_carry_the_dataset_namespace(self):
        stage = _stage_without_neo4j()
        nodes, _ = _extract(stage, "ds-unit", [("Apple", "PARTNERS_WITH", "Foxconn")])
        assert {n["id"] for n in nodes} == {"ds-unit:Apple", "ds-unit:Foxconn"}

    def test_relation_endpoints_follow_the_namespaced_ids(self):
        stage = _stage_without_neo4j()
        _, edges = _extract(stage, "ds-unit", [("Apple", "PARTNERS_WITH", "Foxconn")])
        assert [(e["source"], e["target"]) for e in edges] == [
            ("ds-unit:Apple", "ds-unit:Foxconn")
        ]

    def test_display_name_stays_bare(self):
        stage = _stage_without_neo4j()
        nodes, _ = _extract(stage, "ds-unit", [("Apple", "PARTNERS_WITH", "Foxconn")])
        assert {n["label"] for n in nodes} == {"Apple", "Foxconn"}

    def test_same_name_in_two_datasets_gets_distinct_ids(self):
        stage = _stage_without_neo4j()
        a, _ = _extract(stage, "ds-A", [("Apple", "SUES", "Samsung")])
        b, _ = _extract(stage, "ds-B", [("Apple", "PARTNERS_WITH", "Foxconn")])
        assert {n["id"] for n in a}.isdisjoint({n["id"] for n in b})

    def test_llama_index_extractor_with_stub_llm_namespaces_ids(self):
        stage = _stage_without_neo4j()
        stage.llm = _TripleLLM()
        extractors = stage._build_extractors(_ontology())
        _, _, _, nodes, edges = stage._extract_chunk(
            TextNode(text=APPLE_TEXT), extractors, dataset_id="ds-unit"
        )
        assert {n["id"] for n in nodes} == {"ds-unit:Apple", "ds-unit:Foxconn"}
        assert [(e["source"], e["target"]) for e in edges] == [
            ("ds-unit:Apple", "ds-unit:Foxconn")
        ]

    def test_empty_dataset_id_is_refused(self):
        stage = _stage_without_neo4j()
        with pytest.raises(ValueError):
            _extract(stage, "", [("Apple", "SUES", "Samsung")])

    def test_dataset_id_containing_the_separator_is_refused(self):
        stage = _stage_without_neo4j()
        with pytest.raises(ValueError):
            _extract(stage, "ds:a", [("Apple", "SUES", "Samsung")])


class _TripleLLM(MockLLM):
    """Stub extraction LLM: reports the triples whose fragment the chunk contains."""

    async def apredict(self, prompt, **kwargs) -> str:
        text = kwargs["text"]
        triples = [
            {
                "head": h,
                "head_type": "Company",
                "relation": r,
                "tail": t,
                "tail_type": "Company",
            }
            for fragment, (h, r, t) in _TRIPLES.items()
            if fragment in text
        ]
        return json.dumps(triples)


@pytest_asyncio.fixture
async def live_store():
    """A Neo4j store for reads and cleanup; skips the test when Neo4j is unavailable.

    Every dataset a test builds through `build_dataset` is recorded, and its nodes
    are DETACH DELETEd on teardown.
    """
    # A standalone server is reached over bolt://. NEO4J_URI (which the env loader
    # may set from .env) overrides the default, but a neo4j:// routing scheme is
    # rewritten to bolt://, since routing fails against a standalone server.
    uri = os.getenv("NEO4J_URI") or "bolt://localhost:7687"
    uri = "bolt://" + uri[len("neo4j://") :] if uri.startswith("neo4j://") else uri
    cfg = GraphConfig(neo4j_uri=uri)
    try:
        with neo4j.GraphDatabase.driver(
            cfg.neo4j_uri,
            auth=(cfg.neo4j_username, cfg.neo4j_password),
            connection_timeout=5,
        ) as driver:
            driver.verify_connectivity()
    except Exception as exc:
        pytest.skip(f"Neo4j not available at {cfg.neo4j_uri}: {exc}")
    store = Neo4jPropertyGraphStore(
        username=cfg.neo4j_username,
        password=cfg.neo4j_password,
        url=cfg.neo4j_uri,
        database=cfg.neo4j_database,
    )

    built: list[str] = []
    yield _LiveStore(store, cfg, built)

    if built:
        prefixes = [f"{ds}:" for ds in built] + [f"{ds}-" for ds in built]
        store.structured_query(
            _CLEANUP_ENTITIES_AND_CHUNKS, param_map={"prefixes": prefixes}
        )
        store.structured_query(_CLEANUP_DOCUMENTS, param_map={"datasets": built})
    store.close()


class _LiveStore:
    """Scoped reads over the live store, through the Task 0.2 predicates."""

    def __init__(self, store, cfg: GraphConfig, built: list[str]):
        self.store = store
        self.config = cfg
        self._built = built

    def track(self, dataset_id: str) -> None:
        self._built.append(dataset_id)

    async def entities(self, dataset_id: str) -> list[dict]:
        return await asyncio.to_thread(self._read, _ENTITIES, dataset_id)

    async def edges(self, dataset_id: str) -> list[dict]:
        return await asyncio.to_thread(self._read, _EDGES, dataset_id)

    def _read(self, query: str, dataset_id: str) -> list[dict]:
        return self.store.structured_query(query, param_map={"dataset_id": dataset_id})


@pytest_asyncio.fixture
async def build_dataset(live_store):
    """Run the real `GraphExtractionStage` for one dataset with a stubbed LLM.

    Only the network edges are replaced: the extraction LLM (`_TripleLLM`), the
    embedding model, and the metering wrap. Writes go to the live Neo4j store.
    """
    import src.graph.graph_build as gb

    async def _build(dataset_id: str, text: str) -> None:
        live_store.track(dataset_id)
        with (
            patch.object(gb, "OpenAILike", lambda **_: _TripleLLM()),
            patch.object(gb, "OllamaEmbedding", lambda **_: MockEmbedding(embed_dim=4)),
            patch.object(gb, "wrap_with_metering", lambda llm, **_: llm),
        ):
            stage = gb.GraphExtractionStage(live_store.config)
            try:
                await stage.run(dataset_id, [_chunk(dataset_id, text)], _ontology())
            finally:
                stage.close()

    return _build


@pytest.mark.asyncio
async def test_same_name_in_two_datasets_stays_separate(live_store, build_dataset):
    ds_a, ds_b = _new_dataset_id("A"), _new_dataset_id("B")
    await build_dataset(ds_a, APPLE_TEXT)
    await build_dataset(ds_b, SAMSUNG_TEXT)

    a = await live_store.entities(ds_a)
    b = await live_store.entities(ds_b)

    assert {n["id"] for n in a}.isdisjoint({n["id"] for n in b})
    assert "Samsung" not in {n["name"] for n in a}
    assert "Foxconn" not in {n["name"] for n in b}


@pytest.mark.asyncio
async def test_live_entity_ids_are_namespaced(live_store, build_dataset):
    ds_a = _new_dataset_id("A")
    await build_dataset(ds_a, APPLE_TEXT)

    a = await live_store.entities(ds_a)

    assert {n["id"] for n in a} == {f"{ds_a}:Apple", f"{ds_a}:Foxconn"}


@pytest.mark.asyncio
async def test_live_edges_stay_inside_their_dataset(live_store, build_dataset):
    ds_a, ds_b = _new_dataset_id("A"), _new_dataset_id("B")
    await build_dataset(ds_a, APPLE_TEXT)
    await build_dataset(ds_b, SAMSUNG_TEXT)

    a_edges = await live_store.edges(ds_a)

    assert [(e["source"], e["target"]) for e in a_edges] == [
        (f"{ds_a}:Apple", f"{ds_a}:Foxconn")
    ]
