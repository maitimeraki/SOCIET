"""The Document-first node model (P4-T1), tested through the stage's store seam.

Document nodes are MERGEd before the index build, chunk nodes carry
`document_anchor` / `chunk_id`, and every extracted concept gets a
DERIVED_FROM edge to its source Document afterwards. No live Neo4j: the
llama-index imports are stubbed (as in test_graph_build.py) and the stage's
`graph_store` is a call recorder.
"""
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

from src.graph.models_graph import LocalOntology, OntologyMetadata, ProcessedChunk

_DOCUMENT_MERGE = "MERGE (d:Document {document_id: row.document_id})"


class _RecorderStore:
    """The stage's Neo4jPropertyGraphStore seam, recording (query, params) in order."""

    def __init__(self, events):
        self.calls: list[tuple[str, dict]] = []
        self.events = events

    def structured_query(self, query, param_map=None):
        self.calls.append((query, param_map or {}))
        self.events.append("documents" if _DOCUMENT_MERGE in query else "derived_from")
        return []


class _FakeNode:
    def __init__(self, metadata=None):
        self.metadata = metadata or {}


class _FakeIndex:
    def __init__(self, docs=None):
        self.docstore = types.SimpleNamespace(docs=docs or {})


class _FakeDocument:
    def __init__(self, text=None, metadata=None):
        self.text = text
        self.metadata = dict(metadata or {})


class _FakePropertyGraphIndex:
    """`from_documents` hands back the test's index and records the build order."""

    index = _FakeIndex()
    received_docs: list = []
    events = None

    @classmethod
    def from_documents(cls, docs, **kwargs):
        cls.received_docs = list(docs)
        if cls.events is not None:
            cls.events.append("build")
        return cls.index


@pytest.fixture
def graph_env():
    """A stage wired to a recorder store and a fake llama-index core."""
    events: list[str] = []
    store = _RecorderStore(events)
    core = types.ModuleType("llama_index.core")
    core.Document = _FakeDocument
    core.PropertyGraphIndex = _FakePropertyGraphIndex
    core.Settings = types.SimpleNamespace()
    _FakePropertyGraphIndex.index = _FakeIndex()
    _FakePropertyGraphIndex.received_docs = []
    _FakePropertyGraphIndex.events = events

    modules = {
        "llama_index.core": core,
        "llama_index.core.indices": MagicMock(),
        "llama_index.core.indices.property_graph": MagicMock(),
        "llama_index.llms": MagicMock(),
        "llama_index.llms.openai_like": MagicMock(),
        "llama_index.embeddings": MagicMock(),
        "llama_index.embeddings.ollama": MagicMock(),
        "llama_index.graph_stores": MagicMock(),
        "llama_index.graph_stores.neo4j": MagicMock(),
        "llama_index.core.node_parser": MagicMock(),
        "llama_index.core.node_parser.text_splitter": MagicMock(),
        "llama_index.core.settings": MagicMock(),
    }
    with patch.dict(sys.modules, modules), \
            patch("src.graph.graph_build.OpenAILike"), \
            patch("src.graph.graph_build.OllamaEmbedding"), \
            patch("src.graph.graph_build.Neo4jPropertyGraphStore"), \
            patch("src.graph.graph_build.SentenceSplitter"):
        from src.graph.config_graph import GraphConfig
        from src.graph.graph_build import GraphExtractionStage

        stage = GraphExtractionStage(GraphConfig())
        stage.graph_store = store
        yield stage, store, events


def _chunk(chunk_id: str, parent_doc_id: str, tags, index: int = 0) -> ProcessedChunk:
    return ProcessedChunk(
        chunk_id=chunk_id,
        parent_doc_id=parent_doc_id,
        chunk_index=index,
        content_hash=f"hash-{chunk_id}",
        content=f"content of {chunk_id}",
        summary_context="context",
        breadcrumb="docs",
        header_level=1,
        domain_tags=list(tags),
        expertise_level="Technical",
        metadata={},
    )


async def _run(stage, chunks, dataset_id="ds-1"):
    ontology = LocalOntology(metadata=OntologyMetadata(ontology_id="ont-1"))
    return await stage._run_async(dataset_id, chunks, ontology)


@pytest.mark.asyncio
async def test_one_document_row_per_parent_doc_id_with_deduped_tags(graph_env):
    stage, store, _ = graph_env
    await _run(stage, [
        _chunk("c1", "doc-1", ["a", "b"]),
        _chunk("c2", "doc-1", ["b", "c"], index=1),
        _chunk("c3", "doc-2", ["d"]),
    ])

    query, params = store.calls[0]
    assert params["docs"] == [
        {"document_id": "doc-1", "dataset_id": "ds-1", "domain_tags": ["a", "b", "c"]},
        {"document_id": "doc-2", "dataset_id": "ds-1", "domain_tags": ["d"]},
    ]
    assert "UNWIND $docs AS row" in query
    assert _DOCUMENT_MERGE in query
    assert "coalesce(d.domain_tags, [])" in query  # accumulates, never overwrites


@pytest.mark.asyncio
async def test_single_document_batch_writes_one_row(graph_env):
    stage, store, _ = graph_env
    await _run(stage, [_chunk("c1", "doc-9", ["a"])])

    assert store.calls[0][1]["docs"] == [
        {"document_id": "doc-9", "dataset_id": "ds-1", "domain_tags": ["a"]}
    ]


@pytest.mark.asyncio
async def test_repeat_calls_accumulate_to_the_document_wide_union(graph_env):
    """The live path calls the stage one chunk at a time: each call writes only its
    chunk's tags, and the shipped statement accumulates into the node's existing
    list (it reads `d.domain_tags` and filters the tags already there), so two
    calls for one document converge to the deduped union — not last-chunk-wins."""
    stage, store, _ = graph_env
    await _run(stage, [_chunk("c1", "doc-1", ["a", "b"])])
    await _run(stage, [_chunk("c2", "doc-1", ["b", "c"], index=1)])

    merges = [params["docs"][0] for query, params in store.calls if _DOCUMENT_MERGE in query]
    assert [row["domain_tags"] for row in merges] == [["a", "b"], ["b", "c"]]

    query = store.calls[0][0]
    assert "d.domain_tags = coalesce(d.domain_tags, [])" in query  # reads the existing value
    assert "+ [t IN row.domain_tags WHERE NOT t IN coalesce(d.domain_tags, [])]" in query

    # those two writes, under that expression, converge to the union
    accumulated: list[str] = []
    for row in merges:
        accumulated += [tag for tag in row["domain_tags"] if tag not in accumulated]
    assert accumulated == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_empty_batch_writes_nothing(graph_env):
    stage, store, _ = graph_env

    assert await _run(stage, []) == 0
    assert store.calls == []


@pytest.mark.asyncio
async def test_documents_merge_before_the_build_and_derived_from_after(graph_env):
    stage, store, events = graph_env
    _FakePropertyGraphIndex.index = _FakeIndex({"node-1": _FakeNode({"document_anchor": "doc-1"})})

    assert await _run(stage, [_chunk("c1", "doc-1", ["a"])]) == 1
    assert events == ["documents", "build", "derived_from"]


@pytest.mark.asyncio
async def test_llama_document_metadata_carries_the_document_first_keys(graph_env):
    stage, store, _ = graph_env
    await _run(stage, [_chunk("c1", "doc-1", ["a", "b"])])

    md = _FakePropertyGraphIndex.received_docs[0].metadata
    assert md["document_anchor"] == "doc-1"
    assert md["chunk_id"] == "c1"
    assert md["document_id"] == "doc-1"
    assert md["domain_tags"] == ["a", "b"]


@pytest.mark.asyncio
async def test_derived_from_rows_and_cypher_match_the_contract(graph_env):
    stage, store, _ = graph_env
    _FakePropertyGraphIndex.index = _FakeIndex({
        "node-1": _FakeNode({"document_anchor": "doc-1"}),
        "node-2": _FakeNode({"document_anchor": "doc-2"}),
        "node-3": _FakeNode({}),  # no anchor → never invented
    })
    await _run(stage, [_chunk("c1", "doc-1", ["a"]), _chunk("c2", "doc-2", ["b"], index=1)])

    query, params = store.calls[-1]
    assert params["rows"] == [
        {"chunk_id": "node-1", "document_id": "doc-1"},
        {"chunk_id": "node-2", "document_id": "doc-2"},
    ]
    assert "UNWIND $rows AS row" in query
    assert "MATCH (c:__Node__ {id: row.chunk_id})-[:MENTIONS]->(e:__Entity__)" in query
    assert "MATCH (d:Document {document_id: row.document_id})" in query
    assert "MERGE (e)-[:DERIVED_FROM]->(d)" in query


@pytest.mark.asyncio
async def test_no_chunk_anchor_skips_the_derived_from_call(graph_env):
    stage, store, events = graph_env
    _FakePropertyGraphIndex.index = _FakeIndex({"node-1": _FakeNode({"title": "untitled"})})

    await _run(stage, [_chunk("c1", "doc-1", ["a"])])

    assert events == ["documents", "build"]
    assert len(store.calls) == 1
