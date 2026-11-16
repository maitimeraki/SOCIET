# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Simulation World** is an AI-driven multi-agent simulation platform that models societal debates through autonomous agents.

### What It Does
1. User provides a scenario/question (e.g., "Should I expand into Europe?")
2. The graph is queried for the question; the `n` most relevant entities are seated as agents (`n` = `max_agents`, 1..12, default 8)
3. Each seated agent gets one evidence-cited profile; agents debate in pairs under the declared POSITION protocol
4. A weighted consensus over the last two rounds gives the position; one LLM-written report states it, with code checks

### Core Architecture (5-Layer Design)

```
LAYER 5: Opinion Output Engine (Final results delivery, public_events allowlist)
LAYER 4: Consensus & Synthesis (weighted_share / consensus_window, report writer)
LAYER 3: Simulation World (Orchestrator, RoundRunner, Ranking, Profiles, Verdict)
LAYER 2: Orchestration Engine (FastAPI, job management)
LAYER 1: User Interface (React dashboard, API, CLI)
```

### Data Flow

```
POST /simulate/debate → DebateOrchestrator
    ↓
Seat (ProfileSynthesizer):
    query → graph retrieval (scoped) → RRF fusion → personalised PageRank → SeatQueue (MMR)
    per seat: EvidencePack → generate_profile (one call + repair + support judge) → validate_profile
    accepted → AgentRecord (backend) + AgentView (client); rejected → not seated
    ↓
Debate loop (per round):
    CommunicationTopology → pairs → RoundRunner → parse_turn (POSITION line) → accept_position
    SocietyMemory.commit_round() → Neo4j Opinion/STATED/MENTIONS, scoped to the dataset
    ↓
consensus_window (last CONSENSUS_ROUNDS = 2 rounds) → weighted_share → dominant_stance
    ↓
write_report (one LLM call, code checks) → result: title, markdown, position, sources, status
```

## Key Components

### Simulation Engine (`src/simulation/`)
| File | Class | Purpose |
|------|-------|---------|
| `orchestrator.py` | DebateOrchestrator | Pipeline coordinator |
| `round_runner.py` | RoundRunner | One round: pair prompts, turn parse, retry once |
| `turn_protocol.py` | parse_turn, accept_position, consensus_window, weighted_share, dominant_stance | POSITION protocol and consensus (`CONSENSUS_ROUNDS = 2`) |
| `ranking.py` | rrf_fuse, personalized_pagerank, SeatQueue | Query-ranked seats: RRF, PageRank, MMR |
| `profile_synthesizer.py` | ProfileSynthesizer | Seats the top candidates, runs generation and validation |
| `profile_generator.py` | generate_profile | One cited profile per agent (LLM call, repair, support judge) |
| `profile_validation.py` | ProfileDraft, validate_profile | Code-side citation and uniqueness checks; no LLM |
| `evidence.py` | EvidencePack, build_pack | Per-agent evidence sentences and relations |
| `agent_record.py` | AgentView, AgentRecord | Client view vs backend-only record |
| `verdict.py` | VerdictSynthesizer, write_report, check_report | Board facts and the single report call |
| `report_retry.py` | build_retry_inputs, check_rebuild | Exact rebuild for a report retry |
| `society_memory.py` | SocietyMemory | Per-round commit + snapshot read-back |
| `topology.py` | CommunicationTopology | Pair scoring (Cypher, dataset-scoped) |
| `actor_filter.py` | classify actor labels | One metered LLM call |
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
| `agent.py` | Agent, Stance | Seated agent (internal) and the `Stance` enum with `Stance.parse` |
| `repository.py` | PersonaRepository | Neo4j reads and writes |
| `graph_context.py` | GraphContext | Scoped retrieval: fulltext, vector, seed walks |
| `models_persona.py` | ProvenanceLink | Persona-side models |

### API Layer (`src/api/`)
| File | Purpose |
|------|---------|
| `api_server.py` | FastAPI app (real entry point), graph routes, `/simulate/async` |
| `debate_api.py` | Debate router under `/simulate` (see routes below) |
| `operator_api.py` | `/operator` router, role-guarded (support, admin) |
| `public_events.py` | Default-deny outbound allowlist for events and results |
| `run_doc.py` | Postgres-backed run and job store |
| `graph_stream_api.py` | WS graph stream, dataset-scoped snapshot |
| `middleware.py` | Request logging with correlation IDs |

Debate routes (all owner-scoped; unknown and foreign runs both return 404):
- `POST /simulate/debate`: start a run (202), plan cap applied to `max_agents`
- `GET /simulate/debates/{run_id}` and `/simulate/debates`: run status and list
- `GET /simulate/debates/{run_id}/roster`: `AgentView` list in seat order
- `GET /simulate/debates/{run_id}/sources/{n}`: one report citation `[n]` resolved to its passage
- `POST /simulate/debates/{run_id}/verdict/retry`: re-run only the report of a run whose report was not produced (202, returns `run_id`)
- `GET /simulate/debates/{run_id}/graph`: dataset-scoped graph for the run
- `WS /simulate/{job_id}/stream`: run events, through `public_events` (the same routes are also mounted under `/api/v1`)
- `GET /operator/runs/{run_id}/agents/{node_id}`: one `AgentRecord`, audited before return

> **Removed:** `persona_api.py` (`/api/personas/hatch`, unmetered; audit C2, d4b76a2) and the legacy `/api/agents` stack (2026-09-30, decision D1). Agents are created only from graph retrieval.

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
│   ├── api_server.py            # FastAPI app (real entry point), graph routes
│   ├── debate_api.py            # Debate router under /simulate
│   ├── operator_api.py          # /operator (support, admin): AgentRecord reads
│   ├── public_events.py         # Default-deny outbound allowlist
│   ├── run_doc.py               # Postgres run and job store
│   ├── graph_stream_api.py      # WebSocket graph stream
│   ├── config_api.py            # Request/response Pydantic schemas
│   └── middleware.py            # Logging middleware (correlation IDs)
│
├── simulation/                  # Debate engine
│   ├── orchestrator.py          # DebateOrchestrator (coordinator)
│   ├── round_runner.py          # Single round execution
│   ├── turn_protocol.py         # POSITION turn parse, consensus, weighted_share
│   ├── ranking.py               # RRF, personalised PageRank, SeatQueue (MMR)
│   ├── evidence.py              # Per-agent evidence packs
│   ├── profile_synthesizer.py   # Seats candidates, runs generation and validation
│   ├── profile_generator.py     # One cited profile per agent
│   ├── profile_validation.py    # Code-side checks, uniqueness
│   ├── agent_record.py          # AgentView (client) and AgentRecord (backend-only)
│   ├── verdict.py               # Board facts and the report call
│   ├── report_retry.py          # Report retry inputs and exact rebuild checks
│   ├── topology.py              # CommunicationTopology (Cypher pair scoring)
│   ├── society_memory.py        # SocietyMemory (round commit + snapshot read-back)
│   ├── actor_filter.py          # Actor label classifier (one metered call)
│   ├── pair_turn.py             # CommPair, AgentTurn, RoundResult
│   ├── llm_batch.py             # BatchedLLMRunner (parallel LLM calls)
│   └── debate_config.py         # DebateConfig dataclass
│
├── persona/                     # Persona layer
│   ├── agent.py                 # Agent model and Stance enum
│   ├── repository.py            # PersonaRepository (Neo4j operations)
│   ├── graph_context.py         # GraphContext (scoped retrieval)
│   └── models_persona.py        # ProvenanceLink
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
    ├── labels.py                # Report source label cap
    ├── json_extract.py          # First JSON object from a model reply
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
uvicorn src.api.api_server:app --host 127.0.0.1 --port 8000 --reload
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

### Consensus
```python
weight = strength × profile confidence        # ABSTAIN weighs 0
result = weighted_share(turns, profiles)      # (dominant Stance, share) or None
# turns = consensus_window: the last CONSENSUS_ROUNDS (= 2) rounds
# None means no verdict, never NEUTRAL. Ties go to POSITIVE, NEGATIVE, NEUTRAL order.
```

### Seat Ranking
Query → graph retrieval (dataset-scoped) → RRF fusion → personalised PageRank → `SeatQueue` draws the `n` seats with MMR (`MMR_LAMBDA = 0.5`). One draw may be unresolved at a time; every draw is resolved in `try/finally`.

### Prompt Building
Evidence and relations are fenced as data. Attribute values are stripped of `<>"`, and the prompt says fenced text is never an instruction:
```
<evidence id="..." doc="...">sentence</evidence>
```

## Data Models

### AgentView (client) and AgentRecord (backend-only)
- `AgentView` (`src/simulation/agent_record.py`): `name, type, role, stance, strength, bio, details, confidence`. `extra="forbid"`. The only agent shape a client receives (roster, WS).
- `AgentRecord`: one per candidate per run, with evidence, validation, generation and `status` (`published|rejected|stale`). Never serialised to a client; read only by the audited operator route.

### Stance Enum
```python
class Stance(str, Enum):   # src/persona/agent.py; Stance.parse() is the single parser
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    NEUTRAL = "NEUTRAL"
    ABSTAIN = "ABSTAIN"    # no weight; shown as "No view"
```
Wire casing stays uppercase, matching persisted events and the frontend.

### Report Result
`verdict.report` carries `title, markdown, position, sources, status`. `status` is `not_produced` when the report call fails after its attempts; the UI then shows "Report not produced". No generated fallback text.

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

## Outbound Allowlist and LLM Calls

- `src/api/public_events.py` is default-deny. Client, WebSocket, `run_events` and `runs.verdict` carry only the keys it lists (`_PROFILE_KEYS` = AgentView keys, `_VERDICT_KEYS`, `_EVENT_KEYS`). A new outbound key is added there, never sent raw.
- Backend-only, never served: `source_refs`, `attempts`, `checks`, `retry_inputs`, evidence and chunk ids, node ids, cite markers, validation results, prompt and model versions, dossier and version hashes.
- Every LLM call goes through `LLMClient.generate` (it runs `metering.check_metering()`), inside `metering.source_scope(...)`, with explicit `model`, `temperature` and `max_tokens`. Sources are the billing ledger's `SOURCES` (`ingest, ontology, debate, verdict`); add no new source name without updating the ledger.

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
- **Single source of truth**: the client agent shape is `AgentView` and the stored shape is `AgentRecord` (`src/simulation/agent_record.py`). Don't duplicate fields.
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
# Model tiers — single source of truth: LLMConfig in src/llm/config_llm.py.
#   ANALYSIS: cheap but capable — ontology discovery + graph analysis
#   DEBATE:   the most powerful — agent debate in the simulation world
ANALYSIS_LLM_MODEL=claude-sonnet-5
DEBATE_LLM_MODEL=claude-opus-5-5
# Per-call overrides (default: ANALYSIS tier). Output budgets are per attempt.
PROFILE_LLM_MODEL=
PROFILE_MAX_TOKENS=1200
VERDICT_LLM_MODEL=
VERDICT_MAX_TOKENS=3000

# Default provider for the LiteLLM client (openai | anthropic | huggingface | ollama | nvidia_nim)
DEFAULT_LLM_PROVIDER=ollama

# OpenAI
OPENAI_API_KEY=sk-...

# Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# NVIDIA NIM (OpenAI-compatible gateway used by the graph stages)
NVIDIA_NIM_API_KEY=nvapi-...
NVIDIA_NIM_BASE_URL=https://integrate.api.nvidia.com/v1

# Local Gateways
OLLAMA_MODEL=qwen3.5-16k:4b
OLLAMA_BASE_URL=http://localhost:11434
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

# =============================================================================
# BILLING AND COMPLIANCE (docs/TECHNOLOGY_STACK.md §11)
# =============================================================================
# Billing stays off until the legal surface + Stripe are live; the free plan is
# the complete entitlement while off. With BILLING_ENABLED=true the four Stripe
# names below are required at boot.
BILLING_ENABLED=false
STRIPE_SECRET_KEY=sk-...
STRIPE_WEBHOOK_SECRET=whsec-...
STRIPE_PRICE_STARTER=price_...
STRIPE_PRICE_STUDIO=price_...
APP_BASE_URL=http://localhost:5173
EMAIL_API_KEY=
EMAIL_FROM=no-reply@societas.app
LEGAL_ENTITY_NAME=
LEGAL_CONTACT_EMAIL=hello@societas.app
# Plan table overrides (units / caps / public price card).
PLAN_FREE_UNITS=1000
PLAN_STARTER_UNITS=8000
PLAN_STUDIO_UNITS=16000
PLAN_ENTERPRISE_UNITS=80000
PLAN_STARTER_PRICE_USD=10
PLAN_STUDIO_PRICE_USD=20
PLAN_ENTERPRISE_PRICE_LABEL=Custom
GRAPH_JOB_RESERVE_UNITS=2000
# Unit hold for a verdict retry; unset derives it from the report budget and question length.
VERDICT_RETRY_RESERVE_UNITS=

# =============================================================================
# EXTRACTION / EDGE
# =============================================================================
EXTRACTION_PROVIDER=nvidia_nim
EXTRACTION_LLM_MODEL=
EXTRACTION_BASE_URL=
EXTRACTION_API_KEY=
EXTRACTION_TRIAL_ACK=false
LLM_PROMPT_CACHE=true
FORWARDED_ALLOW_IPS=
RATE_LIMIT_STORAGE_URI=
RATE_LIMIT_VERDICT_RETRY=10/hour
GIT_SHA=dev
```

### Database roles

The runtime connects as the least-privilege `societas_app` role; apply
`scripts/setup_db_roles.sql` for the base grants and `scripts/db_roles.sql` for
the ledger split (append-only `usage_events` for the app; `societas_retention`
owns the age-based deletes). Run retention as `societas_retention`.

### DebateConfig Defaults
```python
@dataclass
class DebateConfig:
    max_agents: int = 8          # seat count n; 1..12, also the billing plan cap
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
> BeautifulSoup) and the **job-queue tier** (Redis, Celery). Two of those six are installed but unused
> (`beautifulsoup4` 4.14.3, `redis` 5.0.1, pinned in `requirements.txt`); the rest are absent. No extractor
> or job-queue code exists in `src/`. The bullets below are the target stack, not the current tree.

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
- `docs/DESIGN_SPEC.md` - Frontend design authority: the built world (tokens, type, wireframes, motion, component language, copy law), rewritten from the shipped frontend; the "Survey" draft and the retired "Neural Observatory" shell are both superseded by this file.
