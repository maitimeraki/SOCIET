/* eslint-disable react-refresh/only-export-components -- this module deliberately exports its pure helpers (the gating predicates, the label drawing and syncGraph) so the unit test can drive them without a renderer. */
import { useCallback, useEffect, useMemo, useRef } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import Graph from 'graphology'
import forceAtlas2 from 'graphology-layout-forceatlas2'
import { SigmaContainer, useSigma } from '@react-sigma/core'
import type { NodeLabelDrawingFunction } from 'sigma/rendering'
import { CheckCircle, CircleDashed, CircleNotch, CirclesThreePlus, UsersThree, Warning, XCircle } from '@phosphor-icons/react'
import type { StreamStatus } from '../../api/ws'
import { useGraphStore } from '../../graph/graphStore'
import type { GraphEdge, GraphNode } from '../../graph/graphStore'
import {
  CORPUS_COLOR,
  EXPERT_COLOR,
  POSITION_COLORS,
  POSITION_ORDER,
  UNPOSITIONED_COLOR,
  entryColor,
  useVisibleLayers,
  visibleSlice,
} from '../../graph/layers'
import { useSelectionStore } from '../../graph/selectionStore'
import type { MapSelection } from '../../graph/selectionStore'
import { useGraphStream } from '../../graph/useGraphStream'
import Skeleton from '../ui/Skeleton'
import StanceSymbol from '../common/StanceSymbol'

export interface GraphCanvasProps {
  datasetId: string
  /**
   * The build job whose stream fills the map. Absent for a run's own map: a debate run is a run, not
   * a build job, and its map is seeded from the run (`runStore.seedMap`) rather than streamed.
   */
  jobId?: string
}

const NODE_SIZE = 7

/**
 * Resolve a Survey token to a concrete colour. Sigma's WebGL colour path and the 2D label halo both
 * take a literal colour — neither reads a `var()` — so the values are read off the document root,
 * where `index.css` (`@theme`) defines them. The `document` guard keeps this module importable under
 * Vitest's Node environment; no test asserts a resolved value, so an empty string there is inert.
 */
const surveyColor = (token: string): string =>
  typeof document === 'undefined' ? '' : getComputedStyle(document.documentElement).getPropertyValue(token).trim()

/**
 * The ground the graph is plotted on — the container's own fill (§3.2, the dark plotting table).
 * Node marks are contrast-validated against it, and the label halo is struck in it, so an edge
 * cannot cut through the label text.
 */
const PLOT_SURFACE = surveyColor('--color-map-ground')
/** Node labels read luminous on the plot; edges take the muted plot ink so labels stay dominant. */
const LABEL_INK = surveyColor('--color-map-ink')
const EDGE_INK = surveyColor('--color-map-ink-2')
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
    : `showing simplified view (${nodeCount} entries)`
}

/** How many text-fallback lines are rendered — a graph can hold thousands of relations. */
export const TEXT_FALLBACK_LIMIT = 120

/** `1 entry` / `2 entries` — a count with its noun, pluralised (the plural is explicit for `entry`). */
function plural(count: number, singular: string, plural = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : plural}`
}

/** The `img` label for the graph region, carrying the live counts a screen reader can read. */
export function graphAriaLabel(nodeCount: number, edgeCount: number, labelCount: number): string {
  return `Your map: ${plural(nodeCount, 'entry', 'entries')}, ${plural(edgeCount, 'connection')}, ${plural(labelCount, 'entity type')}`
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
      return 'Waiting for the first section…'
    case 'failed':
      return 'The live map stream failed — the map stays as the last snapshot.'
    case 'ended':
      return 'The live map stream has ended.'
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
 * Mirror the store's nodes/edges into `graph`, in place.
 *
 * Identity is the store's: a repeated node id updates the one node's attributes,
 * an edge keyed `source|target|label` updates the one edge. Nodes/edges the store
 * no longer holds (a snapshot reset) are dropped, so a reconnect cannot leave stale
 * elements behind. Node colour is the entry's kind and — for an opinion — the position
 * the backend stored with it (§2.4, §9.2).
 *
 * Above the ceilings the `label` attribute is omitted (and any stale one cleared), so
 * Sigma draws no text at all for a graph too big to label.
 */
export function syncGraph(
  graph: Graph,
  nodes: Record<string, GraphNode>,
  edges: Record<string, GraphEdge>,
): void {
  const nodeCount = Object.keys(nodes).length
  const withNodeLabels = showNodeLabels(nodeCount)

  for (const id of graph.nodes()) if (!(id in nodes)) graph.dropNode(id)

  Object.values(nodes).forEach((node, index) => {
    const color = entryColor(node)
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

/** The store's only channel into the rendered graph — every delta re-syncs and re-settles, and the
 *  pane's layer toggles narrow the slice before it lands (a filter, never a rebuild). */
function LiveGraph({ graph }: { graph: Graph }) {
  const nodes = useGraphStore((s) => s.nodes)
  const edges = useGraphStore((s) => s.edges)
  const layers = useVisibleLayers()
  const runLayout = useThrottledLayout(graph, Object.keys(nodes).length)

  useEffect(() => {
    const visible = visibleSlice(nodes, edges, layers)
    syncGraph(graph, visible.nodes, visible.edges)
    runLayout()
  }, [graph, nodes, edges, layers, runLayout])

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
 * The map's one way in: a click on an entry or on a connection puts it in the selection channel,
 * which the details drawer reads. The canvas only writes the channel — it never draws the panel, so
 * the pane that hosts this canvas and the pane's own reading of the map share one way to open an
 * entry. What the selection resolves to lives in `NodeDetailsDrawer`.
 */
function SelectionWatch({ onPick }: { onPick: (selection: MapSelection) => void }) {
  const sigma = useSigma()
  useEffect(() => {
    const onNode = ({ node }: { node: string }) => onPick({ kind: 'entry', id: node })
    const onEdge = ({ edge }: { edge: string }) => onPick({ kind: 'connection', id: edge })
    sigma.on('clickNode', onNode)
    sigma.on('clickEdge', onEdge)
    return () => {
      sigma.off('clickNode', onNode)
      sigma.off('clickEdge', onEdge)
    }
  }, [sigma, onPick])
  return null
}

/**
 * Sigma listens to `window` resize only. A pane that mounts hidden (the minimised phone pane) or
 * gains its box later leaves the canvas at a stale size, so observe the container itself and let
 * Sigma re-read it. `sigma.resize()` is a no-op when the size is unchanged.
 */
function ContainerResizeWatch() {
  const sigma = useSigma()
  useEffect(() => {
    const observer = new ResizeObserver(() => sigma.resize())
    observer.observe(sigma.getContainer())
    return () => observer.disconnect()
  }, [sigma])
  return null
}

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
        LABEL_INK
      : settings.labelColor.color ?? LABEL_INK
  const x = data.x + data.size + 3
  const y = data.y + labelSize / 3
  context.lineJoin = 'round'
  context.lineWidth = LABEL_HALO_WIDTH
  context.strokeStyle = PLOT_SURFACE
  context.strokeText(data.label, x, y)
  context.fillStyle = color
  context.fillText(data.label, x, y)
}

// Sigma defaults to a white stage, black Arial labels and a rainbow of culled labels, so override all
// of it. Identity-stable (a module constant) so Sigma is never torn down on a delta. Edge labels are
// never rendered — they scatter illegible rotated text over the field. Repainted for the plotting
// table (§3.2): labels are luminous plot ink haloed in the dark ground, so an edge cannot cut the text.
export const SIGMA_SETTINGS = {
  // The minimised pane mounts this canvas into a hidden (zero-width) host; a 1×1 initial size is
  // the specified behaviour, and the ResizeObserver below gives it the real box when it opens.
  allowInvalidContainer: true,
  labelColor: { color: LABEL_INK },
  defaultEdgeColor: EDGE_INK,
  labelFont: "'Archivo Variable', Archivo, system-ui, sans-serif",
  labelSize: 12,
  labelWeight: '500',
  labelRenderedSizeThreshold: 4,
  labelGridCellSize: 150,
  labelDensity: 1,
  renderEdgeLabels: false,
  defaultDrawNodeLabel: drawNodeLabel,
}
const CANVAS_STYLE = { '--sigma-background-color': 'transparent' } as CSSProperties

/** One legend row: the mark, the hue and the word — a hue never stands alone (§2.5, §6). */
interface LegendRow {
  mark: ReactNode
  color: string
  word: string
}

/**
 * §2.4/§9.2 The map's key — every colour the canvas draws: the material's blue, an expert's white,
 * the four positions an opinion can hold in the spec's frozen order, and the neutral an opinion
 * draws in while its position is not recorded. Each row is **symbol + colour + word**, so no colour
 * is the only signal. The table is fixed because the colours are: the map encodes kind and position,
 * not entity type.
 */
export const LEGEND_ROWS: readonly LegendRow[] = [
  { mark: <CirclesThreePlus size={12} aria-hidden="true" />, color: CORPUS_COLOR, word: 'Corpus' },
  { mark: <UsersThree size={12} aria-hidden="true" />, color: EXPERT_COLOR, word: 'Experts' },
  ...POSITION_ORDER.map((stance) => ({
    mark: <StanceSymbol stance={stance} size={12} color={POSITION_COLORS[stance]} />,
    color: POSITION_COLORS[stance],
    word: stance,
  })),
  { mark: <CircleDashed size={12} aria-hidden="true" />, color: UNPOSITIONED_COLOR, word: 'No position' },
]

/** The map's key, ruled above the plot while the map holds anything, so it never covers an entry.
 *  `hasEntries` is false only when nothing is drawn. */
export function GraphLegend({ hasEntries }: { hasEntries: boolean }) {
  if (!hasEntries) return null
  return (
    <ul className="pointer-events-none flex shrink-0 flex-wrap gap-x-3 gap-y-1 border-b border-map-rule px-2.5 py-1.5">
      {LEGEND_ROWS.map((row) => (
        <li key={row.word} className="flex items-center gap-1.5 text-micro text-ink-3">
          <span aria-hidden="true" className="inline-flex items-center" style={{ color: row.color }}>
            {row.mark}
          </span>
          <span aria-hidden="true" className="inline-block size-2.5 rounded-[2px]" style={{ backgroundColor: row.color }} />
          {row.word}
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
        <CircleNotch size={22} className="animate-spin text-ink-3" aria-hidden="true" />
        <p role="status" className="text-micro text-ink-3">
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
      className={`pointer-events-none absolute inset-x-0 bottom-0 flex items-center gap-2 border-t bg-map-ground/90 px-3 py-2 ${
        failed ? 'border-map-rule' : 'border-ink-4'
      }`}
    >
      {failed ? (
        <XCircle size={16} className="shrink-0 text-ink-2" aria-hidden="true" />
      ) : (
        <CheckCircle size={16} className="shrink-0 text-ink-2" aria-hidden="true" />
      )}
      <p className="text-micro text-ink-2">{message}</p>
    </div>
  )
}

export default function GraphCanvas({ datasetId, jobId }: GraphCanvasProps) {
  const { status, done } = useGraphStream(jobId ?? '')
  const select = useSelectionStore((s) => s.open)
  // The map is the opener the details drawer returns focus to, so it takes focus as it opens one:
  // `tabIndex={-1}` keeps it out of the tab order, and a click does not paint a ring (`:focus-visible`).
  const root = useRef<HTMLDivElement>(null)
  const pick = useCallback(
    (selection: MapSelection) => {
      root.current?.focus()
      select(selection)
    },
    [select],
  )
  const nodes = useGraphStore((s) => s.nodes)
  const edges = useGraphStore((s) => s.edges)
  const labels = useGraphStore((s) => s.labels)
  const version = useGraphStore((s) => s.version)
  const nodeCount = Object.keys(nodes).length
  const notice = simplifiedViewNotice(nodeCount)
  // A new dataset is a new graph — a fresh instance so no stale nodes survive the switch.
  // `multi: true` is load-bearing: edge identity is `source|target|label`, so two chunks
  // routinely connect the same pair with different labels. A simple graph rejects the
  // second `addEdgeWithKey` with a UsageGraphError, which escapes the sync effect and
  // unmounts the whole page (blank frontend).
  // eslint-disable-next-line react-hooks/exhaustive-deps -- datasetId is the identity trigger, read only as a reset key
  const graph = useMemo(() => new Graph({ multi: true }), [datasetId])

  const canvasLabel = graphAriaLabel(nodeCount, Object.keys(edges).length, labels.length)
  // With no build job there is no stream to report on: the map is seeded from the run, so neither the
  // "waiting for the first chunk" skeleton nor the ended/failed notice belongs over it.
  const phase = jobId === undefined ? 'streaming' : graphStreamPhase(nodeCount, status, done)
  const statusMessage = jobId === undefined ? null : graphStatusMessage(nodeCount, status, done)
  // Keyed on the store's monotonic version, not the maps themselves: the derivation is O(edges), and
  // a re-render from any other slice (labels, selection, a whole-store re-sync) must not re-run it.
  // `version` bumps in the same `set` that swaps `nodes`/`edges`, so the closure is never stale.
  const fallback = useMemo(
    () => graphTextFallback(Object.values(nodes), Object.values(edges), TEXT_FALLBACK_LIMIT),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- version is the invalidation key for nodes/edges
    [version],
  )

  return (
    // The canvas fills its host: the pane owns the height, and the plot fills the box rather than
    // sitting in the top third of a fixed 360px with dead dark ground under it (§9.2).
    <div
      ref={root}
      tabIndex={-1}
      className="relative flex min-h-0 flex-1 flex-col overflow-hidden rounded-[6px] plot-ground"
      style={CANVAS_STYLE}
    >
      <GraphLegend hasEntries={nodeCount > 0} />
      <div role="img" aria-label={canvasLabel} className="relative min-h-0 flex-1">
        {/* The height chain is explicit here: this box is the flex item that grows, Sigma's own
            `.sigma-container` fills it — its sizing rule ships in @react-sigma/core/lib/style.css (imported in main.tsx). */}
        <SigmaContainer
          graph={graph}
          settings={SIGMA_SETTINGS}
          className="h-full w-full"
          style={{ width: '100%', height: '100%' }}
        >
          <LiveGraph graph={graph} />
          <FitCamera nodeCount={nodeCount} />
          <ContainerResizeWatch />
          <SelectionWatch onPick={pick} />
        </SigmaContainer>
        {notice && (
          <p
            role="status"
            className="pointer-events-none absolute right-2 top-2 flex items-center gap-1.5 rounded-[4px] border border-warn/40 bg-map-ground-2 px-2 py-1 text-micro text-ink-2"
          >
            <Warning size={13} className="text-warn" aria-hidden="true" />
            {notice}
          </p>
        )}
        <GraphOverlay phase={phase} message={statusMessage} />
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
    </div>
  )
}
