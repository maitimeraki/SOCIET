"""Tests for ProfileSynthesizer: seating, one generated profile per seat, records, refusal.

The LLM seam is a fake that answers the profile, judge and actor-filter prompts from the
prompt it is given. The graph is a fake that answers the tenant-scoped reads.
"""

import json
import re
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.billing import metering
from src.billing.metering import MeteringError
from src.persona.agent import Stance
from src.persona.graph_context import ChunkHit, ChunkSearch, EntityNode, RelationHit
from src.simulation.evidence import MAX_RELATIONS
from src.simulation.profile_synthesizer import NEIGHBOUR_CAP, ProfileSynthesizer
from src.simulation.ranking import NoAgentsDerivableError

QUESTION = "Should we enter Berlin?"
TEMPLATE_STRINGS = ["Domain expert", "Participant", "direct and evidence-led", "related nodes", "I specialize in"]


class FakeLLM:
    """Answers the profile call with a valid draft that cites the prompt's evidence.

    `fail` names get an unparseable reply, `abstain` names an abstain stance. The
    role echoes the question, so the same node asked two questions gives two profiles.
    `raises` is raised by every call; `raise_on_profile` only by the profile call.
    """

    def __init__(self, actor_flags=None, fail=(), abstain=(), raises=None, raise_on_profile=None, scope_stack=None):
        self.actor_flags = actor_flags or {}
        self.fail = set(fail)
        self.abstain = set(abstain)
        self.raises = raises
        self.raise_on_profile = raise_on_profile
        self.scope_stack = scope_stack
        self.scopes_seen: list[list[str]] = []

    async def generate(self, system_prompt, user_prompt, **kwargs):
        if self.scope_stack is not None:
            self.scopes_seen.append(list(self.scope_stack))
        if self.raises is not None:
            raise self.raises
        if system_prompt.startswith("You are an analyst"):
            if self.raise_on_profile is not None:
                raise self.raise_on_profile
            return self._profile(user_prompt)
        if system_prompt.startswith("You check whether"):
            return json.dumps({"unsupported": []})
        labels = json.loads(user_prompt)
        return json.dumps({label: self.actor_flags.get(label, True) for label in labels})

    def _profile(self, user_prompt: str) -> str:
        name = re.search(r"^name: (.*)$", user_prompt, re.M).group(1)
        question = user_prompt.split("QUESTION\n", 1)[1].split("\n", 1)[0]
        ids = re.findall(r'<evidence id="(e\d+)"', user_prompt)
        if name in self.fail:
            return "this is not json"
        if name in self.abstain:
            return json.dumps(
                {
                    "role": f"sees no bearing on {question}",
                    "stance": "abstain",
                    "strength": 0.2,
                    "bio": _bio(name),
                    "details": _details(ids),
                    "confidence": 0.3,
                    "cites": {"role": ids[:1], "stance": [], "bio": ids[:1], "confidence": []},
                }
            )
        return json.dumps(
            {
                "role": f"presses {question} as proof of demand",
                "stance": "positive",
                "strength": 0.7,
                "bio": _bio(name),
                "details": _details(ids),
                "confidence": 0.4,
                "cites": {"role": ids[:1], "stance": ids[:1], "bio": ids[:1], "confidence": []},
            }
        )


def _bio(name: str) -> str:
    return f"{name} weighs the rollout, tracks compliance and prices the pilot. " * 3


def _details(ids: list[str]) -> str:
    markers = ids[:3]
    return " ".join(
        f"Point {i} weighs the rollout against compliance timing [{markers[i % len(markers)]}]."
        for i in range(30)
    )


def _sentences(name: str) -> str:
    return f"{name} weighs the rollout. {name} tracks compliance. {name} prices the pilot."


def _entity(entity_id: str, name: str, label: str = "Company", score: float = 0.5) -> EntityNode:
    return EntityNode(id=entity_id, name=name, label=label, relevance_score=score)


def _chunks_for(entities: list[EntityNode]) -> ChunkSearch:
    hits = [
        ChunkHit(
            chunk_id=f"c-{entity.id}",
            doc_id=f"doc-{entity.id}",
            doc_title="Market memo",
            section="Pricing",
            text=_sentences(entity.name),
            rank=rank,
            entity_ids=(entity.id,),
        )
        for rank, entity in enumerate(entities, start=1)
    ]
    return ChunkSearch(vector=hits, fulltext=hits)


def _neighbours_for(entities: list[EntityNode], count: int = 1) -> dict[str, list[EntityNode]]:
    return {
        e.id: [_entity(f"{e.id}-n{i}", f"{e.name} partner {i}") for i in range(count)] for e in entities
    }


class FakeGraph:
    """The tenant-scoped reads the synthesizer makes, over fixed entities and chunks."""

    def __init__(self, entities, *, chunks=None, hits=None, neighbours=None, relations=None):
        self.entities = {e.id: e for e in entities}
        self._chunks = chunks if chunks is not None else _chunks_for(list(entities))
        self._hits = list(entities) if hits is None else hits
        self._neighbours = neighbours if neighbours is not None else _neighbours_for(list(entities))
        self._relations = relations or {}
        self.relation_calls: list[tuple[str, list[str]]] = []

    async def find_relevant_chunks(self, query, dataset_id, limit=200):
        return self._chunks

    async def find_relevant_entities(self, query, dataset_id, limit=100):
        return self._hits

    async def find_entities_by_ids(self, entity_ids, dataset_id):
        return [self.entities[i] for i in entity_ids if i in self.entities]

    async def find_connected_nodes_by_seed(self, node_ids, dataset_id, limit=10):
        return {i: self._neighbours.get(i, []) for i in node_ids}

    async def find_relations_for(self, entity_id, counterpart_ids, dataset_id, limit=8):
        self.relation_calls.append((entity_id, list(counterpart_ids)))
        return self._relations.get(entity_id, [])


def _repo() -> MagicMock:
    repo = MagicMock()
    repo.write_persona_provenance = AsyncMock(return_value=1)
    repo.write_persona_entity_links = AsyncMock(return_value=1)
    return repo


def _synth(entities, *, graph: FakeGraph | None = None, repo=None) -> ProfileSynthesizer:
    graph = graph or FakeGraph(entities)
    return ProfileSynthesizer(persona_repo=repo or _repo(), graph_context=graph)


async def _run(synth, llm=None, *, query=QUESTION, max_agents=3, **kwargs):
    return await synth.synthesize(
        query, dataset_id="ds-A", max_agents=max_agents, llm_client=llm or FakeLLM(), **kwargs
    )


KESTRA = _entity("kestra", "Kestra", score=0.9)
LUMEN = _entity("lumen", "Lumen", score=0.8)
ORBIT = _entity("orbit", "Orbit", score=0.7)


# ---- seating: the question decides who is seated -------------------------------------------


@pytest.mark.asyncio
async def test_seats_follow_the_question_not_graph_density():
    lumen = _entity("lumen-pay", "Lumen Pay")
    hub = _entity("dense-hub", "Dense Hub")
    graph = FakeGraph(
        [lumen, hub],
        chunks=ChunkSearch(
            vector=[ChunkHit("c-pay", "doc-pay", "Memo", "Pricing", _sentences("Lumen Pay"), 1, (lumen.id,))],
            fulltext=[ChunkHit("c-pay", "doc-pay", "Memo", "Pricing", _sentences("Lumen Pay"), 1, (lumen.id,))],
        ),
        neighbours={
            hub.id: [_entity(f"hub-{i}", f"Hub part {i}") for i in range(5)],
            lumen.id: [_entity("lumen-n", "Lumen part")],
        },
    )

    agents = await _run(_synth([lumen, hub], graph=graph), max_agents=2)

    assert agents[0].identity.name == "Lumen Pay"


@pytest.mark.asyncio
async def test_a_question_the_graph_does_not_cover_is_refused_with_a_reason():
    graph = FakeGraph([KESTRA], chunks=ChunkSearch(vector=[], fulltext=[]))

    with pytest.raises(NoAgentsDerivableError, match="does not cover"):
        await _run(_synth([KESTRA], graph=graph), query="weather?", max_agents=4)


def test_no_density_fallback_remains():
    from src.simulation import profile_synthesizer

    assert not hasattr(profile_synthesizer, "rank_candidates")


@pytest.mark.asyncio
async def test_decisions_record_every_candidate_and_the_seated_ones_in_order():
    decisions: list = []

    await _run(_synth([KESTRA, LUMEN, ORBIT]), max_agents=2, decisions=decisions)

    seated = [d for d in decisions if d.seated]
    assert [(d.name, d.order) for d in seated] == [("Kestra", 1), ("Lumen", 2)]
    assert [d.reason for d in decisions if not d.seated] == ["eligible, not reached"]


@pytest.mark.asyncio
async def test_an_entity_only_the_chunks_name_is_fetched_by_id_and_seated():
    named_only_by_chunks = _entity("orbit", "Orbit")
    graph = FakeGraph([KESTRA, named_only_by_chunks], hits=[KESTRA])
    graph._chunks = _chunks_for([KESTRA, named_only_by_chunks])

    agents = await _run(_synth([KESTRA], graph=graph), max_agents=2)

    assert {a.identity.name for a in agents} == {"Kestra", "Orbit"}


@pytest.mark.asyncio
async def test_a_non_actor_label_is_not_seated():
    metric = _entity("margin", "Margin", label="Metric")
    entities = [KESTRA, metric]

    agents = await _run(_synth(entities), FakeLLM(actor_flags={"Metric": False}), max_agents=3)

    assert [a.identity.name for a in agents] == ["Kestra"]


@pytest.mark.asyncio
async def test_metering_error_from_the_actor_filter_is_not_absorbed():
    metric = _entity("margin", "Margin", label="Metric")

    with pytest.raises(MeteringError):
        await _run(_synth([metric]), FakeLLM(raises=MeteringError("hold gone")))


@pytest.mark.asyncio
async def test_a_candidate_with_one_piece_of_evidence_is_not_seated():
    graph = FakeGraph([KESTRA], neighbours={"kestra": []})

    agents = await _run(_synth([KESTRA], graph=graph), max_agents=3)

    assert agents == []


@pytest.mark.asyncio
async def test_same_name_entities_share_one_seat():
    twin = _entity("kestra-2", "Kestra")

    agents = await _run(_synth([KESTRA, twin]), max_agents=3)

    assert len(agents) == 1


@pytest.mark.asyncio
async def test_returns_exactly_the_seat_count_when_the_pool_is_larger():
    names = ["Acme", "Borealis", "Cygnet", "Dorado", "Eridanus"]
    entities = [_entity(f"e{i}", name, score=1 - i / 10) for i, name in enumerate(names)]

    agents = await _run(_synth(entities), max_agents=3)

    assert len(agents) == 3


@pytest.mark.asyncio
async def test_returns_fewer_when_the_pool_is_sparse():
    agents = await _run(_synth([KESTRA, LUMEN]), max_agents=5)

    assert len(agents) == 2


# ---- the five profile checks ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_failed_profile_is_not_seated_and_is_recorded():
    records: list = []

    agents = await _run(_synth([KESTRA, LUMEN]), FakeLLM(fail={"Lumen"}), max_agents=2, records=records)

    assert [a.identity.name for a in agents] == ["Kestra"]
    assert [(r.node.name, r.status) for r in records if r.node.name == "Lumen"] == [("Lumen", "rejected")]


@pytest.mark.asyncio
async def test_no_template_string_reaches_any_output():
    records: list = []
    agents = await _run(_synth([KESTRA, LUMEN, ORBIT]), max_agents=3, records=records)

    serialised = json.dumps(
        [a.model_dump(mode="json") for a in agents] + [a.view().model_dump(mode="json") for a in agents]
    )

    assert not [t for t in TEMPLATE_STRINGS if t in serialised]


@pytest.mark.asyncio
async def test_same_node_two_questions_differ():
    synth = _synth([KESTRA])

    first = (await _run(synth, query="Should we enter Berlin?", max_agents=1))[0]
    second = (await _run(synth, query="Is the supplier reliable?", max_agents=1))[0]

    assert first.role != second.role


@pytest.mark.asyncio
async def test_abstain_when_nothing_bears_on_the_question():
    agents = await _run(_synth([KESTRA]), FakeLLM(abstain={"Kestra"}), max_agents=1)

    assert agents[0].stance is Stance.ABSTAIN
    assert agents[0].cites["stance"] == []


@pytest.mark.asyncio
async def test_a_run_where_every_profile_fails_is_refused_with_a_reason():
    with pytest.raises(NoAgentsDerivableError, match="profile"):
        await _run(_synth([KESTRA, LUMEN]), FakeLLM(fail={"Kestra", "Lumen"}), max_agents=2)


# ---- the seated Agent, records, sinks and the seam ------------------------------------------


@pytest.mark.asyncio
async def test_a_seated_agent_carries_the_validated_draft_and_its_pack():
    agents = await _run(_synth([KESTRA]), max_agents=1)

    agent = agents[0]
    assert (agent.node_id, agent.dataset_id, agent.identity.name) == ("kestra", "ds-A", "Kestra")
    assert agent.stance is Stance.POSITIVE
    assert (agent.role, agent.strength, agent.confidence) == (f"presses {QUESTION} as proof of demand", 0.7, 0.4)
    assert agent.bio == _bio("Kestra")
    assert agent.evidence and agent.cites["stance"]


@pytest.mark.asyncio
async def test_relations_are_read_only_to_the_capped_neighbours():
    neighbours = {"kestra": [_entity(f"n{i}", f"Neighbour {i}") for i in range(7)]}
    graph = FakeGraph([KESTRA], neighbours=neighbours)

    await _run(_synth([KESTRA], graph=graph), max_agents=1)

    entity_id, counterparts = graph.relation_calls[0]
    assert (entity_id, len(counterparts)) == ("kestra", NEIGHBOUR_CAP)


@pytest.mark.asyncio
async def test_the_pack_keeps_at_most_eight_relations():
    relations = {
        "kestra": [
            RelationHit("PARTNERS_WITH", True, f"n{i}", f"Neighbour {i}", "c-kestra") for i in range(MAX_RELATIONS + 2)
        ]
    }
    graph = FakeGraph([KESTRA], relations=relations)

    agents = await _run(_synth([KESTRA], graph=graph), max_agents=1)

    assert len(agents[0].relations) == MAX_RELATIONS


@pytest.mark.asyncio
async def test_records_hold_every_candidate_tried_published_or_rejected():
    records: list = []

    await _run(_synth([KESTRA, LUMEN]), FakeLLM(fail={"Lumen"}), max_agents=2, records=records)

    assert sorted((r.node.name, r.status) for r in records) == [("Kestra", "published"), ("Lumen", "rejected")]
    assert all(r.run_id == records[0].run_id for r in records)


@pytest.mark.asyncio
async def test_a_rejected_record_carries_no_client_view_and_no_text():
    records: list = []

    await _run(_synth([KESTRA, LUMEN]), FakeLLM(fail={"Lumen"}), max_agents=2, records=records)

    rejected = next(r for r in records if r.status == "rejected")
    assert (rejected.view, rejected.details_raw) == (None, "")


@pytest.mark.asyncio
async def test_a_profile_call_runs_inside_the_debate_scope(monkeypatch):
    stack: list[str] = []

    @contextmanager
    def spy_scope(source):
        stack.append(source)
        try:
            yield
        finally:
            stack.pop()

    monkeypatch.setattr(metering, "source_scope", spy_scope)
    llm = FakeLLM(scope_stack=stack)

    await _run(_synth([KESTRA]), llm, max_agents=1)

    assert llm.scopes_seen and all("debate" in scope for scope in llm.scopes_seen)


@pytest.mark.asyncio
async def test_metering_error_from_the_profile_call_is_not_absorbed():
    with pytest.raises(MeteringError):
        await _run(_synth([KESTRA]), FakeLLM(raise_on_profile=MeteringError("hold gone")), max_agents=1)


@pytest.mark.asyncio
async def test_the_seated_stance_and_provenance_are_persisted_for_the_topology():
    repo = _repo()

    await _run(_synth([KESTRA], repo=repo), max_agents=1)

    repo.write_persona_entity_links.assert_awaited_once()
    kwargs = repo.write_persona_entity_links.await_args.kwargs
    assert (kwargs["persona_name"], kwargs["stance"]) == ("Kestra", "POSITIVE")
    assert kwargs["chunk_node_ids"] == ["c-kestra"]


@pytest.mark.asyncio
async def test_a_rejected_profile_writes_no_links():
    repo = _repo()

    await _run(_synth([KESTRA, LUMEN], repo=repo), FakeLLM(fail={"Lumen"}), max_agents=2)

    persisted = [c.kwargs["persona_name"] for c in repo.write_persona_entity_links.await_args_list]
    assert persisted == ["Kestra"]


@pytest.mark.asyncio
async def test_a_failed_link_write_warns_and_keeps_the_seat():
    repo = _repo()
    repo.write_persona_provenance = AsyncMock(side_effect=RuntimeError("neo4j down"))
    warnings: list[str] = []

    agents = await _run(_synth([KESTRA], repo=repo), max_agents=1, warnings=warnings)

    assert [a.identity.name for a in agents] == ["Kestra"]
    assert any("provenance write failed" in w for w in warnings)


@pytest.mark.asyncio
async def test_on_profile_emits_each_seated_agent_in_order():
    emitted: list[tuple[str, int, int]] = []

    async def emit(profile, index, total):
        emitted.append((profile.identity.name, index, total))

    await _run(_synth([KESTRA, LUMEN]), max_agents=2, on_profile=emit)

    assert emitted == [("Kestra", 1, 2), ("Lumen", 2, 2)]


@pytest.mark.asyncio
async def test_a_raising_emitter_does_not_drop_the_seat():
    async def emit(profile, index, total):
        raise RuntimeError("socket closed")

    agents = await _run(_synth([KESTRA]), max_agents=1, on_profile=emit)

    assert [a.identity.name for a in agents] == ["Kestra"]


@pytest.mark.asyncio
async def test_synthesize_refuses_to_run_without_an_llm_client():
    with pytest.raises(ValueError, match="llm_client"):
        await _synth([KESTRA]).synthesize(QUESTION, dataset_id="ds-A", max_agents=1)


@pytest.mark.asyncio
async def test_joiners_are_refused_until_task_2_6b():
    with pytest.raises(NotImplementedError, match="2.6b"):
        await _synth([KESTRA]).synthesize_from_names(["Kestra"], QUESTION, dataset_id="ds-A")


@pytest.mark.asyncio
async def test_an_empty_joiner_list_is_a_no_op():
    assert await _synth([KESTRA]).synthesize_from_names([], QUESTION, dataset_id="ds-A") == []
