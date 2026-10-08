/* eslint-disable react-refresh/only-export-components -- this module deliberately exports its pure helpers (the gating predicates, the label drawing and syncGraph) so the unit test can drive them without a renderer. */
import { useCallback, useEffect, useMemo, useRef } from 'react'
import type { CSSProperties } from 'react'
import Graph from 'graphology'
import forceAtlas2 from 'graphology-layout-forceatlas2'
import { SigmaContainer, useSigma } from '@react-sigma/core'
import type { NodeLabelDrawingFunction } from 'sigma/rendering'
import { CheckCircle, CircleNotch, Warning, XCircle } from '@phosphor-icons/react'
import type { StreamStatus } from '../../api/ws'
import { useGraphStore } from '../../graph/graphStore'
import type { GraphEdge, GraphLabel, GraphNode } from '../../graph/graphStore'
import { useGraphStream } from '../../graph/useGraphStream'
import Skeleton from '../ui/Skeleton'

export interface GraphCanvasProps {
  datasetId: string
  jobId: string
}

const NODE_SIZE = 7
/** A node whose type has no label yet (vocabulary frame still in flight). */
const DEFAULT_NODE_COLOR = '#5b6270'
/** The canvas surface (ink-1000). Nodes are contrast-validated against it and the label halo paints in it. */
const STAGE_SURFACE = '#100e09'
/** How often the layout is allowed to run, ms — coalesces a burst of deltas into one settle. */
const LAYOUT_THROTTLE_MS = 180
const LAYOUT_ITERATIONS = 5
/** Growth (in nodes) past which the camera re-fits mid-stream — a modest structural step, not every delta. */
const FIT_STRUCTURAL_STEP = 25
/** Quiet period after the last delta before the camera re-fits, so a settling stream converges on a fitted view. */
const FIT_DEBOUNCE_MS = 350

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

/** Golden angle — successive radii spread seeds around the origin instead of stacking at (0, 0). */
const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5))

/**
 * A deterministic seed position for the n-th node. Sigma renders on a rAF ~16 ms after a delta while
 * the ForceAtlas2 settle is throttled to 180 ms, so a node added without x/y makes Sigma throw
 * "could not find a valid position". Every node therefore enters the graph already positioned; the
 * throttle then settles it. Existing nodes keep their settled position (seeds are only used on add).
 */
export function seedPosition(index: number): { x: number; y: number } {
  const radius = Math.sqrt(index + 1)
  const angle = index * GOLDEN_ANGLE
  return { x: Math.cos(angle) * radius, y: Math.sin(angle) * radius }
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

  for (const id of graph.nodes()) if (!(id in nodes)) graph.dropNode(id)

  Object.values(nodes).forEach((node, index) => {
    const color = colorByLabel.get(node.type) ?? DEFAULT_NODE_COLOR
    if (graph.hasNode(node.id)) graph.mergeNodeAttributes(node.id, { color })
    else graph.addNode(node.id, { color, size: NODE_SIZE, ...seedPosition(index) })
    // Drop the label outright above the ceiling — clearing any stale one left from when the graph was small.
    if (withNodeLabels) graph.setNodeAttribute(node.id, 'label', node.label)
    else graph.removeNodeAttribute(node.id, 'label')
  })

  const edgeKeys = new Set(Object.keys(edges))
  for (const key of graph.edges()) if (!edgeKeys.has(key)) graph.dropEdge(key)

  for (const [key, edge] of Object.entries(edges)) {
    // An edge can land before both endpoints; skip it — the next delta syncs it in.
    if (!graph.hasNode(edge.source) || !graph.hasNode(edge.target)) continue
    if (!graph.hasEdge(key)) graph.addEdgeWithKey(key, edge.source, edge.target)
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

/**
 * Re-centre the camera on the fitted view at meaningful moments — the first data, a snapshot reset
 * (the only path that shrinks the graph), a modest structural growth step, and once growth pauses.
 * Never on every delta, so the framing is not yanked around while the build streams; the debounced
 * fit lets a steady stream settle into a fitted view instead of freezing on the first frame's bounds.
 */
function FitCamera({ nodeCount }: { nodeCount: number }) {
  const sigma = useSigma()
  const previous = useRef(-1)
  const fitted = useRef(0)
  const timer = useRef<number | undefined>(undefined)

  useEffect(() => () => window.clearTimeout(timer.current), [])

  useEffect(() => {
    const fit = () => {
      fitted.current = nodeCount
      void sigma.getCamera().animatedReset()
    }
    const before = previous.current
    previous.current = nodeCount
    const firstData = before <= 0 && nodeCount > 0
    const snapshotReset = before > nodeCount
    const grewPastStep = nodeCount - fitted.current >= FIT_STRUCTURAL_STEP

    window.clearTimeout(timer.current)
    timer.current = undefined
    if (firstData || snapshotReset || grewPastStep) {
      fit()
      return
    }
    if (nodeCount > fitted.current) {
      // Small incremental growth: re-fit once it pauses, so a steady stream converges on a fitted view.
      timer.current = window.setTimeout(fit, FIT_DEBOUNCE_MS)
    }
  }, [sigma, nodeCount])

  return null
}

const LABEL_HALO_WIDTH = 3

/**
 * Draw a node label with a halo struck in the stage colour first, so an edge cannot cut the text.
 * The geometry mirrors Sigma's default (`x + size + 3`, `y + labelSize / 3`); only the halo is added.
 */
export const drawNodeLabel: NodeLabelDrawingFunction = (context, data, settings) => {
  if (!data.label) return
  const { labelSize, labelFont, labelWeight } = settings
  context.font = `${labelWeight} ${labelSize}px ${labelFont}`
  const color =
    typeof settings.labelColor.attribute === 'string'
      ? ((data as unknown as Record<string, unknown>)[settings.labelColor.attribute] as string | undefined) ??
        settings.labelColor.color ??
        '#000'
      : settings.labelColor.color ?? '#000'
  const x = data.x + data.size + 3
  const y = data.y + labelSize / 3
  context.lineJoin = 'round'
  context.lineWidth = LABEL_HALO_WIDTH
  context.strokeStyle = STAGE_SURFACE
  context.strokeText(data.label, x, y)
  context.fillStyle = color
  context.fillText(data.label, x, y)
}

// The Chamber is dark: sigma defaults to a white stage, black Arial labels and a rainbow-less rainbow
// of culled labels, so override all of it. Identity-stable (a module constant) so Sigma is never torn
// down on a delta. Edge labels are never rendered — they scatter illegible rotated text over the field.
const SIGMA_SETTINGS = {
  labelColor: { color: '#c9bfa9' }, // --color-paper-dim
  defaultEdgeColor: '#3a342b', // --color-ink-600
  labelFont: "'Public Sans Variable', 'Public Sans', system-ui, sans-serif",
  labelSize: 12,
  labelWeight: '500',
  labelRenderedSizeThreshold: 4,
  labelGridCellSize: 150,
  labelDensity: 1,
  renderEdgeLabels: false,
  defaultDrawNodeLabel: drawNodeLabel,
}
const CANVAS_STYLE = { '--sigma-background-color': 'transparent' } as CSSProperties

/** The legend — one colour swatch + type name per promoted label, using the nodes' own colours. */
function GraphLegend({ labels }: { labels: GraphLabel[] }) {
  if (labels.length === 0) return null
  return (
    <ul className="pointer-events-none absolute left-2 top-2 inline-flex max-w-[60%] flex-wrap gap-x-3 gap-y-1 rounded-[4px] border border-ink-700 bg-ink-1000/85 px-2.5 py-1.5">
      {labels.map((entry) => (
        <li key={entry.label} className="flex items-center gap-1.5 text-micro text-paper-dim">
          <span aria-hidden="true" className="inline-block size-2.5 rounded-[2px]" style={{ backgroundColor: entry.color }} />
          {entry.label}
        </li>
      ))}
    </ul>
  )
}

/** The phase overlay: a skeleton on the empty stage, an icon + word when the stream fails or ends. */
function GraphOverlay({ phase, message }: { phase: GraphStreamPhase; message: string | null }) {
  if (!message || phase === 'streaming') return null
  if (phase === 'waiting') {
    return (
      <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center gap-3">
        <CircleNotch size={22} className="animate-spin text-paper-faint" aria-hidden="true" />
        <p role="status" className="text-micro text-paper-mute">
          {message}
        </p>
        <div className="flex items-end gap-1.5" aria-hidden="true">
          <Skeleton className="h-2 w-10" />
          <Skeleton className="h-2 w-16" />
          <Skeleton className="h-2 w-12" />
        </div>
      </div>
    )
  }
  const failed = phase === 'failed'
  return (
    <div
      role="status"
      className={`pointer-events-none absolute inset-x-0 bottom-0 flex items-center gap-2 border-t bg-ink-1000/90 px-3 py-2 ${
        failed ? 'border-critical/40' : 'border-ink-700'
      }`}
    >
      {failed ? (
        <XCircle size={16} className="shrink-0 text-critical" aria-hidden="true" />
      ) : (
        <CheckCircle size={16} className="shrink-0 text-paper-dim" aria-hidden="true" />
      )}
      <p className={`text-micro ${failed ? 'text-critical' : 'text-paper-dim'}`}>{message}</p>
    </div>
  )
}

export default function GraphCanvas({ datasetId, jobId }: GraphCanvasProps) {
  const { status, done } = useGraphStream(jobId)
  const nodes = useGraphStore((s) => s.nodes)
  const edges = useGraphStore((s) => s.edges)
  const labels = useGraphStore((s) => s.labels)
  const nodeCount = Object.keys(nodes).length
  const notice = simplifiedViewNotice(nodeCount)
  // A new dataset is a new graph — a fresh instance so no stale nodes survive the switch.
  // eslint-disable-next-line react-hooks/exhaustive-deps -- datasetId is the identity trigger, read only as a reset key
  const graph = useMemo(() => new Graph(), [datasetId])

  const canvasLabel = graphAriaLabel(nodeCount, Object.keys(edges).length, labels.length)
  const phase = graphStreamPhase(nodeCount, status, done)
  const statusMessage = graphStatusMessage(nodeCount, status, done)
  const fallback = useMemo(
    () => graphTextFallback(Object.values(nodes), Object.values(edges), TEXT_FALLBACK_LIMIT),
    [nodes, edges],
  )

  return (
    <div className="relative h-[360px] overflow-hidden rounded-[6px] border border-ink-700 bg-ink-1000" style={CANVAS_STYLE}>
      <div role="img" aria-label={canvasLabel} className="h-full w-full">
        {/* The height chain is explicit here: the wrapper is a fixed box, this is full-height, and Sigma's
            own `.sigma-container` fills it — its sizing rule ships in @react-sigma/core/lib/style.css (imported in main.tsx). */}
        <SigmaContainer
          graph={graph}
          settings={SIGMA_SETTINGS}
          className="h-full w-full"
          style={{ width: '100%', height: '100%' }}
        >
          <LiveGraph graph={graph} />
          <FitCamera nodeCount={nodeCount} />
        </SigmaContainer>
      </div>
      <GraphLegend labels={labels} />
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
        <p
          role="status"
          className="pointer-events-none absolute right-2 top-2 flex items-center gap-1.5 rounded-[4px] border border-brass/40 bg-ink-1000/85 px-2 py-1 text-micro text-brass"
        >
          <Warning size={13} aria-hidden="true" />
          {notice}
        </p>
      )}
      <GraphOverlay phase={phase} message={statusMessage} />
    </div>
  )
}
