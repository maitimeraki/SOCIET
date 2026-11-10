import type { GraphEdge, GraphNode } from './graphStore'

/** How many text-fallback lines are rendered — a graph can hold thousands of relations. */
export const TEXT_FALLBACK_LIMIT = 120

/**
 * The graph's content as text: one line per relation (`Source —REL→ Target`), then the entities no
 * relation mentions. Capped at `limit` lines (a graph can hold thousands); `omitted` counts the rest.
 *
 * Pure and DOM-free, so both owners of the map's text alternative can read it without a renderer:
 * the canvas region (its own reading of the plot) and the workspace pane's counts strip (the reading
 * that must survive the map being minimised).
 */
export function graphTextFallback(
  nodes: GraphNode[],
  edges: GraphEdge[],
  limit: number,
): { lines: string[]; omitted: number } {
  const labelById = new Map(nodes.map((node) => [node.id, node.label]))
  const connected = new Set<string>()
  const lines: string[] = []
  let omitted = 0
  const collect = (line: string) => {
    if (lines.length < limit) lines.push(line)
    else omitted++
  }
  for (const edge of edges) {
    const source = labelById.get(edge.source)
    const target = labelById.get(edge.target)
    if (source === undefined || target === undefined) continue // an endpoint not yet in the store
    connected.add(edge.source)
    connected.add(edge.target)
    collect(`${source} —${edge.label}→ ${target}`)
  }
  for (const node of nodes) if (!connected.has(node.id)) collect(`${node.label} (${node.type})`)
  return { lines, omitted }
}
