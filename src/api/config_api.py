from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Literal



class DocumentContext(BaseModel):
    document_id: str
    title: Optional[str] = None
    source_type: Literal["text", "pdf", "docx", "url", "note"] = "text"
    tags: List[str] = Field(default_factory=list)


class UserQuery(BaseModel):
    scenario: str  # "Should I expand my SaaS into Europe in 2025?"
    context: Dict = Field(default_factory=dict)  # User's company data, constraints
    simulation_depth: Literal["shallow", "standard", "deep"] = "standard"
    required_perspectives: Optional[List[str]] = None  # ["legal", "cultural", "economic"]
    selected_domains: List[str] = Field(default_factory=list)
    documents: List[DocumentContext] = Field(default_factory=list)
    mode: Literal["sync", "async"] = "sync"
    
    
class SimulationResponse(BaseModel):
    society_opinion: Dict
    dissenting_views: List[Dict]
    confidence_metrics: Dict
    agent_profiles: List[Dict]
    raw_debate_log: Optional[List[Dict]] = None


class SimulationAccepted(BaseModel):
    run_id: str
    status: Literal["queued", "running", "completed", "failed"]
    message: str


class SimulationRunStatus(BaseModel):
    run_id: str
    status: Literal["queued", "running", "completed", "failed"]
    progress: float = 0.0
    stage: str = "queued"
    error: Optional[str] = None
    result: Optional[SimulationResponse] = None


class OntologyResult(BaseModel):
    dataset_id: str
    entity_types: List[str] = Field(default_factory=list)
    relation_types: List[str] = Field(default_factory=list)
    chunks_total: int = 0
    chunks_completed: int = 0


class OntologyAccepted(BaseModel):
    job_id: str
    status: Literal["queued", "running", "completed", "failed"]
    message: str


class OntologyRunStatus(BaseModel):
    job_id: str
    status: Literal["queued", "running", "completed", "failed"]
    progress: float = 0.0
    stage: str = "queued"
    error: Optional[str] = None
    result: Optional[OntologyResult] = None
