"""Golden-path acceptance check for the Graph Foundation plan (Task 8).

Proves the two bugs the foundation closed, end to end:

* Bug 1 — a measure the model emitted as a node ("$2.5 billion") is a *literal*,
  not a referenceable entity: it must land in a typed property slot and leave no
  node behind (spec §13.1).
* Bug 2 — that value must land on the SURVIVING real→real edge's declared slot,
  not depend on the model volunteering a property (spec §13.2).

The unit checks prove the parts (`value_type == "money"`, `is_literal_value`);
the end-to-end checks run `GraphExtractionStage._extract_chunk` over a fake
extractor and assert the delta the live path would emit.
"""
import pytest
from unittest.mock import MagicMock, patch

from src.graph.models_graph import LocalOntology, OntologyMetadata


# Mock heavy llama_index imports before importing graph_build — the exact seam
# tests/graph/test_graph_build.py pins: any module that already imported
# graph_build (e.g. graph_snapshot) binds the REAL classes into its namespace,
# so re-point graph_build's own module-level names too. The stage must never
# dial a real Neo4j whatever the import order.
@pytest.fixture(autouse=True)
def mock_llama_index():
    with patch.dict('sys.modules', {
        'llama_index.core': MagicMock(),
        'llama_index.llms': MagicMock(),
        'llama_index.llms.openai_like': MagicMock(),
        'llama_index.embeddings': MagicMock(),
        'llama_index.embeddings.ollama': MagicMock(),
        'llama_index.graph_stores': MagicMock(),
        'llama_index.graph_stores.neo4j': MagicMock(),
        'llama_index.core.node_parser': MagicMock(),
        'llama_index.core.node_parser.text_splitter': MagicMock(),
        'llama_index.core.indices': MagicMock(),
        'llama_index.core.indices.property_graph': MagicMock(),
        'llama_index.core.settings': MagicMock(),
        'llama_index.core.graph_stores': MagicMock(),
        'llama_index.core.graph_stores.types': MagicMock(),
    }):
        import src.graph.graph_build as gb
        with patch.object(gb, "OpenAILike", MagicMock()), \
             patch.object(gb, "OllamaEmbedding", MagicMock()), \
             patch.object(gb, "Neo4jPropertyGraphStore", MagicMock()), \
             patch.object(gb, "SentenceSplitter", MagicMock()):
            yield


def _pin_kg_keys():
    """`_extract_chunk` reads KG_NODES_KEY/KG_RELATIONS_KEY from the mocked
    `llama_index.core.graph_stores.types`; pin them to their real string values
    so this test's metadata bag is the one the code reads."""
    import sys

    types = sys.modules['llama_index.core.graph_stores.types']
    types.KG_NODES_KEY = "nodes"
    types.KG_RELATIONS_KEY = "relations"


def _stage():
    from src.graph.config_graph import GraphConfig
    from src.graph.graph_build import GraphExtractionStage

    return GraphExtractionStage(GraphConfig())


def _ontology(**tiny):
    """The full chain the pipeline runs: flat LLM output → structured props →
    hydrated production schema → LocalOntology."""
    from src.graph.ontology import _structured_properties
    from src.utils.hydrate_ontology import hydrate_ontology

    return LocalOntology.model_validate(
        hydrate_ontology(_structured_properties(tiny))
    )


def test_ontology_hydrates_literal_as_money_slot():
    """The ontology half: a `price: money` declaration hydrates to `value_type ==
    money`, and the measure classifier agrees the value is a literal (§13.1)."""
    from src.graph.literals import is_literal_value

    onto = _ontology(
        entity_types=[{"type_name": "Company", "description": "",
                       "properties": ["revenue: money: annual revenue"]}],
        relation_types=[{"type_name": "ACQUIRED", "description": "",
                         "properties": ["price: money: deal value"],
                         "source_entity_types": ["Company"],
                         "target_entity_types": ["Company"]}],
    )

    assert onto.relation_types[0].properties[0].value_type == "money"
    assert is_literal_value("$2.5 billion") is True
    assert is_literal_value("WholeFoods") is False


def test_extract_chunk_routes_leaked_value_onto_real_to_real_edge():
    """§13.2 end to end: the extractor leaked "$2.5 billion" as a node AND gave
    the real→real ACQUIRED edge a declared `price: money` slot. The value lands
    on that surviving edge; no node named "$2.5 billion" survives and the
    literal's own PRICE edge is dropped."""
    _pin_kg_keys()
    stage = _stage()

    amazon = MagicMock(); amazon.id = "e2"; amazon.name = "Amazon"; amazon.label = "Company"; amazon.properties = {}
    whole = MagicMock(); whole.id = "e3"; whole.name = "WholeFoods"; whole.label = "Company"; whole.properties = {}
    money = MagicMock(); money.id = "e1"; money.name = "$2.5 billion"; money.label = "Money"
    acquired = MagicMock(); acquired.source_id = "e2"; acquired.target_id = "e3"; acquired.label = "ACQUIRED"; acquired.properties = {}
    price_edge = MagicMock(); price_edge.source_id = "e3"; price_edge.target_id = "e1"; price_edge.label = "PRICE"; price_edge.properties = {}

    def _extractor(nodes):
        nodes[0].metadata = {"nodes": [amazon, whole, money], "relations": [acquired, price_edge]}
        return nodes

    onto = _ontology(
        relation_types=[{"type_name": "ACQUIRED", "description": "",
                         "properties": ["price: money: deal value"],
                         "source_entity_types": ["Company"],
                         "target_entity_types": ["Company"]}],
    )

    doc = MagicMock(); doc.metadata = {}
    _, _, _, delta_nodes, delta_edges = stage._extract_chunk(
        doc, [_extractor], onto.relation_types
    )

    assert all(n["label"] != "$2.5 billion" for n in delta_nodes)   # (a) literal node gone
    acquired_edge = next(e for e in delta_edges if e["label"] == "ACQUIRED")
    assert acquired_edge["properties"]["price"] == {"amount": 2.5e9, "currency": "USD"}   # (b) coerced onto surviving edge


def test_extract_chunk_routes_value_onto_surviving_entity():
    """Entity fallback end to end: the literal's ONLY real neighbour is the
    Amazon entity, so the value lands on that entity (under the relation's
    lowercased label) and the dangling edge is dropped (§13.1)."""
    _pin_kg_keys()
    stage = _stage()

    amazon = MagicMock(); amazon.id = "e2"; amazon.name = "Amazon"; amazon.label = "Company"; amazon.properties = {}
    money = MagicMock(); money.id = "e1"; money.name = "$2.5 billion"; money.label = "Money"
    rel = MagicMock(); rel.source_id = "e2"; rel.target_id = "e1"; rel.label = "ACQUIRED"; rel.properties = {}

    def _extractor(nodes):
        nodes[0].metadata = {"nodes": [amazon, money], "relations": [rel]}
        return nodes

    doc = MagicMock(); doc.metadata = {}
    _, _, _, delta_nodes, delta_edges = stage._extract_chunk(doc, [_extractor])

    assert all(n["label"] != "$2.5 billion" for n in delta_nodes)   # literal node gone
    assert delta_edges == []                                        # dangling edge removed
    assert delta_nodes[0]["properties"]["acquired"] == {"amount": 2.5e9, "currency": "USD"}
