import re
from typing import List, Tuple
from .models_persona import PersonaIdentity, PersonaMemory, PersonaBias, PersonaContext
from .repository import PersonaRepository


RELATION_BIAS_MAP = {
    "COMPETES_WITH": ("You are interacting with a competitor. Use a guarded, strategic tone.", 0.9),
    "PARTNERED_WITH": ("You are interacting with a partner. Use a cooperative and trust-preserving tone.", 0.8),
    "SUED_BY": ("You have legal tension with this party. Be precise, risk-aware, and defensive.", 0.95),
    "ACQUIRED": ("You have structural authority from acquisition history. Be integration-focused.", 0.7),
    "WORKED_ON": ("You have relevant execution history. Be concrete and implementation-oriented.", 0.6),
    None: ("No direct relationship found. Stay neutral and evidence-driven.", 0.3),
}


class PersonaFetcher:
    def __init__(self, repo: PersonaRepository, archetype_label: str | None = None):
        self.repo = repo
        self.archetype_label = archetype_label

    async def detect_relevant_entities(self, user_query: str, max_targets: int = 20) -> List[str]:
        known = await self.repo.list_agent_names(archetype_label=self.archetype_label, limit=5000)
        q = user_query.lower()                  
        matched = [n for n in known if re.search(rf"\b{re.escape(n.lower())}\b", q)]
        return matched[:max_targets]

    @staticmethod
    def _derive_bias(relation_type: str | None) -> Tuple[str, float]:
        if not relation_type:
            return RELATION_BIAS_MAP[None]
        if relation_type in RELATION_BIAS_MAP:
            return RELATION_BIAS_MAP[relation_type]

        rel = relation_type.upper()
        negative_tokens = ("SUE", "BLOCK", "DISLIKE", "OPPOSE", "RIVAL", "CONFLICT", "COMPETE", "CHALLENGE")
        positive_tokens = ("PARTNER", "ALLY", "SUPPORT", "INVEST", "ACQUIRE", "MERGE", "COLLAB", "WORK")

        if any(t in rel for t in negative_tokens):
            return ("You are interacting with a tense counterparty. Stay guarded, precise, and strategic.", 0.85)
        if any(t in rel for t in positive_tokens):
            return ("You are interacting with a known collaborator. Stay cooperative but goal-oriented.", 0.75)
        return ("You have prior graph interaction. Stay contextual, neutral, and evidence-driven.", 0.55)

    async def get_persona_context(self, agent_name: str, user_query: str, memory_limit: int = 25) -> PersonaContext:
        identity_row = await self.repo.fetch_identity(self.archetype_label, agent_name)
        if not identity_row:
            raise ValueError(f"Agent node not found: {agent_name}")

        identity = PersonaIdentity(
            name=identity_row["name"],
            archetype=identity_row["archetype"],
            communication_style=identity_row["communication_style"],
            core_values=identity_row["core_values"] if isinstance(identity_row["core_values"], list) else [],
            culture=identity_row.get("culture", ""),
            mission=identity_row.get("mission", ""),
        )

        mem_rows = await self.repo.fetch_recent_memories(self.archetype_label, agent_name, memory_limit=memory_limit)
        memories = [
            PersonaMemory(
                relation_type=r.get("relation_type") or "UNKNOWN",
                target_name=r.get("target_name") or "Unknown",
                summary=r.get("summary") or "",
                timestamp=str(r.get("timestamp") or ""),
            )
            for r in mem_rows
        ]

        targets = await self.detect_relevant_entities(user_query)
        rel_rows = await self.repo.fetch_relationships_to_targets(self.archetype_label, agent_name, targets)

        biases: List[PersonaBias] = []
        for row in rel_rows:
            relation_type = row.get("relation_type")
            instruction, weight = self._derive_bias(relation_type)
            biases.append(
                PersonaBias(
                    target=row["target_name"],
                    relationship=relation_type or "NONE",
                    instruction=instruction,
                    weight=weight,
                )
            )

        return PersonaContext(identity=identity, memories=memories, biases=biases)