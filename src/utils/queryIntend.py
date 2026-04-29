from typing import List, Optional
from pydantic import BaseModel, Field
from langchain_ollama import ChatOllama
from src.logging.setup_logging import setup_logging
import json
logger = setup_logging()


class QueryIntent(BaseModel):
    direct_keywords: List[str] = Field(description="Core terms directly in the query")
    latent_sectors: List[str] = Field(description="Hidden or related sectors/industries")
    search_perspectives: List[str] = Field(description="Specific angles like 'Economic', 'Technical', or 'Legal'")

class QueryIntend:
    def __init__(self, model: str):
        self.llm = ChatOllama(model=model, temperature=0)

    async def expand_user_query(self, user_query: str) -> Optional[QueryIntent]:
        """
        Deconstructs the query into intent vectors to prevent 'Missing Sector' syndrome.
        """
        if not user_query or not user_query.strip():
            logger.warning("Received empty user query for intent expansion.")
            return None
        if not self.llm:
            logger.error("LLM client not initialized for QueryIntend.")
            return None
        try:
            prompt = f"""
            Decompose the following user query for a simulation environment. 
            Identify direct terms and hidden latent sectors that are crucial for a 360-degree debate.
            
            Query: {user_query}
            
            Return the response as a JSON matching the QueryIntent schema.
            """
            # Call your expansion LLM here (e.g., GPT-4o-mini or Llama-3-8B)
            expanded_intent = self.llm.with_structured_output(QueryIntent)
            user_intend= expanded_intent.invoke(prompt)
            return user_intend
        except Exception as e:
            logger.error(f"Error expanding user query: {e}")
            return None
        
        

