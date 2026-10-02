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
User Input → POST /simulate/debate → DebateOrchestrator → ProfileSynthesizer.synthesize()
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
| `relevance_matrix.py` | SelectionRow, rank_candidates | Intent-aware candidate ranking (semantic + density blend, decomposed scores) for the selection step |
| `pair_turn.py` | CommPair, AgentTurn, RoundResult | Data classes |
| `llm_batch.py` | BatchedLLMRunner | Parallel LLM calls per round |
| `debate_config.py` | DebateConfig | Validated debate settings |

### Graph System (`src/graph/`)
| File | Class | Purpose |
|------|-------|---------|
| `graph_pipeline.py` | UniversalGraphPipeline | End-to-end document→graph |
| `ontology.py` | OntologyDiscoveryStage | LLM-based schema discovery |
| `graph_build.py` | GraphExtractionStage | Entity/relation extraction |
| `normalization.py` | GraphNormalizationStage | Deduplication, property normalization |
| `neo4j_bootstrap.py` | — | Neo4j constraints/indexes (CLI: `src/cli/bootstrap_neo4j.py`) |
| `models_graph.py` | — | Graph data models (ProcessedChunk, LocalOntology, GlobalInputDocument) |
| `config_graph.py` | GraphConfig | Neo4j connection + graph settings |

### Persona Layer (`src/persona/`)
| File | Class | Purpose |
|------|-------|---------|
| `agent.py` | Agent | Canonical agent model (identity, stance, conviction, cior) |
| `repository.py` | PersonaRepository | Neo4j operations, agent metrics |
| `graph_context.py` | GraphContext | Vector + keyword retrieval over the graph |
| `models_persona.py` | — | Persona-side data models |

### API Layer (`src/api/`)
| File | Purpose |
|------|---------|
| `api_server.py` | FastAPI app (real entry point), job management, `/simulate` endpoints |
| `config_api.py` | Request/response Pydantic schemas |
| `debate_api.py` | Debate router (`/simulate/debate` + job status + WS stream) |
| `persona_api.py` | Persona router (`/api/personas/hatch`) |
| `middleware.py` | Request/response logging with correlation IDs |

> **Removed 2026-09-30 (decision D1):** the legacy `/api/agents` stack — `src/api/agent_api.py`, `src/persona/agent_repository.py`, `src/persona/response_tracker.py` and the `agent_node.py` model — was deleted. Superseded by the debate path: agents are created only from graph retrieval (`ProfileSynthesizer`), never from a second hardcoded agent store.

### LLM Integration (`src/llm/`)
| File | Class | Purpose |
|------|-------|---------|
| `client.py` | LLMClient | LiteLLM wrapper - 100+ providers unified interface |
| `config_llm.py` | — | LLM configuration |

## Directory Structure

```
src/
├── main.py                      # Graph pipeline demo entry
│
├── api/                         # FastAPI layer
│   ├── api_server.py            # FastAPI app (real entry point), job management
│   ├── config_api.py            # Request/response Pydantic schemas
│   ├── debate_api.py            # Debate router + WebSocket stream
│   ├── persona_api.py           # Persona router (/api/personas/hatch)
│   └── middleware.py            # Logging middleware (correlation IDs)
│
├── simulation/                  # Debate engine
│   ├── orchestrator.py          # DebateOrchestrator (coordinator)
│   ├── round_runner.py          # Single round execution
│   ├── topology.py              # CommunicationTopology (Cypher pair scoring)
│   ├── profile_synthesizer.py   # ProfileSynthesizer (graph → Agent)
│   ├── relevance_matrix.py      # Intent-aware candidate ranking (semantic + density blend)
│   ├── verdict.py               # VerdictSynthesizer (CIOR-weighted consensus)
│   ├── society_memory.py        # SocietyMemory (round commit + snapshot read-back)
│   ├── pair_turn.py             # CommPair, AgentTurn, RoundResult
│   ├── llm_batch.py             # BatchedLLMRunner (parallel LLM calls)
│   └── debate_config.py         # DebateConfig dataclass
│
├── persona/                     # Persona layer
│   ├── agent.py                 # Canonical Agent model (Pydantic)
│   ├── repository.py            # PersonaRepository (Neo4j operations)
│   ├── graph_context.py         # GraphContext (entity retrieval)
│   └── models_persona.py        # Persona data models
│
├── graph/                       # Knowledge graph construction
│   ├── graph_pipeline.py        # UniversalGraphPipeline (end-to-end)
│   ├── ontology.py              # OntologyDiscoveryStage
│   ├── graph_build.py           # GraphExtractionStage
│   ├── normalization.py         # GraphNormalizationStage
│   ├── neo4j_bootstrap.py       # Constraints / indexes / vector index
│   ├── models_graph.py          # Graph data models
│   └── config_graph.py          # Graph configuration
│
├── llm/                         # LLM integration
│   ├── client.py                # LLMClient (LiteLLM, multi-provider)
│   └── config_llm.py            # LLM configuration
│
├── logging/
│   └── setup_logging.py         # Structured logging setup
│
├── cli/
│   └── bootstrap_neo4j.py       # Neo4j schema bootstrap CLI
│
└── utils/
    ├── chunkProcessor.py        # Document chunk processing
    ├── queryIntend.py           # Query intent extraction
    └── hydrate_ontology.py      # Ontology hydration helpers

tests/                           # Single test tree, mirrors src/ subsystems
frontend/                        # React + TypeScript
docs/
└── TECHNOLOGY_STACK.md          # Production tech stack
```

## Development Commands

### Setup & Dependencies
```bash
# Canonical interpreter: .venv/Scripts/python.exe (Python 3.11.9).
# `python` / `pytest` on PATH resolve to the venv.

python -m ensurepip --upgrade         # only if .venv has no pip

# KNOWN ISSUE: `pip install -r requirements.txt` does not resolve —
# langchain==0.1.0 vs langchain-ollama==1.1.0 conflict on langchain-core.
# The runtime dependency that makes the suite pass today:
pip install "litellm>=1.40.0"

uvicorn src.api.api_server:app --reload  # Start API server
python -m src.cli.bootstrap_neo4j        # Initialize Neo4j schema
```

### Run API
```bash
uvicorn src.api.api_server:app --host 127.0.0.1 --port 8000
# Docs: http://localhost:8000/docs
```

### Testing
```bash
pytest                           # Run all tests (single tests/ tree)
pytest tests/simulation/         # Simulation tests only
pytest tests/persona/            # Persona layer tests
```

### Graph Pipeline Demo
> **Parked — not runnable today.** `UniversalGraphPipeline.run` (`src/graph/graph_pipeline.py`) hands
> `List[GlobalInputDocument]` to stages that require `List[ProcessedChunk]`, so `src.main:main()` fails on
> the first stage call. The demo entry is kept for reference pending the pipeline wiring fix; the working
> graph path today is the API job pipeline (`src/api/api_server.py`).

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

> **Implementation status.** Implemented today: **LiteLLM**, **Neo4j**, **FastAPI**, **Pydantic v2**, **asyncio**.
> Planned, not yet implemented: the **document extractors** (PyMuPDF, python-docx, markdown-it-py,
> BeautifulSoup) and the **job-queue tier** (Redis, Celery) — none are installed and no extractor or
> job-queue code exists. The bullets below are the target stack, not a description of the current tree.

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
EXTRACTION (parallel per format)          # planned — no extractor is implemented yet
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
- `docs/DESIGN.md` - Frontend design specification ("The Chamber", draft pending approval; supersedes the retired "Neural Observatory" demo shell)
