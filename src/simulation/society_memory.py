"""Society memory: per-round commit of debate output to Neo4j + snapshot read-back.

Round-barrier protocol: every agent's statements land in the graph the moment
its round ends; every round >= 2 reads the committed society state back before
speaking. Idempotent: Opinion writes MERGE on (dataset_id, query_hash, round_no,
agent_name); REACTED_TO reactions MERGE on (dataset_id, query_hash, round_no)
between dataset-scoped Personas. Re-running any round is safe.
"""
from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from src.simulation.pair_turn import AgentTurn, CommPair, RoundResult

if TYPE_CHECKING:
    from src.persona.agent import Agent

logger = logging.getLogger(__name__)

#: Fixed budget for each self-history summary rendered into the prompt.
SELF_HISTORY_SUMMARY_CHARS = 200


def _profile_float(profile, attr: str, default: float) -> float:
    """Read a float off a profile, falling back only when it is absent or None.

    `Agent.conviction` is `ge=0.0`, so 0.0 is a legitimate value: `value or default`
    would silently rewrite it to the default and fabricate debate weight.
    """
    value = getattr(profile, attr, None) if profile is not None else None
    return default if value is None else float(value)

_OPINION_CYPHER = """
UNWIND $opinions AS op
MERGE (o:Opinion {dataset_id: $dataset_id, query_hash: $query_hash,
                  round_no: op.round_no, agent_name: op.agent_name})
SET o.text = op.text, o.stance = op.stance, o.confidence = op.confidence,
    o.conviction = op.conviction, o.cior = op.cior, o.weight = op.weight,
    o.entities = op.entities, o.ts = datetime()
MERGE (p:Persona {name: op.agent_name, dataset_id: $dataset_id})
MERGE (p)-[:STATED]->(o)
SET p.current_stance = op.stance,
    p.current_summary = left(op.text, 300),
    p.last_round = op.round_no,
    p.updated_at = datetime()
"""

_REACTION_CYPHER = """
UNWIND $reactions AS r
MATCH (a:Persona {name: r.speaker_name, dataset_id: $dataset_id})
MATCH (b:Persona {name: r.target_name, dataset_id: $dataset_id})
MERGE (a)-[x:REACTED_TO {dataset_id: $dataset_id, query_hash: $query_hash,
                          round_no: r.round_no}]->(b)
SET x.summary = left(r.summary, 300), x.stance = r.stance, x.confidence = r.confidence
"""

_SELF_HISTORY_CYPHER = """
MATCH (p:Persona {name: $agent_name, dataset_id: $dataset_id})-[:STATED]->(o:Opinion)
WHERE o.query_hash = $query_hash AND o.round_no < $through_round
RETURN o.round_no AS round_no, o.stance AS stance,
       left(o.text, $summary_chars) AS summary
ORDER BY o.round_no ASC
"""

_MENTIONS_CYPHER = """
UNWIND $rows AS row
MATCH (o:Opinion {dataset_id: $dataset_id, query_hash: $query_hash,
                  round_no: row.round_no, agent_name: row.agent_name})
UNWIND row.entities AS ref
MATCH (e) WHERE e.name = ref AND NOT e:Persona AND NOT e:Chunk
MERGE (o)-[:MENTIONS]->(e)
"""

_OPINION_READ_CYPHER = """
MATCH (o:Opinion {dataset_id: $dataset_id, query_hash: $query_hash})
WHERE o.round_no <= $through_round
WITH o ORDER BY o.weight DESC
LIMIT $cap
RETURN o.agent_name AS agent, o.round_no AS round_no, o.stance AS stance,
       o.confidence AS confidence, o.weight AS weight,
       left(o.text, 150) AS summary, o.entities AS entities
"""

#: Per-speaker variant: the reader's own lines never enter the pool, so its high
#: weight cannot consume the cap slots meant for others' opinions.
_OPINION_READ_EXCLUDING_SPEAKER_CYPHER = """
MATCH (o:Opinion {dataset_id: $dataset_id, query_hash: $query_hash})
WHERE o.round_no <= $through_round AND o.agent_name <> $speaker
WITH o ORDER BY o.weight DESC
LIMIT $cap
RETURN o.agent_name AS agent, o.round_no AS round_no, o.stance AS stance,
       o.confidence AS confidence, o.weight AS weight,
       left(o.text, 150) AS summary, o.entities AS entities
"""


def _opinion_entry(r: dict) -> dict:
    """Map one opinion row to the snapshot entry shape `to_prompt` renders."""
    return {
        "agent": r["agent"], "round": r.get("round_no") or 0,
        "stance": r.get("stance") or "NEUTRAL",
        "confidence": float(r.get("confidence") or 0.0),
        "weight": float(r.get("weight") or 0.0),
        "summary": r.get("summary") or "",
    }


@dataclass
class SocietySnapshot:
    """What the society has committed to the graph, read back per round."""

    round: int
    entries: List[dict] = field(default_factory=list)
    #: Per-speaker opinion pools keyed by speaking agent: each was read with that
    #: speaker excluded, so its own high-weight lines cannot crowd the block.
    entries_by_speaker: Dict[str, List[dict]] = field(default_factory=dict)
    #: The speaker's OWN prior opinions ({agent, round, stance, summary}), keyed
    #: by agent so `self_prompt` can select per speaker. Empty in round 1.
    self_entries: List[dict] = field(default_factory=list)
    neighbor_map: Dict[str, List[str]] = field(default_factory=dict)
    buzz: List[dict] = field(default_factory=list)
    consensus: Optional[dict] = None
    version: str = ""

    def to_prompt(self, speaker: str, opponent: str,
                  max_opinions: int = 6, max_chars: int = 1300) -> str:
        """Rendered SOCIETY STATE block; never includes the speaker's own lines."""
        entries = self.entries_by_speaker.get(speaker, self.entries)
        if not entries:
            return ""
        lines = [f"SOCIETY STATE (through round {self.round}):"]
        if self.consensus:
            lines.append(
                f"Consensus: {self.consensus['stance']} holds {self.consensus['weight_share']:.0%} of CIOR weight."
            )
        neighbors = set(self.neighbor_map.get(speaker, []))
        picked = 0
        for e in sorted(entries, key=lambda x: x.get("weight", 0.0), reverse=True):
            if picked >= max_opinions:
                break
            if e["agent"] == speaker:
                continue
            marker = " [directly connected to you]" if e["agent"] in neighbors else ""
            lines.append(
                f"- {e['agent']} (R{e['round']}, {e['stance']}, "
                f"conf {e.get('confidence', 0.0):.2f}){marker}: {(e.get('summary') or '')[:150]}"
            )
            picked += 1
        if self.buzz:
            buzz_str = ", ".join(f"{b['entity']} ({b['mentions']})" for b in self.buzz[:3])
            lines.append(f"Widely discussed entities: {buzz_str}")
        text = "\n".join(lines)
        if len(text) > max_chars:
            text = text[:max_chars].rsplit("\n", 1)[0]
        return text

    def self_prompt(self, speaker: str, max_chars: int = 1200) -> str:
        """Rendered YOUR PRIOR POSITIONS block for `speaker`; "" when it has none.

        Distinct from `to_prompt`: that block is what *others* said, this one is
        the speaker's own committed positions, ordered by round.
        """
        mine = [e for e in self.self_entries if e.get("agent") == speaker]
        if not mine:
            return ""
        lines = [f"YOUR PRIOR POSITIONS (through round {self.round}):"]
        for e in sorted(mine, key=lambda x: x.get("round", 0)):
            lines.append(f"- R{e.get('round', 0)} ({e.get('stance') or 'NEUTRAL'}): {e.get('summary') or ''}")
        text = "\n".join(lines)
        if len(text) > max_chars:
            text = text[:max_chars].rsplit("\n", 1)[0]
        return text


class SocietyMemory:
    """Single owner of the society graph memory: write (commit_round) + read (read_snapshot)."""

    def __init__(self, driver, db: str):
        self._driver = driver
        self._db = db

    async def commit_round(
        self,
        round_result: RoundResult,
        dataset_id: str,
        query_hash: str,
        profile_map: Dict[str, "Agent"],
    ) -> dict:
        """Commit one round atomically. MERGE — idempotent. Returns receipt dict."""
        turns_by_agent: Dict[str, list] = {}
        for turn in round_result.turns:
            turns_by_agent.setdefault(turn.agent_name, []).append(turn)

        # Reactions are pair relations, so they come from the pair loop — but keyed
        # by (speaker, target): REACTED_TO MERGEs on (dataset_id, query_hash, round_no)
        # between the same two Personas, so a repeated CommPair yields one edge, not
        # two. Last turn wins, matching the Opinion stance/confidence below.
        reactions_by_key: Dict[tuple, dict] = {}
        for pair in round_result.pairs:
            for turn in round_result.turns:
                if turn.agent_name == pair.agent_a:
                    target_name = pair.agent_b
                elif turn.agent_name == pair.agent_b:
                    target_name = pair.agent_a
                else:
                    continue
                if target_name == turn.agent_name:
                    continue
                reactions_by_key[(turn.agent_name, target_name)] = {
                    "speaker_name": turn.agent_name,
                    "target_name": target_name,
                    "round_no": round_result.round_num,
                    "summary": turn.content,
                    "stance": turn.stance,
                    "confidence": turn.confidence,
                }
        reactions: List[dict] = list(reactions_by_key.values())

        opinions: List[dict] = []
        for agent_name, turns in turns_by_agent.items():
            profile = profile_map.get(agent_name)
            if profile is None:
                logger.warning(
                    "SocietyMemory: agent '%s' absent from profile_map; opinion weight "
                    "falls back to conviction=0.5, cior=0.0 (reduced weight)",
                    agent_name,
                )
            conviction = _profile_float(profile, "conviction", 0.5)
            cior = _profile_float(profile, "cior", 0.0)
            last = turns[-1]  # final position in this round is the canonical stance
            entities: list[str] = []
            for t in turns:
                for ref in t.references:
                    if ref not in entities:
                        entities.append(ref)
            opinions.append({
                "agent_name": agent_name,
                "round_no": round_result.round_num,
                "text": "\n\n".join(t.content for t in turns),
                "stance": last.stance,
                "confidence": last.confidence,
                "conviction": conviction,
                "cior": cior,
                "weight": round(last.confidence * conviction * (1 + cior) / 2, 6),
                "entities": entities[:8],
            })

        receipt = {"round": round_result.round_num, "opinions": len(opinions),
                   "edges": len(reactions), "failed": False}
        if not opinions:
            return receipt

        mention_rows = [{"agent_name": o["agent_name"], "round_no": o["round_no"],
                         "entities": o["entities"]} for o in opinions if o["entities"]]
        try:
            async with self._driver.session(database=self._db) as session:
                tx = await session.begin_transaction()
                await tx.run(_OPINION_CYPHER, opinions=opinions,
                             dataset_id=dataset_id, query_hash=query_hash)
                await tx.run(_REACTION_CYPHER, reactions=reactions,
                             dataset_id=dataset_id, query_hash=query_hash)
                if mention_rows:
                    await tx.run(_MENTIONS_CYPHER, rows=mention_rows,
                                 dataset_id=dataset_id, query_hash=query_hash)
                await tx.commit()
        except Exception as exc:
            logger.exception("SocietyMemory: commit failed for round %s", round_result.round_num)
            return {"round": round_result.round_num, "opinions": len(opinions),
                    "edges": len(reactions), "failed": True, "error": str(exc)}
        return receipt

    async def read_snapshot(
        self, dataset_id: str, query_hash: str,
        through_round: int, top_k: int = 8,
        speakers: Optional[List[str]] = None,
    ) -> SocietySnapshot:
        """Read committed society state through a round. One bounded opinion query per
        speaking agent + one neighbor query.

        When `speakers` is given, the opinions are read once per speaker with that
        speaker excluded, so a dominant speaker's own high-weight lines cannot crowd
        the pool; the per-speaker rows land in `entries_by_speaker`. Without it the
        read is a single pool (older callers).
        """
        cap = max(top_k * 4, 40)
        # OPPOSES/SUPPORTS are static graph edges (no query_hash), so alone they would
        # let a [directly connected to you] marker leak from an unrelated debate on
        # the dataset. They only count as "directly connected" when the pair also
        # shares a graph entity (the same static relation topology pairs on) or has a
        # REACTED_TO edge in this run. The REACTED_TO arm stays narrowed to this debate.
        neighbor_q = """
        MATCH (p:Persona)-[r:OPPOSES|SUPPORTS|REACTED_TO]-(q:Persona)
        WHERE coalesce(p.dataset_id, '') = $dataset_id
          AND coalesce(q.dataset_id, '') = $dataset_id
          AND (
            (type(r) = 'REACTED_TO' AND r.query_hash = $query_hash)
            OR (
              type(r) <> 'REACTED_TO'
              AND (
                EXISTS {
                  MATCH (p)-[r1]-(e)-[r2]-(q)
                  WHERE NOT e:Chunk AND NOT e:Persona
                }
                OR EXISTS {
                  MATCH (p)-[x:REACTED_TO]-(q) WHERE x.query_hash = $query_hash
                }
              )
            )
          )
        RETURN p.name AS src, collect(DISTINCT q.name) AS neighbors
        """
        entries_by_speaker: Dict[str, List[dict]] = {}
        async with self._driver.session(database=self._db) as session:
            if speakers:
                all_rows: List[dict] = []
                for speaker in speakers:
                    s_rows = await (await session.run(
                        _OPINION_READ_EXCLUDING_SPEAKER_CYPHER,
                        dataset_id=dataset_id, query_hash=query_hash,
                        through_round=through_round, cap=cap, speaker=speaker,
                    )).data()
                    entries_by_speaker[speaker] = [_opinion_entry(r) for r in s_rows]
                    all_rows.extend(s_rows)
                seen: Dict[tuple, dict] = {}
                for r in all_rows:
                    seen[(r["agent"], r.get("round_no") or 0)] = r
                rows = list(seen.values())
            else:
                rows = await (await session.run(
                    _OPINION_READ_CYPHER, dataset_id=dataset_id, query_hash=query_hash,
                    through_round=through_round, cap=cap,
                )).data()
            n_rows = await (await session.run(
                neighbor_q, dataset_id=dataset_id, query_hash=query_hash,
            )).data()

        counts: Counter = Counter()
        for r in rows:
            for ent in (r.get("entities") or []):
                counts[str(ent)] += 1

        entries = [_opinion_entry(r) for r in rows]
        neighbor_map = {r["src"]: list(r.get("neighbors") or []) for r in n_rows}
        buzz = [{"entity": ent, "mentions": n}
                for ent, n in counts.most_common(5)]
        return SocietySnapshot(
            round=through_round,
            entries=entries,
            entries_by_speaker=entries_by_speaker,
            neighbor_map=neighbor_map,
            buzz=buzz,
            version=f"r{through_round}:{len(entries)}",
        )

    async def read_self_history(
        self, dataset_id: str, query_hash: str, agent_name: str,
        through_round: int,
    ) -> List[dict]:
        """The speaker's own committed opinions from strictly-prior rounds.

        Run-scoped by `dataset_id` + `query_hash`; bounded by `round_no <
        through_round`. Returns `{round, stance, summary}` rows ordered by round
        (empty when the speaker has not spoken yet).
        """
        async with self._driver.session(database=self._db) as session:
            rows = await (await session.run(
                _SELF_HISTORY_CYPHER, dataset_id=dataset_id, query_hash=query_hash,
                agent_name=agent_name, through_round=through_round,
                summary_chars=SELF_HISTORY_SUMMARY_CHARS,
            )).data()
        return sorted(
            ({
                "round": r.get("round_no") or 0,
                "stance": r.get("stance") or "NEUTRAL",
                "summary": (r.get("summary") or "")[:SELF_HISTORY_SUMMARY_CHARS],
            } for r in rows),
            key=lambda e: e["round"],
        )
