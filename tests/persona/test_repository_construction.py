"""PersonaRepository construction: the embed call path is env-addressed and bounded."""
from unittest.mock import patch

from src.persona.repository import PersonaRepository


def test_embed_model_is_bounded_and_env_addressed(monkeypatch):
    """OllamaEmbedding gets LLMConfig's Ollama base URL plus a request timeout."""
    from src.llm.config_llm import LLMConfig

    monkeypatch.setattr(LLMConfig, "ollama_base_url", "http://sentinel-ollama:1234")

    with patch('src.persona.repository.AsyncGraphDatabase'), \
         patch('src.persona.repository.OllamaEmbedding') as mock_embed:
        PersonaRepository(
            neo4j_uri="bolt://x", neo4j_user="u", neo4j_password="p", neo4j_database="d"
        )

    kwargs = mock_embed.call_args.kwargs
    assert kwargs["base_url"] == "http://sentinel-ollama:1234"
    assert kwargs["client_kwargs"]["timeout"] == 60
