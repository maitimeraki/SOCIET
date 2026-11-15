"""One slim-Agent factory for the persona and simulation tests.

Every field the Agent needs is passed explicitly, so a test never leans on a
fabricated default. Override any field by keyword.
"""

from src.persona.agent import Agent, DiscoveryType, PersonaIdentity, Stance


def slim_agent(name: str = "A", **over) -> Agent:
    base = dict(
        identity=PersonaIdentity(
            name=name,
            archetype="analyst",
            communication_style="direct",
            type_label="Company",
        ),
        stance=Stance.POSITIVE,
        strength=0.5,
        confidence=0.5,
        role="analyst",
        bio="A two-sentence bio.",
        details_raw="A first-person profile.",
        # Old-model field, still required until C3 removes it.
        discovery_type=DiscoveryType.GRAPH_DISCOVERY,
    )
    base.update(over)
    return Agent(**base)
