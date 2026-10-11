"""Tests for api_server chunking and unified job execution.

Chunking is sentence-aware (shared owner: chunkProcessor.split_text_sentences);
these assertions fail under the retired fixed character windows.
"""
import asyncio
import json
import logging
from unittest.mock import AsyncMock

import pytest

import src.api.api_server as api_server
from src.api.api_server import _chunk_documents
from src.graph.config_graph import GraphConfig
from src.graph.models_graph import GlobalInputDocument, LocalOntology
from src.graph.vocabulary import spread_indexes


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
        self.frames = []  # (parent_doc_id, chunk_index) passed to each call

    async def run(self, documents, sample_size=1):
        self.calls.append((documents[0].chunk_id, len(documents), sample_size))
        self.frames.append([(d.parent_doc_id, d.chunk_index) for d in documents])
        return _ontology(f"TYPE_{len(self.calls)}")


class _FakeExtraction:
    def __init__(self, *args, **kwargs):
        self.calls = []  # list of chunk counts per run

    async def run(self, dataset_id, documents, ontology, job_id=None):
        self.calls.append(len(documents))
        return len(documents)  # simulate one docstore node per chunk


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
    assert discovery.calls == []
    assert len(extraction.calls) == 2                        # one run per source document
    assert all(n > 1 for n in extraction.calls)              # each run received the doc's chunks
    assert result["docs_built"] == result["chunks_total"]    # 1 docstore node per chunk, summed
    assert result["entity_types"] == ["PERSON"]               # the ontology job's schema


@pytest.mark.asyncio
async def test_build_extraction_runs_once_per_document(monkeypatch):
    discovery = _CountingDiscovery()
    extraction = _FakeExtraction()
    _patch_build_pipeline(monkeypatch, discovery, extraction)
    job_id = "test-build-per-doc"
    api_server.RUNS[job_id] = {"job_id": job_id, "result": None}

    await api_server._execute_unified_job(job_id, "build_graph", "ds1", _docs())

    result = api_server.RUNS[job_id]["result"]
    assert result["chunks_total"] > 2
    assert len(extraction.calls) == 2                        # docs, not chunks


@pytest.mark.asyncio
async def test_build_job_without_ontology_discovers_once_per_dataset(monkeypatch):
    discovery = _CountingDiscovery()
    extraction = _FakeExtraction()
    _patch_build_pipeline(monkeypatch, discovery, extraction)
    # Force a sample smaller than the corpus so the spread must pick endpoints.
    monkeypatch.setattr(
        api_server,
        "GraphConfig",
        lambda: GraphConfig(vocabulary_sample_size=2, vocabulary_max_labels=200),
    )
    job_id = "test-build-fallback"
    api_server.RUNS[job_id] = {"job_id": job_id, "result": None}
    documents = _docs()

    await api_server._execute_unified_job(job_id, "build_graph", "ds1", documents)

    # ONE discovery call for the whole dataset — not one per chunk.
    assert len(discovery.calls) == 1
    # ...over a spread sample that spans the dataset: first and last chunk present.
    full = await _chunk_documents(
        documents, GraphConfig().chunk_size_tokens, GraphConfig().chunk_overlap_tokens
    )
    coord = lambda c: (c.parent_doc_id, c.chunk_index)
    expected = [coord(full[i]) for i in spread_indexes(len(full), 2)]
    assert discovery.frames[0] == expected
    assert expected[0] == coord(full[0])
    assert expected[-1] == coord(full[-1])
    assert len(extraction.calls) == 2                         # one run per document, not per chunk


class _ExplodingDiscovery:
    """Stand-in for OntologyDiscoveryStage whose call always raises."""

    def __init__(self, *args, **kwargs):
        pass

    async def run(self, documents, sample_size=1):
        raise RuntimeError("provider down")


@pytest.mark.asyncio
async def test_build_job_discovery_failure_marks_job_failed(monkeypatch):
    discovery = _ExplodingDiscovery()
    _patch_build_pipeline(monkeypatch, discovery, _FakeExtraction())
    # One attempt, no backoff: keep the failure path fast.
    monkeypatch.setattr(
        api_server,
        "GraphConfig",
        lambda: GraphConfig(discovery_retry_attempts=1, discovery_retry_backoff_seconds=0.0),
    )
    job_id = "test-build-discovery-fail"
    api_server.RUNS[job_id] = {"job_id": job_id, "status": "queued", "result": None}

    await api_server._execute_unified_job(job_id, "build_graph", "ds1", _docs())

    # A terminal discovery failure must persist, not leave the job stuck.
    assert api_server.RUNS[job_id]["status"] == "failed"
    assert api_server.RUNS[job_id]["stage"] == "failed"
    assert "dataset vocabulary discovery failed" in api_server.RUNS[job_id]["error"]


class _FlakyDiscovery:
    """Stand-in that fails the first call, then succeeds."""

    def __init__(self, *args, **kwargs):
        self.calls = 0

    async def run(self, documents, sample_size=1):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("transient provider error")
        return _ontology("TYPE_OK")


@pytest.mark.asyncio
async def test_build_job_retries_transient_discovery_failure(monkeypatch):
    discovery = _FlakyDiscovery()
    extraction = _FakeExtraction()
    _patch_build_pipeline(monkeypatch, discovery, extraction)
    monkeypatch.setattr(
        api_server,
        "GraphConfig",
        lambda: GraphConfig(discovery_retry_attempts=2, discovery_retry_backoff_seconds=0.0),
    )
    job_id = "test-build-retry"
    api_server.RUNS[job_id] = {"job_id": job_id, "status": "queued", "result": None}

    await api_server._execute_unified_job(job_id, "build_graph", "ds1", _docs())

    assert discovery.calls == 2                               # one retry absorbed the blip
    assert api_server.RUNS[job_id]["status"] == "completed"
    assert len(extraction.calls) == 2


class TestOntologyFromRun:
    """The persisted-run read must never raise: a bad read falls back to discovery."""

    @pytest.mark.asyncio
    async def test_valid_persisted_run_file_is_parsed(self, tmp_path, monkeypatch):
        monkeypatch.setattr(api_server, "_RUNS_RUNTIME_DIR", tmp_path)
        api_server.RUNS.pop("onto-on-disk", None)
        run = {
            "job_id": "onto-on-disk",
            "status": "completed",
            "result": {"ontology": _ontology("PERSON").model_dump()},
        }
        (tmp_path / "onto-on-disk.json").write_text(json.dumps(run), encoding="utf-8")

        ontology = await api_server._ontology_from_run("onto-on-disk")

        assert ontology is not None
        assert ontology.entity_labels == ["PERSON"]

    @pytest.mark.asyncio
    async def test_corrupt_persisted_run_file_returns_none_and_warns(
        self, tmp_path, monkeypatch, caplog
    ):
        """A crash mid-`_persist_run` leaves invalid JSON; the read degrades, never raises."""
        monkeypatch.setattr(api_server, "_RUNS_RUNTIME_DIR", tmp_path)
        api_server.RUNS.pop("onto-corrupt", None)
        (tmp_path / "onto-corrupt.json").write_text("{not json", encoding="utf-8")

        with caplog.at_level(logging.WARNING, logger=api_server.logger.name):
            ontology = await api_server._ontology_from_run("onto-corrupt")

        assert ontology is None
        assert "onto-corrupt" in caplog.text


class _ExplodingExtractionInit:
    """Neo4j-unreachable stand-in: constructing the extraction stage raises."""

    def __init__(self, *args, **kwargs):
        raise RuntimeError("Neo4j unreachable")


@pytest.mark.asyncio
async def test_stage_construction_failure_marks_job_failed_not_queued(monkeypatch):
    """C1: a raise anywhere in the prologue (here: extraction-stage construction)
    must leave the job terminal. `_execute_unified_job` is fire-and-forget, so the
    old out-of-try prologue would die silently and strand the job "queued" forever,
    hanging the WS route's wait for a terminal status."""
    monkeypatch.setattr(api_server, "OntologyDiscoveryStage", _CountingDiscovery)
    monkeypatch.setattr(api_server, "GraphNormalizationStage", lambda cfg: AsyncMock())
    monkeypatch.setattr(api_server, "_persist_run", AsyncMock())
    monkeypatch.setattr("src.graph.graph_build.GraphExtractionStage", _ExplodingExtractionInit)

    job_id = "test-construction-fail"
    api_server.RUNS[job_id] = {"job_id": job_id, "status": "queued", "result": None}

    await api_server._execute_unified_job(job_id, "build_graph", "ds1", _docs())

    assert api_server.RUNS[job_id]["status"] == "failed"
    assert api_server.RUNS[job_id]["stage"] == "failed"
    assert "Neo4j unreachable" in api_server.RUNS[job_id]["error"]


class _FailThenBlockExtraction:
    """`d0`'s extraction raises; every other document blocks until cancelled — so
    the test can tell whether the canceller freed it or left it running."""

    def __init__(self, *args, **kwargs):
        self.cancelled: list[str] = []

    async def run(self, dataset_id, documents, ontology, job_id=None):
        doc_id = documents[0].parent_doc_id
        if doc_id == "d0":
            raise RuntimeError("extraction boom on d0")
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled.append(doc_id)
            raise


@pytest.mark.asyncio
async def test_raising_worker_cancels_its_siblings(monkeypatch):
    """I2: when one worker raises, the job goes terminal AND the other in-flight
    workers are cancelled — not left extracting / writing / publishing for a job
    already marked failed."""
    extraction = _FailThenBlockExtraction()
    monkeypatch.setattr(api_server, "OntologyDiscoveryStage", _CountingDiscovery)
    monkeypatch.setattr(api_server, "GraphNormalizationStage", lambda cfg: AsyncMock())
    monkeypatch.setattr(api_server, "_persist_run", AsyncMock())
    monkeypatch.setattr("src.graph.graph_build.GraphExtractionStage", lambda cfg: extraction)
    # Keep both document workers in flight together so the sibling is startable.
    monkeypatch.setattr(api_server, "GraphConfig", lambda: GraphConfig(ontology_max_concurrency=8))

    job_id = "test-worker-cancel"
    api_server.RUNS[job_id] = {"job_id": job_id, "status": "queued", "result": None}

    await api_server._execute_unified_job(job_id, "build_graph", "ds1", _docs())

    assert api_server.RUNS[job_id]["status"] == "failed"
    assert extraction.cancelled == ["d1"]  # the sibling was cancelled, not left writing


@pytest.mark.asyncio
async def test_get_job_degrades_on_a_corrupt_runtime_file(tmp_path, monkeypatch):
    """A crash mid-`_persist_run` leaves invalid JSON. The job read must degrade to
    the same not-found shape `_job_state` and `_ontology_from_run` already use, not
    raise out of the endpoint."""
    monkeypatch.setattr(api_server, "_RUNS_RUNTIME_DIR", tmp_path)
    api_server.RUNS.pop("job-corrupt", None)
    (tmp_path / "job-corrupt.json").write_text("{not json", encoding="utf-8")

    result = await api_server.get_job("job-corrupt")

    assert result["status"] == "failed"
    assert result["stage"] == "not_found"
