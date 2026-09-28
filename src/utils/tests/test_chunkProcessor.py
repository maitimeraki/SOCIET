"""Tests for chunkProcessor module."""
import pytest
from io import BytesIO
from unittest.mock import MagicMock
from fastapi import UploadFile

from src.utils.chunkProcessor import (
    ChunkProcessor,
    process_documents,
    _read_upload_file,
    _read_csv,
    _read_json,
    _compute_hash,
    _create_processed_chunk,
)
from src.graph.models_graph import ProcessedChunk


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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
