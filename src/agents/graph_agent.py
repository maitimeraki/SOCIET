import json
from typing import Any, Dict, List, Optional
from src.llm.client import LLMClient
from src.persona.fetcher import PersonaFetcher
from src.persona.prompt_builder import PersonaPromptBuilder


def _strip_json_fences(text: str) -> str:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.replace("```json", "").replace("```", "").strip()
    return cleaned


class GraphAgent:
    """
    Graph-grounded agent.
    Here actions are just speaking turns in the debate, but could be extended to include graph updates (new beliefs, new relationships, etc.)
     - Each turn, agent fetches its persona context from the graph (identity + memory + relationship bias)
     - Generates a response based on that context and the debate history
    """

    def __init__(
        self,
        name: str,
        persona_fetcher: PersonaFetcher,
        llm_client: LLMClient,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        self.name = name
        self.persona_fetcher = persona_fetcher
        self.llm_client = llm_client
        self.provider = provider
        self.model = model

    async def speak(
        self,
        topic: str,
        debate_history: List[str],
        round_no: int,
    ) -> Dict[str, Any]:
        query_context = "\n".join([topic] + debate_history[-8:])
        persona_ctx = await self.persona_fetcher.get_persona_context(
            agent_name=self.name,
            user_query=query_context,
        )
        system_prompt = PersonaPromptBuilder.build_system_prompt(persona_ctx)
        user_prompt = PersonaPromptBuilder.build_user_prompt(
            topic=topic,
            debate_history=debate_history,
            round_no=round_no,
        )

        raw = await self.llm_client.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            provider=self.provider,
            model=self.model,
            temperature=0.4,
        )

        parsed = self._parse_turn(raw)
        parsed["agent_name"] = self.name
        parsed["round_no"] = round_no
        parsed["raw_response"] = raw
        return parsed

    def _parse_turn(self, raw_response: str) -> Dict[str, Any]:
        text = _strip_json_fences(raw_response)

        try:
            obj = json.loads(text)
            return {
                "stance": str(obj.get("stance", "neutral")).lower(),
                "position": str(obj.get("position", "")).strip(),
                "evidence": str(obj.get("evidence", "")).strip(),
                "confidence": float(obj.get("confidence", 0.5)),
                "summary": str(obj.get("summary", "")).strip(),
            }
        except Exception:
            return {
                "stance": "neutral",
                "position": raw_response.strip(),
                "evidence": "",
                "confidence": 0.5,
                "summary": raw_response.strip()[:240],
            }