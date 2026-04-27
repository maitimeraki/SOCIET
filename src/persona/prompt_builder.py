from .models_persona import PersonaContext


class PersonaPromptBuilder:
    @staticmethod
    def build_system_prompt(ctx: PersonaContext) -> str:
        payload = ctx.to_prompt_dict()
        history_text = "; ".join(payload["recent_history"][:20]) if payload["recent_history"] else "No recent history available."
        bias_text = " ".join(payload["bias_instructions"]) if payload["bias_instructions"] else "No relationship-specific bias."

        return f"""
You are an autonomous agent representing {payload["org_name"]}.

Your Identity:
- Archetype: {payload["archetype"]}
- Communication style: {payload["communication_style"]}
- Core values: {payload["core_values"]}
- Culture: {payload["culture"]}
- Mission: {payload["mission"]}

Your Context:
- Based on your graph history, you have recently: {history_text}

Relationship Bias Instructions:
- {bias_text}

Constraint:
- Do not argue from a general organizational perspective.
- Only use the specific values and history provided above.
- If context is missing, state uncertainty instead of inventing facts.
- Keep the response strategic, concise, and directly tied to the topic.
""".strip()

    @staticmethod
    def build_user_prompt(topic: str, debate_history: list[str], round_no: int) -> str:
        history = "\n".join(debate_history[-12:]) if debate_history else "No prior statements."
        return f"""
Debate topic:
{topic}

Current round:
{round_no}

Recent debate transcript:
{history}

Return ONLY valid JSON with keys:
{{
  "stance": "support|oppose|neutral",
  "position": "your current argument",
  "evidence": "direct reference to provided identity/history",
  "counterpoint": "specific response to one prior speaker or 'none'",
  "confidence": 0.0,
  "summary": "one-line strategic summary"
}}
""".strip()
