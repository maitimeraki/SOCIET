"""Task 16 — one bad chunk is a skip, not a catastrophe.

A chunk whose extract+insert keeps failing is retried a bounded number of
times, then skipped: logged, published as a terminal `error` delta, and the
sliding window refills. The JOB fails only when every chunk across every
document failed (R17 — the verdict is job-scoped, not document-scoped).

No live LLM/Neo4j: llama_index is mocked at the module level (same shape as
tests/graph/test_incremental_insert.py) and the per-chunk seams are stubbed.
The job machinery is driven (`_execute_unified_job`), so the assertions are on
JOB STATUS, not just `_run_async`.
"""
import asyncio
import time
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.api.api_server as api_server
from src.graph.models_graph import (
    EntityTypeDefinition,
    LocalOntology,
    OntologyMetadata,
    ProcessedChunk,
    RelationTypeDefinition,
)


FAILING_DOC = "doc-1"
FAILING_CHUNK = "doc-1-2"


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


def _chunk(i: int, parent: str) -> ProcessedChunk:
    return ProcessedChunk(
        chunk_id=f"{parent}-{i}",
        parent_doc_id=parent,
        chunk_index=i,
        content_hash=f"hash{parent}{i}",
        content=f"Pre-split chunk body number {i}.",
        summary_context="Software architecture overview",
        breadcrumb="docs/architecture",
        header_level=1,
        domain_tags=["software"],
        expertise_level="Technical",
        metadata={"title": "System Architecture"},
    )


def _ontology() -> LocalOntology:
    return LocalOntology(
        metadata=OntologyMetadata(ontology_id="task16"),
        entity_types=[EntityTypeDefinition(type_name="Person")],
        relation_types=[RelationTypeDefinition(type_name="RELATED_TO")],
    )


class _Doc:
    """Stand-in for the llama Document, carrying its source chunk back to the stub."""

    def __init__(self, chunk):
        self.chunk = chunk


class _RecorderIndex:
    """The index `PropertyGraphIndex(...)` yields: a real docstore that fills up.

    `_run_async` reports `len(index.docstore.docs)` as its docs-built count, so
    the docstore must actually grow with the inserted nodes — otherwise a
    document whose chunks all failed would still report a non-zero count.
    """

    def __init__(self):
        self.docstore = types.SimpleNamespace(docs={})
        self.insert_calls = 0

    def insert_nodes(self, nodes):
        self.insert_calls += 1
        for node in nodes:
            self.docstore.docs[id(node)] = node


def _install_index():
    """One FRESH recorder index per `PropertyGraphIndex(...)` call (as prod does)."""
    import sys

    indexes = []

    def _factory(*args, **kwargs):
        index = _RecorderIndex()
        indexes.append(index)
        return index

    sys.modules['llama_index.core'].PropertyGraphIndex.side_effect = _factory
    return indexes


def _stage(**config_kwargs):
    from src.graph.config_graph import GraphConfig
    from src.graph.graph_build import GraphExtractionStage

    with patch('src.graph.graph_build.OpenAILike'), \
         patch('src.graph.graph_build.OllamaEmbedding'), \
         patch('src.graph.graph_build.Neo4jPropertyGraphStore'), \
         patch('src.graph.graph_build.SentenceSplitter'):
        return GraphExtractionStage(GraphConfig(**config_kwargs))


def _good(self, doc, extractors):
    return (
        [object()],  # one node inserted per successful chunk
        ["Person"],
        [],
        [{"id": "Person:Alpha", "label": "Alpha", "type": "Person"}],
        [{"source": "Person:Alpha", "target": "Person:Beta", "label": "RELATED_TO"}],
    )


class _FakeWS:
    def __init__(self):
        self.frames = []

    async def send_json(self, payload):
        self.frames.append(payload)


async def _drive_build_job(monkeypatch, stage, chunks, recorded):
    """Run the real `build_graph` job over `chunks` with the stubbed stage."""
    import src.graph.graph_build as gb

    monkeypatch.setattr(gb, "GraphExtractionStage", lambda cfg: stage)
    monkeypatch.setattr(gb, "publish", lambda job_id, delta: recorded.append(delta))
    monkeypatch.setattr(api_server, "GraphNormalizationStage", lambda cfg: AsyncMock())
    monkeypatch.setattr(api_server, "_persist_run", AsyncMock())
    monkeypatch.setattr(api_server, "_chunk_documents", AsyncMock(return_value=chunks))
    monkeypatch.setattr(api_server, "_ontology_from_run", AsyncMock(return_value=_ontology()))

    job_id = "task16-job"
    api_server.RUNS[job_id] = {"job_id": job_id, "status": "queued", "result": None}
    await api_server._execute_unified_job(
        job_id, "build_graph", "ds1", [MagicMock()], ontology_job_id="onto-x"
    )
    return job_id


async def _frames_for(deltas):
    from src.api.graph_stream_api import _send_delta

    ws = _FakeWS()
    for delta in deltas:
        await _send_delta(ws, delta)
    return ws.frames


def _wire(stage, chunks, extract):
    indexes = _install_index()
    stage._to_llama_document = lambda dataset_id, d, ontology: _Doc(d)
    stage._build_extractors = lambda slice_: []
    return indexes, patch.object(type(stage), "_extract_chunk", extract)


class TestOneBadChunkAmongFour:
    @pytest.mark.asyncio
    async def test_three_deltas_one_error_frame_and_job_completes(self, monkeypatch):
        chunks = [_chunk(i, FAILING_DOC) for i in range(4)]
        stage = _stage(
            chunk_parallelism=4,
            extraction_chunk_retries=1,
            extraction_chunk_retry_backoff_seconds=0.0,
        )

        def _extract(self, doc, extractors):
            if doc.chunk.chunk_id == FAILING_CHUNK:
                raise RuntimeError("provider 500")
            return _good(self, doc, extractors)

        indexes, extract_patch = _wire(stage, chunks, _extract)
        recorded = []
        with extract_patch:
            job_id = await _drive_build_job(monkeypatch, stage, chunks, recorded)

        # the job completes: three chunks landed, one was skipped
        assert api_server.RUNS[job_id]["status"] == "completed"
        assert indexes[0].insert_calls == 3

        good = [d for d in recorded if not d.error]
        errors = [d for d in recorded if d.error]
        assert len(good) == 3
        assert len(errors) == 1
        assert errors[0].chunk_id == FAILING_CHUNK
        assert "provider 500" in errors[0].error

        frames = await _frames_for(recorded)
        assert [f["type"] for f in frames].count("delta") == 3
        error_frames = [f for f in frames if f["type"] == "error"]
        assert len(error_frames) == 1
        assert error_frames[0]["chunk_id"] == FAILING_CHUNK
        assert "provider 500" in error_frames[0]["message"]

    @pytest.mark.asyncio
    async def test_bare_exception_still_yields_an_error_frame(self, monkeypatch):
        """A message-less exception must not be reported as an ordinary delta."""
        chunks = [_chunk(i, FAILING_DOC) for i in range(2)]
        stage = _stage(
            chunk_parallelism=2,
            extraction_chunk_retries=0,
            extraction_chunk_retry_backoff_seconds=0.0,
        )

        def _extract(self, doc, extractors):
            raise RuntimeError()

        _, extract_patch = _wire(stage, chunks, _extract)
        recorded = []
        with extract_patch:
            await _drive_build_job(monkeypatch, stage, chunks, recorded)

        assert all(d.error for d in recorded)          # non-empty, despite the bare raise
        frames = await _frames_for(recorded)
        assert [f["type"] for f in frames] == ["error", "error"]


class TestEveryChunkFails:
    @pytest.mark.asyncio
    async def test_job_fails_when_no_chunk_succeeds(self, monkeypatch):
        chunks = [_chunk(i, FAILING_DOC) for i in range(4)]
        stage = _stage(
            chunk_parallelism=4,
            extraction_chunk_retries=1,
            extraction_chunk_retry_backoff_seconds=0.0,
        )

        def _always_fail(self, doc, extractors):
            raise RuntimeError("provider down")

        _, extract_patch = _wire(stage, chunks, _always_fail)
        recorded = []
        with extract_patch:
            job_id = await _drive_build_job(monkeypatch, stage, chunks, recorded)

        assert api_server.RUNS[job_id]["status"] == "failed"
        # every chunk reported its terminal failure before the job died
        assert len([d for d in recorded if d.error]) == len(chunks)
        assert all(d.error for d in recorded)


class TestJobScopedFailureVerdict:
    """R17 — the "all chunks failed" verdict is DATASET-wide, not per-document."""

    @pytest.mark.asyncio
    async def test_one_bad_document_does_not_sink_the_job(self, monkeypatch):
        chunks = [
            _chunk(0, "doc-a"), _chunk(1, "doc-a"),
            _chunk(0, "doc-b"), _chunk(1, "doc-b"),
        ]
        stage = _stage(
            chunk_parallelism=4,
            extraction_chunk_retries=1,
            extraction_chunk_retry_backoff_seconds=0.0,
        )

        def _extract(self, doc, extractors):
            if doc.chunk.parent_doc_id == "doc-a":
                raise RuntimeError("provider 500")
            return _good(self, doc, extractors)

        _, extract_patch = _wire(stage, chunks, _extract)
        recorded = []
        with extract_patch:
            job_id = await _drive_build_job(monkeypatch, stage, chunks, recorded)

        # doc-a is entirely lost, doc-b's work is intact and the job succeeds
        assert api_server.RUNS[job_id]["status"] == "completed"
        assert {d.chunk_id for d in recorded if not d.error} == {"doc-b-0", "doc-b-1"}
        assert {d.chunk_id for d in recorded if d.error} == {"doc-a-0", "doc-a-1"}

        frames = await _frames_for(recorded)
        assert [f["chunk_id"] for f in frames if f["type"] == "error"] == ["doc-a-0", "doc-a-1"]
        assert len([f for f in frames if f["type"] == "delta"]) == 2

    @pytest.mark.asyncio
    async def test_every_document_failing_fails_the_job(self, monkeypatch):
        chunks = [
            _chunk(0, "doc-a"), _chunk(1, "doc-a"),
            _chunk(0, "doc-b"), _chunk(1, "doc-b"),
        ]
        stage = _stage(
            chunk_parallelism=4,
            extraction_chunk_retries=1,
            extraction_chunk_retry_backoff_seconds=0.0,
        )

        def _always_fail(self, doc, extractors):
            raise RuntimeError("provider down")

        _, extract_patch = _wire(stage, chunks, _always_fail)
        recorded = []
        with extract_patch:
            job_id = await _drive_build_job(monkeypatch, stage, chunks, recorded)

        assert api_server.RUNS[job_id]["status"] == "failed"


class TestFailureLeavesNoOrphanedWriters:
    @pytest.mark.asyncio
    async def test_in_flight_chunks_are_cancelled_not_orphaned(self, monkeypatch):
        """A chunk that blows up mid-window must not strand its siblings.

        The failing chunk returns instantly; the others are still mid-extraction
        (a 0.3 s sleep on the thread) when the failure propagates. Without the
        `finally` cancel/await, those in-flight tasks would run on and publish
        their deltas after the job was marked failed.
        """
        from src.graph.vocabulary import promote as real_promote

        chunks = [_chunk(i, FAILING_DOC) for i in range(4)]
        stage = _stage(
            chunk_parallelism=4,
            extraction_chunk_retries=1,
            extraction_chunk_retry_backoff_seconds=0.0,
        )

        def _extract(self, doc, extractors):
            if doc.chunk.chunk_id == FAILING_CHUNK:
                return ([], ["EXPLODE"], [], [], [])  # fails later, in promote
            time.sleep(0.3)  # hold the siblings in flight
            return _good(self, doc, extractors)

        def _promote(vocabulary, proposed, kind="entity"):
            if "EXPLODE" in proposed:
                raise RuntimeError("promote boom")
            return real_promote(vocabulary, proposed, kind)

        _, extract_patch = _wire(stage, chunks, _extract)
        recorded = []
        with extract_patch, patch('src.graph.graph_build.promote', _promote):
            job_id = await _drive_build_job(monkeypatch, stage, chunks, recorded)

        assert api_server.RUNS[job_id]["status"] == "failed"
        # nothing published before the failure, and the cancelled siblings stay silent
        assert recorded == []

        await asyncio.sleep(0.5)  # give any orphaned writer time to run
        assert recorded == []  # no task wrote after the failure propagated
