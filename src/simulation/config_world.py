from typing import Set, Dict, List
from dataclasses import dataclass


@dataclass
class WorldEvent:
    event_type: str  # "economic", "technological", "social", "environmental"
    description: str
    severity: float  # -1.0 (negative) to 1.0 (positive)
    affected_domains: List[str]
    timestamp: str