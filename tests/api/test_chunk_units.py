"""The chunk-size env vars are character-facing; the splitter receives tokens.

The env names previously said ..._CHARS but held SentenceSplitter token budgets.
GraphConfig now carries chars and derives tokens (chars // 4); the job must hand
the splitter the token value, never the char value.
"""
from unittest.mock import AsyncMock
import sys
import types

import pytest

import src.api.api_server as api_server
from src.graph.config_graph import GraphConfig
from src.graph.models_graph import GlobalInputDocument, LocalOntology


def test_config_derives_token_budget_from_char_budget():
    cfg = GraphConfig(chunk_size_chars=8000, chunk_overlap_chars=800)

    assert cfg.chunk_size_tokens == 2000
    assert cfg.chunk_overlap_tokens == 200


class _Discovery:
    async def run(self, documents, sample_size=1):
        return LocalOntology.model_validate({
            "metadata": {"ontology_id": "onto-chunk-units"},
            "entity_types": [{
                "type_name": "PERSON",
                "description": "Person",
                "properties": [{"name": "name", "description": "n"}],
            }],
            "relation_types": [],
        })


@pytest.mark.asyncio
async def test_job_passes_token_budget_not_char_budget(monkeypatch):
    """The call site (api_server.py:331) feeds split_text_sentences tokens, not chars."""
    seen = {}

    def split_spy(text, chunk_size, chunk_overlap):
        seen["chunk_size"] = chunk_size
        seen["chunk_overlap"] = chunk_overlap
        return ["One sentence about the migration plan."]

    monkeypatch.setattr(api_server, "split_text_sentences", split_spy)
    monkeypatch.setattr(api_server, "OntologyDiscoveryStage", lambda **kwargs: _Discovery())
    monkeypatch.setattr(api_server, "_persist_run", AsyncMock())
    # Pin the char budget so the assertion is independent of the local .env.
    monkeypatch.setattr(api_server, "GraphConfig", lambda: GraphConfig(chunk_size_chars=8000, chunk_overlap_chars=800))
    # _execute_unified_job lazily imports GraphExtractionStage; stub it so this
    # chunk-budget test does not depend on the extraction module at all.
    stub = types.ModuleType("src.graph.graph_build")
    stub.GraphExtractionStage = lambda cfg: None
    monkeypatch.setitem(sys.modules, "src.graph.graph_build", stub)

    job_id = "test-chunk-units"
    api_server.RUNS[job_id] = {"job_id": job_id, "result": None}
    documents = [GlobalInputDocument(document_id="d1", source_type="text", text="ignored", metadata={})]

    await api_server._execute_unified_job(job_id, "ontology", "ds1", documents)

    assert seen["chunk_size"] == 2000   # 8000 chars // 4, not 8000
    assert seen["chunk_overlap"] == 200  # 800 chars // 4, not 800
