import { createContext, useContext } from 'react'
import { EXPERT_TYPE } from './graphStore'
import type { GraphEdge, GraphNode } from './graphStore'
import type { Stance } from '../run/events'

/** The backend's label for an opinion entry a commit reports it wrote. The store keeps it verbatim
 *  as the entry's `type`, so it is the only signal the renderer has for the opinion layer. */
export const OPINION_TYPE = 'Opinion'

/** §9.1 The layers the pane's toggles filter. Three are kinds of entry; the fourth is every connection. */
export type LayerName = 'corpus' | 'experts' | 'opinions' | 'connections'

/** The toggle order, left to right (§9.1). */
export const LAYER_NAMES: readonly LayerName[] = ['corpus', 'experts', 'opinions', 'connections']

/** The three layers that filter ENTRIES — every layer but the connections (§9.1). */
const ENTRY_LAYERS: readonly LayerName[] = LAYER_NAMES.filter((name) => name !== 'connections')

/** Every layer visible — the state the map opens in. */
export const ALL_LAYERS: ReadonlySet<LayerName> = new Set(LAYER_NAMES)

/**
 * §9.1's glyph per layer — a shape beside the word, so no control leans on its hue alone. The pane
 * draws one per toggle; the entry-details drawer draws the same glyph for the entry's kind, so an
 * entry read on the map and the same entry read in the drawer carry one mark.
 */
export const LAYER_GLYPHS: Record<LayerName, string> = {
  corpus: '⊕',
  experts: '◉',
  opinions: '⊗',
  connections: '—',
}

/**
 * Which layer an entry belongs to: the two the debate stream seats (an expert, an opinion), or the
 * material itself. An entry the backend wrote under a kind we do not know reads as material rather
 * than vanishing — an unknown kind is kept, never dropped (see `composeRunGraph`).
 */
export function nodeLayer(node: GraphNode): LayerName {
  if (node.type === EXPERT_TYPE) return 'experts'
  if (node.type === OPINION_TYPE) return 'opinions'
  return 'corpus'
}

/** §2.4 The material's own colour — one blue for every entry the reading wrote. */
export const CORPUS_COLOR = '#3B82F6'

/** §2.4 An expert's luminous white, held luminous against the dark ground. */
export const EXPERT_COLOR = '#E2E8F0'

/**
 * §2.4/§2.5 The four positions' colours on the dark ground, in the spec's frozen order —
 * POSITIVE, NEUTRAL, AMBIVALENT, NEGATIVE. Literal hex, not a `var()`: Sigma's WebGL colour path
 * draws black on anything it cannot parse, and the store loads under Vitest's Node environment,
 * where there is no document to resolve a token against.
 */
export const POSITION_COLORS: Record<Stance, string> = {
  POSITIVE: '#4ADE80',
  NEUTRAL: '#94A3B8',
  AMBIVALENT: '#FBBF24',
  NEGATIVE: '#F87171',
}

/** The frozen order the legend draws the four positions in (§2.5). */
export const POSITION_ORDER: readonly Stance[] = ['POSITIVE', 'NEUTRAL', 'AMBIVALENT', 'NEGATIVE']

/** §2.5 The shape each position carries, so its colour is never the only signal. */
export const POSITION_GLYPHS: Record<Stance, string> = {
  POSITIVE: '●',
  NEUTRAL: '□',
  AMBIVALENT: '◇',
  NEGATIVE: '⊗',
}

/**
 * The colour an opinion draws in when the stored events carry no position for it — a stream that
 * dropped a pass's turns, say. It is the neutral family's darker step (`--color-ink-3`, and the
 * NEUTRAL mark on the light ground), chosen so it clears the 3:1 graphical floor on the map ground
 * (3.93:1) while reading as none of the four position hues. It claims no position; it never guesses
 * one (D7).
 */
export const UNPOSITIONED_COLOR = '#64748B'

/** The glyph an entry of an unresolved position carries in the legend. */
export const UNPOSITIONED_GLYPH = '◌'

/**
 * The colour an entry draws in (§2.4, §9.2): the material's blue, an expert's luminous white, or —
 * for an opinion — the colour of the position the backend stored with it. An opinion the stored
 * events give no position draws in the unpositioned neutral, never a guess.
 */
export function entryColor(node: GraphNode): string {
  const layer = nodeLayer(node)
  if (layer === 'experts') return EXPERT_COLOR
  if (layer === 'opinions') return node.stance ? POSITION_COLORS[node.stance] : UNPOSITIONED_COLOR
  return CORPUS_COLOR
}

/**
 * The visible slice of the one store, by layer. With every entry layer visible it hands the store's
 * own entry map straight back — hiding only the connections narrows the relations, so it must not
 * rebuild (and copy) the entries on every delta (F32).
 *
 * Hiding an entry's layer is enough to take its connections with it: the renderer seats no
 * connection without both its endpoints, so it drops an orphaned one for free. Only the connections
 * toggle needs the edge map walked, so a slice costs one pass over the entries, not the relations.
 */
export function visibleSlice(
  nodes: Record<string, GraphNode>,
  edges: Record<string, GraphEdge>,
  layers: ReadonlySet<LayerName>,
): { nodes: Record<string, GraphNode>; edges: Record<string, GraphEdge> } {
  const visibleEdges = layers.has('connections') ? edges : {}
  // No entry layer hidden: hand the store's own entry map back, so hiding only the connections —
  // which narrows the relations, not the entries — never rebuilds it on a delta (F32).
  if (ENTRY_LAYERS.every((name) => layers.has(name))) return { nodes, edges: visibleEdges }

  const visibleNodes: Record<string, GraphNode> = {}
  for (const node of Object.values(nodes)) if (layers.has(nodeLayer(node))) visibleNodes[node.id] = node

  return { nodes: visibleNodes, edges: visibleEdges }
}

/**
 * The layers the canvas may draw. The pane provides it; the canvas consumes it. The default is
 * every layer, so a canvas rendered without a pane draws the whole map rather than nothing.
 */
export const LayerVisibilityContext = createContext<ReadonlySet<LayerName>>(ALL_LAYERS)

export const useVisibleLayers = (): ReadonlySet<LayerName> => useContext(LayerVisibilityContext)
