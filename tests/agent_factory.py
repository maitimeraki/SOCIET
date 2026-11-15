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


def agent_record(
    node_id: str,
    *,
    run_id: str = "run-x",
    status: str = "published",
    seat: int = 0,
    name: str | None = None,
):
    """A real AgentRecord for one candidate. Published rows carry a view; others do not."""
    from src.persona.agent import Stance
    from src.simulation.agent_record import (
        AgentRecord,
        AgentView,
        CiteIds,
        GenerationInfo,
        NodeInfo,
        RankInfo,
        UniquenessInfo,
        ValidationInfo,
        dossier_hash,
    )
    from src.simulation.evidence import ChunkRow, build_pack

    name = name or f"Agent {node_id}"
    seated = status == "published"
    pack = build_pack(name, [], [ChunkRow("c1", "d1", "Memo", "Market", "Some text.", 0.9)], [])
    view = (
        AgentView(
            name=name,
            type="Company",
            role="analyst",
            stance=Stance.POSITIVE,
            strength=0.5,
            bio="A bio.",
            details="Claim one.",
            confidence=0.5,
        )
        if seated
        else None
    )
    return AgentRecord(
        run_id=run_id,
        node_id=node_id,
        query_hash="qh",
        question="Should we?",
        decision_axis="",
        node=NodeInfo(name=name, aliases=[], type_label="Company", type_source="graph"),
        rank=RankInfo(
            features={"query_relevance": 0.5},
            score=0.5,
            seated=seated,
            reason="seated" if seated else "rejected: profile not seated",
            order=seat if seated else None,
        ),
        evidence=list(pack.items),
        relations=[],
        view=view,
        details_raw="Claim one." if seated else "",
        cites=CiteIds(),
        validation=ValidationInfo(json_ok=True, repairs=0, rejected=[], details_chars=10, cites_valid=True),
        uniqueness=UniquenessInfo(),
        generation=GenerationInfo(model="m", prompt_version="p1", temperature=0.2, attempts=1, latency_ms=1),
        dossier_hash=dossier_hash(pack, "p1"),
        status=status,
        reason=None if seated else "profile not seated",
    )
