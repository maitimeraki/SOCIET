"""Recall fixes: explicit extraction caps, and no ontology detail silently dropped.

Three separate recall losses this file pins down:
  (a) `_structured_properties` kept a property string only if it contained a
      colon — a bare name was thrown away.
  (b) `hydrate_ontology` truncated relation source/target entity-type lists to
      their first entry.
  (c) both extractors carried a hardcoded cap (10 on the simple one, an
      unset library default on the dynamic one) instead of a configured value.
"""
import sys
from unittest.mock import MagicMock, patch

import pytest

from src.graph.models_graph import LocalOntology, OntologyMetadata
from src.graph.ontology import _structured_properties
from src.utils.hydrate_ontology import hydrate_ontology


# Mock heavy llama_index imports before importing graph_build, mirroring
# tests/graph/test_graph_build.py.
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
        'llama_index.core.indices': MagicMock(),
        'llama_index.core.indices.property_graph': MagicMock(),
        'llama_index.core.settings': MagicMock(),
    }):
        yield


class TestNoColonPropertiesSurvive:
    """A property string with no colon is a bare name, not a reason to drop it."""

    def test_entity_property_without_colon_survives(self):
        data = {
            "entity_types": [
                {"type_name": "Person", "properties": ["no colon here"]},
            ],
            "relation_types": [],
        }

        _structured_properties(data)

        assert data["entity_types"][0]["properties"] == [
            {"name": "no colon here", "description": ""}
        ]

    def test_relation_property_without_colon_survives(self):
        data = {
            "entity_types": [],
            "relation_types": [
                {"type_name": "WORKS_FOR", "properties": ["no colon here"]},
            ],
        }

        _structured_properties(data)

        assert data["relation_types"][0]["properties"] == [
            {"name": "no colon here", "description": ""}
        ]

    def test_colon_property_still_parsed(self):
        """The with-colon path is unchanged."""
        data = {
            "entity_types": [
                {"type_name": "Person", "properties": ["name: brief description"]},
            ],
            "relation_types": [],
        }

        _structured_properties(data)

        assert data["entity_types"][0]["properties"] == [
            {"name": "name", "description": "brief description"}
        ]


class TestHydrateKeepsAllEntityTypes:
    """The relation's source/target entity-type lists must be copied whole."""

    def test_hydrate_preserves_two_source_and_target_types(self):
        tiny = {
            "entity_types": [],
            "relation_types": [
                {
                    "type_name": "WORKS_FOR",
                    "source_entity_types": ["Person", "Employee"],
                    "target_entity_types": ["Company", "Organization"],
                    "properties": [],
                },
            ],
        }

        out = hydrate_ontology(tiny)
        rel = out["relation_types"][0]

        assert rel["source_entity_types"] == ["Person", "Employee"]
        assert rel["target_entity_types"] == ["Company", "Organization"]


class TestExtractorCaps:
    """Both extractors read their cap from GraphConfig, not a hardcoded literal."""

    def _stage(self):
        from src.graph.config_graph import GraphConfig
        from src.graph.graph_build import GraphExtractionStage

        with patch('src.graph.graph_build.OpenAILike'), \
             patch('src.graph.graph_build.OllamaEmbedding'), \
             patch('src.graph.graph_build.Neo4jPropertyGraphStore'), \
             patch('src.graph.graph_build.SentenceSplitter'):
            return GraphExtractionStage(GraphConfig())

    def test_both_extractors_use_configured_cap(self):
        from src.graph.config_graph import GraphConfig

        stage = self._stage()
        ontology = LocalOntology(
            metadata=OntologyMetadata(ontology_id="test-ontology"),
            entity_types=[],
            relation_types=[],
        )

        stage._build_extractors(ontology)

        cap = GraphConfig().extraction_max_triplets_per_chunk
        property_graph = sys.modules['llama_index.core.indices.property_graph']
        assert (
            property_graph.SimpleLLMPathExtractor.call_args.kwargs["max_paths_per_chunk"]
            == cap
        )
        assert (
            property_graph.DynamicLLMPathExtractor.call_args.kwargs["max_triplets_per_chunk"]
            == cap
        )
