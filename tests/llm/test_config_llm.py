from src.llm.config_llm import LLMConfig


def test_profile_model_defaults_to_the_analysis_tier(monkeypatch):
    monkeypatch.delenv("PROFILE_LLM_MODEL", raising=False)
    monkeypatch.setenv("ANALYSIS_LLM_MODEL", "analysis-tier-model")
    assert LLMConfig().profile_model == "analysis-tier-model"


def test_profile_model_env_overrides_the_analysis_tier(monkeypatch):
    monkeypatch.setenv("PROFILE_LLM_MODEL", "profile-model")
    assert LLMConfig().profile_model == "profile-model"


def test_profile_max_tokens_defaults_to_1200(monkeypatch):
    monkeypatch.delenv("PROFILE_MAX_TOKENS", raising=False)
    assert LLMConfig().profile_max_tokens == 1200
