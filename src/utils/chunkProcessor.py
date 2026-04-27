# src/utils/chunkProcessor.py (Suggested Refinements)
import hashlib
from typing import List, Dict, Any
from pydantic import BaseModel, Field
from src.graph.models_graph import ProcessedChunk
from llama_index.core.llms import ChatMessage, MessageRole
from llama_index.core.prompts import ChatPromptTemplate
# Assuming ProcessedChunk and other models are correctly defined elsewhere
# from src.graph.models_graph import ProcessedChunk

class ChunkEnrichment(BaseModel):
    # ... existing code ...
    summary_context: str = Field(description="5-6 sentence summary focusing on key entities and actions.")
    domain_tags: List[str] = Field(description="List of up to 3 tags, MUST map to existing ontology tags.")
    expertise_level: str = Field(description="Must be one of: Strategic, Technical, Operational.")

class ChunkProcessor:
    def __init__(self, llm):
        self.llm = llm

    async def get_chunk_metadata(self, chunk_text: str) -> ChunkEnrichment:
        # --- REVISED PROMPT ---
        prompt = ChatPromptTemplate(
            message_templates=[
                ChatMessage(
                    role=MessageRole.SYSTEM,
                    content="You are an expert knowledge analyst. Analyze the following text chunk. Your goal is to extract structured metadata that will enhance searchability and graph connectivity."
                ),
                ChatMessage(
                    role=MessageRole.USER,
                    content=f"""
                    Constraints:
                    1. summary_context: Must be 5-6 sentences, summarizing the core facts, entities, and actions.
                    2. domain_tags: Must be 3 tags selected ONLY from the known ontology: [List of known tags here].
                    3. expertise_level: Must be one of: Strategic, Technical, Operational.

                    Chunk Text:
                    ---
                    {chunk_text}
                    ---
                    Return ONLY a JSON object matching the schema.
                    """
                )
            ]
        )
        return await self.llm.astructured_predict(ChunkEnrichment, prompt)

    def _hash(self, text: str) -> str:
        return hashlib.sha256((text or "").encode("utf-8")).hexdigest()

    async def process_document(self, chunk: str, chunk_index: int, parent_doc_id: str = "", metadata: Dict[str, Any] = {}) -> ProcessedChunk:
        """
        Process a single chunk: enrich with metadata and create ProcessedChunk object
        
        Args:
            chunk: The text chunk to process
            chunk_index: Index of this chunk in the original document
            parent_doc_id: ID of the parent document
        
        Returns:
            ProcessedChunk object with enriched metadata
        """
        # 1. Get metadata enrichment for the chunk
        enrichment = await self.get_chunk_metadata(chunk)
        
        # 2. Create and return ProcessedChunk
        return ProcessedChunk(
            parent_doc_id=parent_doc_id,
            chunk_index=chunk_index,
            content_hash=self._hash(chunk),
            content=chunk,
            summary_context=enrichment.summary_context,
            breadcrumb="",  # Default value
            header_level=0,  # Default value
            domain_tags=enrichment.domain_tags,
            expertise_level=enrichment.expertise_level,
            metadata=metadata
        )
        