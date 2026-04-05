import os
import dotenv
from dataclasses import dataclass
dotenv.load_dotenv()  # Load environment variables from .env file

@dataclass
class GraphConfig:
    discovery_model: str = os.getenv("GRAPH_DISCOVERY_MODEL", "gpt-4.1")
    extraction_model: str = os.getenv("GRAPH_EXTRACTION_MODEL", "gpt-4.1-mini")
    temperature: float = float(os.getenv("GRAPH_TEMPERATURE", "0.0"))
    discovery_sample_size: int = int(os.getenv("GRAPH_DISCOVERY_SAMPLE_SIZE", "12"))

    neo4j_uri: str = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_username: str = os.getenv("NEO4J_USERNAME", "neo4j")
    neo4j_password: str = os.getenv("NEO4J_PASSWORD", "password")
    neo4j_database: str = os.getenv("NEO4J_DATABASE", "neo4j")