# Simulation World (AI Society Simulator)

**An AI-driven multi-agent simulation platform for structured societal debate and consensus generation.**

---

## What It Does

Simulation World transforms a business question or scenario into a synthesized societal opinion by:

1. **Creating a Society** of domain-specific AI agents with distinct expertise, personalities, and stances
2. **Running Structured Debate** where agents argue, counter-argue, and respond to each other
3. **Generating Consensus** using CIOR-weighted opinion clustering (not simple voting)
4. **Delivering Insights** with confidence metrics, dissenting views, and supporting evidence

### Example

```json
// Input: "Should I expand into Europe?"
{
  "scenario": "Should I expand my SaaS business into Europe in 2026?",
  "context": { "budget_usd": 200000, "team_size": 12 }
}

// Output: Synthesized society opinion
{
  "society_opinion": "Cautionary expansion with phased approach recommended...",
  "confidence_metrics": { "overall_confidence": 0.78, "debate_rounds": 3 },
  "agent_profiles": [
    { "name": "Conservative Analyst", "expertise": ["finance", "risk_management"] },
    { "name": "Growth Strategist", "expertise": ["business_development"] }
  ],
  "dissenting_views": [...]
}
```

---

## Architecture Overview

### 5-Layer System Design

```
┌─────────────────────────────────────────────────────────────────┐
│  LAYER 5: Opinion Output Engine (Final results delivery)         │
├─────────────────────────────────────────────────────────────────┤
│  LAYER 4: Consensus & Synthesis (CIOR-weighted verdict)         │
├─────────────────────────────────────────────────────────────────┤
│  LAYER 3: Simulation World (Debate orchestration)               │
├─────────────────────────────────────────────────────────────────┤
│  LAYER 2: Orchestration Engine (API, job management)             │
├─────────────────────────────────────────────────────────────────┤
│  LAYER 1: User Interface (React dashboard, API, CLI)             │
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow

```
User Input → Parse Scenario → Design Society → Create Agents
    ↓
Debate Loop (per round):
    Topology (Cypher) → RoundRunner → LLM API → Parse → Write-back to Neo4j
    ↓
Convergence Check (80% threshold)
    ↓
Verdict Synthesis → Society Opinion + Confidence + Dissenting Views
```

---

## Key Components

### Simulation Engine (`src/simulation/`)

| File | Purpose |
|------|---------|
| `orchestrator.py` | **DebateOrchestrator** - 5-stage pipeline coordinator |
| `round_runner.py` | Executes single debate rounds, builds prompts |
| `topology.py` | **CommunicationTopology** - Cypher-based agent pair scoring |
| `verdict.py` | **VerdictSynthesizer** - CIOR-weighted consensus |
| `society_memory.py` | **SocietyMemory** - Commits rounds to Neo4j (Opinion/STATED/REACTED_TO) + snapshot read-back |
| `profile_synthesizer.py` | Creates agents from graph entities |
| `pair_turn.py` | Data classes for turns, pairs, verdicts |

### Graph System (`src/graph/`)

| File | Purpose |
|------|---------|
| `graph_pipeline.py` | **UniversalGraphPipeline** - end-to-end document→graph |
| `ontology.py` | **OntologyDiscoveryStage** - LLM-based schema discovery |
| `graph_build.py` | **GraphExtractionStage** - entity/relation extraction |
| `normalization.py` | Deduplication and property normalization |
| `neo4j_bootstrap.py` | Schema initialization |

### Persona Layer (`src/persona/`)

| File | Purpose |
|------|---------|
| `agent.py` | **Canonical Agent model** - identity, stance, conviction, cior |
| `repository.py` | **PersonaRepository** - Neo4j operations for agents |
| `graph_context.py` | Entity discovery from graph |

### API Layer (`src/api/`)

| File | Purpose |
|------|---------|
| `api_server.py` | FastAPI server, job management, endpoints |
| `config_api.py` | Request/response schemas |
| `middleware.py` | Logging middleware |
| `runtime/jobs/` | Async job state persistence |

### LLM Integration (`src/llm/`)

| File | Purpose |
|------|---------|
| `client.py` | **LLMClient** - unified multi-provider interface |
| `config_llm.py` | Provider configuration |

---

## Tech Stack

### Backend
- **Python 3.11+** - Core language
- **FastAPI** - Async HTTP API
- **Neo4j** - Knowledge graph storage
- **LiteLLM** - Universal LLM gateway (100+ providers)
- **Pydantic v2** - Schema validation
- **Redis** - Caching and rate limiting
- **Celery** - Background job processing

### LLM Providers (via LiteLLM)
- **OpenAI** (GPT-4, GPT-3.5, o1-preview)
- **Anthropic** (Claude 3.5, Claude 3)
- **Azure OpenAI** (Enterprise deployment)
- **AWS Bedrock** (Claude, Llama on AWS)
- **Ollama** (Local: Llama3, Mistral, any GGUF)
- **Any OpenAI-compatible endpoint** (LocalAI, vLLM, custom Docker gateways)

### File Format Support
- **PDF** - PyMuPDF extraction with page/table preservation
- **DOCX** - python-docx with headings/lists
- **Markdown** - markdown-it with structure
- **Plain Text** - Built-in read
- **URLs** - requests + BeautifulSoup web scraping

### Frontend
- **React 19** + **TypeScript** - UI and type safety
- **Vite 8** - Build tool
- **Tailwind CSS 4** - Styling
- **Zustand 5** - State management
- **React Router 7** - Routing
- **Framer Motion 11** - Animations

---

## Quickstart

### Backend
1. Install the runtime dependencies — `pip install -r requirements.txt` does not resolve
   (langchain pin conflict); install the runtime set directly:
   `pip install "litellm>=1.40.0" fastapi uvicorn websockets pydantic python-dotenv neo4j httpx \`
   `  python-multipart PyMuPDF python-docx beautifulsoup4 requests`
2. Point `.env` at Neo4j and an LLM provider (`NEO4J_URI`, `NEO4J_USERNAME`,
   `NEO4J_PASSWORD`, plus your provider key), then bootstrap the schema:
   `python -m src.cli.bootstrap_neo4j`
3. `uvicorn src.api.api_server:app --host 127.0.0.1 --port 8000`

### Frontend
1. `cd frontend && npm install`
2. `npm run dev` → http://localhost:5173
   The API base defaults to `http://127.0.0.1:8000`; override with `VITE_API_BASE`
   in `frontend/.env.local`.

### Golden path
Ingest 2 PDFs → Build the graph → Set the question → watch the roster build and the
debate → read the verdict → reopen the run from Runs.

---

## Environment

### 1. Environment Setup

```bash
# Create Python environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows
```

### 2. Configure Environment

Create `.env` file:
```env
DEFAULT_LLM_PROVIDER=ollama
OPENAI_API_KEY=
HUGGINGFACEHUB_API_TOKEN=
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3.5-100k:9b

NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your_password
NEO4J_DATABASE=neo4j
```

Startup (backend, frontend) and the golden path: see [Quickstart](#quickstart). API docs at http://localhost:8000/docs once the backend is up.

---

## API Endpoints

### Main Simulation

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/simulate` | POST | Synchronous simulation |
| `/simulate/async` | POST | Async simulation (returns job_id) |
| `/simulate/jobs/{job_id}` | GET | Poll job status |

### Graph Operations

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/simulate/build_graph` | POST | Document → Knowledge Graph |
| `/simulate/ontology` | POST | Ontology discovery only |
| `/simulate/normalize_graph` | POST | Normalize existing graph |

### Graph Debate

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/simulate/debate` | POST | Graph-backed agent debate |

### Runs History

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/simulate/debates` | GET | List run summaries (newest first) |
| `/simulate/debates/{run_id}` | GET | Fetch one run document (events + verdict) |

### Health

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Health check |

---

## Example API Requests

### Sync Simulation
```bash
curl -X POST http://localhost:8000/simulate \
  -H "Content-Type: application/json" \
  -d '{
    "scenario": "Should I expand my SaaS into Europe?",
    "context": { "budget_usd": 200000, "team_size": 12 },
    "simulation_depth": "standard"
  }'
```

### Build Knowledge Graph
```bash
curl -X POST http://localhost:8000/simulate/build_graph \
  -H "Content-Type: application/json" \
  -d '{
    "dataset_id": "merger_2025",
    "documents": [{
      "document_id": "doc_001",
      "title": "Merger Agreement",
      "text": "Acme Corp agrees to acquire Beta Industries for $2.5B..."
    }]
  }'
```

---

## Testing

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/simulation/test_orchestrator.py

# Run with coverage
pytest --cov=src tests/
```

---

## Project Structure

```
src/
├── main.py                    # Entry point
├── api/                      # FastAPI server + endpoints
├── simulation/               # Core debate engine
│   ├── orchestrator.py       # 5-stage pipeline coordinator
│   ├── round_runner.py       # Round execution
│   ├── topology.py           # Cypher pair scoring
│   ├── verdict.py            # CIOR-weighted synthesis
│   ├── society_memory.py     # Opinion/REACTED_TO commit + snapshot read
│   └── profile_synthesizer.py # Agent creation
├── persona/                  # Agent models + repository
│   ├── agent.py             # Canonical Agent schema
│   └── repository.py        # Neo4j operations
├── graph/                   # Knowledge graph construction
│   ├── graph_pipeline.py    # End-to-end pipeline
│   ├── ontology.py          # Schema discovery
│   └── graph_build.py       # Entity extraction
└── llm/                     # Multi-provider LLM client
    └── client.py            # Unified interface

frontend/                     # React + TypeScript dashboard
tests/                       # Pytest test suite
docs/
└── ARCHITECTURE.md          # Detailed architecture docs
```

---

## Key Concepts

### CIOR (Certainty-Instinct Opinion Range)
Weighting formula for consensus:
```
weight = confidence × conviction × (1 + cior) / 2
```
- `cior = +1.0` → Maximum receptivity
- `cior =  0.0` → Neutral
- `cior = -1.0` → Maximum hostility

### Communication Topology
- **Round 1**: Single-hop entity overlap via Cypher
- **Round N**: Multi-hop paths up to agent's `communication_radius`
- **Pair Scoring**: Jaccard similarity + OPPOSES/SUPPORTS edge bonuses

### Convergence
Debate stops when dominant stance reaches 80% weighted consensus.

---

## Documentation

- [TECHNOLOGY_STACK.md](docs/TECHNOLOGY_STACK.md) - Complete tech stack and production architecture
- [ARCHITECTURE.md](docs/ARCHITECTURE.md) - Detailed component architecture
- [DESIGN.md](docs/DESIGN.md) - Frontend design specification (The Chamber)

---

## License

MIT
