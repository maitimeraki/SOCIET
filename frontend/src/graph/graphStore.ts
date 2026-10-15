import { create } from 'zustand'

/** A graph entity. Identity is `id` — the same entity in two chunks is ONE node. */
export interface GraphNode {
  id: string
  label: string
  type: string
  /** The extracted type, as the delta frames it (`type` is the stored label). */
  kind?: string
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
  /**
   * Monotonic count of node/edge merges. A cheap primitive invalidation key for derived views, so
   * they key on "the graph changed" without deep-comparing (or holding a reference to) the maps.
   * Labels are vocabulary, not content, so `mergeVocabulary` does not bump it.
   */
  version: number
  mergeDelta: (delta: GraphDelta) => void
  applySnapshot: (snapshot: GraphSnapshot) => void
  mergeVocabulary: (labels: string[]) => void
}

/**
 * The territory's categorical legend palette — one hue per entity type, hand-picked and mutually
 * distinct, in a format Sigma's WebGL colour path parses (hex; it draws black on anything it cannot
 * read). This is a data encoding the graph module owns, not styling: it feeds Sigma's parser and the
 * legend swatches directly, so it stays literal here rather than becoming a CSS custom property —
 * the store also loads under Vitest's Node environment, where there is no document to resolve a
 * `var()` against, and a palette that resolved to empty strings there would make the
 * arrival-order-invariance test below pass vacuously.
 *
 * Repainted for the Survey sheet (addendum §5). The incumbent set was validated against the dark
 * Chamber surface; every one of those hues measured 1.44–2.14:1 on the light sheet `--survey-paper`
 * and failed SC 1.4.11's 3:1 non-text floor. These clear it, measured on the sheet:
 * 5.57 · 5.11 · 5.30 · 4.86 · 4.21 · 4.47 · 4.87. The map's *meaning* hues (the four stance tokens,
 * datum, route, brass) are deliberately not reused: an entity type is not a stance.
 *
 * Colours are keyed off the label SET (labels taken in sorted order), so a given set maps to the same
 * colours whatever order it arrives in — a reconnect or reload that replays the labels differently
 * cannot recolour the graph.
 */
export const LABEL_PALETTE = [
  '#17635f', // teal
  '#2b5ea6', // azure
  '#6e4a9e', // violet
  '#a83a5b', // rose
  '#a8541f', // coral
  '#7e6410', // gold
  '#4a6b22', // green
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
}))
