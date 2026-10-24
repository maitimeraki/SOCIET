/* eslint-disable react-refresh/only-export-components -- this module deliberately exports its pure helpers (the gating predicates, the label drawing and syncGraph) so the unit test can drive them without a renderer. */
import { useCallback, useEffect, useMemo, useRef } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import Graph from 'graphology'
import type { Attributes } from 'graphology-types'
import forceAtlas2 from 'graphology-layout-forceatlas2'
import { SigmaContainer, useSigma } from '@react-sigma/core'
import type { NodeHoverDrawingFunction, NodeLabelDrawingFunction } from 'sigma/rendering'
import { CheckCircle, CircleDashed, CircleNotch, CirclesThreePlus, UsersThree, Warning, XCircle } from '@phosphor-icons/react'
import type { StreamStatus } from '../../api/ws'
import { useGraphStore } from '../../graph/graphStore'
import type { GraphEdge, GraphNode } from '../../graph/graphStore'
import Legend from '../common/Legend'
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
import { PositionGlyph } from '../ui/PositionMark'

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
 * The ramp's two stops, read off the document root (§2.3). The plot ground is not one colour: the
 * `.plot-ground` pane paints a radial ramp from the lit centre (`map-ground-2`) at 50% 0% out to
 * the deep floor (`map-ground`) at 72%, and the canvas is a window onto that ramp. The halo is
 * sampled from the same box at the label's position (offset by the canvas's place in the pane), so
 * it is the paint under the text, not a flat tone that matches neither end.
 */
const RAMP_LIT = surveyColor('--color-map-ground-2')
const RAMP_DEEP = surveyColor('--color-map-ground')
/** Node labels read luminous on the plot; edges take the muted plot ink so labels stay dominant. */
const LABEL_INK = surveyColor('--color-map-ink')
const EDGE_INK = surveyColor('--color-map-ink-2')
/** The hover ring's ink — the accent rebound for the dark ground (§2.3). */
const RING_INK = surveyColor('--color-map-accent')
/** The quiet ink a dimmed entry blends toward — still 4.6:1 or better on the lit end of the ramp. */
const DIM_INK = surveyColor('--color-map-ink-2')
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

/* ── The ramp (§12.4 Wave 2) ──────────────────────────────────────────────────────────────────── */

/** The ramp's geometry, verbatim from `--gradient-map`: `radial-gradient(120% 100% at 50% 0%, …)`. */
const RAMP_WIDTH = 1.2
const RAMP_HEIGHT = 1
/** Where the deep stop sits along the ray (`… 72%`); past it the ramp paints the deep floor. */
const RAMP_STOP = 0.72

/** A `#rrggbb` or `rgb(r, g, b)` colour's channels — Sigma hands colours back in either notation. */
const parseColor = (color: string): [number, number, number] | null => {
  const hex = /^#([0-9a-f]{6})$/i.exec(color.trim())
  if (hex) {
    const value = parseInt(hex[1], 16)
    return [(value >> 16) & 255, (value >> 8) & 255, value & 255]
  }
  const rgbMatch = /^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/i.exec(color.trim())
  return rgbMatch ? [Number(rgbMatch[1]), Number(rgbMatch[2]), Number(rgbMatch[3])] : null
}

const rgb = (channels: number[]): string => `rgb(${channels.map((channel) => Math.round(channel)).join(', ')})`

/**
 * `from` blended toward `to` by `level` (0–1), channel-wise in sRGB — the interpolation a CSS
 * transition paints. Pure, and the one blend used by the entry dim, the label dim and the ramp.
 */
export function blendColor(from: string, to: string, level: number): string {
  const a = parseColor(from)
  const b = parseColor(to)
  if (!a || !b) return from
  const t = Math.min(1, Math.max(0, level))
  return rgb(a.map((channel, index) => channel + (b[index] - channel) * t))
}

/**
 * The colour the map's CSS ramp paints at `(x, y)` on a box of `width × height`.
 *
 * It is the gradient's own geometry: an ellipse centred at (50%, 0%), 120% wide and 100% tall,
 * whose colour runs from `lit` at the centre to `deep` at 72% of the ray and stays `deep` past it.
 * The interpolation is sRGB, channel-wise — what an opaque CSS gradient paints — and the result is
 * a literal `rgb(...)`, because a canvas reads none of the document's `var()`s.
 *
 * Pure: no DOM, no canvas, so the halo's contrast contract is unit-testable.
 */
export function rampColorAt(
  x: number,
  y: number,
  width: number,
  height: number,
  lit: string,
  deep: string,
): string {
  const from = parseColor(lit)
  const to = parseColor(deep)
  if (!from || !to) return deep
  const floor = rgb(to)
  // No box yet (the minimised pane mounts a 1×1 host): the far stop is the honest reading.
  if (!(width > 0) || !(height > 0) || !Number.isFinite(x) || !Number.isFinite(y)) return floor

  const dx = (x - width * 0.5) / (width * RAMP_WIDTH)
  const dy = y / (height * RAMP_HEIGHT)
  const along = Math.min(1, Math.max(0, Math.hypot(dx, dy) / RAMP_STOP))
  return rgb(from.map((channel, index) => channel + (to[index] - channel) * along))
}

/**
 * Where the label canvas sits inside the pane that paints the ramp. The gradient's box is the
 * `.plot-ground` pane, not the canvas — the pane wraps the legend, the toggles and the counts strip
 * around the plot — so the sampler needs the pane's size and the canvas's offset within it.
 * Measured on mount and on either box resizing; in a renderer-less test it stays null, and the
 * pure sampler is driven directly. One map is on screen at a time (D14), so one frame is enough.
 */
interface RampFrame {
  width: number
  height: number
  offsetX: number
  offsetY: number
}
let rampFrame: RampFrame | null = null

function RampFrameWatch() {
  const sigma = useSigma()
  useEffect(() => {
    const canvas = sigma.getContainer()
    const pane = canvas.closest('.plot-ground')
    if (!pane) return
    const measure = () => {
      const canvasBox = canvas.getBoundingClientRect()
      const paneBox = pane.getBoundingClientRect()
      rampFrame = {
        width: paneBox.width,
        height: paneBox.height,
        offsetX: canvasBox.left - paneBox.left,
        offsetY: canvasBox.top - paneBox.top,
      }
    }
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(canvas)
    observer.observe(pane)
    return () => {
      observer.disconnect()
      rampFrame = null
    }
  }, [sigma])
  return null
}

/* ── The hover reducer and the bloom (§12.4 Wave 2, §14.4 LIVE) ─────────────────────────────── */

/** How far a dimmed entry shrinks — the shape carries the reduction beside the muted colour. */
export const DIM_SIZE_RATIO = 0.6
/** The bloom's duration — the grammar's bloom (§13.10 rule 12). */
export const BLOOM_MS = 560
/** The hover dim's duration — the grammar's state curve (§13.10 rule 12). */
export const HOVER_MS = 120

/** One entry's read-only override: the dimmed colour and size, computed once per hover. */
export interface EntryOverride {
  color: string
  size: number
}

/**
 * The hover dim's level at `elapsed` ms, eased on the project's state curve —
 * `cubic-bezier(0.2, 0, 0, 1)` (`--ease-standard`). Endpoints are exact (0 at 0ms, 1 at 120ms);
 * under `prefers-reduced-motion: reduce` the level is the endpoint immediately, with no tween.
 * Pure, so the curve is unit-testable.
 */
export function hoverLevel(elapsed: number, reduced = false): number {
  if (reduced || elapsed >= HOVER_MS) return 1
  if (!Number.isFinite(elapsed) || elapsed <= 0) return 0
  return bezierY(elapsed / HOVER_MS)
}

const BEZIER_X1 = 0.2
const BEZIER_X2 = 0
const BEZIER_Y1 = 0
const BEZIER_Y2 = 1

const bezier = (t: number, p1: number, p2: number): number => {
  const u = 1 - t
  return 3 * u * u * t * p1 + 3 * u * t * t * p2 + t * t * t
}

const bezierSlope = (t: number, p1: number, p2: number): number =>
  3 * (1 - t) * (1 - t) * p1 + 6 * (1 - t) * t * (p2 - p1) + 3 * t * t * (1 - p2)

/** The y of `cubic-bezier(0.2, 0, 0, 1)` at x: solve x(t) = x by Newton, then read y(t). */
function bezierY(x: number): number {
  let t = x
  for (let i = 0; i < 8; i += 1) {
    const delta = bezier(t, BEZIER_X1, BEZIER_X2) - x
    if (Math.abs(delta) < 1e-5) return bezier(t, BEZIER_Y1, BEZIER_Y2)
    const slope = bezierSlope(t, BEZIER_X1, BEZIER_X2)
    if (Math.abs(slope) < 1e-6) break
    t -= delta / slope
  }
  let low = 0
  let high = 1
  t = x
  for (let i = 0; i < 24; i += 1) {
    const value = bezier(t, BEZIER_X1, BEZIER_X2)
    if (Math.abs(value - x) < 1e-5) break
    if (value < x) low = t
    else high = t
    t = (low + high) / 2
  }
  return bezier(t, BEZIER_Y1, BEZIER_Y2)
}

/**
 * Whether an entry still needs its one bloom. The set is per graph instance: a layer filter that
 * drops and re-adds an entry does not bloom it again, while a new dataset (a new graph instance)
 * starts empty, so genuinely new material still blooms.
 */
export function shouldBloom(bloomed: ReadonlySet<string>, id: string): boolean {
  return !bloomed.has(id)
}

/**
 * The per-node state the label renderer reads. The dim map is the same object the node reducer
 * reads (computed once per hover change); the level is the same 0→1 tween the marks follow, so a
 * dimmed entry's label moves with its mark instead of staying at full white. One map on screen
 * (D14), so one module-level state is enough.
 */
const labelDynamics: { dimmed: Map<string, EntryOverride>; level: number } = { dimmed: new Map(), level: 0 }

/**
 * An entry's colour at rest in a hovered map: its own kind blended halfway toward the map's quiet
 * ink. The kind is still readable, and every entry colour clears 3:1 against the lit end of the ramp
 * in this state (the darkest, the material blue, measures 5.07:1), so a dimmed entry never vanishes
 * — the map is a record, not a game.
 */
export function dimEntryColor(color: string, floor: string): string {
  return blendColor(color, floor, 0.5)
}

/**
 * The entries a hover reduces: everything that is neither the hovered entry nor one of its
 * neighbours. This is the whole computation — it runs once per hover change, and the node reducer
 * only looks each entry up, so no frame walks the graph.
 */
export function hoverDimmedEntries(graph: Graph, hovered: string, floor: string): Map<string, EntryOverride> {
  const dimmed = new Map<string, EntryOverride>()
  if (!graph.hasNode(hovered)) return dimmed
  const keep = new Set<string>([hovered, ...graph.neighbors(hovered)])
  graph.forEachNode((id, attributes) => {
    if (keep.has(id)) return
    dimmed.set(id, { color: dimEntryColor(String(attributes.color), floor), size: NODE_SIZE * DIM_SIZE_RATIO })
  })
  return dimmed
}

/**
 * The bloom's scale at `elapsed` ms — the scale half of the CSS keyframe `plot-bloom`
 * (0 → 1.28 → 1 over 560ms). The CSS keyframe also fades opacity 0 → 1; this canvas path carries
 * **no opacity at all**, so the entry rises into place and never fades (§13.10 rule 11). Under
 * `prefers-reduced-motion: reduce` the entry is simply there.
 */
export function bloomScale(elapsed: number, reduced = false): number {
  if (reduced || elapsed >= BLOOM_MS) return 1
  if (!Number.isFinite(elapsed) || elapsed <= 0) return 0
  const t = elapsed / BLOOM_MS
  return t < 0.6 ? (t / 0.6) * 1.28 : 1.28 - ((t - 0.6) / 0.4) * 0.28
}

/**
 * One node as the reducer hands it back to Sigma. Sigma does **not** merge a reducer's result onto
 * the node's attributes — it replaces them — so the returned object is the whole node: this entry's
 * own position, colour, label and type, with the hover dim (blended by `level`) and the bloom's
 * scale applied on top. The dim map is computed once per hover change; only the level moves.
 */
export function entryOverride(
  data: Attributes,
  dim: EntryOverride | undefined,
  level: number,
  started: number | undefined,
  now: number,
  reduced = false,
): Attributes {
  const scale = started === undefined ? 1 : bloomScale(now - started, reduced)
  if (!dim && scale === 1) return data
  const baseSize = (data.size as number) ?? NODE_SIZE
  const size = dim ? baseSize + (dim.size - baseSize) * Math.min(1, Math.max(0, level)) : baseSize
  const color = dim ? blendColor(String(data.color ?? ''), dim.color, level) : String(data.color ?? '')
  return { ...data, color, size: size * scale }
}

const prefersReducedMotion = (): boolean =>
  typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches

/**
 * The hover ring: a 2px stroke in the map accent around the hovered entry. Sigma's default hover is
 * a white label plate — a second surface over the plot, which §13.10 rule 3 forbids on the map. The
 * ring marks the entry without covering what is around it.
 */
export const drawHoverRing: NodeHoverDrawingFunction = (context, data) => {
  context.beginPath()
  context.arc(data.x, data.y, data.size + 4, 0, Math.PI * 2)
  context.lineWidth = 2
  context.strokeStyle = RING_INK
  context.stroke()
}

/**
 * The map's two live behaviours, kept off the React tree so neither repaints it:
 *
 * - **the bloom**: a node the graph gains blooms once over 560ms and settles. The graph's own
 *   `nodeAdded` event starts the clock, a rAF loop drives Sigma until the last bloom expires, and
 *   the node reducer reads the remaining time. Nothing else moves with it; a persistent set means
 *   an entry a layer filter drops and re-adds never blooms twice.
 * - **the hover reducer**: entering a node computes the dimmed set **once**; the level then moves
 *   0→1 over the 120ms state curve, and leaving runs the same curve back to 0 before the dim map is
 *   cleared — it never snaps.
 */
function MapDynamics({ graph }: { graph: Graph }) {
  const sigma = useSigma()
  const dimmed = useRef<Map<string, EntryOverride>>(new Map())
  const blooms = useRef<Map<string, number>>(new Map())
  const bloomed = useRef<Set<string>>(new Set())
  const tween = useRef<{ startedAt: number; from: number; to: number } | null>(null)
  const frame = useRef<number | undefined>(undefined)

  /** The current 0→1 dim level; 0 when no hover has happened. */
  const levelAt = useCallback((now: number) => {
    const current = tween.current
    if (!current) return 0
    return current.from + (current.to - current.from) * hoverLevel(now - current.startedAt, prefersReducedMotion())
  }, [])

  /** One rAF loop for both behaviours; it runs only while a bloom or a hover tween is live. */
  const startLoop = useCallback(() => {
    if (frame.current !== undefined) return
    const tick = () => {
      frame.current = undefined
      const now = performance.now()
      for (const [node, started] of blooms.current) if (now - started >= BLOOM_MS) blooms.current.delete(node)
      const current = tween.current
      if (current && !prefersReducedMotion() && now - current.startedAt >= HOVER_MS && current.to === 0) {
        dimmed.current = new Map()
        labelDynamics.dimmed = dimmed.current
        labelDynamics.level = 0
        tween.current = null
      }
      sigma.scheduleRefresh()
      const hoverActive =
        tween.current !== null && !prefersReducedMotion() && now - tween.current.startedAt < HOVER_MS
      if (blooms.current.size > 0 || hoverActive) frame.current = requestAnimationFrame(tick)
    }
    frame.current = requestAnimationFrame(tick)
  }, [sigma])

  useEffect(() => {
    const reducer = (node: string, data: Attributes) => {
      const now = performance.now()
      const level = levelAt(now)
      labelDynamics.level = level
      return entryOverride(data, dimmed.current.get(node), level, blooms.current.get(node), now)
    }
    // Install-only: `@react-sigma`'s SigmaContainer cleanup has already killed the instance when this
    // effect's cleanup would run, and a `setSetting` on the killed instance schedules a render whose
    // node programs are gone — it throws. The reducer dies with the instance, so it needs no reset.
    sigma.setSetting('nodeReducer', reducer)
  }, [levelAt, sigma])

  useEffect(() => {
    // A new graph instance starts with no history: the bloom set is per dataset.
    bloomed.current = new Set()
    const onAdd = ({ key }: { key: string }) => {
      if (!shouldBloom(bloomed.current, key) || prefersReducedMotion()) return
      bloomed.current.add(key)
      blooms.current.set(key, performance.now())
      startLoop()
    }
    graph.on('nodeAdded', onAdd)
    return () => {
      graph.off('nodeAdded', onAdd)
      blooms.current = new Map()
      if (frame.current !== undefined) cancelAnimationFrame(frame.current)
      frame.current = undefined
    }
  }, [graph, startLoop])

  useEffect(() => {
    const enter = ({ node }: { node: string }) => {
      const now = performance.now()
      const from = levelAt(now)
      dimmed.current = hoverDimmedEntries(graph, node, DIM_INK)
      labelDynamics.dimmed = dimmed.current
      tween.current = { startedAt: now, from, to: 1 }
      if (!prefersReducedMotion()) startLoop()
      sigma.scheduleRefresh()
    }
    const leave = () => {
      const now = performance.now()
      const from = levelAt(now)
      tween.current = { startedAt: now, from, to: 0 }
      if (prefersReducedMotion()) {
        dimmed.current = new Map()
        labelDynamics.dimmed = dimmed.current
        labelDynamics.level = 0
        tween.current = null
      } else {
        startLoop()
      }
      sigma.scheduleRefresh()
    }
    sigma.on('enterNode', enter)
    sigma.on('leaveNode', leave)
    return () => {
      sigma.off('enterNode', enter)
      sigma.off('leaveNode', leave)
      dimmed.current = new Map()
      labelDynamics.dimmed = dimmed.current
      labelDynamics.level = 0
      tween.current = null
    }
  }, [graph, levelAt, sigma, startLoop])

  return null
}

/**
 * Draw a node label with a halo struck in the ramp colour under the label first, so an edge cannot
 * cut the text and the halo never reads as a plate: it is the paint itself, sampled at the label's
 * position. The geometry mirrors Sigma's default (`x + size + 3`, `y + labelSize / 3`).
 */
export const drawNodeLabel: NodeLabelDrawingFunction = (context, data, settings) => {
  if (!data.label) return
  const { labelSize, labelFont, labelWeight } = settings
  context.font = `${labelWeight} ${labelSize}px ${labelFont}`
  const base =
    typeof settings.labelColor.attribute === 'string'
      ? ((data as unknown as Record<string, unknown>)[settings.labelColor.attribute] as string | undefined) ??
        settings.labelColor.color ??
        LABEL_INK
      : settings.labelColor.color ?? LABEL_INK
  // An entry is its mark AND its label: a dimmed entry's label moves with its mark on the same
  // 0→1 level, toward the map's quiet ink (≥ 6.16:1 on the lit end of the ramp). The hovered entry
  // and its neighbours are not in the dim map, so their labels stay at the full label ink.
  const key = (data as { key?: string }).key
  const dim = key === undefined ? undefined : labelDynamics.dimmed.get(key)
  const ink = dim ? blendColor(base, DIM_INK, labelDynamics.level) : base
  const x = data.x + data.size + 3
  const y = data.y + labelSize / 3
  // Sigma's label canvas is scaled by the device pixel ratio while the label's x/y are CSS pixels.
  // The ramp is painted on the pane, so the point moves into the pane's box when that frame is known.
  const scale = typeof context.getTransform === 'function' ? context.getTransform().a || 1 : 1
  const canvasWidth = context.canvas ? context.canvas.width / scale : 0
  const canvasHeight = context.canvas ? context.canvas.height / scale : 0
  const frame = rampFrame
  context.lineJoin = 'round'
  context.lineWidth = LABEL_HALO_WIDTH
  context.strokeStyle = frame
    ? rampColorAt(x + frame.offsetX, y + frame.offsetY, frame.width, frame.height, RAMP_LIT, RAMP_DEEP)
    : rampColorAt(x, y, canvasWidth, canvasHeight, RAMP_LIT, RAMP_DEEP)
  context.strokeText(data.label, x, y)
  context.fillStyle = ink
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
  // The hovered entry takes the map's accent ring, not Sigma's white label plate (§12.4 Wave 2).
  defaultDrawNodeHover: drawHoverRing,
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
    mark: <PositionGlyph position={stance} size={12} ground="map" />,
    color: POSITION_COLORS[stance],
    word: stance,
  })),
  { mark: <CircleDashed size={12} aria-hidden="true" />, color: UNPOSITIONED_COLOR, word: 'No position' },
]

/**
 * The map's key, ruled above the plot while the map holds anything, so it never covers an entry.
 * `hasEntries` is false only when nothing is drawn.
 *
 * The kit's `Legend` is the one legend block (§6): symbol + colour + word, never a hue alone. It is
 * keyed to the map's ink because it is rendered inside `plot-ground`, which rebinds `--color-ink-*`
 * to the map's tokens — so the same component reads on the dark surface without a per-instance
 * override. The swatch rides beside the symbol so the row carries shape, colour and word.
 */
export function GraphLegend({ hasEntries }: { hasEntries: boolean }) {
  if (!hasEntries) return null
  return (
    // The map's height is a measured floor (568×475 at 1440, 209 at 390 — Task 6), so the kit's
    // default legend padding is tightened at the call site to fit the strip the old legend occupied.
    <Legend
      className="shrink-0 border-t-0! px-2.5 py-1! [&>ul]:gap-y-1!"
      entries={LEGEND_ROWS.map((row) => ({
        symbol: (
          <span className="inline-flex items-center gap-1" style={{ color: row.color }}>
            {row.mark}
            <span aria-hidden="true" className="inline-block size-2.5 rounded-[2px]" style={{ backgroundColor: row.color }} />
          </span>
        ),
        label: row.word,
      }))}
    />
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
  return (
    // The canvas fills its host: the pane owns the height, and the plot fills the box rather than
    // sitting in the top third of a fixed 360px with dead dark ground under it (§9.2).
    <div
      ref={root}
      tabIndex={-1}
      className="relative flex min-h-0 flex-1 flex-col overflow-hidden rounded-[6px]"
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
          {/* Dynamics attaches before the sync effect below, so the first entries' bloom is caught. */}
          <MapDynamics graph={graph} />
          <LiveGraph graph={graph} />
          <FitCamera nodeCount={nodeCount} />
          <RampFrameWatch />
          <ContainerResizeWatch />
          <SelectionWatch onPick={pick} />
        </SigmaContainer>
        {notice && (
          <p
            role="status"
            className="pointer-events-none absolute right-2 top-2 flex items-center gap-1.5 rounded-xs border border-warn/40 bg-map-ground-2 px-2 py-1 text-micro text-ink-2"
          >
            <Warning size={13} className="text-warn" aria-hidden="true" />
            {notice}
          </p>
        )}
        <GraphOverlay phase={phase} message={statusMessage} />
      </div>
      {/* The counts grow on every delta; role="img" alone is read on demand, so mirror the label into a live region.
          The relation list lives in the pane's counts strip, outside this host, so it survives the map being
          minimised (§14.4 row 10) instead of sitting in a hidden subtree. */}
      <div aria-live="polite" className="sr-only">
        {canvasLabel}
      </div>
    </div>
  )
}
