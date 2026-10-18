/* eslint-disable react-refresh/only-export-components -- this module deliberately exports its pure helpers (the counts by kind and the state-free view) so the no-DOM suite can drive every toggle state and every map size without a renderer. */
import { useState } from 'react'
import type { ReactNode } from 'react'
import IconButton from '../ui/IconButton'
import { ALL_LAYERS, LAYER_NAMES, LayerVisibilityContext, nodeLayer } from '../../graph/layers'
import type { LayerName } from '../../graph/layers'
import type { GraphEdge, GraphNode } from '../../graph/graphStore'
import type { MapCounts, MapSummary, PaneState } from './Workspace'

export interface GraphPaneProps {
  mapId: string
  state: PaneState
  onStateChange: (next: PaneState) => void
  summary: MapSummary
  children: ReactNode
}

// §9.1/§9.3 The pane's own height per state — minimised collapses to the live strip under the map.
const SIZE: Record<PaneState, string> = {
  split: 'min-h-[60vh] lg:min-h-[70vh]',
  expanded: 'min-h-[70vh]',
  minimised: 'min-h-0',
}

const CONTROL = 'hover:bg-map-ground-2'

/** §9.1 The toggles' words, in the order the pane draws them. `all` is the master, not a layer. */
const LAYER_LABELS: Record<LayerName, string> = {
  corpus: 'Corpus',
  experts: 'Experts',
  opinions: 'Opinions',
  connections: 'Connections',
}

/** §9.1's glyph per layer — a shape beside the word, so no toggle leans on its hue alone. */
const LAYER_GLYPHS: Record<LayerName, string> = {
  corpus: '⊕',
  experts: '◉',
  opinions: '⊗',
  connections: '—',
}

/** A toggle's identity: one layer, or the master `all` that shows them together. */
export type LayerToggle = LayerName | 'all'

/**
 * The map's counts, by kind, as §9.4/§12's text alternative reads them. Entries are the material
 * the extraction stream wrote; the experts and opinions the debate stream wrote are counted apart
 * from it, so no kind is folded into another and no total stands in for the kinds.
 */
export function mapCounts(nodes: Record<string, GraphNode>, edges: Record<string, GraphEdge>): MapCounts {
  const counts: MapCounts = { entries: 0, experts: 0, opinions: 0, connections: Object.keys(edges).length }
  for (const node of Object.values(nodes)) {
    const layer = nodeLayer(node)
    if (layer === 'experts') counts.experts += 1
    else if (layer === 'opinions') counts.opinions += 1
    else counts.entries += 1
  }
  return counts
}

/**
 * One layer's toggle. A real button carrying `aria-pressed`, and a hidden layer is struck through —
 * a shape, so the state reads to the eye without hue and never leans on a dimmed colour: `ink-2`
 * measures 13.7:1 on the map ground and `ink-3` 6.7:1, both clear of AA for the control's own label.
 */
function LayerButton({ label, glyph, on, onClick }: { label: string; glyph?: string; on: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={onClick}
      className={`inline-flex items-center gap-1 rounded-[4px] border border-ink-3 px-2 py-1 text-micro transition-colors hover:bg-map-ground-2 ${
        on ? 'bg-map-ground-2 text-ink-2' : 'text-ink-3 line-through'
      }`}
    >
      {glyph !== undefined && <span aria-hidden="true">{glyph}</span>}
      {label}
    </button>
  )
}

export interface GraphPaneViewProps extends GraphPaneProps {
  /** The layers the canvas may draw. */
  layers: ReadonlySet<LayerName>
  onToggleLayer: (key: LayerToggle) => void
}

/**
 * §9 The map pane, as static markup — the layer set is a prop, so every toggle state renders without
 * a DOM (Ruling F17). It owns three states — split, expanded, minimised — the text alternative that
 * makes the map readable without sight, and the toggles that filter what the one canvas draws.
 *
 * The canvas host (the `children`) is rendered in every state and simply `hidden` in minimised, and
 * it is wrapped in the layer context rather than rebuilt: the map never unmounts, so a toggle change
 * is a filter, not a re-fetch (§9.3, D14).
 */
export function GraphPaneView({
  mapId,
  state,
  onStateChange,
  summary,
  layers,
  onToggleLayer,
  children,
}: GraphPaneViewProps) {
  const minimised = state === 'minimised'
  const expanded = state === 'expanded'
  const hostId = `workspace-map-${mapId}`
  const { counts, busiest, step } = summary
  const allOn = LAYER_NAMES.every((name) => layers.has(name))

  return (
    <section
      aria-label="The map"
      className={`plot-ground order-2 flex flex-col overflow-hidden rounded-md border border-map-rule lg:order-1 ${SIZE[state]}`}
    >
      <div id={hostId} className="min-h-0 flex-1" hidden={minimised} aria-hidden={minimised || undefined}>
        <LayerVisibilityContext.Provider value={layers}>{children}</LayerVisibilityContext.Provider>
      </div>

      {/* §9.1 The layer toggles. Each one filters what the one canvas draws; none of them unmounts it.
          Hidden with the map in minimised, so no off-screen control stays in the tab order. */}
      <div
        role="group"
        aria-label="What the map shows"
        hidden={minimised}
        className="flex flex-wrap items-center gap-1 border-t border-map-rule px-3 py-2"
      >
        <LayerButton label="All" on={allOn} onClick={() => onToggleLayer('all')} />
        {LAYER_NAMES.map((name) => (
          <LayerButton
            key={name}
            label={LAYER_LABELS[name]}
            glyph={LAYER_GLYPHS[name]}
            on={layers.has(name)}
            onClick={() => onToggleLayer(name)}
          />
        ))}
      </div>

      {/* §9.4/§12 The accessible reading — counts by kind, the busiest entries, the current step.
          Always present; in minimised it is the whole pane. */}
      <div
        aria-label="What the map holds"
        className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-map-rule px-3 py-2 text-micro text-ink-3"
      >
        <p>
          {step} · {counts.entries} entries · {counts.experts} experts · {counts.opinions} opinions ·{' '}
          {counts.connections} connections
        </p>
        {busiest.length > 0 && <p>Busiest: {busiest.join(', ')}</p>}

        <div className="ml-auto flex items-center gap-1">
          <IconButton
            label={minimised ? 'Restore the map' : 'Minimise the map'}
            aria-expanded={!minimised}
            aria-controls={hostId}
            onClick={() => onStateChange(minimised ? 'split' : 'minimised')}
            className={CONTROL}
          >
            <span aria-hidden="true">{minimised ? '▲' : '–'}</span>
          </IconButton>
          {!minimised && (
            <IconButton
              label={expanded ? 'Restore the split' : 'Expand the map'}
              aria-expanded={expanded}
              aria-controls={hostId}
              onClick={() => onStateChange(expanded ? 'split' : 'expanded')}
              className={CONTROL}
            >
              <span aria-hidden="true">{expanded ? '↙' : '↗'}</span>
            </IconButton>
          )}
        </div>
      </div>
    </section>
  )
}

/** Nothing shown — the state the master toggle reaches when every layer is already on. */
const NO_LAYERS: ReadonlySet<LayerName> = new Set()

/**
 * §9 The stateful pane. It owns the layer set and hands it to the view, which is the only thing the
 * toggles change — the canvas beneath stays the same element, so filtering never remounts the map.
 */
export default function GraphPane(props: GraphPaneProps) {
  const [layers, setLayers] = useState<ReadonlySet<LayerName>>(ALL_LAYERS)

  const toggleLayer = (key: LayerToggle) =>
    setLayers((current) => {
      if (key === 'all') return LAYER_NAMES.every((name) => current.has(name)) ? NO_LAYERS : ALL_LAYERS
      const next = new Set(current)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })

  return <GraphPaneView {...props} layers={layers} onToggleLayer={toggleLayer} />
}
