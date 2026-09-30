from typing import Set, Dict, List
from dataclasses import dataclass


@dataclass
class WorldEvent:
    event_type: str  # "economic", "technological", "social", "environmental"
    description: str # Brief text describing the event
    severity: float  # -1.0 (negative) to 1.0 (positive)
    affected_domains: List[str] # e.g., ["finance", "tech", "regulation"]
    timestamp: str # ISO format or simulation tick