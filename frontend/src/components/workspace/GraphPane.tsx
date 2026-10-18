import type { ReactNode } from 'react'
import IconButton from '../ui/IconButton'
import type { MapSummary, PaneState } from './Workspace'

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

/**
 * §9 The map pane. It owns three states — split, expanded, minimised — the text alternative that
 * makes the map readable without sight, and the controls that move between the states.
 *
 * The canvas host (the `children`) is rendered in every state and simply `hidden` in minimised: the
 * map never unmounts, so restoring is instant and no state change can trigger a re-fetch (§9.3).
 */
export default function GraphPane({ mapId, state, onStateChange, summary, children }: GraphPaneProps) {
  const minimised = state === 'minimised'
  const expanded = state === 'expanded'
  const hostId = `workspace-map-${mapId}`
  const { counts, busiest, step } = summary

  return (
    <section
      aria-label="The map"
      className={`plot-ground order-2 flex flex-col overflow-hidden rounded-md border border-map-rule lg:order-1 ${SIZE[state]}`}
    >
      <div id={hostId} className="min-h-0 flex-1" hidden={minimised} aria-hidden={minimised || undefined}>
        {children}
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
