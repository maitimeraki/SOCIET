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
 * The territory's categorical legend palette — one NAMED hue per entity type. R33: the graph's
 * categorical palette is data encoding, not theme colour, so it stays literal rather than becoming a
 * CSS custom property. It feeds Sigma's WebGL colour path and the legend swatches directly, in a
 * format Sigma parses (hex; it draws black on anything it cannot read). It stays literal because the
 * store also loads under Vitest's Node environment, where there is no document to resolve a `var()`
 * against, and a palette that resolved to empty strings there would make the arrival-order-invariance
 * test below pass vacuously.
 *
 * The table's KEYS are the legend entries — every hue has a name, so none is an anonymous hex (DSPEC
 * §3: a hue with no legend entry does not exist). `Legend` (components/common/Legend.tsx) renders this
 * same table, so the palette and its legend share one source.
 *
 * Repainted for the Survey sheet (addendum §5). The incumbent set was validated against the dark
 * Chamber surface; every one of those hues measured 1.44–2.14:1 on the light sheet `--survey-paper`
 * and failed SC 1.4.11's 3:1 non-text floor. These clear it on the sheet:
 * 5.57 · 5.11 · 5.30 · 4.86 · 4.21 · 4.47 · 4.87. On the plotting table (`--plot-ground` #14150F)
 * only coral (3.46) and gold (3.25) clear 3:1 — teal 2.61 · azure 2.85 · violet 2.74 · rose 2.99 ·
 * green 2.99 do not, so a node of those hues cannot carry a mark on the dark plot without a
 * non-colour cue (its legend symbol and label). The map's *meaning* hues (the four stance tokens,
 * datum, route, brass) are deliberately not reused: an entity type is not a stance.
 *
 * Colours are keyed off the label SET (labels taken in sorted order), so a given set maps to the same
 * colours whatever order it arrives in — a reconnect or reload that replays the labels differently
 * cannot recolour the graph.
 */
export const GRAPH_PALETTE = {
  teal: '#17635f',
  azure: '#2b5ea6',
  violet: '#6e4a9e',
  rose: '#a83a5b',
  coral: '#a8541f',
  gold: '#7e6410',
  green: '#4a6b22',
} as const

/** The palette in slot order — `Object.values` preserves insertion order, so slots are stable. */
const PALETTE_SLOTS = Object.values(GRAPH_PALETTE)

// ponytail: a 7-colour palette wraps past the 7th label (two types can share a hue); extend the table if a corpus ever promotes more.
/** The palette colour for a label at `index` (its slot in the sorted label set). */
export const labelColor = (index: number): string => PALETTE_SLOTS[index % PALETTE_SLOTS.length]

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
