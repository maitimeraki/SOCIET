"""One slim-Agent factory for the persona and simulation tests.

Every required field is set here, so a test never leans on a fabricated default
and a field the Agent does not carry fails loudly. Override any field by keyword.
"""

from src.persona.agent import Agent, PersonaIdentity, Stance


def slim_agent(name: str = "A", **over) -> Agent:
    base = dict(
        node_id=f"node-{name}",
        dataset_id="ds-test",
        identity=PersonaIdentity(name=name, type_label="Company"),
        role="analyst",
        stance=Stance.POSITIVE,
        strength=0.5,
        confidence=0.5,
        bio="A two-sentence bio.",
        details_raw="A first-person profile.",
        evidence=[],
        relations=[],
        cites={},
    )
    base.update(over)
    return Agent(**base)
