from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional
import os
from dataclasses import dataclass

@dataclass
class LLMConfig:
    """Configuration for LLM providers"""
    
    # OpenAI settings 
    openai_api_key: Optional[str] = os.getenv("OPENAI_API_KEY")
    openai_model: str = "gpt-3.5-turbo"  # or "gpt-4"
    
    # HuggingFace settings
    huggingface_api_key: Optional[str] = os.getenv("HUGGINGFACEHUB_API_TOKEN")
    huggingface_model: str = "Qwen/Qwen3.5-9B"
    
    # Ollama settings (local)
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen3.5:4b")  # or "mistral", "codellama", etc.
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    
    # Default provider (user's favorite)
    default_llm_provider: str = os.getenv("DEFAULT_LLM_PROVIDER", "ollama")
    default_model: str = ollama_model  # For backward compatibility
    
    @classmethod
    def update_provider(cls, provider: str):
        """Update the default provider"""
        if provider in ["openai", "huggingface", "ollama"]:
            cls.default_llm_provider = provider
        else:
            raise ValueError(f"Invalid provider: {provider}")

@lru_cache()
def get_llm_config() -> LLMConfig:
    """Get LLM configuration instance"""
    return LLMConfig()