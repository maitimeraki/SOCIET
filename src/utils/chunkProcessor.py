"""Chunk processing utilities for document ingestion."""
import uuid
import hashlib
from typing import Any, List, Optional
from io import StringIO, BytesIO
from fastapi import UploadFile
from llama_index.core.node_parser import SentenceSplitter
import csv
import json

from src.graph.models_graph import ProcessedChunk


def _read_upload_file(file: UploadFile) -> str:
    """Read content from an UploadFile, handling different file types."""
    content = file.file.read()

    # Detect content type
    mime_type = file.content_type or ""

    if mime_type == "text/csv" or file.filename.endswith(".csv"):
        return _read_csv(content)
    elif mime_type == "application/json" or file.filename.endswith(".json"):
        return _read_json(content)
    elif mime_type == "application/pdf" or file.filename.endswith(".pdf"):
        # ponytail: basic PDF text extraction - upgrade to pypdf/pdfplumber if needed
        return _read_basic_pdf(content)
    else:
        # Plain text
        return content.decode("utf-8", errors="replace")


def _read_csv(content: bytes) -> str:
    """Extract text content from CSV bytes."""
    try:
        text_content = content.decode("utf-8")
    except UnicodeDecodeError:
        text_content = content.decode("latin-1")

    reader = csv.reader(StringIO(text_content))
    lines = []
    for row in reader:
        lines.append(" | ".join(str(cell) for cell in row if cell))
    return "\n".join(lines)


def _read_json(content: bytes) -> str:
    """Extract text content from JSON bytes."""
    try:
        data = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        data = json.loads(content.decode("latin-1"))

    return _extract_text_from_json(data)


def _extract_text_from_json(obj) -> str:
    """Recursively extract text from JSON structure."""
    if isinstance(obj, str):
        return obj
    elif isinstance(obj, dict):
        parts = []
        for value in obj.values():
            text = _extract_text_from_json(value)
            if text:
                parts.append(text)
        return " ".join(parts)
    elif isinstance(obj, list):
        parts = [_extract_text_from_json(item) for item in obj]
        return " ".join(p for p in parts if p)
    else:
        return str(obj) if obj else ""


def _read_basic_pdf(content: bytes) -> str:
    """Basic PDF text extraction - reads raw PDF content."""
    # ponytail: real PDF extraction needs pypdf or pdfplumber
    try:
        text = content.decode("latin-1")
        # Extract text between BT and ET markers (basic PDF text extraction)
        import re
        text_parts = re.findall(r"BT(.*?)ET", text, re.DOTALL)
        result = []
        for part in text_parts:
            # Extract strings in parentheses
            strings = re.findall(r"\(([^)]+)\)", part)
            result.extend(strings)
        return " ".join(result)
    except Exception:
        return ""


def _compute_hash(text: str) -> str:
    """Compute SHA-256 hash of text."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _create_processed_chunk(
    content: str,
    chunk_index: int,
    parent_doc_id: str,
    source_document: str,
) -> ProcessedChunk:
    """Create a ProcessedChunk with required fields."""
    return ProcessedChunk(
        chunk_id=str(uuid.uuid4()),
        parent_doc_id=parent_doc_id,
        chunk_index=chunk_index,
        content_hash=_compute_hash(content),
        content=content,
        summary_context="",  # Enrichment happens in a separate stage
        breadcrumb="",
        header_level=0,
        domain_tags=[],  # Enrichment happens in a separate stage
        expertise_level="",  # Enrichment happens in a separate stage
        metadata={"source_document": source_document},
    )


def split_text_sentences(text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
    """Sentence-aware splitting with whole-sentence overlap — the single splitting owner.

    Both ingestion paths (process_documents, api_server._chunk_documents) route
    through here. chunk_size / chunk_overlap go straight to SentenceSplitter,
    whose native budget is tokens (llama-index default tokenizer), not characters.
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return []

    splitter = SentenceSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    return [chunk for chunk in (raw.strip() for raw in splitter.split_text(cleaned)) if chunk]


def process_documents(
    files: List[UploadFile],
    chunk_size: int = 512,
    chunk_overlap: int = 50,
) -> List[ProcessedChunk]:
    """
    Split uploaded files into overlapping text chunks.

    Args:
        files: List of FastAPI UploadFile objects
        chunk_size: Target size for each chunk (SentenceSplitter token budget)
        chunk_overlap: Overlap between chunks (SentenceSplitter token budget)

    Returns:
        List of ProcessedChunk objects with chunk_id, text, source_document, chunk_index
    """
    if not files:
        return []

    all_chunks: List[ProcessedChunk] = []

    for file in files:
        # Reset file position
        file.file.seek(0)

        # Read file content
        text = _read_upload_file(file)
        source_document = file.filename or "unknown"
        parent_doc_id = str(uuid.uuid4())

        if not text.strip():
            continue

        text_chunks = split_text_sentences(text, chunk_size, chunk_overlap)

        for idx, chunk_text in enumerate(text_chunks):
            chunk = _create_processed_chunk(
                content=chunk_text,
                chunk_index=idx,
                parent_doc_id=parent_doc_id,
                source_document=source_document,
            )
            all_chunks.append(chunk)

    return all_chunks


class ChunkProcessor:
    """Chunk-level processor for the API layer (api_server._chunk_documents).

    Thin adapter over _create_processed_chunk. Enrichment fields stay blank —
    a separate enrichment stage owns them (see models_graph ProcessedChunk docstring).
    The llama-index LLM argument is accepted and ignored (API-shape compatibility).
    """

    def __init__(self, llm: Any = None):
        self._llm = llm

    async def process_document(
        self,
        chunk: str,
        chunk_index: int,
        parent_doc_id: str,
        metadata: dict,
    ) -> ProcessedChunk:
        return _create_processed_chunk(
            content=chunk,
            chunk_index=chunk_index,
            parent_doc_id=parent_doc_id,
            source_document=str(
                (metadata or {}).get("title")
                or (metadata or {}).get("source_document")
                or "unknown"
            ),
        )
