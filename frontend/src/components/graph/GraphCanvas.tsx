/* eslint-disable react-refresh/only-export-components -- this module deliberately exports its pure helpers (the gating predicates and syncGraph) so the unit test can drive them without a renderer. */
import { useCallback, useEffect, useMemo, useRef } from 'react'
import type { CSSProperties } from 'react'
import Graph from 'graphology'
import forceAtlas2 from 'graphology-layout-forceatlas2'
import { SigmaContainer } from '@react-sigma/core'
import type { StreamStatus } from '../../api/ws'
import { useGraphStore } from '../../graph/graphStore'
import type { GraphEdge, GraphLabel, GraphNode } from '../../graph/graphStore'
import { useGraphStream } from '../../graph/useGraphStream'

export interface GraphCanvasProps {
  datasetId: string
  jobId: string
}

const NODE_SIZE = 6
/** A node whose type has no label yet (vocabulary frame still in flight). */
const DEFAULT_NODE_COLOR = '#5b6270'
/** How often the layout is allowed to run, ms — coalesces a burst of deltas into one settle. */
const LAYOUT_THROTTLE_MS = 180
const LAYOUT_ITERATIONS = 5

// Ceilings past which the renderer sheds work rather than freezes the browser.
export const MAX_ANIMATED_NODES = 1500
export const MAX_LABELLED_NODES = 400

// ponytail: freeze layout above the ceiling; upgrade to label-clustering (graphology communities) if users need to explore huge graphs.
/** The force layout may settle only while the graph is at or below the animation ceiling. */
export function shouldAnimateLayout(nodeCount: number): boolean {
  return nodeCount <= MAX_ANIMATED_NODES
}

/** Node labels are the most expensive text — drop them well below the layout ceiling. */
export function showNodeLabels(nodeCount: number): boolean {
  return nodeCount <= MAX_LABELLED_NODES
}

/** Edge labels are dropped at the same ceiling that freezes the layout. */
export function showEdgeLabels(nodeCount: number): boolean {
  return nodeCount <= MAX_ANIMATED_NODES
}

/** The notice shown while the view is simplified, else null. */
export function simplifiedViewNotice(nodeCount: number): string | null {
  return shouldAnimateLayout(nodeCount) && showNodeLabels(nodeCount)
    ? null
    : `showing simplified view (${nodeCount} nodes)`
}

/** How many text-fallback lines are rendered — a graph can hold thousands of relations. */
export const TEXT_FALLBACK_LIMIT = 120

/** `1 node` / `2 nodes` — a count with its noun, pluralised. */
function plural(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? '' : 's'}`
}

/** The `img` label for the graph region, carrying the live counts a screen reader can read. */
export function graphAriaLabel(nodeCount: number, edgeCount: number, labelCount: number): string {
  return `Knowledge graph: ${plural(nodeCount, 'node')}, ${plural(edgeCount, 'edge')}, ${plural(labelCount, 'entity type')}`
}

export type GraphStreamPhase = 'waiting' | 'streaming' | 'failed' | 'ended'

/**
 * Which overlay the live graph is in: `waiting` until the first node arrives, `failed` when the
 * socket closed before `done`, `ended` on a `done` frame, else `streaming` (no overlay).
 */
export function graphStreamPhase(nodeCount: number, status: StreamStatus, done: boolean): GraphStreamPhase {
  if (done) return 'ended'
  if (status === 'closed') return 'failed'
  return nodeCount === 0 ? 'waiting' : 'streaming'
}

/** The overlay text for the current phase, or null while the graph is streaming normally. */
export function graphStatusMessage(nodeCount: number, status: StreamStatus, done: boolean): string | null {
  switch (graphStreamPhase(nodeCount, status, done)) {
    case 'waiting':
      return 'Waiting for the first chunk…'
    case 'failed':
      return 'The live graph stream failed — the graph stays as the last snapshot.'
    case 'ended':
      return 'The live graph stream has ended.'
    case 'streaming':
      return null
  }
}

/**
 * The graph's content as text: one line per relation (`Source —REL→ Target`), then the entities no
 * relation mentions. Capped at `limit` lines (a graph can hold thousands); `omitted` counts the rest.
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

/**
 * Mirror the store's nodes/edges/labels into `graph`, in place.
 *
 * Identity is the store's: a repeated node id updates the one node's attributes,
 * an edge keyed `source|target|label` updates the one edge. Nodes/edges the store
 * no longer holds (a snapshot reset) are dropped, so a reconnect cannot leave stale
 * elements behind. Node colour is the colour of its type's promoted label.
 *
 * Above the ceilings the `label` attribute is omitted (and any stale one cleared), so
 * Sigma draws no text at all for a graph too big to label.
 */
export function syncGraph(
  graph: Graph,
  nodes: Record<string, GraphNode>,
  edges: Record<string, GraphEdge>,
  labels: GraphLabel[],
): void {
  const colorByLabel = new Map(labels.map((entry) => [entry.label, entry.color]))
  const nodeCount = Object.keys(nodes).length
  const withNodeLabels = showNodeLabels(nodeCount)
  const withEdgeLabels = showEdgeLabels(nodeCount)

  for (const id of graph.nodes()) if (!(id in nodes)) graph.dropNode(id)

  for (const node of Object.values(nodes)) {
    const color = colorByLabel.get(node.type) ?? DEFAULT_NODE_COLOR
    if (graph.hasNode(node.id)) graph.mergeNodeAttributes(node.id, { color })
    else graph.addNode(node.id, { color, size: NODE_SIZE })
    // Drop the label outright above the ceiling — clearing any stale one left from when the graph was small.
    if (withNodeLabels) graph.setNodeAttribute(node.id, 'label', node.label)
    else graph.removeNodeAttribute(node.id, 'label')
  }

  const edgeKeys = new Set(Object.keys(edges))
  for (const key of graph.edges()) if (!edgeKeys.has(key)) graph.dropEdge(key)

  for (const [key, edge] of Object.entries(edges)) {
    // An edge can land before both endpoints; skip it — the next delta syncs it in.
    if (!graph.hasNode(edge.source) || !graph.hasNode(edge.target)) continue
    if (!graph.hasEdge(key)) graph.addEdgeWithKey(key, edge.source, edge.target)
    if (withEdgeLabels) graph.mergeEdgeAttributes(key, { label: edge.label })
    else graph.removeEdgeAttribute(key, 'label')
  }
}

/** Coalesce a burst of syncs into at most one ForceAtlas2 settle per throttle window. */
function useThrottledLayout(graph: Graph, nodeCount: number): () => void {
  const timer = useRef<number | undefined>(undefined)

  useEffect(() => () => window.clearTimeout(timer.current), [])

  return useCallback(() => {
    // Above the ceiling the layout is frozen: never schedule a settle, so the loop is never started.
    if (!shouldAnimateLayout(nodeCount)) return
    if (timer.current !== undefined) return
    timer.current = window.setTimeout(() => {
      timer.current = undefined
      if (graph.order === 0) return
      forceAtlas2.assign(graph, { iterations: LAYOUT_ITERATIONS, settings: forceAtlas2.inferSettings(graph) })
    }, LAYOUT_THROTTLE_MS)
  }, [graph, nodeCount])
}

/** The store's only channel into the rendered graph — every delta re-syncs and re-settles. */
function LiveGraph({ graph }: { graph: Graph }) {
  const nodes = useGraphStore((s) => s.nodes)
  const edges = useGraphStore((s) => s.edges)
  const labels = useGraphStore((s) => s.labels)
  const runLayout = useThrottledLayout(graph, Object.keys(nodes).length)

  useEffect(() => {
    syncGraph(graph, nodes, edges, labels)
    runLayout()
  }, [graph, nodes, edges, labels, runLayout])

  return null
}

// The Chamber is dark: sigma defaults to a white stage and black labels, so override both.
const SIGMA_SETTINGS = {
  labelColor: { color: '#c9bfa9' }, // --color-paper-dim
  defaultEdgeColor: '#3a342b', // --color-ink-600
}
const CANVAS_STYLE = { '--sigma-background-color': 'transparent' } as CSSProperties

export default function GraphCanvas({ datasetId, jobId }: GraphCanvasProps) {
  const { status, done } = useGraphStream(jobId)
  const nodes = useGraphStore((s) => s.nodes)
  const edges = useGraphStore((s) => s.edges)
  const labels = useGraphStore((s) => s.labels)
  const nodeCount = Object.keys(nodes).length
  const notice = simplifiedViewNotice(nodeCount)
  // Edge labels are the degradation lever at the animation ceiling. Keep the settings object
  // identity-stable (only the boolean flips) so Sigma is not torn down on every delta.
  const renderEdgeLabels = showEdgeLabels(nodeCount)
  const settings = useMemo(() => ({ ...SIGMA_SETTINGS, renderEdgeLabels }), [renderEdgeLabels])
  // A new dataset is a new graph — a fresh instance so no stale nodes survive the switch.
  // eslint-disable-next-line react-hooks/exhaustive-deps -- datasetId is the identity trigger, read only as a reset key
  const graph = useMemo(() => new Graph(), [datasetId])

  const canvasLabel = graphAriaLabel(nodeCount, Object.keys(edges).length, labels.length)
  const statusMessage = graphStatusMessage(nodeCount, status, done)
  const fallback = useMemo(
    () => graphTextFallback(Object.values(nodes), Object.values(edges), TEXT_FALLBACK_LIMIT),
    [nodes, edges],
  )

  return (
    <div className="relative h-[360px] overflow-hidden rounded-[6px] border border-ink-700 bg-ink-900" style={CANVAS_STYLE}>
      <div role="img" aria-label={canvasLabel} className="h-full w-full">
        <SigmaContainer graph={graph} settings={settings} className="h-full w-full">
          <LiveGraph graph={graph} />
        </SigmaContainer>
      </div>
      {/* The counts grow on every delta; role="img" alone is read on demand, so mirror the label into a live region. */}
      <div aria-live="polite" className="sr-only">
        {canvasLabel}
      </div>
      {/* The canvas is pixels — a non-visual user reads the graph from this list instead. */}
      {fallback.lines.length > 0 && (
        <ul className="sr-only">
          {fallback.lines.map((line, index) => (
            <li key={index}>{line}</li>
          ))}
          {fallback.omitted > 0 && <li>and {fallback.omitted} more</li>}
        </ul>
      )}
      {notice && (
        <p role="status" className="pointer-events-none absolute inset-x-0 top-2 text-center text-micro text-paper-mute">
          {notice}
        </p>
      )}
      {statusMessage && (
        <p role="status" className="pointer-events-none absolute inset-x-0 bottom-2 text-center text-micro text-paper-mute">
          {statusMessage}
        </p>
      )}
    </div>
  )
}
