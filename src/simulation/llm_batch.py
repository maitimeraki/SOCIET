import asyncio
import logging
from dataclasses import dataclass
from typing import Any, AsyncIterator, Optional

from src.billing.metering import MeteringError
from src.observability import LLM_CALLS, LLM_FAILURES

logger = logging.getLogger(__name__)


@dataclass
class PairPrompt:
    system_prompt: str
    user_prompt: str
    pair_id: str
    provider: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None


@dataclass
class PairResult:
    pair_id: str
    response: str
    error: Optional[str] = None


class BatchedLLMRunner:
    def __init__(self, llm: Any, concurrency: int = 8):
        self._llm = llm
        self._sem = asyncio.Semaphore(concurrency)

    async def _run_single(self, prompt: PairPrompt) -> PairResult:
        async with self._sem:
            LLM_CALLS.inc()
            try:
                response = await self._llm.generate(
                    system_prompt=prompt.system_prompt,
                    user_prompt=prompt.user_prompt,
                    provider=prompt.provider,
                    model=prompt.model,
                    temperature=prompt.temperature,
                )
                return PairResult(pair_id=prompt.pair_id, response=response, error=None)
            except MeteringError:
                # Accounting already failed: never degrade this into an empty
                # turn — the job must stop (R9).
                raise
            except Exception as exc:
                LLM_FAILURES.inc()
                logger.error(f"LLM call failed for pair {prompt.pair_id}: {exc}")
                return PairResult(pair_id=prompt.pair_id, response="", error=str(exc))

    async def gather(
        self,
        prompts: list[PairPrompt],
    ) -> AsyncIterator[PairResult]:
        tasks = [self._run_single(p) for p in prompts]
        for coro in asyncio.as_completed(tasks):
            result = await coro
            yield result
