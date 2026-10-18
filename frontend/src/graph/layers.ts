import { createContext, useContext } from 'react'
import { EXPERT_TYPE } from './graphStore'
import type { GraphEdge, GraphNode } from './graphStore'

/** The backend's label for an opinion entry a commit reports it wrote. The store keeps it verbatim
 *  as the entry's `type`, so it is the only signal the renderer has for the opinion layer. */
export const OPINION_TYPE = 'Opinion'

/** §9.1 The layers the pane's toggles filter. Three are kinds of entry; the fourth is every connection. */
export type LayerName = 'corpus' | 'experts' | 'opinions' | 'connections'

/** The toggle order, left to right (§9.1). */
export const LAYER_NAMES: readonly LayerName[] = ['corpus', 'experts', 'opinions', 'connections']

/** Every layer visible — the state the map opens in. */
export const ALL_LAYERS: ReadonlySet<LayerName> = new Set(LAYER_NAMES)

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

/**
 * The visible slice of the one store, by layer. With nothing hidden it hands the store's own maps
 * straight back, so the renderer's hot path pays nothing for the toggles being present.
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
  if (LAYER_NAMES.every((name) => layers.has(name))) return { nodes, edges }

  const visibleNodes: Record<string, GraphNode> = {}
  for (const node of Object.values(nodes)) if (layers.has(nodeLayer(node))) visibleNodes[node.id] = node

  return { nodes: visibleNodes, edges: layers.has('connections') ? edges : {} }
}

/**
 * The layers the canvas may draw. The pane provides it; the canvas consumes it. The default is
 * every layer, so a canvas rendered without a pane draws the whole map rather than nothing.
 */
export const LayerVisibilityContext = createContext<ReadonlySet<LayerName>>(ALL_LAYERS)

export const useVisibleLayers = (): ReadonlySet<LayerName> => useContext(LayerVisibilityContext)
