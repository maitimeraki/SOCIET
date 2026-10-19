import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import ActivityPane from './ActivityPane'
import GraphPane from './GraphPane'
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
 * §9 The stateful workspace. It owns nothing but the pane state, which it persists per run — the
 * layout itself lives in `WorkspaceView` so every state can be asserted from static markup (Ruling F17).
 */
export default function Workspace({ mapId, map, work, summary }: WorkspaceProps) {
  const [state, setState] = useState<PaneState>(() => {
    const stored = typeof sessionStorage === 'undefined' ? null : sessionStorage.getItem(paneStorageKey(mapId))
    const narrow = typeof matchMedia === 'function' && matchMedia('(max-width: 640px)').matches
    return paneStateFrom(stored, narrow)
  })

  useEffect(() => {
    if (typeof sessionStorage !== 'undefined') sessionStorage.setItem(paneStorageKey(mapId), state)
  }, [mapId, state])

  return (
    <WorkspaceView mapId={mapId} state={state} onStateChange={setState} map={map} work={work} summary={summary} />
  )
}

export interface WorkspaceViewProps extends WorkspaceProps {
  state: PaneState
  onStateChange: (next: PaneState) => void
}

/**
 * The pure view — pane state as a prop, so it renders to static markup without a DOM (Ruling F17).
 *
 * The two panes are siblings laid out by class, never conditionally rendered: the map host is a child
 * of `GraphPane` in every state, and the activity pane is hidden with `hidden` in expanded. That is the
 * construction under which "restore never re-fetches" and "focus stays on the toggle" hold — no state
 * change can unmount or remount either surface.
 */
export function WorkspaceView({ mapId, state, onStateChange, map, work, summary }: WorkspaceViewProps) {
  return (
    <div className={`grid gap-4 ${state === 'split' ? 'lg:grid-cols-2' : 'grid-cols-1'}`}>
      {/* The work sits above the map when the panes stack (§9 responsive); the map is left on wide. */}
      <ActivityPane hidden={state === 'expanded'}>{work}</ActivityPane>
      <GraphPane mapId={mapId} state={state} onStateChange={onStateChange} summary={summary}>
        {map}
      </GraphPane>
    </div>
  )
}
