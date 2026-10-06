"""Tests for api_server chunking and unified job execution.

Chunking is sentence-aware (shared owner: chunkProcessor.split_text_sentences);
these assertions fail under the retired fixed character windows.
"""
from unittest.mock import AsyncMock

import pytest

import src.api.api_server as api_server
from src.api.api_server import _chunk_documents
from src.graph.models_graph import GlobalInputDocument, LocalOntology


SENTENCES = [
    f"Fact number {i:02d} about the migration plan states that the northern region will grow slowly."
    for i in range(10)
]
TEXT = " ".join(SENTENCES)
CHUNK_SIZE = 64  # SentenceSplitter token budget
OVERLAP = 32


def _document(document_id: str, text: str, metadata: dict = None) -> GlobalInputDocument:
    return GlobalInputDocument(
        document_id=document_id,
        source_type="text",
        text=text,
        metadata=metadata or {},
    )


@pytest.mark.asyncio
async def test_chunks_are_sentence_aware_and_indexed_per_document():
    documents = [
        _document("doc-a", TEXT, {"title": "Doc A"}),
        _document("doc-b", TEXT, {"source_document": "doc_b.txt"}),
    ]

    chunks = await _chunk_documents(documents, CHUNK_SIZE, OVERLAP)

    by_document = {}
    for chunk in chunks:
        by_document.setdefault(chunk.parent_doc_id, []).append(chunk)

    assert set(by_document) == {"doc-a", "doc-b"}
    for group in by_document.values():
        assert len(group) > 2
        assert [c.chunk_index for c in group] == list(range(len(group)))
        # Sentence-aware: fixed character windows would cut chunks mid-sentence.
        for chunk in group[:-1]:
            assert chunk.content.endswith("."), f"cut mid-sentence: ...{chunk.content[-40:]!r}"

    assert {c.metadata["source_document"] for c in by_document["doc-a"]} == {"Doc A"}
    assert {c.metadata["source_document"] for c in by_document["doc-b"]} == {"doc_b.txt"}


@pytest.mark.asyncio
async def test_whitespace_only_text_produces_no_chunks():
    documents = [_document("blank", "   \n\t "), _document("real", "One short sentence.")]

    chunks = await _chunk_documents(documents, CHUNK_SIZE, OVERLAP)

    assert {c.parent_doc_id for c in chunks} == {"real"}
    assert len(chunks) == 1
    assert chunks[0].chunk_index == 0


@pytest.mark.asyncio
async def test_missing_metadata_falls_back_to_unknown_source():
    chunks = await _chunk_documents([_document("doc-c", "One short sentence.")], CHUNK_SIZE, OVERLAP)

    assert len(chunks) == 1
    assert chunks[0].chunk_index == 0
    assert chunks[0].parent_doc_id == "doc-c"
    assert chunks[0].metadata["source_document"] == "unknown"


def _ontology(type_name: str) -> LocalOntology:
    return LocalOntology.model_validate({
        "metadata": {"ontology_id": f"onto-{type_name.lower()}"},
        "entity_types": [{
            "type_name": type_name,
            "description": type_name,
            "properties": [{"name": "name", "description": "n"}],
        }],
        "relation_types": [{
            "type_name": "RELATED_TO",
            "description": "generic",
            "source_entity_types": [],
            "target_entity_types": [],
            "properties": [],
        }],
    })


class _CountingDiscovery:
    def __init__(self, *args, **kwargs):
        self.calls = []

    async def run(self, documents, sample_size=1):
        self.calls.append((documents[0].chunk_id, len(documents), sample_size))
        return _ontology(f"TYPE_{len(self.calls)}")


class _FakeExtraction:
    def __init__(self, *args, **kwargs):
        self.calls = []

    async def run(self, dataset_id, documents, ontology):
        self.calls.append(documents[0].chunk_id)
        return 1


def _docs() -> list[GlobalInputDocument]:
    # Sentence-rich and long: 2+ chunks per doc at the default 2000-token chunk size.
    return [
        GlobalInputDocument(document_id=f"d{i}", source_type="text", text="alpha beta gamma delta. " * 800, metadata={})
        for i in range(2)
    ]


def _patch_build_pipeline(monkeypatch, discovery, extraction):
    monkeypatch.setattr(api_server, "OntologyDiscoveryStage", lambda **kwargs: discovery)
    # Extraction is imported lazily inside _execute_unified_job (api_server.py:262),
    # so patch it where that import resolves it from.
    monkeypatch.setattr("src.graph.graph_build.GraphExtractionStage", lambda cfg: extraction)
    # Real normalization would hit Neo4j at the end of a build job.
    monkeypatch.setattr(api_server, "GraphNormalizationStage", lambda cfg: AsyncMock())
    monkeypatch.setattr(api_server, "_persist_run", AsyncMock())


@pytest.mark.asyncio
async def test_ontology_job_runs_one_discovery_per_chunk_and_merges(monkeypatch):
    discovery = _CountingDiscovery()
    _patch_build_pipeline(monkeypatch, discovery, _FakeExtraction())
    job_id = "test-onto-once"
    api_server.RUNS[job_id] = {"job_id": job_id, "result": None}

    await api_server._execute_unified_job(job_id, "ontology", "ds1", _docs())

    result = api_server.RUNS[job_id]["result"]
    assert result["chunks_total"] > 1
    assert len(discovery.calls) == result["chunks_total"]   # exactly once per chunk
    assert all(n == 1 and s == 1 for _, n, s in discovery.calls)
    merged = LocalOntology.model_validate(result["ontology"])
    assert merged.entity_labels == result["entity_types"]  # union of per-chunk types
    assert len(merged.entity_labels) == len(discovery.calls)


@pytest.mark.asyncio
async def test_build_job_reuses_ontology_and_skips_discovery(monkeypatch):
    discovery = _CountingDiscovery()
    extraction = _FakeExtraction()
    _patch_build_pipeline(monkeypatch, discovery, extraction)
    api_server.RUNS["onto-done"] = {
        "job_id": "onto-done",
        "status": "completed",
        "result": {"ontology": _ontology("PERSON").model_dump()},
    }
    job_id = "test-build-reuse"
    api_server.RUNS[job_id] = {"job_id": job_id, "result": None}

    await api_server._execute_unified_job(job_id, "build_graph", "ds1", _docs(), ontology_job_id="onto-done")

    result = api_server.RUNS[job_id]["result"]
    assert discovery.calls == []                              # zero re-discovery
    assert len(extraction.calls) == result["chunks_total"]    # one extraction run per chunk
    assert result["entity_types"] == ["PERSON"]               # the ontology job's schema


@pytest.mark.asyncio
async def test_build_job_without_ontology_keeps_per_chunk_discovery(monkeypatch):
    discovery = _CountingDiscovery()
    extraction = _FakeExtraction()
    _patch_build_pipeline(monkeypatch, discovery, extraction)
    job_id = "test-build-fallback"
    api_server.RUNS[job_id] = {"job_id": job_id, "result": None}

    await api_server._execute_unified_job(job_id, "build_graph", "ds1", _docs())

    result = api_server.RUNS[job_id]["result"]
    assert len(discovery.calls) == result["chunks_total"]     # standalone path unchanged
    assert len(extraction.calls) == result["chunks_total"]
