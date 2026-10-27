import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import ActivityPane from './ActivityPane'
import GraphPane from './GraphPane'
import SplitDivider, { ratioFromKey } from './SplitDivider'
import { paneStateFrom, paneStorageKey, type PaneState } from './paneState'

export type { PaneState }

/** §2.4 The map's counts, by kind, as the text alternative reads them. Internal keys; the copy law
 *  governs the rendered labels, which `GraphPane` owns. */
export interface MapCounts {
  entries: number
  experts: number
  opinions: number
  connections: number
}

/** §9.4/§12 The accessible reading of the map: counts by kind, the busiest entries, the current step. */
export interface MapSummary {
  counts: MapCounts
  busiest: string[]
  step: string
}

export interface WorkspaceProps {
  /** The run or session id — the persistence key and the map host's id both hang off it. */
  mapId: string
  /** The map surface (`GraphCanvas`). Rendered once and kept mounted across every state. */
  map: ReactNode
  /** The work surface (the step's activity). */
  work: ReactNode
  summary: MapSummary
}

/**
 * §9 The stateful workspace. It owns nothing but the pane geometry, which it persists per run — the
 * layout itself lives in `WorkspaceView` so every state can be asserted from static markup (Ruling F17).
 */
export default function Workspace({ mapId, map, work, summary }: WorkspaceProps) {
  const [state, setState] = useState<PaneState>(() => {
    const stored = typeof sessionStorage === 'undefined' ? null : sessionStorage.getItem(paneStorageKey(mapId))
    const narrow = typeof matchMedia === 'function' && matchMedia('(max-width: 640px)').matches
    return paneStateFrom(stored, narrow)
  })
  const [ratio, setRatio] = useState(() =>
    ratioFromKey(typeof sessionStorage === 'undefined' ? null : sessionStorage.getItem(ratioStorageKey(mapId))),
  )

  useEffect(() => {
    if (typeof sessionStorage !== 'undefined') sessionStorage.setItem(paneStorageKey(mapId), state)
  }, [mapId, state])

  useEffect(() => {
    if (typeof sessionStorage !== 'undefined') sessionStorage.setItem(ratioStorageKey(mapId), String(ratio))
  }, [mapId, ratio])

  return (
    <WorkspaceView
      mapId={mapId}
      state={state}
      onStateChange={setState}
      map={map}
      work={work}
      summary={summary}
      ratio={ratio}
      onRatioChange={setRatio}
    />
  )
}

/** The split's share of the width, alongside the pane state under the same `chamber.workspace.*` key. */
const ratioStorageKey = (mapId: string) => `${paneStorageKey(mapId)}.ratio`

export interface WorkspaceViewProps extends WorkspaceProps {
  state: PaneState
  onStateChange: (next: PaneState) => void
  /** The map's share of the split, 0.25–0.75. */
  ratio?: number
  onRatioChange?: (next: number) => void
}

/**
 * The pure view — pane state as a prop, so it renders to static markup without a DOM (Ruling F17).
 *
 * The two panes are siblings laid out by class, never conditionally rendered: the map host is a child
 * of `GraphPane` in every state, and the activity pane is hidden with `hidden` in expanded. That is the
 * construction under which "restore never re-fetches" and "focus stays on the toggle" hold — no state
 * change can unmount or remount either surface.
 */
export function WorkspaceView({
  mapId,
  state,
  onStateChange,
  map,
  work,
  summary,
  ratio = 0.5,
  onRatioChange = () => {},
}: WorkspaceViewProps) {
  // Stacked below `lg` (flex column), the brief's three-column split from `lg` up (grid). The inline
  // template is inert while the container is a flex column, so the stacked order is class-only.
  return (
    <div
      className={`flex flex-col gap-4 ${state === 'split' ? 'lg:grid' : ''}`}
      style={
        state === 'split' ? { gridTemplateColumns: `minmax(320px, ${ratio * 100}%) 8px minmax(0, 1fr)` } : undefined
      }
    >
      {/* The work sits above the map when the panes stack (§9 responsive); the map is left on wide.
          Each pane rides in its own order wrapper so the outer layout owns the order, not the panes. */}
      <div className="order-1 lg:order-3">
        <ActivityPane hidden={state === 'expanded'}>{work}</ActivityPane>
      </div>
      {state === 'split' && <SplitDivider ratio={ratio} onChange={onRatioChange} />}
      <div className="order-2 lg:order-1">
        <GraphPane mapId={mapId} state={state} onStateChange={onStateChange} summary={summary}>
          {map}
        </GraphPane>
      </div>
    </div>
  )
}
