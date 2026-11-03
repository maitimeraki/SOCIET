"""Meter llama-index responses for the graph extraction path (ledger R25).

The graph stages construct ``OpenAILike`` directly and bypass ``LLMClient``,
so their tokens never reach the ledger without this wrapper. Each wrapped
method awaits the original call, records the response, and returns it
unchanged; metering failures never break extraction.
"""

import logging
import types

from src.billing import metering

logger = logging.getLogger(__name__)

_WRAPPED_FLAG = "_societas_metering_wrapped"


def wrap_with_metering(llm, *, provider: str, model: str) -> object:
    """Wrap ``llm``'s ``_achat``/``_acomplete`` to record usage. Idempotent."""
    if getattr(llm, _WRAPPED_FLAG, False):
        return llm

    def _wrap(method_name: str) -> None:
        original = getattr(llm, method_name, None)
        if original is None:
            return

        async def wrapper(self, *args, **kwargs):
            response = await original(*args, **kwargs)
            try:
                await metering.record_llama_response(
                    response, provider=provider, model=model
                )
            except Exception as exc:
                logger.warning("could not meter extraction call (%s): %s", provider, exc)
            return response

        object.__setattr__(llm, method_name, types.MethodType(wrapper, llm))

    _wrap("_achat")
    _wrap("_acomplete")
    object.__setattr__(llm, _WRAPPED_FLAG, True)
    return llm
