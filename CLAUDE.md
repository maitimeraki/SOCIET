# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Simulation World** is an AI-driven multi-agent simulation platform that models societal debates through autonomous agents.

### What It Does
1. User provides a scenario/question (e.g., "Should I expand into Europe?")
2. System creates a society of domain-specific AI agents
3. Agents engage in structured debate with Cypher-computed pairings
4. CIOR-weighted consensus generates final verdict with confidence metrics

### Core Architecture (5-Layer Design)

```
LAYER 5: Opinion Output Engine (Final results delivery)
LAYER 4: Consensus & Synthesis (CIOR-weighted verdict generation)
LAYER 3: Simulation World (Debate orchestration - Orchestrator, RoundRunner, Topology, Verdict)
LAYER 2: Orchestration Engine (FastAPI, job management)
LAYER 1: User Interface (React dashboard, API, CLI)
```

### Data Flow

```
User Input → parse_scenario() → design_society() → recruit_agents()
    ↓
Debate Loop (per round):
    SocietyMemory.read_snapshot() → SocietySnapshot → prompt society state (round ≥ 2)
    CommunicationTopology.compute_round_pairs() → Cypher queries
    RoundRunner.execute_round() → LLM API → parse stance/confidence
    SocietyMemory.commit_round() → Neo4j Opinion/STATED/MENTIONS + round-keyed REACTED_TO
    CommunicationTopology.find_activation_candidates() → new agents join next round
    ↓
check_convergence() → config.convergence_threshold weighted consensus (last two rounds)
    ↓
VerdictSynthesizer.synthesize() → CIOR-weighted verdict
    ↓
SimulationResponse (society_opinion, confidence_metrics, dissenting_views)
```

## Key Components

### Simulation Engine (`src/simulation/`)
| File | Class | Purpose |
|------|-------|---------|
| `orchestrator.py` | DebateOrchestrator | 5-stage pipeline coordinator |
| `round_runner.py` | RoundRunner | Single round execution, prompt building |
| `topology.py` | CommunicationTopology | Cypher-based agent pair scoring |
| `verdict.py` | VerdictSynthesizer | CIOR-weighted consensus synthesis |
| `society_memory.py` | SocietyMemory | Per-round commit (Opinion/STATED/REACTED_TO) + snapshot read-back |
| `profile_synthesizer.py` | ProfileSynthesizer | Graph → Agent creation |
| `pair_turn.py` | CommPair, AgentTurn, RoundResult | Data classes |

### Graph System (`src/graph/`)
| File | Class | Purpose |
|------|-------|---------|
| `graph_pipeline.py` | UniversalGraphPipeline | End-to-end document→graph |
| `ontology.py` | OntologyDiscoveryStage | LLM-based schema discovery |
| `graph_build.py` | GraphExtractionStage | Entity/relation extraction |
| `normalization.py` | GraphNormalizationStage | Deduplication, property normalization |

### Persona Layer (`src/persona/`)
| File | Class | Purpose |
|------|-------|---------|
| `agent.py` | Agent | Canonical agent model (identity, stance, conviction, cior) |
| `repository.py` | PersonaRepository | Neo4j operations, agent metrics |

### API Layer (`src/api/`)
| File | Purpose |
|------|---------|
| `api_server.py` | FastAPI server, job management, endpoints |
| `config_api.py` | Request/response Pydantic schemas |

### LLM Integration (`src/llm/`)
| File | Class | Purpose |
|------|-------|---------|
| `client.py` | LLMClient | LiteLLM wrapper - 100+ providers unified interface |

### File Extractors (`src/infrastructure/extractors/`)
| File | Class | Purpose |
|------|-------|---------|
| `base.py` | BaseExtractor | Abstract extractor interface |
| `pdf_extractor.py` | PDFExtractor | PyMuPDF implementation |
| `docx_extractor.py` | DOCXExtractor | python-docx implementation |
| `md_extractor.py` | MarkdownExtractor | markdown-it implementation |
| `url_extractor.py` | URLExtractor | requests + BeautifulSoup |

## Directory Structure

```
src/
├── main.py
├── config.py
│
├── api/
│   ├── server.py              # FastAPI app
│   └── routes/
│       ├── simulation.py      # /simulate endpoints
│       ├── documents.py       # /documents endpoints
│       └── health.py         # /health, /metrics
│
├── domain/                    # Pure domain models (no dependencies)
│   ├── agent/
│   │   └── agent_profile.py  # AgentProfile schema
│   ├── debate/
│   │   └── debate_session.py # DebateSession
│   ├── graph/
│   │   ├── node.py          # GraphNode (standard schema)
│   │   └── relationship.py   # GraphRelationship
│   └── verdict/
│       └── verdict_output.py  # VerdictOutput
│
├── application/              # Use cases
│   ├── simulation/
│   │   └── run_simulation.py
│   ├── graph/
│   │   └── build_graph.py   # Document → Graph
│   └── society/
│       └── create_society.py # Agent society creation
│
├── infrastructure/           # External dependencies
│   ├── llm/
│   │   ├── litellm_client.py # LiteLLM implementation
│   │   └── gateways.py       # Gateway configuration
│   ├── extractors/
│   │   ├── base.py          # BaseExtractor interface
│   │   ├── pdf_extractor.py  # PyMuPDF
│   │   ├── docx_extractor.py # python-docx
│   │   ├── md_extractor.py  # markdown-it
│   │   └── url_extractor.py  # requests + BeautifulSoup
│   ├── chunking/
│   │   ├── semantic_chunker.py # Semantic chunking
│   │   └── chunking_pipeline.py # Parallel chunking
│   ├── graph/
│   │   └── neo4j_repository.py # Neo4j operations
│   └── cache/
│       └── redis_client.py   # Redis caching
│
└── tests/

frontend/                      # React + TypeScript
docs/
└── TECHNOLOGY_STACK.md       # Production tech stack
```

## Development Commands

### Setup & Dependencies
```bash
pip install -r requirements.txt       # Root dependencies
uvicorn src.api.api_server:app --reload # Start API server
```

### Run API
```bash
uvicorn src.api.api_server:app --host 127.0.0.1 --port 8000
# Docs: http://localhost:8000/docs
```

### Testing
```bash
pytest                           # Run all tests
pytest tests/simulation/         # Simulation tests only
pytest src/persona/              # Persona layer tests
```

### Graph Pipeline Demo
```python
from src.main import main
asyncio.run(main())
```

## Common Patterns

### Agent Pair Scoring (Cypher)
```cypher
-- Round 1: Single-hop Jaccard + edge bonuses
MATCH (a:Persona)-[r1]-(e)-[r2]-(b:Persona)
WHERE a.name IN $agent_names AND b.name IN $agent_names
WITH a, b, count(DISTINCT e) AS shared_count
WITH a, b, shared_count,
     jaccard + CASE WHEN has_opposes THEN 0.3 WHEN has_supports THEN 0.2 END AS score
RETURN a.name AS agent_a, b.name AS agent_b, score
```

### CIOR Weight Formula
```python
weight = confidence × conviction × (1 + cior) / 2
# cior: -1.0 (hostile) to +1.0 (receptive)
```

### Convergence Check
```python
if dominant_stance_weight / total_weight >= 0.8:
    # Converged - stop debate
```

### Prompt Building
```python
def _build_system_prompt(agent: Agent, opponent: Agent, shared_entities: list) -> str:
    return f"""You are {agent.identity.name}, an expert in {domains}.
    Perspective: {agent.detailed_perspective[:500]}
    Stance: {agent.stance.value} (intensity {agent.intensity:.2f})
    Confidence breakdown: sources={cb.source_breadth}, nodes={cb.node_density}
    You share these entities: {shared}
    Engage genuinely with opposing viewpoints."""
```

## Data Models

### Agent (Canonical)
```python
class Agent(BaseModel):
    identity: PersonaIdentity                    # name, archetype, communication_style
    bio: str                                  # 2-3 sentence narrative
    detailed_perspective: str                 # First-person voice for prompts
    stance: Stance                            # POSITIVE, NEGATIVE, NEUTRAL, AMBIVALENT
    intensity: float                           # [0.0, 1.0]
    confidence: float                          # [0.0, 1.0]
    conviction: float                         # [0.0, 1.0]
    cior: float                              # [-1.0, 1.0] Certainty-Instinct Opinion Range
    domain_tags: List[str]                   # Areas of expertise
    communication_radius: int                 # [1, 5] hops for topology
    summary_provenance: List[ProvenanceLink] # Source chunk links
    confidence_breakdown: ConfidenceBreakdown  # Mathematical proof
```

### Stance Enum
```python
class Stance(str, Enum):
    POSITIVE = "POSITIVE"      # Supports proposal
    NEGATIVE = "NEGATIVE"     # Opposes proposal
    NEUTRAL = "NEUTRAL"       # Balanced/conditional
    AMBIVALENT = "AMBIVALENT" # Mixed feelings
```

### DebateVerdict
```python
@dataclass
class DebateVerdict:
    overall_stance: Stance
    confidence_score: float
    supporting_entities: List[str]
    opposing_entities: List[str]
    summary: str
    cluster_details: Dict[Stance, ClusterSummary]
    rounds_executed: int
```

## API Schemas

### UserQuery
```python
class UserQuery(BaseModel):
    scenario: str                              # The question/proposal
    context: Optional[Dict[str, Any]]          # User-provided context
    simulation_depth: str = "standard"         # shallow, standard, deep
    selected_domains: Optional[List[str]]      # Domain filter
    mode: str = "sync"
```

### SimulationResponse
```python
class SimulationResponse(BaseModel):
    society_opinion: str
    dissenting_views: List[Dict[str, Any]]
    confidence_metrics: Dict[str, Any]        # overall_confidence, debate_rounds, etc.
    agent_profiles: List[Dict[str, Any]]
    raw_debate_log: Optional[List[Dict[str, Any]]]
```

## Development Guidelines

### Code Quality
- **Verify before claiming done**: Test the golden path and edge cases in a browser or REPL before reporting completion.
- **Code is self-documenting**: Well-named identifiers replace comments. Add comments only for the non-obvious "why", not the "what".
- **Small, focused functions**: Each function does one thing well. If a function needs a paragraph to explain, split it.
- **Follow existing patterns**: Match the codebase's established conventions before introducing new ones.

### Error Handling
- **Validate at trust boundaries**: Always validate user input and external API responses.
- **Graceful degradation**: System should fail predictably, not catastrophically. Log errors appropriately.
- **Never swallow exceptions silently**: At minimum, log the error. Propagate if caller needs to handle it.

### Dependencies
- **Prefer stdlib**: Use built-in libraries before adding external dependencies.
- **No speculative dependencies**: Don't add a library "just in case". Add when actually needed.
- **No hardcoded secrets**: Use environment variables or config files for credentials.

### Testing
- **Golden path first**: Ensure the main user flow works before testing edge cases.
- **Mock external services**: LLM responses should be mocked during unit tests via `src/llm/client.py`.
- **One assertion per logical check**: Multiple `assert` statements in one test = multiple tests.

### Async Patterns
- **Proper async/await**: Never use blocking calls in async functions. Never forget to await.
- **Connection management**: Always close connections (DB, HTTP, streams) in finally blocks or context managers.

### State & Architecture
- **Single source of truth**: Agent model lives in `src/persona/agent.py`. Don't duplicate fields.
- **Layered dependencies**: UI → API → Simulation → LLM. Don't skip layers.
- **No circular imports**: Structure modules to avoid circular dependencies.

### Performance
- **No premature optimization**: First make it correct, then profile, then optimize the bottleneck.
- **Avoid obvious inefficiencies**: N+1 queries, loading everything into memory when streaming works.
- **Cache appropriately**: Cache expensive computations, but invalidate when underlying data changes.

## File Interaction Principles

### Core Rules
- **No redundant files**: Do not create planning documents, decision logs, or temporary files unless explicitly requested.
- **Immediate-work files are ephemeral**: Files created for single-session tasks must be deleted after completion.
- **Only persist what belongs**: Create or update files only when they represent permanent additions to the codebase.
- **Consistency is key**: Any new instructions or patterns established must remain consistent throughout the project lifecycle.

### Application
- When integrating, updating, or creating files, verify the file serves a lasting purpose.
- Speculative features, imagined extension points, or temporary debugging aids should not become permanent artifacts.
- If a file exists solely to support immediate work (e.g., temporary notes, session-specific configurations), delete it before completing the task.

## Configuration

### Environment Variables
```env
# =============================================================================
# LLM PROVIDERS (via LiteLLM - 100+ providers supported)
# =============================================================================
PRIMARY_LLM_PROVIDER=openai
PRIMARY_LLM_MODEL=gpt-4

# OpenAI
OPENAI_API_KEY=sk-...

# Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# Azure OpenAI
AZURE_OPENAI_KEY=...
AZURE_OPENAI_BASE=https://company.openai.azure.com/v1

# Local Gateways
OLLAMA_BASE_URL=http://localhost:11434/v1
LOCALAI_BASE_URL=http://localhost:8080/v1

# =============================================================================
# NEO4J
# =============================================================================
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=password
NEO4J_DATABASE=neo4j

# =============================================================================
# REDIS (optional - caching and job queue)
# =============================================================================
REDIS_URL=redis://localhost:6379
```

### DebateConfig Defaults
```python
@dataclass
class DebateConfig:
    max_agents: int = 50
    max_rounds: int = 5
    comm_radius: int = 1
    min_entity_overlap: int = 1
    max_pairs_per_round: int = 50
    convergence_threshold: float = 0.8
    llm_concurrency: int = 8
    topology_score_threshold: float = 0.15
    max_new_agents_per_round: int = 2
    snapshot_top_k: int = 8
```

## graphify

This project has a graphify knowledge graph at `graphify-out/`.

Rules:
- Before answering architecture or codebase questions, read `graphify-out/GRAPH_REPORT.md` for god nodes and community structure
- If `graphify-out/wiki/index.md` exists, navigate it instead of reading raw files
- After modifying code files in this session, run `graphify update .` to keep the graph current (AST-only, no API cost)

## Technology Stack

### LLM Gateway (Production-Grade)
- **LiteLLM** - Universal LLM abstraction for 100+ providers
- Supports: OpenAI, Anthropic, Azure, AWS Bedrock, Ollama, LocalAI, vLLM, any OpenAI-compatible endpoint
- Features: Cost tracking, rate limiting, retries, fallback routing

### File Extraction
- **PyMuPDF** - PDF extraction with page/table preservation
- **python-docx** - Word document extraction
- **markdown-it-py** - Markdown parsing
- **requests + BeautifulSoup** - URL/web scraping

### Graph & Storage
- **Neo4j** - Knowledge graph with Cypher queries
- **Redis** - Caching, rate limiting, job queue

### Production
- **FastAPI** - Async HTTP API
- **Pydantic v2** - Schema validation
- **Celery + Redis** - Background job processing
- **asyncio** - Parallel execution

## Document Processing Pipeline

```
INPUT: PDF, DOCX, MD, TXT, URL
    ↓
EXTRACTION (parallel per format)
    ↓
CHUNKING (semantic, sentence boundaries, overlap)
    ↓
EMBEDDING (batch, parallel)
    ↓
NODE CREATION (standard schema, no extra fields)
    ↓
RELATIONSHIP CREATION (SIMILAR_TO, FOLLOWS, REFERENCES, TOPIC_LINK)
    ↓
NEO4J GRAPH
```

## Agent Society System

```
USER DATA (documents, URLs, text)
    ↓
GRAPH CREATION (nodes from user's data only)
    ↓
USER QUERY (the question being asked)
    ↓
GRAPH RETRIEVAL (find relevant nodes based on query)
    ↓
AGENT CREATION (agents derived from retrieved nodes)

CRITICAL RULES:
- Agents are NOT predefined or hardcoded
- Agents are created dynamically from retrieved graph nodes
- Agent count varies based on graph size and query relevance
- If no graph exists → No agents → No debate possible
```

## Documentation

- `docs/TECHNOLOGY_STACK.md` - Production tech stack and architecture (source of truth)
- `docs/ARCHITECTURE.md` - Detailed component documentation
- `docs/DESIGN.md` - Frontend design specification (Neural Observatory)
