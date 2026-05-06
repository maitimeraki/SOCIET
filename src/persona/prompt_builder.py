from .models_persona import AgentProfile


class PersonaPromptBuilder:
    @staticmethod
    def build_system_prompt(profile: AgentProfile, recent_memories: list[dict] | None = None) -> str:
        """Construct a system prompt for the agent based on its profile to contribute in simulation debate."""
        # Build a lightweight payload from AgentProfile for the system prompt
        identity = getattr(profile, "identity", None)
        name = identity.name if identity and getattr(identity, "name", None) else "Agent"
        archetype = identity.archetype if identity and getattr(identity, "archetype", None) else "Entity"
        communication_style = identity.communication_style if identity and getattr(identity, "communication_style", None) else "strategic and factual"
        core_values = getattr(identity, "core_values", []) or []
        culture = getattr(identity, "culture", "") or ""
        mission = getattr(identity, "mission", "") or ""

        recent_history = recent_memories or []
        bias_instructions = []

        # convert recent memories rows to short summaries for the prompt
        history_text = "; ".join([str(m.get("summary") or m.get("breadcrumb") or m.get("title") or "memory") for m in recent_history[:20]]) if recent_history else "No recent history available."
        bias_text = " ".join(bias_instructions) if bias_instructions else "No relationship-specific bias."

        return f"""
            You are an autonomous agent representing {name}.

            Your Identity:
            - Archetype: {archetype}
            - Communication style: {communication_style}
            - Core values: {core_values}
            - Culture: {culture}
            - Mission: {mission}

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
        """Construct a user prompt that provides the current debate context to the agent."""
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
