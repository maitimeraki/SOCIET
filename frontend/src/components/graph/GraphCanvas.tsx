import { useCallback, useEffect, useMemo, useRef } from 'react'
import type { CSSProperties } from 'react'
import Graph from 'graphology'
import forceAtlas2 from 'graphology-layout-forceatlas2'
import { SigmaContainer } from '@react-sigma/core'
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

/**
 * Mirror the store's nodes/edges/labels into `graph`, in place.
 *
 * Identity is the store's: a repeated node id updates the one node's attributes,
 * an edge keyed `source|target|label` updates the one edge. Nodes/edges the store
 * no longer holds (a snapshot reset) are dropped, so a reconnect cannot leave stale
 * elements behind. Node colour is the colour of its type's promoted label.
 */
// eslint-disable-next-line react-refresh/only-export-components -- the pure core the unit test drives directly
export function syncGraph(
  graph: Graph,
  nodes: Record<string, GraphNode>,
  edges: Record<string, GraphEdge>,
  labels: GraphLabel[],
): void {
  const colorByLabel = new Map(labels.map((entry) => [entry.label, entry.color]))

  for (const id of graph.nodes()) if (!(id in nodes)) graph.dropNode(id)

  for (const node of Object.values(nodes)) {
    const color = colorByLabel.get(node.type) ?? DEFAULT_NODE_COLOR
    if (graph.hasNode(node.id)) graph.mergeNodeAttributes(node.id, { label: node.label, color })
    else graph.addNode(node.id, { label: node.label, color, size: NODE_SIZE })
  }

  const edgeKeys = new Set(Object.keys(edges))
  for (const key of graph.edges()) if (!edgeKeys.has(key)) graph.dropEdge(key)

  for (const [key, edge] of Object.entries(edges)) {
    // An edge can land before both endpoints; skip it — the next delta syncs it in.
    if (!graph.hasNode(edge.source) || !graph.hasNode(edge.target)) continue
    if (graph.hasEdge(key)) graph.mergeEdgeAttributes(key, { label: edge.label })
    else graph.addEdgeWithKey(key, edge.source, edge.target, { label: edge.label })
  }
}

/** Coalesce a burst of syncs into at most one ForceAtlas2 settle per throttle window. */
function useThrottledLayout(graph: Graph): () => void {
  const timer = useRef<number | undefined>(undefined)

  useEffect(() => () => window.clearTimeout(timer.current), [])

  return useCallback(() => {
    if (timer.current !== undefined) return
    timer.current = window.setTimeout(() => {
      timer.current = undefined
      if (graph.order === 0) return
      forceAtlas2.assign(graph, { iterations: LAYOUT_ITERATIONS, settings: forceAtlas2.inferSettings(graph) })
    }, LAYOUT_THROTTLE_MS)
  }, [graph])
}

/** The store's only channel into the rendered graph — every delta re-syncs and re-settles. */
function LiveGraph({ graph }: { graph: Graph }) {
  const nodes = useGraphStore((s) => s.nodes)
  const edges = useGraphStore((s) => s.edges)
  const labels = useGraphStore((s) => s.labels)
  const runLayout = useThrottledLayout(graph)

  useEffect(() => {
    syncGraph(graph, nodes, edges, labels)
    runLayout()
  }, [graph, nodes, edges, labels, runLayout])

  return null
}

// The Chamber is dark: sigma defaults to a white stage and black labels, so override both.
const SIGMA_SETTINGS = {
  renderEdgeLabels: false,
  labelColor: { color: '#c9bfa9' }, // --color-paper-dim
  defaultEdgeColor: '#3a342b', // --color-ink-600
}
const CANVAS_STYLE = { '--sigma-background-color': 'transparent' } as CSSProperties

export default function GraphCanvas({ datasetId, jobId }: GraphCanvasProps) {
  const { status } = useGraphStream(jobId)
  // A new dataset is a new graph — a fresh instance so no stale nodes survive the switch.
  // eslint-disable-next-line react-hooks/exhaustive-deps -- datasetId is the identity trigger, read only as a reset key
  const graph = useMemo(() => new Graph(), [datasetId])

  return (
    <div className="relative h-[360px] overflow-hidden rounded-[6px] border border-ink-700 bg-ink-900" style={CANVAS_STYLE}>
      <SigmaContainer graph={graph} settings={SIGMA_SETTINGS} className="h-full w-full">
        <LiveGraph graph={graph} />
      </SigmaContainer>
      {status !== 'open' && (
        <p role="status" className="pointer-events-none absolute inset-x-0 bottom-2 text-center text-micro text-paper-mute">
          {status === 'closed' ? 'The live graph stream has ended.' : 'Connecting to the live graph…'}
        </p>
      )}
    </div>
  )
}
