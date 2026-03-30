import asyncio
import uuid
import json
from datetime import datetime
from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Optional, AsyncGenerator
from contextlib import asynccontextmanager
from src.api.config_api import UserQuery, SimulationResponse
from src.simulation.simulation_engine import SimulationSociety
from src.simulation.world_state import SharedWorldState, MessageBus
from src.simulation.config_world import WorldEvent
from src.llm.client import LLMClient, global_llm_client
from src.llm.config_llm import get_llm_config


@asynccontextmanager
async def lifespan(app: FastAPI)-> AsyncGenerator[None, None]:
    """Startup and shutdown events for the API server"""
    # 1. Setup: Everything before 'yield' runs on STARTUP
    print("Starting up API server...")
    client = global_llm_client  # Use the global client instance
    # Test LLM connectivity, warm up caches, etc.
    try:
        test = await client.generate(
            "You are a test system.", 
            "Say 'OK' if working.",
            provider=get_llm_config().default_llm_provider,
            model=get_llm_config().default_model,
            temperature=0.7
        )
        if test:
            print(f"✅ LLM connected: {get_llm_config().default_llm_provider}")
        
    except Exception as e:
        print(f"LLM connectivity test failed: {e}")
        raise RuntimeError("LLM provider is not reachable. Check configuration.")

    yield # The app runs while it's paused here
    # 2. Shutdown: Everything after 'yield' runs on SHUTDOWN

app = FastAPI(
    title="Socirty Simulator API",
    description="API for simulating societal debates using AI agents",
    version="1.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)




@app.post("/simulate", response_model=SimulationResponse)
async def create_simulation(query: UserQuery, background_tasks: BackgroundTasks):
    """
    Main endpoint: User input -> Society opinion
    """
    client = global_llm_client  # Use the global client instance
    sim_id = str(uuid.uuid4())
    llm_cfg = get_llm_config()

    # 1. Parse query into world parameters using configured provider/model
    world_params = await parse_scenario(
        scenario=query.scenario,
        context=query.context or {},
        provider=llm_cfg.default_llm_provider,
        model=llm_cfg.default_model
    )

    # 2. Spawn society
    society_config = design_society(
        topic=query.scenario,
        required_perspectives=query.required_perspectives,
        depth=query.simulation_depth
    )

    # Optional: merge inferred domains from parser
    inferred_domains = world_params.get("domains", [])
    if inferred_domains:
        society_config["domains"] = sorted(set(society_config["domains"] + inferred_domains))

    # 3. Initialize simulation world
    world = SharedWorldState()
    bus = MessageBus()
    society = SimulationSociety(world, bus)

    world.inject_event(WorldEvent(
        event_type="user_query",
        description=query.scenario,
        severity=0,
        affected_domains=society_config["domains"],
        timestamp=str(datetime.now())
    ))
    world.economic_indicators["user_context"] = query.context or {}

    # 4. Recruit and run with backend built from llm config
    # llm_backend = get_llm_backend(
    #     provider=llm_cfg.default_llm_provider,
    #     model_name=llm_cfg.default_model,
    #     temperature=0.7
    # )
    # llm_backend = await client.generate(user_prompt="How was the days going on??", system_prompt="You are the helpful asistant",provider=llm_cfg.default_llm_provider, model=llm_cfg.default_model, temperature=0.7)
    
    society.recruit_agents(society_config["agents"], client.generate)
    result = await society.run_simulation(query.scenario)

    # 5. Format response
    return SimulationResponse(
        society_opinion=result["society_opinion"],
        dissenting_views=result["dissent"]["alternative_views"],
        confidence_metrics={
            "overall_confidence": result["society_opinion"]["confidence"],
            "debate_rounds": result["meta"]["rounds_to_convergence"],
            "debate_intensity": result["meta"]["debate_intensity"],
            "provider": llm_cfg.default_llm_provider,
            "model": llm_cfg.default_model
        },
        agent_profiles=[
            {
                "name": a.name,
                "expertise": a.domain_expertise,
                "personality": [p.value for p in a.personality],
                "final_stance": "unknown"
            }
            for a in society.agents
        ],
        raw_debate_log=result.get("debate_log") if query.simulation_depth == "deep" else None
    )
    
async def parse_scenario(
    scenario: str,
    context: Dict,
    provider: Optional[str] = None,
    model: Optional[str] = None
) -> Dict:
    
    world_state_json = json.dumps(context, ensure_ascii=False)
    prompt = f"""
Analyze this business scenario and extract JSON with keys:
- domains: string[]
- time_horizon: string
- risk_factors: string[]
- success_criteria: string[]

Scenario: {scenario}
Context: {world_state_json}
"""
    raw = await global_llm_client.generate(
        system_prompt="You extract structured simulation parameters. Return valid JSON only.",
        user_prompt=prompt,
        provider=provider,
        model=model,
        temperature=0.2
    )

    try:
        parsed = json.loads(raw)
        return {
            "domains": parsed.get("domains", []),
            "time_horizon": parsed.get("time_horizon", "unknown"),
            "risk_factors": parsed.get("risk_factors", []),
            "success_criteria": parsed.get("success_criteria", []),
        }
    except Exception:
        return {
            "domains": [],
            "time_horizon": "unknown",
            "risk_factors": [],
            "success_criteria": []
        }
    
    

def design_society(topic: str, required_perspectives: Optional[List[str]], depth: str) -> Dict:
    base_agents = [
        {
            "name": "Conservative Analyst",
            "domain_expertise": ["finance", "risk_management"],
            "personality": ["pessimist", "conservative", "skeptic"],
            "initial_beliefs": [{"statement": "Market expansion is inherently risky", "confidence": 0.8, "evidence": ["historical volatility"]}]
        },
        {
            "name": "Growth Strategist",
            "domain_expertise": ["business_development", "market_analysis"],
            "personality": ["optimist", "innovator"],
            "initial_beliefs": [{"statement": "First-mover advantage outweighs risks", "confidence": 0.75, "evidence": ["competitive dynamics"]}]
        },
        {
            "name": "Cultural Translator",
            "domain_expertise": ["anthropology", "international_business", "cultural_studies"],
            "personality": ["skeptic", "optimist"],
            "initial_beliefs": [{"statement": "Local adaptation determines success", "confidence": 0.9, "evidence": ["cross-market variance"]}]
        }
    ]

    if "europe" in topic.lower() or "eu" in topic.lower():
        base_agents.append({
            "name": "Regulatory Expert",
            "domain_expertise": ["international_law", "gdpr", "trade_regulation"],
            "personality": ["skeptic", "conservative"],
            "initial_beliefs": [{"statement": "Compliance costs are underestimated", "confidence": 0.85, "evidence": ["regulatory overhead"]}]
        })

    if "tech" in topic.lower() or "ai" in topic.lower():
        base_agents.append({
            "name": "Technology Scout",
            "domain_expertise": ["emerging_tech", "ai", "innovation"],
            "personality": ["innovator", "optimist"],
            "initial_beliefs": [{"statement": "Technology obsoletes old business models", "confidence": 0.8, "evidence": ["adoption curves"]}]
        })

    if depth == "deep":
        base_agents.append({
            "name": "Contrarian",
            "domain_expertise": ["logic", "philosophy", "systems_thinking"],
            "personality": ["skeptic", "pessimist"],
            "initial_beliefs": [{"statement": "Group consensus is often wrong", "confidence": 0.9, "evidence": ["groupthink patterns"]}]
        })

    # Optional perspective filter
    if required_perspectives:
        rp = set(p.lower() for p in required_perspectives)
        base_agents = [
            a for a in base_agents
            if any(d.lower() in rp for d in a["domain_expertise"]) or a["name"] in {"Conservative Analyst", "Growth Strategist"}
        ]

    return {
        "agents": base_agents,
        "domains": sorted(set(d for a in base_agents for d in a["domain_expertise"]))
    }

    
# def get_llm_backend(
#     provider: Optional[str] = None,
#     model_name: Optional[str] = None,
#     temperature: float = 0.7
# ):
#     """
#     Sync adapter because Agent.perceive/deliberate call llm_backend(prompt) synchronously.
#     """
#     cfg = get_llm_config()
#     selected_provider = provider or cfg.default_llm_provider
#     selected_model = model_name or cfg.default_model

#     def call_llm(prompt: str) -> str:
#         if selected_provider == "openai":
#             llm = global_llm_client._get_openai()
#             if not llm:
#                 raise ValueError("OpenAI not configured")
#             llm.temperature = temperature
#             messages = [
#                 SystemMessage(content="You are a simulation agent. Return strict JSON only."),
#                 HumanMessage(content=prompt),
#             ]
#             return llm.invoke(messages).content

#         if selected_provider == "huggingface":
#             llm = global_llm_client._get_huggingface()
#             if not llm:
#                 raise ValueError("HuggingFace not configured")
#             full_prompt = f"<s>[INST] Return strict JSON only.\\n\\n{prompt} [/INST]"
#             return llm.invoke(full_prompt).strip()

#         llm = global_llm_client._get_ollama(selected_model)
#         if not llm:
#             raise ValueError(f"Ollama unavailable for model: {selected_model}")
#         llm.temperature = temperature
#         full_prompt = f"<<SYS>>\\nYou are a simulation agent. Return strict JSON only.\\n<</SYS>>\\n\\n{prompt}"
#         return llm.invoke(full_prompt).strip()

#     return call_llm






if __name__=="__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)