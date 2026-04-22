# Agent Persona Synthesis & Profile Construction Framework

This document outlines the **Senior Developer** architecture for generating high-fidelity, data-grounded agent profiles from a Neo4j Knowledge Graph. This pipeline ensures agents are representative of both the user's specific intent and the actual data density within the graph.

## 🚀 The 5-Stage Synthesis Path

### 1. Semantic Intent Extraction
Instead of broad sector mapping, the system extracts high-precision **Intent Vectors** from the user's query.
* **Method:** A fast LLM pass to identify primary Keywords, Entities, and Concepts.
* **Goal:** Capture the "Direction" of the query (e.g., a query about "Market Impact" extracts vectors for *Economics, Trends, and Competition*).

### 2. Global Graph Density Audit (Deterministic Discovery)
To prevent "Missing Sector" syndrome, the system performs a bottom-up scan of the Neo4j database before persona creation.
* **Method:** Cypher query to count occurrences of all `domain_tags`.
* **Goal:** Identify the system’s actual strengths and knowledge clusters independently of the user's prompt.

### 3. The Relevance-Knowledge Matrix
This stage aligns the user’s intent with the graph’s available data using a **Hybrid Relevance Score ($S$)**:
$$S = (w_1 \cdot \text{Semantic Similarity}) + (w_2 \cdot \text{Graph Density})$$
* **Direct Matches:** High overlap between user intent and graph tags.
* **Latent Matches:** Sectors related to intent found in the graph but not mentioned by the user.
* **Discovery Logic:** Identifies the highest-density sector *not* in the intent to serve as a "Blindspot Observer."

### 4. Batch Persona Distillation (Synthesis)
Efficiently transforms sub-graph clusters into human-readable profiles.
* **Method:** A single structured LLM call containing the top node summaries and metadata from the selected sectors.
* **Logic:** The LLM "distills" a persona based on the **Expertise Level** (Strategic/Technical) and **Summary Context** stored in the nodes.

### 5. Deterministic Confidence Scoring
Every agent profile is assigned a reliability metric based on the integrity of its underlying data.
* **Metrics:** * **Source Breadth:** Number of unique `parent_doc_ids` supporting the persona.
    * **Node Density:** Total volume of evidence (nodes).
    * **Connectivity:** Degree centrality of the nodes within the specific sector cluster.

---

## 🛠 Best Methodologies for Profile Building

### Metadata Inheritance
During graph construction, ensure every Entity Node inherits the `domain_tags`, `expertise`, and `parent_doc_id` from its parent `ProcessedChunk`. This allows the agent to "know" its origins and expertise level without re-processing raw text.

### The "Context Anchor" Strategy
Instead of expensive global summaries, every agent profile uses a "Context Anchor" derived from the **Document Title** and **Subject**. This provides the agent with a grounded "World View" or "Initial Perspective" for the simulation.

### "Blindspot" Agent Injection
Always include one agent representing a high-density graph sector that the user query ignored. This ensures the simulation provides an "All-Sector" perspective and uncovers hidden risks or opportunities.

---

## 📊 Agent Profile Production Schema

| Field | Description | Logic |
| :--- | :--- | :--- |
| `agent_id` | Unique UUID | Primary key for simulation state management. |
| `name` | Synthesized Title | e.g., "The Infrastructure Strategist". |
| `type` | Persona Category | Operational, Technical, or Strategic. |
| `perspective` | Initial Description | A 1st-person statement of the agent's "World View". |
| `confidence` | 0.0 - 1.0 Score | Calculated from Node Density and Source Breadth. |
| `provenance` | List of Sources | Direct links to `parent_doc_titles` and `breadcrumbs`. |

---

## 🏗 Implementation Flow



1.  **Extract Intent** from Query.
2.  **Scan Neo4j** for Sector Density.
3.  **Map Similarity** to select top 3-5 Sectors.
4.  **Batch Distill** Personas via LLM.
5.  **Inject Metrics** and deliver JSON payload to Front-End.