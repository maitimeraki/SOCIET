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

/**
 * A fixed categorical palette for entity types — hand-picked, mutually distinct, and in a format
 * Sigma's WebGL colour path parses (hex; it draws black on `hsl()`). Every entry clears the spec's
 * ≥3:1 mark floor against the canvas surface (`#100e09`); validated min pairwise ΔE 29.7 (normal) /
 * 9.8 (deuteranopia), min contrast 7.14:1 — comfortably better than the stance palette's own residual.
 * Colours are keyed off the label SET (labels taken in sorted order), so a given set maps to the same
 * colours whatever order it arrives in — a reconnect or reload that replays the labels differently
 * cannot recolour the graph.
 */
export const LABEL_PALETTE = [
  '#45C2BE', // teal
  '#7C9CE8', // azure
  '#C88CE2', // violet
  '#EC7F9C', // rose
  '#EC8B52', // coral
  '#D6C055', // gold
  '#88CC68', // green
] as const

// ponytail: a 7-colour palette wraps past the 7th label (two types can share a hue); extend the array if a corpus ever promotes more.
/** The palette colour for a label at `index` (its slot in the sorted label set). */
export const labelColor = (index: number): string => LABEL_PALETTE[index % LABEL_PALETTE.length]

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

/**
 * Add unseen labels (the array keeps first-seen order, so the legend stays append-only), but derive
 * every colour from the SET: labels taken in sorted order take palette slots 0..n-1. The mapping is
 * therefore a pure function of the set — the same labels in any arrival order, across an
 * `applySnapshot` reset or a reload, land on the same colours.
 */
const mergeLabels = (incoming: string[], existing: GraphLabel[]): GraphLabel[] => {
  const byLabel = new Map(existing.map((entry) => [entry.label, entry]))
  for (const label of incoming) if (!byLabel.has(label)) byLabel.set(label, { label, color: '' })
  const colorByName = new Map([...byLabel.keys()].sort().map((label, index) => [label, labelColor(index)]))
  return [...byLabel.values()].map((entry) => ({ label: entry.label, color: colorByName.get(entry.label) ?? entry.color }))
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
