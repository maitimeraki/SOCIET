import { create } from 'zustand'
import type Graph from 'graphology'
import type { Stance, WrittenLink, WrittenNode } from '../run/events'

/** A graph entity. Identity is `id` — the same entity in two chunks is ONE node. */
export interface GraphNode {
  id: string
  label: string
  type: string
  /** The extracted type, as the delta frames it (`type` is the stored label). */
  kind?: string
  /**
   * The position the backend stored with this entry — an opinion's own stance, resolved from the run's
   * folded state and carried here so the one map can colour the entry by it (§9.2). Absent on entries
   * the backend stores no position for: the material, an expert, and an opinion whose holder's turn
   * the stored events do not carry.
   */
  stance?: Stance
  /** The entity's extracted facts — lineage keys stripped server-side. */
  properties?: Record<string, unknown>
}

/** A graph relation. Identity is `source|target|label`. */
export interface GraphEdge {
  source: string
  target: string
  label: string
  /** The relation's extracted facts — lineage keys stripped server-side. */
  properties?: Record<string, unknown>
}

/** The payload of a `delta` frame — the incremental slice a chunk contributed. */
export interface GraphDelta {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

/** The payload of a `snapshot` frame — the full graph so far plus the dataset's label set. */
export interface GraphSnapshot extends GraphDelta {
  labels: string[]
}

/**
 * An expert the debate stream seats — the two halves of the backend's Persona identity. The map
 * keys the entry exactly as the backend keys the stored Persona (`{dataset_id}:{name}`), so the
 * `STATED`/`REACTED_TO` connections a `commit` reports land on it.
 */
export interface ExpertIdentity {
  datasetId: string
  name: string
}

/** The Persona key the backend merges under — `society_memory._persona_key`, reproduced verbatim. */
export const expertKey = (expert: ExpertIdentity): string => `${expert.datasetId}:${expert.name}`

/** An expert the store renders as an entry. */
export const EXPERT_TYPE = 'Expert'

interface GraphStoreState {
  nodes: Record<string, GraphNode>
  edges: Record<string, GraphEdge>
  /** The entity types the map's vocabulary holds, in first-seen order — the text alternative's count. */
  labels: string[]
  /**
   * Monotonic count of node/edge merges. A cheap primitive invalidation key for derived views, so
   * they key on "the graph changed" without deep-comparing (or holding a reference to) the maps.
   * Labels are vocabulary, not content, so `mergeVocabulary` does not bump it.
   */
  version: number
  mergeDelta: (delta: GraphDelta) => void
  applySnapshot: (snapshot: GraphSnapshot) => void
  mergeVocabulary: (labels: string[]) => void
  /** Fold one expert the debate stream seated into the one map. Idempotent on the Persona key. */
  mergeExpert: (expert: ExpertIdentity) => void
  /**
   * Fold one commit's written entries and connections into the one map, verbatim (D7). `stances` is
   * the position resolved for each entry the commit wrote, keyed as the backend keyed it — the entry
   * itself carries none, so the caller resolves it from the run's folded state.
   */
  mergeOpinions: (nodes: WrittenNode[], links: WrittenLink[], stances?: Record<string, Stance>) => void
  /**
   * Replace the whole map with a composed graph — the reopened run's seed (§11.2, F36). It reads a
   * graphology graph (the composer's output) into the record maps verbatim, so a run switch REPLACES
   * the run before it rather than merging onto a stale one, and corpus labels ride the vocabulary.
   * Bumps `version` — the invalidation key every derived view (the text alternative, the drawer)
   * reads — in the same `set` that swaps the maps, so no view is left holding the run before it.
   */
  seedFromGraph: (graph: Graph, labels: string[]) => void
}

const edgeKey = (edge: GraphEdge): string => `${edge.source}|${edge.target}|${edge.label}`

/** A written entry as the store holds it: the backend's key is the id, its name and kind become the label and type. */
const asGraphNode = (node: WrittenNode, stances: Record<string, Stance>): GraphNode => {
  const entry: GraphNode = { id: node.key, label: node.name, type: node.label }
  const stance = stances[node.key]
  if (stance !== undefined) entry.stance = stance
  return entry
}

/** A written connection as the store holds it — endpoints and kind verbatim. */
const asGraphEdge = (link: WrittenLink): GraphEdge => ({ source: link.from, target: link.to, label: link.kind })

const upsertNodes = (existing: Record<string, GraphNode>, incoming: GraphNode[]): Record<string, GraphNode> => {
  const next = { ...existing }
  for (const node of incoming) next[node.id] = node
  return next
}

const upsertEdges = (existing: Record<string, GraphEdge>, incoming: GraphEdge[]): Record<string, GraphEdge> => {
  const next = { ...existing }
  for (const edge of incoming) next[edgeKey(edge)] = edge
  return next
}

/**
 * Add unseen labels, keeping first-seen order — so the vocabulary is append-only and the text
 * alternative's count of entity types never reshuffles on a reconnect.
 */
const mergeLabels = (incoming: string[], existing: string[]): string[] => {
  const seen = new Set(existing)
  const merged = [...existing]
  for (const label of incoming) {
    if (seen.has(label)) continue
    seen.add(label)
    merged.push(label)
  }
  return merged
}

/** A composed graph's node attributes back into a store entry — the composer's `nodeAttributes`, read backwards. */
const fromNodeAttributes = (id: string, attributes: Record<string, unknown>): GraphNode => {
  const node: GraphNode = { id, label: String(attributes.label), type: String(attributes.type) }
  if (attributes.kind !== undefined) node.kind = String(attributes.kind)
  if (attributes.stance !== undefined) node.stance = attributes.stance as Stance
  if (attributes.properties !== undefined) node.properties = attributes.properties as GraphNode['properties']
  return node
}

/** A composed graph's edge attributes back into a store entry — endpoints are the graph's, so only the rest rides here. */
const fromEdgeAttributes = (source: string, target: string, attributes: Record<string, unknown>): GraphEdge => {
  const edge: GraphEdge = { source, target, label: String(attributes.label) }
  if (attributes.properties !== undefined) edge.properties = attributes.properties as GraphEdge['properties']
  return edge
}

export const useGraphStore = create<GraphStoreState>((set) => ({
  nodes: {},
  edges: {},
  labels: [],
  version: 0,

  mergeDelta: (delta) =>
    set((state) => ({
      nodes: upsertNodes(state.nodes, delta.nodes),
      edges: upsertEdges(state.edges, delta.edges),
      version: state.version + 1,
    })),

  applySnapshot: (snapshot) =>
    set((state) => ({
      nodes: upsertNodes({}, snapshot.nodes),
      edges: upsertEdges({}, snapshot.edges),
      labels: mergeLabels(snapshot.labels, []),
      version: state.version + 1,
    })),

  mergeVocabulary: (incoming) => set((state) => ({ labels: mergeLabels(incoming, state.labels) })),

  mergeExpert: (expert) =>
    set((state) => ({
      nodes: upsertNodes(state.nodes, [{ id: expertKey(expert), label: expert.name, type: EXPERT_TYPE }]),
      version: state.version + 1,
    })),

  mergeOpinions: (written, links, stances = {}) =>
    set((state) => ({
      nodes: upsertNodes(
        state.nodes,
        written.map((node) => asGraphNode(node, stances)),
      ),
      edges: upsertEdges(state.edges, links.map(asGraphEdge)),
      version: state.version + 1,
    })),

  seedFromGraph: (graph, labels) =>
    set((state) => {
      const nodes: Record<string, GraphNode> = {}
      graph.forEachNode((id, attributes) => {
        nodes[id] = fromNodeAttributes(id, attributes)
      })
      const edges: Record<string, GraphEdge> = {}
      graph.forEachEdge((key, attributes, source, target) => {
        edges[key] = fromEdgeAttributes(source, target, attributes)
      })
      return { nodes, edges, labels: mergeLabels(labels, []), version: state.version + 1 }
    }),
}))
