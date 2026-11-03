import asyncio
import logging
import sys
import uuid
from typing import List, Optional

from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.graph_stores.neo4j import Neo4jPropertyGraphStore
from llama_index.llms.openai_like import OpenAILike

from src.api.graph_stream import GraphDelta, publish
from src.graph.config_graph import GraphConfig
from src.graph.literals import coerce_value, is_literal_value
from src.graph.llm_metering import wrap_with_metering
from src.graph.models_graph import LocalOntology, ProcessedChunk
from src.graph.vocabulary import promote, select_slice
from src.llm.config_llm import LLMConfig
from src.llm.extraction import (
    assert_extraction_licensed,
    resolve_extraction_settings,
)
from src.logging.setup_logging import setup_logging

# Configure basic logging
logging.basicConfig(
    level=logging.INFO,  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],  # Output to terminal
)
logging.warning(
    "This is a warning message. Check your configuration or code for potential issues."
)
logging.basicConfig(
    level=logging.ERROR, format="%(asctime)s - %(levelname)s - %(message)s"
)

# Create logger instance
# logger = logging.getLogger(__name__)
logger = (
    setup_logging()
)  # Ensure logging is configured with handler clearing to prevent duplication

# The ollama clients default to httpx `timeout=None` (unbounded) — a stuck
# localhost embed call would wait forever. 60 s is a generous bound for it.
_EMBED_TIMEOUT_SECONDS = 60

# Document-first node model (P4-T1): a Document node per source document, created
# before extraction, and a DERIVED_FROM edge from every extracted concept to it.
# `domain_tags` accumulates and dedupes instead of overwriting: the live path
# calls the stage one chunk at a time, so repeated calls for one document must
# converge to the document-wide union.
_MERGE_DOCUMENTS = """
UNWIND $docs AS row
MERGE (d:Document {document_id: row.document_id, dataset_id: row.dataset_id})
SET d.domain_tags = coalesce(d.domain_tags, []) + [t IN row.domain_tags WHERE NOT t IN coalesce(d.domain_tags, [])]
"""

_LINK_CONCEPTS_TO_DOCUMENTS = """
UNWIND $rows AS row
MATCH (c:__Node__ {id: row.chunk_id})-[:MENTIONS]->(e:__Entity__)
MATCH (d:Document {document_id: row.document_id, dataset_id: $dataset_id})
MERGE (e)-[:DERIVED_FROM]->(d)
"""

# The dynamic extractor's `extract_prompt`. Its `{...}` placeholders are exactly
# the ones `DynamicLLMPathExtractor._apredict_with_props` supplies — `text`,
# `max_knowledge_triplets`, `allowed_entity_types`, `allowed_relation_types`,
# `allowed_entity_properties`, `allowed_relation_properties` — so `.format()`
# never raises. The rules below are the prompt half of the literal guard; the
# deterministic backstop lives in `src.graph.literals` (spec §6.3).
_EXTRACTION_PROMPT = """Extract up to {max_knowledge_triplets} knowledge triplets from the given text. Each triplet should be in the form of (head, relation, tail) with their respective types and properties.
---------------------
INITIAL ONTOLOGY:
Entity Types: {allowed_entity_types}
Entity Properties: {allowed_entity_properties}
Relation Types: {allowed_relation_types}
Relation Properties: {allowed_relation_properties}

Use these types as a starting point, but introduce new types if necessary based on the context.

RULES:
1. Emit ONLY real, referenceable entities (organizations, people, places, products, events, concepts).
2. NEVER emit money, dates, quantities, percentages, or bare numbers as entities.
3. Put those values in properties, using the declared slots (e.g. price, date, revenue).
4. Use only the allowed entity and relation types.

GUIDELINES:
- Output in JSON format: [{{'head': '', 'head_type': '', 'head_props': {{...}}, 'relation': '', 'relation_props': {{...}}, 'tail': '', 'tail_type': '', 'tail_props': {{...}}}}]
- Use the most complete form for entities (e.g., 'United States of America' instead of 'USA')
- Keep entities concise (3-5 words max)
- Break down complex phrases into multiple triplets
- Ensure the knowledge graph is coherent and easily understandable
---------------------
Text: {text}
Output:
"""


def _document_rows(dataset_id: str, documents: List[ProcessedChunk]) -> List[dict]:
    """One row per unique `parent_doc_id`: its dataset plus the deduped,
    order-stable union of its chunks' `domain_tags`."""
    rows: dict[str, dict] = {}
    for d in documents:
        row = rows.setdefault(
            d.parent_doc_id,
            {
                "document_id": d.parent_doc_id,
                "dataset_id": dataset_id,
                "domain_tags": [],
            },
        )
        for tag in d.domain_tags or []:
            if tag not in row["domain_tags"]:
                row["domain_tags"].append(tag)
    return list(rows.values())


def _proposed_labels(extracted) -> tuple[List[str], List[str]]:
    """The `(entity_labels, relation_labels)` a chunk's extraction result proposed.

    llama-index extractors return the input nodes with their extracted
    `EntityNode`s stashed under `metadata["nodes"]` and `Relation`s under
    `metadata["relations"]` (see `DynamicLLMPathExtractor._aextract`), so each
    label sits one level down. The two kinds come back separately so the caller
    can `promote` each under its own side. llama-index's generic default entity
    label — the literal `"entity"`, which the simple extractor stamps on every
    `EntityNode` it builds unlabelled — and blank labels are dropped; the caller
    wants real types, not the sentinel. Order-stable and de-duplicated per kind.
    """
    from llama_index.core.graph_stores.types import KG_NODES_KEY, KG_RELATIONS_KEY

    entity_labels: List[str] = []
    relation_labels: List[str] = []
    for node in extracted or []:
        metadata = getattr(node, "metadata", None) or {}
        for item in metadata.get(KG_NODES_KEY, []):
            label = getattr(item, "label", None)
            if (
                label
                and label.strip()
                and label != "entity"
                and label not in entity_labels
            ):
                entity_labels.append(label)
        for item in metadata.get(KG_RELATIONS_KEY, []):
            label = getattr(item, "label", None)
            if label and label.strip() and label not in relation_labels:
                relation_labels.append(label)
    return entity_labels, relation_labels


# The writers' bookkeeping — llama-index stamps chunk lineage onto every entity,
# and the pipeline stamps the dataset/ontology id. Never a displayable fact.
_LINEAGE_KEYS = frozenset(
    {
        "document_id",
        "chunk_id",
        "document_anchor",
        "chunk_index",
        "content_hash",
        "dataset_id",
        "ontology_id",
    }
)


def _public_props(obj) -> dict:
    """An entity/relation's display properties: its extraction facts, lineage stripped.

    ONE definition for BOTH projections — the live delta and the reconnect
    snapshot — so the stripped-key list lives in exactly one place. Accepts an
    object carrying `.properties` (an `EntityNode`/`Relation`) or a bare props
    dict (the snapshot's `properties(e)` projection).
    """
    props = obj if isinstance(obj, dict) else getattr(obj, "properties", None)
    if not isinstance(props, dict):
        return {}
    return {key: value for key, value in props.items() if key not in _LINEAGE_KEYS}


def _delta_payload(extracted) -> tuple[List[dict], List[dict]]:
    """The `(nodes, edges)` a chunk's extraction result contributes to a GraphDelta.

    Reads the SAME metadata bags `_proposed_labels` does — and, critically,
    BEFORE `index.insert_nodes` pops them (llama-index's `_insert_nodes` removes
    `KG_NODES_KEY` / `KG_RELATIONS_KEY`). Node entries are
    `{id, label, type, kind, properties}` (label = the entity's display name,
    type/kind = its extracted type, properties = its facts); edge entries are
    `{source, target, label, properties}`. Order-stable, de-duplicated by node id.
    """
    from llama_index.core.graph_stores.types import KG_NODES_KEY, KG_RELATIONS_KEY

    nodes: List[dict] = []
    edges: List[dict] = []
    seen: set = set()
    for node in extracted or []:
        metadata = getattr(node, "metadata", None) or {}
        for item in metadata.get(KG_NODES_KEY, []):
            item_id = getattr(item, "id", None)
            if item_id and item_id not in seen:
                seen.add(item_id)
                nodes.append(
                    {
                        "id": item_id,
                        "label": getattr(item, "name", None) or item_id,
                        "type": getattr(item, "label", None),
                        "kind": getattr(item, "label", None),
                        "properties": _public_props(item),
                    }
                )
        for rel in metadata.get(KG_RELATIONS_KEY, []):
            edges.append(
                {
                    "source": getattr(rel, "source_id", None),
                    "target": getattr(rel, "target_id", None),
                    "label": getattr(rel, "label", None),
                    "properties": _public_props(rel),
                }
            )
    return nodes, edges


def _pick_slot(rel, relation_slots, kind: str) -> Optional[str]:
    """The declared property name on this relation whose `value_type` is `kind`.

    `relation_slots` is a `LocalOntology`'s `relation_types`. Returns `None` when
    the relation's type declares no slot of that kind — the caller decides the
    fallback, since a real→real edge needs a declared slot but an entity can also
    take the relation's label as its slot name.
    """
    label = getattr(rel, "label", None)
    for rel_def in relation_slots or []:
        if getattr(rel_def, "type_name", None) == label:
            for prop in rel_def.properties:
                if prop.value_type == kind:
                    return prop.name
    return None


def _attach_property(holder, slot: str, value) -> None:
    """Set `holder.properties[slot] = value`, preserving the holder's others."""
    holder.properties = {**(getattr(holder, "properties", None) or {}), slot: value}


def _real_relation_target(relations, literal_id, entities, relation_slots, kind: str):
    """The real→real relation the literal's value belongs to, else `None`.

    This is the spec §13.2 case: the model leaked a value node, but the edge
    between the two REAL entities it describes already declares the typed slot —
    so the coerced value lands on that surviving edge
    (`(Amazon)-[:ACQUIRED {price}]->(WholeFoods)`).

    A leaked literal is often attached to ONE real entity
    (`(WholeFoods)-[:PRICE]->(lit)`). When a chunk extracts two same-kind
    literals (a deal price and a revenue), a plain first-match scan routes BOTH
    to whichever real→real edge declares the slot first — one overwriting the
    other. So prefer the real→real edge sharing the literal's own real
    neighbour; fall back to the first matching real→real edge only when that
    neighbour's edge declares no such slot.
    """
    neighbour = None
    for rel in relations:
        source = getattr(rel, "source_id", None)
        target = getattr(rel, "target_id", None)
        if literal_id not in (source, target):
            continue
        other = target if source == literal_id else source
        if other in entities:
            neighbour = other
            break

    if neighbour is not None:
        for rel in relations:
            source = getattr(rel, "source_id", None)
            target = getattr(rel, "target_id", None)
            if source not in entities or target not in entities:
                continue
            if neighbour not in (source, target):
                continue
            slot = _pick_slot(rel, relation_slots, kind)
            if slot:
                return rel, slot

    for rel in relations:
        source = getattr(rel, "source_id", None)
        target = getattr(rel, "target_id", None)
        if source not in entities or target not in entities:
            continue
        slot = _pick_slot(rel, relation_slots, kind)
        if slot:
            return rel, slot
    return None


def _neighbour_target(relations, literal_id, entities, relation_slots, kind: str):
    """The real endpoint of the literal's incident relation, else `None`.

    Slot precedence: the relation's declared matching slot, else the relation's
    lowercased label, else the generic `"value"` — so the value still survives
    on an entity (§13.1 "edge/entity property").
    """
    for rel in relations:
        source = getattr(rel, "source_id", None)
        target = getattr(rel, "target_id", None)
        if literal_id not in (source, target):
            continue
        other = target if source == literal_id else source
        entity = entities.get(other)
        if entity is None:
            continue
        slot = (
            _pick_slot(rel, relation_slots, kind)
            or (getattr(rel, "label", None) or "").strip().lower()
        )
        return entity, slot or "value"
    return None


def _route_literals(nodes, relation_slots=None):
    """Route each literal's coerced value onto a SURVIVING target, then drop the
    literal node and any relation orphaned by the drop (spec §6.3, §13.1).

    A literal ("$2.5 billion", "2018") that the extractor emitted as an
    `EntityNode` is not a referenceable entity; its value belongs in the typed
    property slot of the edge or entity it describes. The target is chosen so it
    survives the drop:

    1. a real→real relation declaring a slot of the coerced kind (§13.2); else
    2. the real endpoint of the literal's incident relation, under that
       relation's declared matching slot, else its lowercased label, else
       `"value"`.

    Runs on the harvested `metadata[KG_NODES_KEY]` / `metadata[KG_RELATIONS_KEY]`
    bags before `_proposed_labels` / `_delta_payload` read them, so the dropped
    literal never reaches the node list, the delta, or the proposed label set.
    """
    from llama_index.core.graph_stores.types import KG_NODES_KEY, KG_RELATIONS_KEY

    attached, dropped = [], []
    for node in nodes:
        meta = getattr(node, "metadata", None) or {}
        bag_nodes = meta.get(KG_NODES_KEY, [])
        literals = {
            getattr(i, "id", None): (getattr(i, "name", "") or "")
            for i in bag_nodes
            if is_literal_value(getattr(i, "name", "") or "")
        }
        if not literals:
            continue
        relations = meta.get(KG_RELATIONS_KEY, [])
        entities = {
            getattr(i, "id", None): i
            for i in bag_nodes
            if getattr(i, "id", None) not in literals
        }
        for node_id, value in literals.items():
            kind, coerced = coerce_value(value)
            target = _real_relation_target(
                relations, node_id, entities, relation_slots, kind
            )
            if target is None:
                target = _neighbour_target(
                    relations, node_id, entities, relation_slots, kind
                )
            if target is None:
                continue
            holder, slot = target
            _attach_property(holder, slot, coerced)
            attached.append(
                (
                    getattr(holder, "label", None) or getattr(holder, "name", None),
                    slot,
                )
            )
        meta[KG_NODES_KEY] = [
            i for i in bag_nodes if getattr(i, "id", None) not in literals
        ]
        meta[KG_RELATIONS_KEY] = [
            r
            for r in relations
            if getattr(r, "source_id", None) not in literals
            and getattr(r, "target_id", None) not in literals
        ]
        dropped.extend(literals.values())
    if dropped:
        logger.info(
            "Routed %d literal slot(s) %s; dropped %d literal node(s)",
            len(attached),
            attached[:5],
            len(dropped),
        )
    return nodes


class _NoOpSplit:
    """Truthy pass-through transform: returns its input nodes unchanged.

    Needed because `BaseIndex.from_documents` resolves
    `transformations = transformations or Settings.transformations`. An empty
    list is falsy, so it would be replaced by `Settings.transformations`, which
    is `[Settings.node_parser]` and is pinned to `self.splitter` below — the
    exact re-split this stage must not perform. A truthy no-op keeps the
    fallback from firing and preserves the input nodes 1:1, so index node count
    equals chunk count.
    """

    def __call__(self, nodes, **kwargs):
        return list(nodes)


def _refresh_schema_once(store: Neo4jPropertyGraphStore) -> None:
    """Quiet llama-index's post-insert schema refreshes: the first refresh through
    this guard is real, every later one is a no-op. llama-index calls
    get_schema(refresh=True) after every insert, which runs apoc.meta.subGraph({})
    + apoc.schema.nodes() over the whole graph; the extraction path never reads
    the refreshed schema, so all but the first pass is waste."""
    original_refresh = store.refresh_schema
    refreshed = False

    def refresh_schema_once(**kwargs):
        nonlocal refreshed
        if refreshed:
            return None
        refreshed = True
        return original_refresh(**kwargs)

    store.refresh_schema = refresh_schema_once


class GraphExtractionStage:
    """Extracts entities and relationships from documents using LLMs and stores them in a Neo4j graph database.
    This stage is responsible for taking raw text documents, applying the defined ontology schema to extract structured information.
    """

    def __init__(self, config: GraphConfig):
        self.config = config
        conversation_session_id = str(uuid.uuid4())
        settings = resolve_extraction_settings(model=self.config.extraction_model)
        assert_extraction_licensed(settings)
        self.llm = OpenAILike(
            model=settings.model,
            api_base=settings.base_url,
            api_key=settings.api_key,
            temperature=0.7,
            is_chat_model=True,
            timeout=self.config.extraction_timeout_seconds,
            max_retries=1,  # a hung attempt must not stack retries on top of the timeout
            additional_kwargs={
                "seed": 42,  # Fixed seed for reproducibility
                "extra_headers": {"x-opencode-session": conversation_session_id},
            },
        )
        wrap_with_metering(
            self.llm, provider=settings.provider, model=settings.model
        )
        self.embed_model = OllamaEmbedding(
            model_name=LLMConfig.embedding_model,
            base_url=LLMConfig.ollama_base_url,
            client_kwargs={"timeout": _EMBED_TIMEOUT_SECONDS},
            ollama_additional_kwargs={"mirostat": 0},
        )
        self.graph_store = Neo4jPropertyGraphStore(
            username=self.config.neo4j_username,
            password=self.config.neo4j_password,
            url=self.config.neo4j_uri,
            database=self.config.neo4j_database,
        )
        _refresh_schema_once(self.graph_store)
        self.splitter = SentenceSplitter(chunk_size=2048, chunk_overlap=400)
        # ONE lock for the whole extraction path, never per chunk: the sliding
        # window keeps several extractions in flight, but only one of them may
        # write the shared store/index at a time, so "an entity in two chunks
        # yields ONE node" cannot depend on the store converging under a race.
        # Extraction stays fully concurrent; only the write is serialised.
        # Instance-level (not module-level) so it binds to the loop that runs
        # THIS stage, and is shared across concurrent `run` calls for a stage.
        self._insert_lock = asyncio.Lock()

    def close(self) -> None:
        """Close the graph store's driver. Idempotent — a second call is a no-op."""
        store = getattr(self, "graph_store", None)
        if store is None:
            return
        self.graph_store = None
        store.close()

    async def run(
        self,
        dataset_id: str,
        documents: List[ProcessedChunk],
        ontology: LocalOntology,
        job_id: Optional[str] = None,
    ) -> int:
        try:
            # Call the async logic directly
            return await self._run_async(dataset_id, documents, ontology, job_id=job_id)
        except Exception as e:
            logger.error(f"Error in GraphExtractionStage for dataset {dataset_id}: {e}")
            raise

    @staticmethod
    def _to_llama_document(dataset_id: str, d: ProcessedChunk, ontology: LocalOntology):
        """One llama-index Document per ProcessedChunk, metadata carried through."""
        from llama_index.core import Document

        md = dict(d.metadata)
        md["dataset_id"] = dataset_id
        # llama-index overwrites the graph `document_id` property with the
        # split node's ref_doc_id at write time (node_to_metadata_dict) —
        # `document_anchor` is the graph-level carrier of the source
        # document id, and `chunk_id` the original chunk id.
        md["document_id"] = d.parent_doc_id
        md["chunk_id"] = d.chunk_id
        md["document_anchor"] = d.parent_doc_id
        md["chunk_index"] = d.chunk_index
        md["content_hash"] = d.content_hash
        md["summary_context"] = d.summary_context
        md["domain_tags"] = d.domain_tags
        md["expertise_level"] = d.expertise_level
        md["breadcrumb"] = d.breadcrumb
        md["header_level"] = d.header_level
        md["ontology_id"] = ontology.metadata.ontology_id
        # `_create_processed_chunk` carries the filename as `source_document`;
        # without the fallback every provenance link title is "Untitled Document".
        md["title"] = (
            md.get("title") or md.get("source_document") or "Untitled Document"
        )
        new_doc = Document(text=d.content, metadata=md)

        new_doc.excluded_llm_metadata_keys = [
            "dataset_id",
            "ontology_id",
            "document_id",
            "chunk_id",
            "document_anchor",
            "content_hash",
            "chunk_index",
        ]  # Exclude sensitive or non-informative metadata from LLM input
        new_doc.excluded_embed_metadata_keys = [
            "dataset_id",
            "ontology_id",
            "document_id",
            "chunk_id",
            "document_anchor",
            "content_hash",
            "chunk_index",
        ]  # Exclude from embedding metadata as well to prevent noise in vector representations
        return new_doc

    async def _run_async(
        self,
        dataset_id: str,
        documents: List[ProcessedChunk],
        ontology: LocalOntology,
        job_id: Optional[str] = None,
    ) -> int:
        import os

        os.environ["LLAMA_INDEX_DISABLE_ASYNC_EMBEDDINGS"] = "1"
        from llama_index.core import PropertyGraphIndex, Settings

        Settings.llm = self.llm
        # ✅ FIX: Disable async embeddings to prevent nested loop creation
        Settings.embed_model = self.embed_model
        Settings.node_parser = self.splitter

        logger.info(
            f"Transforming ontology schema for dataset {dataset_id} into property-aware format."
        )
        try:
            logger.info(
                f"Initializing extractors for dataset {dataset_id} with "
                f"{ontology.entity_labels} entity schemas and "
                f"{ontology.relation_labels} relation schemas."
            )

            pairs = [
                (d, self._to_llama_document(dataset_id, d, ontology)) for d in documents
            ]

            # One empty index bound to the shared store. `kg_extractors=[_NoOpSplit()]`
            # (a TRUTHY no-op) is essential: `PropertyGraphIndex.__init__` does
            # `kg_extractors or [SimpleLLMPathExtractor(...), ImplicitPathExtractor()]`,
            # so an empty list would silently re-extract every chunk through the
            # default extractors. The no-op keeps `_insert_nodes` to its store
            # writes only — the extractors already ran once, per chunk, below.
            def _build_index():
                return PropertyGraphIndex(
                    nodes=[],
                    embed_model=self.embed_model,
                    property_graph_store=self.graph_store,
                    kg_extractors=[_NoOpSplit()],
                    use_async=False,
                )

            # Document-first: the Document nodes exist before extraction so the
            # DERIVED_FROM pass below has something to link to.
            await asyncio.to_thread(self._write_documents, dataset_id, documents)

            index = await asyncio.to_thread(_build_index)

            logger.info(f"Building property graph for dataset {dataset_id}")

            # The shared vocabulary: exactly two touch points, both cheap and
            # both on the single event loop between awaits — read the slice at
            # chunk start, append new labels at chunk finish. No lock needed.
            vocabulary = ontology
            total = len(pairs)
            state = {"done": 0}

            async def process(chunk: ProcessedChunk, doc) -> bool:
                """Extract + insert ONE chunk, retrying on failure; return success.

                A chunk that fails `extraction_chunk_retries` retries (exponential
                backoff, mirroring `_discover_for_chunk`) is SKIPPED: logged,
                published as an error delta, and the window refills. Never raises
                on a chunk error, so one bad chunk cannot sink the loop.
                """
                nonlocal vocabulary
                last_exc: Optional[Exception] = None
                attempts = max(1, self.config.extraction_chunk_retries + 1)
                for attempt in range(attempts):
                    try:
                        slice_ = select_slice(
                            vocabulary, chunk.content, self.config.chunk_slice_size
                        )
                        extractors = self._build_extractors(slice_)
                        (
                            nodes,
                            entity_labels,
                            relation_labels,
                            delta_nodes,
                            delta_edges,
                        ) = await asyncio.to_thread(
                            self._extract_chunk, doc, extractors, slice_.relation_types
                        )
                        # Serialise the store write: extraction is concurrent, but
                        # only one chunk writes the shared index at a time. The
                        # `to_thread` keeps the loop free while the lock waits.
                        async with self._insert_lock:
                            await asyncio.to_thread(index.insert_nodes, nodes)
                    except Exception as exc:
                        last_exc = exc
                        if attempt < attempts - 1:
                            logger.warning(
                                f"Chunk {chunk.chunk_id} extraction attempt {attempt + 1} "
                                f"failed: {exc}. Retrying..."
                            )
                            await asyncio.sleep(
                                self.config.extraction_chunk_retry_backoff_seconds
                                * (2**attempt)
                            )
                        continue
                    # Synchronous read-modify-write: never split by an await.
                    vocabulary, new_entities = promote(
                        vocabulary, entity_labels, kind="entity"
                    )
                    vocabulary, new_relations = promote(
                        vocabulary, relation_labels, kind="relation"
                    )
                    state["done"] += 1
                    if job_id is not None:
                        publish(
                            job_id,
                            GraphDelta(
                                nodes=delta_nodes,
                                edges=delta_edges,
                                new_labels=new_entities + new_relations,
                                chunk_id=chunk.chunk_id,
                                progress=state["done"] / total if total else 0.0,
                            ),
                        )
                    return True
                logger.error(
                    f"Chunk {chunk.chunk_id} failed terminally after {attempts} attempts: {last_exc}"
                )
                if job_id is not None:
                    publish(
                        job_id,
                        GraphDelta(
                            chunk_id=chunk.chunk_id,
                            # A non-empty message is load-bearing: `if delta.error:` in
                            # the WS route treats "" as an ordinary delta. A bare
                            # `RuntimeError()` would otherwise be emitted as a `delta`.
                            error=f"{type(last_exc).__name__}: {last_exc}",
                        ),
                    )
                return False

            # Sliding window: `chunk_parallelism` chunk-tasks in flight at all
            # times. Seed the first window, then start exactly one replacement
            # the instant any one finishes — a Semaphore would gate concurrency
            # but would not keep the window full. Insert order is completion
            # order, never buffered by `chunk_index`.
            remaining = iter(pairs)
            pending: set = set()
            successes = 0
            try:
                for _ in range(max(1, self.config.chunk_parallelism)):
                    nxt = next(remaining, None)
                    if nxt is None:
                        break
                    pending.add(asyncio.create_task(process(*nxt)))
                while pending:
                    finished, pending = await asyncio.wait(
                        pending, return_when=asyncio.FIRST_COMPLETED
                    )
                    for fut in finished:
                        successes += int(fut.result())
                    for _ in range(len(finished)):
                        nxt = next(remaining, None)
                        if nxt is None:
                            break
                        pending.add(asyncio.create_task(process(*nxt)))
            finally:
                # An unexpected raise must not strand the other in-flight chunks:
                # without this they would keep extracting and writing to the store
                # after the job was marked failed ("Task exception was never
                # retrieved"). Cancel and await them before propagating.
                for task in pending:
                    task.cancel()
                if pending:
                    await asyncio.gather(*pending, return_exceptions=True)

            # One bad chunk is a skip, not a catastrophe. A document whose chunks
            # ALL failed contributed nothing, but it does NOT sink the run: the
            # job-scoped "every chunk failed" verdict is `_execute_unified_job`'s
            # (R17) — one bad document must not discard every other document's
            # work. Real extraction/store errors, timeouts and cancellation still
            # propagate from the loop above; only per-chunk skips land here.
            if total and not successes:
                logger.error(
                    f"All {total} chunks failed for dataset {dataset_id} — "
                    f"this document contributed no nodes"
                )

            await asyncio.to_thread(self._link_concepts_to_documents, index, dataset_id)
            return len(index.docstore.docs)

        except Exception as e:
            logger.error(f"Error during graph extraction for dataset {dataset_id}: {e}")
            raise

    def _extract_chunk(self, doc, extractors, relation_slots=None):
        """Extract ONE chunk exactly once and harvest its delta + proposed labels.

        Runs off the event loop (the path extractors call `asyncio.run`
        internally, which a running loop would reject). The extractors populate
        `metadata["nodes"]` / `metadata["relations"]` in place; those are read
        HERE, before the caller's `index.insert_nodes` pops them (llama-index's
        `_insert_nodes` removes both keys), so the delta and the proposed labels
        survive. The insert itself is NOT done here — the caller serialises it
        under `_insert_lock`.

        `run_transformations([doc], extractors)` from `llama_index.core.ingestion`
        is exactly `for transform in extractors: nodes = transform(nodes)` — no
        cache is configured, so this direct loop is the same work with one fewer
        import (and it keeps the seam stubbable in tests).

        `relation_slots` is the chunk slice's `relation_types`; literal nodes are
        routed into those declared slots (falling back to `"value"`) and removed
        before the labels and delta are harvested.
        """
        nodes = [doc]
        for extractor in extractors:
            nodes = list(extractor(nodes))
        _route_literals(nodes, relation_slots)
        entity_labels, relation_labels = _proposed_labels(nodes)
        delta_nodes, delta_edges = _delta_payload(nodes)
        return nodes, entity_labels, relation_labels, delta_nodes, delta_edges

    def _build_extractors(self, ontology: LocalOntology) -> tuple:
        """The extractor set for one ontology (or vocabulary slice).

        The dynamic extractor's `allowed_*` schemas come from whatever
        `ontology` is handed in, so a per-chunk slice (Task 7's sliding window)
        builds its own extractors from a smaller vocabulary: `_run_async` calls
        this once PER CHUNK with that chunk's slice.

        Only two extractors remain: the triple-only `SimpleLLMPathExtractor` is
        retired because its schema-free prompt was the source of value nodes
        ("$2.5 billion", "2018") — `_EXTRACTION_PROMPT` plus the literal guard
        in `_extract_chunk` replaces it.
        """
        from llama_index.core.indices.property_graph import (
            DynamicLLMPathExtractor,
            ImplicitPathExtractor,
        )

        # num_workers=1: llama-index runs a call's chunks through
        # run_jobs(jobs, workers=num_workers), so sync mode fans out for
        # real. The outer semaphore (GraphConfig.ontology_max_concurrency,
        # one slot per document) is the single concurrency lever: aggregate
        # in-flight extraction calls = GRAPH_ONTOLOGY_MAX_CONCURRENCY ×
        # num_workers. Raise num_workers only alongside cutting the semaphore.
        # Dynamic extractor - schema-guided but flexible(Dynamic extractor captures labeled entities/relations following your schema)
        dynamic_extractor = DynamicLLMPathExtractor(
            llm=self.llm,
            extract_prompt=_EXTRACTION_PROMPT,
            allowed_entity_types=ontology.entity_labels,
            allowed_relation_types=ontology.relation_labels,
            allowed_entity_props=ontology.entity_props,
            allowed_relation_props=ontology.relation_props,
            max_triplets_per_chunk=self.config.extraction_max_triplets_per_chunk,
            num_workers=1,
        )
        # Implicit extractor - from node relationships(Implicit extractor adds structural relationships between nodes that LLMs don't generate)
        implicit_extractor = ImplicitPathExtractor()
        return (dynamic_extractor, implicit_extractor)

    def _write_documents(
        self, dataset_id: str, documents: List[ProcessedChunk]
    ) -> None:
        """MERGE one Document node per unique source document. Sync — called off the loop."""
        rows = _document_rows(dataset_id, documents)
        if rows:
            self.graph_store.structured_query(
                _MERGE_DOCUMENTS, param_map={"docs": rows}
            )

    def _link_concepts_to_documents(self, index, dataset_id: str) -> None:
        """MERGE `(concept)-[:DERIVED_FROM]->(Document)` for every stored chunk
        that carries a `document_anchor`. Sync — called off the loop."""
        rows = []
        for node_id, node in (index.docstore.docs or {}).items():
            document_id = (getattr(node, "metadata", None) or {}).get("document_anchor")
            if document_id:
                rows.append({"chunk_id": node_id, "document_id": document_id})
        if rows:
            self.graph_store.structured_query(
                _LINK_CONCEPTS_TO_DOCUMENTS,
                param_map={"rows": rows, "dataset_id": dataset_id},
            )


def extract_graph(
    chunks: List[ProcessedChunk],
    ontology: LocalOntology,
    dataset_id: Optional[str] = None,
    config: Optional[GraphConfig] = None,
) -> int:
    """Extract entities and relationships from chunks using ontology schema.

    Args:
        chunks: List of processed document chunks to extract from.
        ontology: LocalOntology defining entity and relation types to extract.
        dataset_id: Optional dataset identifier. Auto-generated if not provided.
        config: Optional GraphConfig. Creates default if not provided.

    Returns:
        Number of documents/chunks processed.
    """
    if dataset_id is None:
        dataset_id = str(uuid.uuid4())

    if config is None:
        config = GraphConfig()

    stage = GraphExtractionStage(config)

    # Synchronous wrapper for the async run method
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If loop is already running, create a new task
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run, stage.run(dataset_id, chunks, ontology)
                )
                return future.result()
        else:
            return loop.run_until_complete(stage.run(dataset_id, chunks, ontology))
    except RuntimeError:
        # No event loop exists, create one
        return asyncio.run(stage.run(dataset_id, chunks, ontology))
