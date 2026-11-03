import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional

import dotenv

dotenv.load_dotenv()  # Load .env before the class defaults below read os.getenv


@dataclass
class LLMConfig:
    """Configuration for LLM providers"""

    # OpenAI settings
    openai_api_key: Optional[str] = os.getenv("OPENAI_API_KEY")
    openai_model: str = "gpt-3.5-turbo"  # or "gpt-4"

    # Anthropic settings
    anthropic_api_key: Optional[str] = os.getenv("ANTHROPIC_API_KEY")
    anthropic_model: str = "claude-sonnet-4-5"

    # HuggingFace settings
    huggingface_api_key: Optional[str] = os.getenv("HUGGINGFACEHUB_API_TOKEN")
    huggingface_model: str = "Qwen/Qwen3.5-9B"

    # Ollama settings (local)
    ollama_model: str = os.getenv(
        "OLLAMA_MODEL", "qwen3.5-16k:4b"
    )  # or "mistral", "codellama", etc.
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    # Embedding model — ONE source for graph ingestion (graph_build), retrieval
    # (graph_context) and persona writes (repository), plus the schema's vector
    # dimension (neo4j_bootstrap). They MUST agree: Neo4j's vector index returns
    # an EMPTY set (no error) for a query vector whose length differs from the
    # index, so a mismatch surfaces as "no agents derivable from graph".
    # qwen3-embedding:0.6b produces 1024-dim vectors.
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "qwen3-embedding:0.6b")
    embedding_dimensions: int = int(os.getenv("EMBEDDING_DIMENSIONS", "1024"))

    # Nvidia Nim
    nvidia_nim_api_key: str = os.getenv("NVIDIA_NIM_API_KEY", "")
    nvidia_nim_base_url: str = os.getenv("NVIDIA_NIM_BASE_URL", "")

    # OpenRouter (used by the configurable extraction provider)
    openrouter_api_key: Optional[str] = os.getenv("OPENROUTER_API_KEY")

    # Default provider (user's favorite)
    default_llm_provider: str = os.getenv("DEFAULT_LLM_PROVIDER", "ollama")

    # Extraction-tier provider (graph ingestion). Default stays NVIDIA NIM so
    # dev behaviour is unchanged; production must escape the free trial catalog
    # (see src/llm/extraction.py).
    extraction_provider: str = os.getenv("EXTRACTION_PROVIDER", "nvidia_nim")
    extraction_model: str = (
        os.getenv("EXTRACTION_LLM_MODEL")
        or os.getenv("ANALYSIS_LLM_MODEL", "claude-sonnet-5")
    )
    extraction_base_url: str = os.getenv("EXTRACTION_BASE_URL", "")
    extraction_api_key: str = os.getenv("EXTRACTION_API_KEY", "")
    extraction_trial_ack: bool = os.getenv("EXTRACTION_TRIAL_ACK", "").lower() in (
        "1",
        "true",
        "yes",
    )
    fallback_chain: str = os.getenv(
        "LLM_FALLBACK_CHAIN", "ollama,openai,anthropic,huggingface"
    )
    prompt_cache: bool = os.getenv("LLM_PROMPT_CACHE", "true").lower() not in (
        "0",
        "false",
        "no",
    )

    # Output cap applied when a caller does not name max_tokens.
    max_output_tokens: int = int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "2048"))

    # Two-tier model defaults — the single source for every model reference.
    # ANALYSIS: cheap but capable — ontology discovery and graph analysis.
    # DEBATE: the most powerful — agent debate in the simulation world.
    analysis_model: str = os.getenv("ANALYSIS_LLM_MODEL", "claude-sonnet-5")
    debate_model: str = os.getenv("DEBATE_LLM_MODEL", "claude-opus-5-5")

    # Verdict answer-writer (the final narrative). Defaults to the ANALYSIS tier
    # — it is a single structured-JSON call over the completed debate, not the
    # debate itself. VERDICT_LLM_MODEL overrides the model, VERDICT_MAX_TOKENS the
    # strict-JSON output budget. default_factory (not a class-body default) reads
    # the env when the config is built, so cache-clearing re-reads it.
    verdict_model: str = field(
        default_factory=lambda: os.getenv("VERDICT_LLM_MODEL")
        or os.getenv("ANALYSIS_LLM_MODEL", "claude-sonnet-5")
    )
    verdict_max_tokens: int = field(
        default_factory=lambda: int(os.getenv("VERDICT_MAX_TOKENS", "3000"))
    )

    @classmethod
    def update_provider(cls, provider: str):
        """Update the default provider"""
        if provider in ["openai", "anthropic", "huggingface", "ollama"]:
            cls.default_llm_provider = provider
        else:
            raise ValueError(f"Invalid provider: {provider}")


@lru_cache()
def get_llm_config() -> LLMConfig:
    """Get LLM configuration instance"""
    return LLMConfig()
