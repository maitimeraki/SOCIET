"""Task 7 — per-chunk incremental insert with live GraphDelta publishing.

No live LLM/Neo4j: llama_index is mocked at the module level exactly as
tests/graph/test_graph_build.py does, and the two per-chunk seams
(`_build_extractors`, `_extract_chunk`) are stubbed.
"""
import threading

import pytest
from unittest.mock import MagicMock, patch

from src.graph.models_graph import (
    EntityTypeDefinition,
    LocalOntology,
    OntologyMetadata,
    ProcessedChunk,
    RelationTypeDefinition,
)


# Mock heavy llama_index imports before importing graph_build. The two
# graph_stores entries are needed because `_proposed_labels` / `_delta_payload`
# import KG_NODES_KEY / KG_RELATIONS_KEY lazily — both the code under test and
# the test's fake extractor must get the *same* key objects.
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
        yield


class _FakeEntity:
    def __init__(self, name, label):
        self.name = name
        self.label = label
        self.id = f"{label}:{name}"


class _FakeRelation:
    def __init__(self, label, source_id, target_id):
        self.label = label
        self.source_id = source_id
        self.target_id = target_id


def _chunk(i):
    return ProcessedChunk(
        chunk_id=f"chunk-{i}",
        parent_doc_id="doc-1",
        chunk_index=i,
        content_hash=f"hash{i}",
        content=f"Pre-split chunk body number {i}.",
        summary_context="Software architecture overview",
        breadcrumb="docs/architecture",
        header_level=1,
        domain_tags=["software"],
        expertise_level="Technical",
        metadata={"title": "System Architecture"},
    )


def _ontology():
    return LocalOntology(
        metadata=OntologyMetadata(ontology_id="task7"),
        entity_types=[EntityTypeDefinition(type_name="Person")],
        relation_types=[RelationTypeDefinition(type_name="RELATED_TO")],
    )


def _stage(config=None):
    from src.graph.config_graph import GraphConfig
    from src.graph.graph_build import GraphExtractionStage

    with patch('src.graph.graph_build.OpenAILike'), \
         patch('src.graph.graph_build.OllamaEmbedding'), \
         patch('src.graph.graph_build.Neo4jPropertyGraphStore'), \
         patch('src.graph.graph_build.SentenceSplitter'):
        return GraphExtractionStage(config or GraphConfig())


def _binding_index(n):
    """The MagicMock `PropertyGraphIndex(...)` returns, with a sized docstore."""
    import sys
    core = sys.modules['llama_index.core']
    index = core.PropertyGraphIndex.return_value
    index.docstore.docs = {f"node-{i}": MagicMock() for i in range(n)}
    return index


def _fake_extractor():
    """One extraction per chunk: entities Person + Novel, one RELATED_TO edge."""
    from llama_index.core.graph_stores.types import KG_NODES_KEY, KG_RELATIONS_KEY

    def _extract(nodes):
        for node in nodes:
            metadata = dict(getattr(node, "metadata", None) or {})
            metadata[KG_NODES_KEY] = [
                _FakeEntity("Alpha", "Person"),
                _FakeEntity("Beta", "Novel"),  # a label the vocabulary does not carry
            ]
            metadata[KG_RELATIONS_KEY] = [
                _FakeRelation("RELATED_TO", "Person:Alpha", "Novel:Beta")
            ]
            node.metadata = metadata
        return nodes

    return _extract


def _identity_extractor(nodes):
    """Pass-through extractor: extraction completes, harvest finds no triples."""
    return nodes


class TestIncrementalInsertDeltas:
    @pytest.mark.asyncio
    async def test_one_insert_and_one_publish_per_chunk_new_label_once(self):
        chunks = [_chunk(i) for i in range(3)]
        stage = _stage()
        index = _binding_index(len(chunks))

        with patch.object(stage, "_build_extractors", return_value=[_fake_extractor()]), \
             patch('src.graph.graph_build.publish') as mock_publish:
            count = await stage.run("ds", chunks, _ontology(), job_id="job-1")

        # one insert per chunk — the graph store receives exactly len(chunks)
        assert index.insert_nodes.call_count == len(chunks)
        # one delta per chunk
        assert mock_publish.call_count == len(chunks)
        assert count == len(chunks)

        deltas = [call.args[1] for call in mock_publish.call_args_list]
        assert all(call.args[0] == "job-1" for call in mock_publish.call_args_list)
        assert sorted(d.chunk_id for d in deltas) == ["chunk-0", "chunk-1", "chunk-2"]

        # "Novel" is new on first sighting and only on the chunk that saw it first
        novel = [d for d in deltas if "Novel" in d.new_labels]
        assert len(novel) == 1
        assert novel[0].new_labels == ["Novel"]

        # the delta carries the extracted nodes/edges, not the popped metadata
        assert novel[0].nodes and novel[0].edges
        assert {n["id"] for n in novel[0].nodes} == {"Person:Alpha", "Novel:Beta"}

    @pytest.mark.asyncio
    async def test_progress_is_monotone_and_reaches_one(self):
        chunks = [_chunk(i) for i in range(3)]
        stage = _stage()
        _binding_index(len(chunks))

        with patch.object(stage, "_build_extractors", return_value=[_fake_extractor()]), \
             patch('src.graph.graph_build.publish') as mock_publish:
            await stage.run("ds", chunks, _ontology(), job_id="job-1")

        progress = sorted(call.args[1].progress for call in mock_publish.call_args_list)
        assert progress == pytest.approx([1 / 3, 2 / 3, 1.0])

    @pytest.mark.asyncio
    async def test_no_job_id_publishes_nothing(self):
        chunks = [_chunk(i) for i in range(2)]
        stage = _stage()
        _binding_index(len(chunks))

        with patch.object(stage, "_build_extractors", return_value=[_fake_extractor()]), \
             patch('src.graph.graph_build.publish') as mock_publish:
            await stage.run("ds", chunks, _ontology())

        mock_publish.assert_not_called()


class TestSlidingWindow:
    @pytest.mark.asyncio
    async def test_window_stays_full_and_never_exceeds_parallelism(self):
        from src.graph.config_graph import GraphConfig

        chunks = [_chunk(i) for i in range(4)]
        stage = _stage(GraphConfig(chunk_parallelism=2))
        _binding_index(len(chunks))

        lock = threading.Lock()
        barrier = threading.Barrier(2, timeout=10)
        state = {"active": 0, "peak": 0, "starts": 0}

        def _gated_extract(self, doc, extractors):
            with lock:
                state["active"] += 1
                state["peak"] = max(state["peak"], state["active"])
                state["starts"] += 1
            try:
                # Rendezvous: if fewer than 2 chunks are ever in flight this
                # blocks until the timeout and raises BrokenBarrierError, which
                # `fut.result()` re-raises — so a serial window fails loudly.
                barrier.wait()
            finally:
                with lock:
                    state["active"] -= 1
            return (doc, [], [], [], [])

        with patch.object(type(stage), "_extract_chunk", _gated_extract), \
             patch('src.graph.graph_build.publish') as mock_publish:
            await stage.run("ds", chunks, _ontology(), job_id="job-1")

        assert state["starts"] == len(chunks)      # every chunk ran
        assert state["peak"] == 2                  # window filled to the limit
        assert state["peak"] <= 2                  # and never exceeded it
        assert mock_publish.call_count == len(chunks)


class TestSerialisedInserts:
    @pytest.mark.asyncio
    async def test_concurrent_chunks_never_overlap_a_store_write(self):
        """Extraction runs concurrently, but the store write never overlaps.

        `_insert_lock` serialises `index.insert_nodes`; without it two of the
        window's chunks could write the shared index at once, so "an entity in
        two chunks yields ONE node" would rest on the store converging under a
        race. The 20 ms sleep widens the window a concurrent write would need.
        """
        import sys
        import time
        import types

        chunks = [_chunk(i) for i in range(4)]
        stage = _stage()

        lock = threading.Lock()
        state = {"active": 0, "peak": 0, "calls": 0, "overlap": False}

        class _RecorderIndex:
            def __init__(self):
                self.docstore = types.SimpleNamespace(
                    docs={f"node-{i}": object() for i in range(len(chunks))}
                )

            def insert_nodes(self, nodes):
                with lock:
                    state["active"] += 1
                    state["calls"] += 1
                    state["peak"] = max(state["peak"], state["active"])
                    if state["active"] > 1:
                        state["overlap"] = True
                time.sleep(0.02)
                with lock:
                    state["active"] -= 1

        core = sys.modules["llama_index.core"]
        core.PropertyGraphIndex.return_value = _RecorderIndex()

        with patch.object(stage, "_build_extractors", return_value=[_identity_extractor]), \
             patch('src.graph.graph_build.publish') as mock_publish:
            await stage.run("ds", chunks, _ontology(), job_id="job-1")

        assert state["calls"] == len(chunks)
        assert state["overlap"] is False   # two writes were never concurrent
        assert state["peak"] == 1          # strictly serialised
        assert mock_publish.call_count == len(chunks)
