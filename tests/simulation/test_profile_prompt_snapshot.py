import os
from pathlib import Path

import pytest

from src.simulation.evidence import EvidenceItem, EvidencePack, RelationItem
from src.simulation.profile_generator import build_prompt

SNAPSHOT = Path(__file__).parent / "snapshots" / "profile_prompt.txt"


@pytest.fixture
def fixed_pack() -> EvidencePack:
    items = (
        EvidenceItem("e1", "c1", "d1", "Market memo", "Summary", (0, 90),
                     "Kestra expanded its scheduler product into Berlin during the spring pilot.", "own", 0.9),
        EvidenceItem("e2", "c2", "d2", "Analyst note", "Outlook", (0, 80),
                     "Kestra Labs says a second German rollout waits for the compliance review.", "own", 0.7),
    )
    relations = (RelationItem("r1", "COMPETES_WITH", "out", "n2", "Airflow", "c1"),)
    return EvidencePack(items, relations, doc_count=2, chunk_count=2)


def test_profile_prompt_is_unchanged_until_reviewed(fixed_pack):
    system, user = build_prompt("Should we enter Berlin?", "enter vs wait", "Lumen Pay", ["Lumen"], "Competitor", fixed_pack)
    actual = f"{system}\n----\n{user}\n"
    if os.environ.get("UPDATE_SNAPSHOTS") == "1":
        SNAPSHOT.write_text(actual, encoding="utf-8")
    assert actual == SNAPSHOT.read_text(encoding="utf-8")
