"""S3 query understanding — raw question → structured intent.

The intent object is the standard output every later stage reads: the core
question, domain tags, the keyword/entity frame, the stance axis, and the
audit trail (extraction confidence + model/provider used). `extraction_confidence`
and the model/provider fields are set in Python, never asked of the LLM.

The LLM path goes through the LiteLLM client (`src/llm/client.py`) and is fully
async; `fallback_intent` is the deterministic, network-free intent used when
extraction fails, so a debate is never blocked by a provider outage.
"""
import json
from typing import List, Optional

from pydantic import BaseModel, Field

from src.llm.client import LLMClient, global_llm_client
from src.llm.config_llm import get_llm_config
from src.logging.setup_logging import setup_logging

logger = setup_logging()

LLM_EXTRACTION_CONFIDENCE = 0.9
FALLBACK_EXTRACTION_CONFIDENCE = 0.2

_SYSTEM_PROMPT = (
    "You decompose a user's question for a multi-agent debate simulation, to avoid missing sectors. "
    "Reply with one JSON object and nothing else. Keys: "
    "core_question (string: the question restated in one line); "
    "domain_tags (array of strings: domains/capabilities the question touches, e.g. legal, economic, cultural); "
    "direct_keywords (array of strings: core terms directly in the question); "
    "latent_sectors (array of strings: hidden or related sectors/industries a 360-degree debate needs); "
    "entity_frame (array of strings: named entities — organisations, people, places, products); "
    "search_perspectives (array of strings: angles such as Economic, Technical, Legal); "
    "stance_axis (string: what 'support' and what 'oppose' mean for THIS question)."
)


class QueryIntent(BaseModel):
    """Structured intent for one question. Constructible and serializable without an LLM."""

    # Filled by the LLM.
    direct_keywords: List[str] = Field(description="Core terms directly in the query")
    latent_sectors: List[str] = Field(description="Hidden or related sectors/industries")
    search_perspectives: List[str] = Field(description="Specific angles like 'Economic', 'Technical', or 'Legal'")
    core_question: str = Field(default="", description="The question restated in one line")
    domain_tags: List[str] = Field(default_factory=list, description="Domain/capability tags, e.g. legal, economic, cultural")
    entity_frame: List[str] = Field(default_factory=list, description="Named entities in the query (organisations, people, places, products)")
    stance_axis: str = Field(default="", description="What 'support' vs 'oppose' means for THIS question")

    # Set in Python, never by the LLM.
    extraction_confidence: float = Field(default=FALLBACK_EXTRACTION_CONFIDENCE, description="0-1 confidence in this extraction")
    llm_model: str = Field(default="", description="Model the extraction used, for auditability")
    llm_provider: str = Field(default="", description="Provider the extraction used, for auditability")


class QueryIntend:
    """Extracts a `QueryIntent` from a user query via the LiteLLM client."""

    def __init__(
        self,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        client: Optional[LLMClient] = None,
    ):
        config = get_llm_config()
        self.provider = provider or getattr(config, "default_llm_provider", "ollama")
        self.model = model or getattr(config, f"{self.provider}_model", None)
        self.llm = client or global_llm_client

    async def expand_user_query(
        self,
        user_query: str,
        selected_domains: Optional[List[str]] = None,
    ) -> Optional[QueryIntent]:
        """Return the intent for `user_query`, or the deterministic fallback if extraction fails.

        Returns None only for an empty query — an extraction failure never does,
        so a failed provider cannot block the debate.
        """
        query = " ".join((user_query or "").split())
        if not query:
            logger.warning("Received empty user query for intent expansion.")
            return None
        try:
            raw = await self.llm.generate(
                _SYSTEM_PROMPT,
                f"Query: {query}",
                provider=self.provider,
                model=self.model,
                temperature=0,
            )
            return self._parse(raw)
        except Exception as e:
            logger.warning(f"Intent extraction failed ({e}) — using the deterministic fallback intent.")
            return self.fallback_intent(query, selected_domains)

    def fallback_intent(
        self,
        user_query: str,
        selected_domains: Optional[List[str]] = None,
    ) -> QueryIntent:
        """Deterministic, network-free intent: the query text plus the request's selected domains."""
        query = " ".join((user_query or "").split())
        domains = list(selected_domains or [])
        logger.warning("Deterministic fallback intent used for query: %s", query[:80])
        return QueryIntent(
            direct_keywords=[query] if query else [],
            latent_sectors=[],
            search_perspectives=domains,
            core_question=query,
            domain_tags=domains,
            entity_frame=[],
            stance_axis="",
            extraction_confidence=FALLBACK_EXTRACTION_CONFIDENCE,
            llm_model=self.model or "",
            llm_provider=self.provider,
        )

    def _parse(self, raw: str) -> QueryIntent:
        """Parse a JSON object out of the model's reply. Raises on anything unusable."""
        text = raw or ""
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("no JSON object in LLM reply")
        payload = json.loads(text[start:end + 1])
        for audit_field in ("extraction_confidence", "llm_model", "llm_provider"):
            payload.pop(audit_field, None)
        return QueryIntent(
            **payload,
            extraction_confidence=LLM_EXTRACTION_CONFIDENCE,
            llm_model=self.model or "",
            llm_provider=self.provider,
        )
