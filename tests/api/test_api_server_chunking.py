"""Tests for api_server._chunk_documents — the API ingestion path.

Chunking is sentence-aware (shared owner: chunkProcessor.split_text_sentences);
these assertions fail under the retired fixed character windows.
"""
import pytest

from src.api.api_server import _chunk_documents
from src.graph.models_graph import GlobalInputDocument


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
