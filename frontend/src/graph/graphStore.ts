import { create } from 'zustand'

/** A graph entity. Identity is `id` — the same entity in two chunks is ONE node. */
export interface GraphNode {
  id: string
  label: string
  type: string
}

/** A graph relation. Identity is `source|target|label`. */
export interface GraphEdge {
  source: string
  target: string
  label: string
}

/** A legend label (an entity type) with its assigned colour. */
export interface GraphLabel {
  label: string
  color: string
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

interface GraphStoreState {
  nodes: Record<string, GraphNode>
  edges: Record<string, GraphEdge>
  labels: GraphLabel[]
  mergeDelta: (delta: GraphDelta) => void
  applySnapshot: (snapshot: GraphSnapshot) => void
  mergeVocabulary: (labels: string[]) => void
}

/** Stable colour per label: a pure hash of the label, so it survives resets, reorders and reloads. */
// ponytail: hash%360 can collide two labels onto one hue; swap for a golden-angle counter if the legend ever needs hard distinctness.
const labelColor = (label: string): string => {
  let hash = 0
  for (let i = 0; i < label.length; i++) hash = (hash * 31 + label.charCodeAt(i)) | 0
  return `hsl(${Math.abs(hash) % 360} 70% 55%)`
}

const edgeKey = (edge: GraphEdge): string => `${edge.source}|${edge.target}|${edge.label}`

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

/** Add unseen labels (keeping any existing entry's colour), preserving first-seen order. */
const mergeLabels = (incoming: string[], existing: GraphLabel[]): GraphLabel[] => {
  const byLabel = new Map(existing.map((entry) => [entry.label, entry]))
  for (const label of incoming) if (!byLabel.has(label)) byLabel.set(label, { label, color: labelColor(label) })
  return [...byLabel.values()]
}

export const useGraphStore = create<GraphStoreState>((set) => ({
  nodes: {},
  edges: {},
  labels: [],

  mergeDelta: (delta) =>
    set((state) => ({
      nodes: upsertNodes(state.nodes, delta.nodes),
      edges: upsertEdges(state.edges, delta.edges),
    })),

  applySnapshot: (snapshot) =>
    set(() => ({
      nodes: upsertNodes({}, snapshot.nodes),
      edges: upsertEdges({}, snapshot.edges),
      labels: mergeLabels(snapshot.labels, []),
    })),

  mergeVocabulary: (incoming) => set((state) => ({ labels: mergeLabels(incoming, state.labels) })),
}))
