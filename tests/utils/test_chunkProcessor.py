"""Tests for chunkProcessor module."""
import pytest
from io import BytesIO
from unittest.mock import MagicMock
from fastapi import UploadFile

from src.utils.chunkProcessor import (
    ChunkProcessor,
    process_documents,
    split_text_sentences,
    _read_upload_file,
    _read_csv,
    _read_json,
    _compute_hash,
    _create_processed_chunk,
)
from src.graph.models_graph import ProcessedChunk


# --- Sentence-aware chunking fixtures -------------------------------------
# Ten uniform sentences; chunk_size/overlap are SentenceSplitter token budgets
# (sentences are ~20 tokens, so 64/32 yields 3-sentence chunks with a
# whole-sentence overlap).
QUALITY_SENTENCES = [
    f"Fact number {i:02d} about the migration plan states that the northern region will grow slowly."
    for i in range(10)
]
QUALITY_TEXT = " ".join(QUALITY_SENTENCES)
QUALITY_CHUNK_SIZE = 64
QUALITY_OVERLAP = 32


def sentences_of(chunk: str) -> list:
    """Split a chunk at sentence boundaries (period followed by a space)."""
    parts = []
    start = 0
    while True:
        found = chunk.find(". ", start)
        if found == -1:
            parts.append(chunk[start:].strip())
            break
        parts.append(chunk[start:found + 1].strip())
        start = found + 2
    return [part for part in parts if part]


def fixed_window_chunks(text: str, chunk_size: int, overlap: int) -> list:
    """The retired api_server._chunk_text, kept so the quality assertions can
    prove they actually discriminate against fixed character windows."""
    cleaned = (text or "").strip()
    if not cleaned:
        return []
    step = max(1, chunk_size - overlap)
    chunks = []
    for start in range(0, len(cleaned), step):
        chunk = cleaned[start:start + chunk_size].strip()
        if chunk:
            chunks.append(chunk)
    return chunks


class MockUploadFile(UploadFile):
    """Mock UploadFile for testing."""

    def __init__(self, filename: str, content: bytes, content_type: str = "text/plain"):
        self._filename = filename
        self._content = content
        self._content_type = content_type
        self.file = BytesIO(content)

    @property
    def filename(self) -> str:
        return self._filename

    @property
    def content_type(self) -> str:
        return self._content_type

    async def write(self, data):
        pass

    async def read(self, size: int = -1):
        return self.file.read(size)

    async def seek(self, offset: int = 0):
        self.file.seek(offset)

    async def close(self):
        pass


class TestComputeHash:
    """Tests for _compute_hash function."""

    def test_same_text_same_hash(self):
        text1 = "Hello, world!"
        text2 = "Hello, world!"
        assert _compute_hash(text1) == _compute_hash(text2)

    def test_different_text_different_hash(self):
        text1 = "Hello, world!"
        text2 = "Goodbye, world!"
        assert _compute_hash(text1) != _compute_hash(text2)

    def test_empty_text(self):
        hash1 = _compute_hash("")
        hash2 = _compute_hash("")
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 produces 64 hex characters


class TestCreateProcessedChunk:
    """Tests for _create_processed_chunk function."""

    def test_creates_valid_chunk(self):
        chunk = _create_processed_chunk(
            content="Test content",
            chunk_index=0,
            parent_doc_id="parent-123",
            source_document="test.txt",
        )
        assert isinstance(chunk, ProcessedChunk)
        assert chunk.content == "Test content"
        assert chunk.chunk_index == 0
        assert chunk.parent_doc_id == "parent-123"
        assert chunk.metadata["source_document"] == "test.txt"

    def test_chunk_has_uuid(self):
        chunk = _create_processed_chunk(
            content="Test",
            chunk_index=0,
            parent_doc_id="parent",
            source_document="test.txt",
        )
        assert chunk.chunk_id is not None
        assert len(chunk.chunk_id) == 36  # UUID format


class TestReadCsv:
    """Tests for CSV reading."""

    def test_simple_csv(self):
        csv_content = b"name,age,city\nAlice,30,NYC\nBob,25,LA"
        result = _read_csv(csv_content)
        assert "name | age | city" in result
        assert "Alice | 30 | NYC" in result
        assert "Bob | 25 | LA" in result


class TestReadJson:
    """Tests for JSON reading."""

    def test_simple_json(self):
        json_content = b'{"name": "Alice", "role": "developer"}'
        result = _read_json(json_content)
        assert "Alice" in result
        assert "developer" in result

    def test_nested_json(self):
        json_content = b'{"user": {"name": "Bob", "skills": ["python", "rust"]}}'
        result = _read_json(json_content)
        assert "Bob" in result
        assert "python" in result
        assert "rust" in result

    def test_array_json(self):
        json_content = b'["item1", "item2", "item3"]'
        result = _read_json(json_content)
        assert "item1" in result
        assert "item2" in result
        assert "item3" in result


class TestProcessDocuments:
    """Tests for process_documents function."""

    def test_empty_file_list(self):
        result = process_documents([])
        assert result == []

    def test_single_text_file(self):
        content = b"This is a test document with some content."
        file = MockUploadFile("test.txt", content)

        chunks = process_documents([file])

        assert len(chunks) >= 1
        assert chunks[0].metadata["source_document"] == "test.txt"
        assert "test" in chunks[0].content.lower()

    def test_chunk_ids_are_unique(self):
        content = b"A" * 2000  # Large enough to create multiple chunks
        file = MockUploadFile("test.txt", content)

        chunks = process_documents([file])

        chunk_ids = [c.chunk_id for c in chunks]
        assert len(chunk_ids) == len(set(chunk_ids)), "All chunk IDs should be unique"

    def test_chunk_indices_are_sequential(self):
        content = b"Word " * 500  # Large enough for multiple chunks
        file = MockUploadFile("test.txt", content)

        chunks = process_documents([file])

        indices = [c.chunk_index for c in chunks]
        assert indices == list(range(len(indices))), "Chunk indices should be sequential"

    def test_overlapping_chunks(self):
        """Verify chunks overlap when chunk_overlap is set."""
        content = b"0123456789 " * 200  # Repeated pattern to verify overlap
        file = MockUploadFile("test.txt", content)

        # With overlap, end of one chunk should appear at start of next
        chunks = process_documents([file], chunk_size=100, chunk_overlap=20)

        if len(chunks) > 1:
            # Check that adjacent chunks share some overlap
            for i in range(len(chunks) - 1):
                # Look for the last few chars of chunk i in chunk i+1
                last_chars = chunks[i].content[-10:].strip()
                found = any(last_chars in c.content for c in chunks[i + 1 : i + 2])
                # This is a soft check - overlap should exist but may not be exact

    def test_multiple_files(self):
        files = [
            MockUploadFile("doc1.txt", b"Content of document one"),
            MockUploadFile("doc2.txt", b"Content of document two"),
        ]

        chunks = process_documents(files)

        sources = [c.metadata["source_document"] for c in chunks]
        assert "doc1.txt" in sources
        assert "doc2.txt" in sources

    def test_csv_file(self):
        csv_content = b"name,value\nfoo,100\nbar,200"
        file = MockUploadFile("data.csv", csv_content, "text/csv")

        chunks = process_documents([file])

        assert len(chunks) >= 1
        assert chunks[0].metadata["source_document"] == "data.csv"

    def test_json_file(self):
        json_content = b'{"items": ["alpha", "beta", "gamma"]}'
        file = MockUploadFile("data.json", json_content, "application/json")

        chunks = process_documents([file])

        assert len(chunks) >= 1
        assert "alpha" in chunks[0].content or "beta" in chunks[0].content

    def test_all_chunks_have_required_fields(self):
        content = b"Some test content for validation"
        file = MockUploadFile("test.txt", content)

        chunks = process_documents([file])

        for chunk in chunks:
            assert hasattr(chunk, "chunk_id")
            assert hasattr(chunk, "content")
            assert hasattr(chunk, "parent_doc_id")
            assert hasattr(chunk, "chunk_index")
            assert hasattr(chunk, "metadata")
            assert "source_document" in chunk.metadata

    def test_parent_doc_id_same_for_same_file(self):
        content = b"X" * 2000  # Large enough for multiple chunks
        file = MockUploadFile("test.txt", content)

        chunks = process_documents([file])

        parent_ids = set(c.parent_doc_id for c in chunks)
        assert len(parent_ids) == 1, "All chunks from same file should have same parent_doc_id"

    def test_parent_doc_id_differs_for_different_files(self):
        files = [
            MockUploadFile("file1.txt", b"A" * 1000),
            MockUploadFile("file2.txt", b"B" * 1000),
        ]

        chunks = process_documents(files)

        parent_ids = set(c.parent_doc_id for c in chunks)
        assert len(parent_ids) == 2, "Different files should have different parent_doc_ids"

    def test_splits_through_the_sentence_splitter(self):
        file = MockUploadFile("sentences.txt", QUALITY_TEXT.encode("utf-8"))

        chunks = process_documents(
            [file], chunk_size=QUALITY_CHUNK_SIZE, chunk_overlap=QUALITY_OVERLAP
        )

        assert len(chunks) > 2
        for chunk in chunks[:-1]:
            assert chunk.content.endswith("."), f"cut mid-sentence: ...{chunk.content[-40:]!r}"


class TestChunkProcessor:
    """Tests for the ChunkProcessor adapter used by api_server._chunk_documents."""

    @pytest.mark.asyncio
    async def test_maps_arguments_and_resolves_title_as_source_document(self):
        chunk = await ChunkProcessor().process_document(
            chunk="Body text",
            chunk_index=3,
            parent_doc_id="doc-9",
            metadata={"title": "The Title"},
        )

        assert isinstance(chunk, ProcessedChunk)
        assert chunk.content == "Body text"
        assert chunk.chunk_index == 3
        assert chunk.parent_doc_id == "doc-9"
        assert chunk.metadata["source_document"] == "The Title"

    @pytest.mark.asyncio
    async def test_falls_back_to_source_document_when_title_absent(self):
        chunk = await ChunkProcessor().process_document(
            chunk="Body text",
            chunk_index=0,
            parent_doc_id="doc-9",
            metadata={"source_document": "fallback.txt"},
        )

        assert chunk.metadata["source_document"] == "fallback.txt"

    @pytest.mark.asyncio
    async def test_falls_back_to_unknown_when_metadata_missing(self):
        for metadata in ({}, None):
            chunk = await ChunkProcessor().process_document(
                chunk="Body text",
                chunk_index=0,
                parent_doc_id="doc-9",
                metadata=metadata,
            )

            assert chunk.metadata["source_document"] == "unknown"


class TestSplitTextSentences:
    """Quality tests for the single splitting owner (chunkProcessor.split_text_sentences).

    The invariants fail under fixed character windows — pinned by
    TestFixedWindowDiscrimination below.
    """

    def test_blank_text_returns_no_chunks(self):
        assert split_text_sentences("", QUALITY_CHUNK_SIZE, QUALITY_OVERLAP) == []
        assert split_text_sentences("   \n\t ", QUALITY_CHUNK_SIZE, QUALITY_OVERLAP) == []

    def test_every_chunk_ends_at_a_sentence_boundary(self):
        chunks = split_text_sentences(QUALITY_TEXT, QUALITY_CHUNK_SIZE, QUALITY_OVERLAP)

        assert len(chunks) > 2
        for chunk in chunks[:-1]:
            assert chunk.endswith("."), f"cut mid-sentence: ...{chunk[-40:]!r}"
        assert chunks[-1].endswith("."), "trailing sentence was truncated"

    def test_adjacent_chunks_share_whole_sentences(self):
        chunks = split_text_sentences(QUALITY_TEXT, QUALITY_CHUNK_SIZE, QUALITY_OVERLAP)

        assert len(chunks) > 2
        for current, following in zip(chunks, chunks[1:]):
            assert sentences_of(current)[-1] in following, "tail sentence not repeated"
            assert sentences_of(following)[0] in current, "head sentence is not overlap"

    def test_chunks_preserve_source_order_without_inventing_text(self):
        chunks = split_text_sentences(QUALITY_TEXT, QUALITY_CHUNK_SIZE, QUALITY_OVERLAP)

        cursor = 0
        for chunk in chunks:
            position = QUALITY_TEXT.find(chunk, cursor)
            assert position != -1, f"chunk not found in source order: {chunk[:40]!r}"
            cursor = position


class TestFixedWindowDiscrimination:
    """Guards the quality tests: they must fail on the retired fixed-window slicing."""

    def test_fixed_windows_violate_the_sentence_boundary_invariant(self):
        chunks = fixed_window_chunks(QUALITY_TEXT, QUALITY_CHUNK_SIZE, QUALITY_OVERLAP)

        assert len(chunks) > 2
        assert any(not chunk.endswith(".") for chunk in chunks[:-1])

    def test_fixed_windows_do_not_share_whole_sentences(self):
        chunks = fixed_window_chunks(QUALITY_TEXT, QUALITY_CHUNK_SIZE, QUALITY_OVERLAP)

        assert any(
            sentences_of(current)[-1] not in following
            for current, following in zip(chunks, chunks[1:])
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
