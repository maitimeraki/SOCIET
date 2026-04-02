# Simulation World (AI Society Simulator)

Simulation World is a multi-agent decision simulation platform.  
It takes a user scenario, creates a society of domain-specific AI agents, runs structured debate, and returns:

- A synthesized society opinion
- Confidence metrics
- Dissenting/alternative views
- Agent profile summary
- Optional raw debate logs (deep mode)

## Project Structure

- `src/` — Python backend and simulation engine
  - `src/api/` — FastAPI server and API schemas
  - `src/simulation/` — world state, message bus, simulation orchestration
  - `src/agents/` — agent logic and behavior
  - `src/llm/` — LLM provider client and configuration
- `frontend/` — React + Vite dashboard UI

## Core Architecture

1. **User/API Layer** receives scenario and context.
2. **Orchestration** parses scenario into simulation parameters.
3. **Simulation World** creates a society of agents with different expertise/personality.
4. **Debate + Consensus** runs iterative argument exchange and aggregation.
5. **Output Engine** returns final recommendation, confidence, and dissent.

## Tech Stack

### Backend
- Python 3.11+
- FastAPI
- Uvicorn
- Pydantic
- OpenAI / HuggingFace / Ollama support
- LangChain ecosystem (installed in requirements)

### Frontend
- React
- TypeScript
- Vite
- Tailwind CSS

## API Overview

Base URL (local): `http://127.0.0.1:8000`

Main endpoints:

- `GET /domains`  
  Returns supported expert domains.
- `POST /simulate`  
  Runs simulation synchronously and returns final result.
- `POST /simulate/async`  
  Queues simulation and returns a `run_id`.
- `GET /simulate/{run_id}`  
  Polls async simulation status/result.

### Example request (`POST /simulate`)

```json
{
  "scenario": "Should I expand my SaaS business into Europe in 2026?",
  "context": {
    "budget_usd": 200000,
    "team_size": 12,
    "current_markets": ["India", "Singapore"]
  },
  "simulation_depth": "standard",
  "selected_domains": ["finance", "international_law", "market_analysis"],
  "mode": "sync"
}
```

## Local Setup

## 1) Clone and open project

```bash
git clone <your-repo-url>
cd SIMULATION-WORLD
```

## 2) Create Python environment and install backend dependencies

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 3) Configure environment variables

Create `.env` (or use existing env setup) and set values as needed:

```env
DEFAULT_LLM_PROVIDER=ollama
OPENAI_API_KEY=
HUGGINGFACEHUB_API_TOKEN=
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3.5-100k:9b
```

> At least one provider must be reachable. The API performs an LLM connectivity check at startup.

## 4) Run backend API server

```bash
python src/api/api_server.py
```

Server starts on `http://127.0.0.1:8000`.

## 5) Run frontend

In a new terminal:

```bash
cd frontend
npm install
npm run dev
```

Frontend dev server starts on Vite default port (typically `http://localhost:5173`).

## Development Notes

- `simulation_depth` supports: `shallow`, `standard`, `deep`
- `deep` mode includes a richer debate trace and may add contrarian reasoning
- Domain selection can influence which agents are recruited
- Async mode is suitable for longer runs and UI polling

## Current Status

This repository contains active backend and frontend scaffolding with working simulation flow via API.  
Some files still include placeholder metadata (for example in `src/pyproject.toml`) and can be refined as project packaging matures.

## License

Add your preferred license (MIT, Apache-2.0, etc.) in this repository.