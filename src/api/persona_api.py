from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional

from src.graph.config_graph import GraphConfig
from src.persona.repository import PersonaRepository
from src.persona.fetcher import PersonaFetcher
from src.llm.client import global_llm_client
from src.llm.config_llm import get_llm_config
from src.logging.setup_logging import setup_logging
import json
import re


router = APIRouter(prefix="/api/personas", tags=["personas"])
logger = setup_logging()

class HatchRequest(BaseModel):
    query: str
    limit: Optional[int] = 10


@router.post("/hatch", response_model=List[dict])
async def hatch_personas(req: HatchRequest):
    if not req.query or not req.query.strip():
        raise HTTPException(status_code=400, detail="query is required")

    cfg = GraphConfig()
    repo = PersonaRepository(
        neo4j_uri=cfg.neo4j_uri,
        neo4j_user=cfg.neo4j_username,
        neo4j_password=cfg.neo4j_password,
        neo4j_database=cfg.neo4j_database,
    )

    fetcher = PersonaFetcher(repo=repo, archetype_label=None)

    # 1) Extract intent (keywords + desired outcome) from the user query via LLM
    llm_cfg = get_llm_config()
    system_prompt = "Decompose the following user query for a simulation environment.Identify direct terms and hidden latent sectors that are crucial for a 360-degree debate Return JSON: {\"direct_keywords\": [description='Core terms directly in the query'], \"latent_sectors\":[description='Hidden or related sectors/industries or concept'], \"search_perspectives\": [description='Specific angles like 'Economic', 'Technical', or 'Legal'']}" 
    user_prompt = f"User query: {req.query}\n\nRespond with compact JSON only."
    try:
        raw = await global_llm_client.generate(system_prompt, user_prompt, provider=llm_cfg.default_llm_provider, model=llm_cfg.default_model, temperature=0.0)
        logger.info(f"LLM raw response for intent extraction: {raw}")

        # Extract JSON object from any fences or surrounding text
        raw_text = (raw or "")
        m = re.search(r"\{[\s\S]*\}", raw_text)
        if m:
            json_text = m.group(0)
        else:
            json_text = raw_text.strip()

        try:
            parsed = json.loads(json_text)
            keywords = [k.lower() for k in parsed.get("direct_keywords", []) if isinstance(k, str)]
        except Exception as e:
            logger.error(f"Error parsing LLM response: {e}; extracted text: {json_text}")
            # fallback to simple tokenization
            keywords = [t for t in re.findall(r"[\w'-]{2,}", req.query.lower()) if len(t) > 1]
    except Exception as e:
        logger.error(f"Error generating LLM response: {e}")
        # LLM unavailable - fallback to naive tokenization
        keywords = [t for t in re.findall(r"[\w'-]{2,}", req.query.lower()) if len(t) > 1]

    try:
        # 2) Search graph across all node fields using tokens
        rows = await repo.search_agents_by_query(archetype_label=None, query_tokens=keywords, limit=req.limit or 10)
        profiles = []
        for node_props in rows:
            name = node_props.get("name") or node_props.get("title") or node_props.get("id")
            if not name:
                continue
            try:
                profile = await fetcher.get_persona_context(name, req.query)
                profiles.append(profile.dict())
            except Exception as e:
                logger.error(f"Error fetching persona context for {name}: {e}")
                continue
        return profiles
    finally:
        await repo.close()
