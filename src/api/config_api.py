from pydantic import BaseModel
from typing import List, Dict, Optional



class UserQuery(BaseModel):
    scenario: str  # "Should I expand my SaaS into Europe in 2025?"
    context: Optional[Dict]= {} # User's company data, constraints
    simulation_depth: str ="standard"  # "shallow", "standard", "deep"
    required_perspectives: Optional[List[str]] = None  # ["legal", "cultural", "economic"]
    
    
class SimulationResponse(BaseModel):
    society_opinion: Dict
    dissenting_views: List[Dict]
    confidence_metrics: Dict
    agent_profiles: List[Dict]
    raw_debate_log: Optional[List[Dict]] = None