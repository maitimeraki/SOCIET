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


# 🧠 Graphify: AI-Powered Knowledge Graph & Reasoning Engine

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Production%20Ready%20Architecture-brightgreen.svg)]()

This project is an advanced system designed to ingest unstructured data (PDFs, web content, etc.), extract structured knowledge, build a persistent Knowledge Graph (KG), and enable sophisticated reasoning via specialized AI Agents.

---

## 🛑 1. The Core Problem: The Hallucination & Redundancy Trap

When building advanced AI systems that rely on external knowledge, the way metadata is structured and persisted is the single most critical factor determining reliability. Our initial approach suffered from two major, interconnected flaws:

### 🔴 1. Metadata Redundancy (The Bloat Problem)
We were attaching all high-level metadata (like `domain_tags`) directly to *every single chunk node*.
*   **The Flaw:** If a single source document generates 100 chunks, the same high-level metadata is written 100 times across 100 different nodes. This bloats the graph, increases storage costs, and makes the graph schema brittle.

### 🔴 2. Weak Grounding (The Hallucination Risk)
The system lacked a clear, authoritative link back to the source document's overall context.
*   **The Flaw:** An agent could retrieve a chunk but lose the explicit link to the *source document's* overall context. This ambiguity allows the LLM to hallucinate or misinterpret the scope of the information, as it cannot definitively trace its claims back to the source.

---

## ✅ 💡 The Solution: Source-Centric Metadata Model

We refactored the architecture to enforce a **Source-Centric Metadata Model**. The goal is to make the graph structure *authoritative* and *minimal*.

1.  **Document Node Elevation:** The primary source document (`Document` node) becomes the single source of truth for high-level metadata (Title, Source Tags, etc.).
2.  **Chunk Node Simplification:** The `Concept` node (the chunk) now only links *to* the `Document` node via a `[:DERIVED_FROM]` relationship.
3.  **Graph Integrity:** All high-level context is stored once on the `Document` node, ensuring that every piece of derived knowledge is traceable back to its authoritative source context.

---

## ⚙️ 2. System Architecture & Workflow (The Pipeline)

The system operates in three distinct, decoupled phases:

1.  **API Gateway (`src/api/`):** Receives raw data $\rightarrow$ **Queues Job** (Non-blocking).
2.  **Worker Service (External):** Consumes the job $\rightarrow$ **Processes $\rightarrow$ Writes to Graph.**
3.  **Chunk Processor (`src/utils/chunkProcessor.py`):** Handles the enrichment of raw text into structured, context-rich data dictionaries.
4.  **Graph Builder (`src/graph/graph_build.py`):** Orchestrates the write process:
    *   **Document Node Creation:** Creates/Updates the main `(:Document)` node first, attaching the source tags.
    *   **Concept Node Creation:** Creates the `(:Concept)` node, linking it to the `Document` node via `[:DERIVED_FROM]`.
    *   **Relationship Extraction:** Uses LLMs to extract entities and relationships, linking them to the correct nodes, all while respecting the source context.

---

## 🛠️ 3. Implementation Details & Code Changes

### A. `src/utils/chunkProcessor.py` (The Enricher)
The function is refactored to **return a dictionary of components** rather than a final `ProcessedChunk` object. This separates the *enrichment* (LLM work) from the *assembly* (Graph Builder work).

*   **Key Change:** The function now explicitly accepts and passes the `document_anchor` (Title/Subject) to ensure the context is available for the final graph assembly.

### B. `src/graph/graph_build.py` (The Gatekeeper)
This module is responsible for enforcing the new schema:

1.  **Document Node First:** It now *must* execute a step to create or find the main `(:Document)` node using the `document_id` and `document_anchor`.
2.  **Tag Attachment:** The `domain_tags` are attached to this **Document Node**, not the chunk node.
3.  **Schema Enforcement:** The `Concept` node is created, and its metadata is enriched with the `document_anchor` to guarantee traceability.

---

## 🚀 Next Steps for Development

1.  **Implement Message Queue:** Set up a dedicated worker service to consume jobs from the queue (Decoupling).
2.  **Refine Splitting:** Replace `simple_splitter` with a **Semantic Splitter** that respects natural document boundaries (e.g., section headers).
3.  **Ontology Mapping:** Formalize the `[List of known tags here]` placeholder in the prompt with a definitive, external taxonomy source.