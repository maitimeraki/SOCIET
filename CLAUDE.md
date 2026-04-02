# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Simulation World** is an AI-driven simulation framework that models "societies" of autonomous agents debating complex topics and generating consensus opinions. The system simulates how diverse viewpoints interact through structured argumentation, producing nuanced outputs including confidence levels, dissenting views, and risk analysis.

### Core Architecture (5-Layer Design)

```
┌───────────────── USER INTERFACE ────────────────────┐
│   Web Dashboard / API / CLI                         │
└───────────────→ Orchestration Engine ←──────────────┘
                ↓ Simulation World (Agent Society)
    → Message Bus + Shared State
                ↓ Consensus & Synthesis Layer
              Opinion Output Engine
```

## Key Components

### `src/agents` - Agent System
- **Agent.py**: Core agent class with beliefs, memory, and reasoning capabilities
- **config_agents.py**: Configuration for different agent types/domains (e.g., Domain 1, Skeptic)

**Usage Pattern:** Agents maintain internal state (beliefs + memories), communicate via message bus, and update shared world state based on interactions.

### `src/simulation` - Simulation Engine  
- **simulation_engine.py**: Main orchestration logic; manages lifecycle: init → debate rounds → consensus aggregation
- **world_state.py**: Shared reality model containing facts/events accessible by all agents
- **config_world.py**: World configuration (agent count, domains, initial conditions)

**Key Concept:** Debate is structured argumentation with weighted belief aggregation—not simple voting. Dissent is preserved in outputs.

### `src/api` - API Layer
- **api_server.py**: FastAPI server exposing simulation endpoints; handles async request/response streaming
- **config_api.py**: API configuration (endpoints, rate limits)

**Usage Pattern:** Submit scenarios via POST → receive streamed debate output with final opinion synthesis.

## Development Commands

### Setup & Dependencies
```bash
# Install dependencies from root or src/
pip install -r requirements.txt  # Root level
cd src && pip install -e .       # Editable install of project
```

### Run Simulation (CLI)
```python
from src.main import main
main()  # Placeholder; actual CLI logic in api_server.py
```

### API Testing
```bash
# Start server and test via curl or Postman
uvicorn src.api.api_server:app --reload
curl http://localhost:8000/docs  # OpenAPI spec at /docs
```

### LLM Integration
- **src/llm/client.py**: Handles async LLM calls with streaming support
- **config_llm.py**: Model configuration (temperature, max tokens)

## Testing Strategy

No test files exist yet. To add tests:
1. Use `pytest` for unit testing agents/simulation logic
2. Mock LLM responses via `src/llm/client.py` interface
3. Test async operations with `asyncio.get_event_loop().run_until_complete()`

Example structure to create:
```python
# src/tests/test_agent.py
from unittest.mock import AsyncMock, patch
import pytest
from src.agents.Agent import Agent
```

## Common Patterns

### Creating a Simulation Run
1. Configure world via `config_world.py` (agent domains)
2. Initialize agents with beliefs/memories per domain
3. Start debate rounds; monitor message bus for interactions
4. Aggregate consensus using weighted reasoning quality scores
5. Generate opinion output with dissent preservation

### Agent Communication Flow
```python
# Agents publish to shared world state → Message Bus broadcasts updates
# Other agents subscribe and update their beliefs/memories based on events
```

## Important Notes

- **Async-first design**: All LLM calls use `async/await`; coroutines must be properly awaited before JSON parsing (see commit 340b9d1)
- **Streaming support**: API server streams responses; handle partial data correctly
- **Belief aggregation** weights opinions by reasoning quality, not just vote count
- Output format includes: confidence level + dissenting views + assumptions made

## File Structure Reference

```
src/
├── main.py              # Entry point (currently placeholder)
├── pyproject.toml       # Project metadata & dependencies
├── README.md            # Architecture diagram
│
├── agents/              # Agent system layer
│   ├── __init__.py
│   ├── config_agents.py  # Domain configurations
│   └── Agent.py          # Core agent class
│
├── simulation/          # Simulation world layer  
│   ├── __init__.py
│   ├── config_world.py    # World settings
│   ├── simulation_engine.py  # Orchestration logic
│   └── world_state.py     # Shared state model
│
├── api/                 # API interface layer
│   ├── __init__.py
│   ├── config_api.py      # API configuration  
│   └── api_server.py      # FastAPI server (async streaming)
│
└── llm/                # LLM integration layer
    ├── client.py          # Async HTTP client with streaming
    └── config_llm.py      # Model settings
```

## Recent Changes to Note

- Commit 0b0b423: Applied async I/O operations using asyncio throughout the codebase
- Commits b3e5346/e0bb677/340b9d1: Fixed handling of awaitable responses and empty string LLM outputs (JSON parsing errors)
