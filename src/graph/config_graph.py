import os
from dataclasses import dataclass

from src.llm.config_llm import LLMConfig

@dataclass
class GraphConfig:
    # Graph stages are the analysis tier — cheap but capable. Single source:
    # LLMConfig (env: ANALYSIS_LLM_MODEL); .env is loaded there too.
    discovery_model: str = LLMConfig.analysis_model
    extraction_model: str = LLMConfig.analysis_model
    # Explicit per-attempt bound for the extraction LLM call: a hung request
    # must fail inside the caller's window instead of riding the library default.
    extraction_timeout_seconds: int = int(os.getenv("GRAPH_EXTRACTION_TIMEOUT_SECONDS", "300"))
    temperature: float = float(os.getenv("GRAPH_TEMPERATURE", "0.0"))
    discovery_sample_size: int = int(os.getenv("GRAPH_DISCOVERY_SAMPLE_SIZE", "12"))
    discovery_timeout_seconds: int = int(os.getenv("GRAPH_DISCOVERY_TIMEOUT_SECONDS", "90"))
    discovery_retry_attempts: int = int(os.getenv("GRAPH_DISCOVERY_RETRY_ATTEMPTS", "3"))
    discovery_retry_backoff_seconds: float = float(
        os.getenv("GRAPH_DISCOVERY_RETRY_BACKOFF_SECONDS", "1.0")
    )
    # Chunking budget is character-facing (operator-friendly). The splitter
    # (SentenceSplitter) consumes *tokens*, so the token budget is derived at
    # this boundary rather than configured directly.
    chunk_size_chars: int = int(os.getenv("GRAPH_CHUNK_SIZE_CHARS", "8000"))
    chunk_overlap_chars: int = int(os.getenv("GRAPH_CHUNK_OVERLAP_CHARS", "800"))

    @property
    def chunk_size_tokens(self) -> int:
        # ponytail: 4 chars/token is an English-prose approximation; revisit if the tokenizer changes.
        return self.chunk_size_chars // 4

    @property
    def chunk_overlap_tokens(self) -> int:
        return self.chunk_overlap_chars // 4

    # Aggregate in-flight extraction LLM calls = this × each extractor's
    # num_workers (pinned to 1 in graph_build.py — raise one only by lowering
    # the other).
    ontology_max_concurrency: int = int(os.getenv("GRAPH_ONTOLOGY_MAX_CONCURRENCY", "8"))

    neo4j_uri: str = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_username: str = os.getenv("NEO4J_USERNAME", "neo4j")
    neo4j_password: str = os.getenv("NEO4J_PASSWORD", "password")
    neo4j_database: str = os.getenv("NEO4J_DATABASE", "neo4j")
