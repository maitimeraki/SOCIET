from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum

# Define an enumeration for agent types
class PersonalityType(Enum):
    OPTIMIST = "optimist"           # Sees opportunities
    PESSIMIST = "pessimist"         # Sees risks  
    SKEPTIC = "skeptic"             # Challenges assumptions
    INNOVATOR = "innovator"        # Novel combinations
    CONSERVATIVE = "conservative"   # Favors statement quo
    
    
    
@dataclass
class Belief:
    """A belief has confidence, evidence, and can be revised"""
    statement: str
    confidence: float  # 0.0 to 1.0
    # This can be used to specify fields with mutable default values
    evidence: List[str] = field(default_factory=list)
    source: Optional[str] = None  # e.g., "observation", "inference", "testimony"
    timestamp: str = field(default_factory=lambda: str(datetime.now()))
    def update_confidence(self,new_evidence:str, impact:float):
        """Bayesian-ish update (simplified)"""
        # Strong evidence increases confidence, conflicting decreases
        self.confidence = max(0.0, min(1.0, self.confidence + impact))
        self.evidence.append(new_evidence)
        
        
@dataclass
class AgentMemory:
    """Persistent memory across conversations"""
    short_term :List[Dict]= field(default_factory=list)  # Recent interactions
    long_term: Dict[str,Belief] = field(default_factory=dict)   # Core beliefs
    relationships: Dict[str, float] = field(default_factory=dict)  # Trust levels with other agents
    
    def add_interaction(self, agent_id:str, sentiment:float, content:str):
        """Track how this agent feels about others"""
        current_trust = self.relationships.get(agent_id, 0.5)  # Start neutral
        self.relationships[agent_id] = min(1.0, current_trust + sentiment+0.1)  # Positive sentiment increases trust