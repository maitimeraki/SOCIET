import os
from dataclasses import dataclass

from src.llm.config_llm import LLMConfig

@dataclass
class GraphConfig:
    # Graph stages are the analysis tier — cheap but capable. Single source:
    # LLMConfig (env: ANALYSIS_LLM_MODEL); .env is loaded there too.
    discovery_model: str = LLMConfig.analysis_model
    extraction_model: str = LLMConfig.analysis_model
    temperature: float = float(os.getenv("GRAPH_TEMPERATURE", "0.0"))
    discovery_sample_size: int = int(os.getenv("GRAPH_DISCOVERY_SAMPLE_SIZE", "12"))
    discovery_timeout_seconds: int = int(os.getenv("GRAPH_DISCOVERY_TIMEOUT_SECONDS", "90"))
    discovery_retry_attempts: int = int(os.getenv("GRAPH_DISCOVERY_RETRY_ATTEMPTS", "3"))
    discovery_retry_backoff_seconds: float = float(
        os.getenv("GRAPH_DISCOVERY_RETRY_BACKOFF_SECONDS", "1.0")
    )
    # Units are SentenceSplitter *tokens* (llama-index's native budget), not
    # characters. The env var names keep their historical CHARS spelling for
    # operator compatibility — renaming them would silently drop overrides.
    ontology_chunk_size_tokens: int = int(os.getenv("GRAPH_ONTOLOGY_CHUNK_SIZE_CHARS", "2000"))
    ontology_chunk_overlap_tokens: int = int(os.getenv("GRAPH_ONTOLOGY_CHUNK_OVERLAP_CHARS", "200"))
    ontology_max_concurrency: int = int(os.getenv("GRAPH_ONTOLOGY_MAX_CONCURRENCY", "8"))

    neo4j_uri: str = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_username: str = os.getenv("NEO4J_USERNAME", "neo4j")
    neo4j_password: str = os.getenv("NEO4J_PASSWORD", "password")
    neo4j_database: str = os.getenv("NEO4J_DATABASE", "neo4j")
