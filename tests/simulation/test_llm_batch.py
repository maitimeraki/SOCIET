import asyncio
import pytest
from unittest.mock import AsyncMock

from src.simulation.llm_batch import BatchedLLMRunner, PairPrompt, PairResult


@pytest.fixture
def mock_llm():
    llm = AsyncMock()
    llm.generate = AsyncMock(return_value="mock response")
    return llm


@pytest.mark.asyncio
async def test_concurrency_limit(mock_llm):
    """Verify no more than concurrency LLM calls are in-flight at once."""
    concurrency = 4
    runner = BatchedLLMRunner(mock_llm, concurrency=concurrency)

    max_in_flight = 0
    current_in_flight = 0

    async def slow_generate(system_prompt, user_prompt, **kwargs):
        nonlocal current_in_flight
        current_in_flight += 1
        nonlocal max_in_flight
        max_in_flight = max(max_in_flight, current_in_flight)
        await asyncio.sleep(0.05)
        current_in_flight -= 1
        return "slow response"

    mock_llm.generate = slow_generate

    prompts = [PairPrompt(system_prompt="s", user_prompt=f"u{i}", pair_id=f"p{i}") for i in range(16)]
    results = []
    async for result in runner.gather(prompts):
        results.append(result)

    assert len(results) == 16
    assert max_in_flight <= concurrency, f"Max in-flight was {max_in_flight}, expected {concurrency}"


@pytest.mark.asyncio
async def test_error_isolation(mock_llm):
    """If one call raises, others still complete."""
    async def patched_generate(system_prompt, user_prompt, **kwargs):
        await asyncio.sleep(0.01)
        if user_prompt == "u4":
            raise ValueError("intentional failure")
        return f"ok-{user_prompt}"

    mock_llm.generate = patched_generate

    runner = BatchedLLMRunner(mock_llm, concurrency=8)
    prompts = [PairPrompt(system_prompt="s", user_prompt=f"u{i}", pair_id=f"p{i}") for i in range(10)]

    results = []
    async for result in runner.gather(prompts):
        results.append(result)

    assert len(results) == 10
    errors = [r for r in results if r.error is not None]
    ok_results = [r for r in results if r.error is None]
    assert len(errors) >= 1
    assert len(ok_results) >= 9


@pytest.mark.asyncio
async def test_results_correlation(mock_llm):
    """Each result has the correct pair_id."""
    runner = BatchedLLMRunner(mock_llm, concurrency=4)
    prompts = [
        PairPrompt(system_prompt="s1", user_prompt="u1", pair_id="alpha"),
        PairPrompt(system_prompt="s2", user_prompt="u2", pair_id="beta"),
        PairPrompt(system_prompt="s3", user_prompt="u3", pair_id="gamma"),
    ]

    results_list = []
    async for result in runner.gather(prompts):
        results_list.append(result)

    result_by_id = {r.pair_id: r for r in results_list}

    assert "alpha" in result_by_id
    assert "beta" in result_by_id
    assert "gamma" in result_by_id
    assert result_by_id["alpha"].response == "mock response"
    assert result_by_id["beta"].response == "mock response"
    assert result_by_id["gamma"].response == "mock response"
